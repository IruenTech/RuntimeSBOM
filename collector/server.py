#!/usr/bin/env python3
"""Phase 16 reference collector: authenticated tenant+asset snapshots, SQLite revision history and diff.
Python 3.8+. Development/reference service; deploy behind TLS reverse proxy and access controls.
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import sqlite3
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

MAX_BYTES = 8 * 1024 * 1024
ASSET_RE = re.compile(r'^[a-zA-Z0-9._:-]{1,128}$')
DELIVERY_RE = re.compile(r'^[0-9a-f]{32}$')


def db_connect(path):
    conn = sqlite3.connect(str(path), timeout=15, check_same_thread=False)
    conn.execute('PRAGMA busy_timeout=15000')
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('''CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL, asset TEXT NOT NULL,
        sha256 TEXT NOT NULL, created_at TEXT NOT NULL, components INTEGER NOT NULL,
        document TEXT NOT NULL)''')
    # Migration is additive: pre-16 databases have snapshots but no delivery_id.
    columns = {r[1] for r in conn.execute('PRAGMA table_info(snapshots)')}
    if 'delivery_id' not in columns:
        conn.execute('ALTER TABLE snapshots ADD COLUMN delivery_id TEXT')
    conn.execute('CREATE INDEX IF NOT EXISTS ix_asset ON snapshots(tenant,asset,id)')
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS ix_delivery ON snapshots(tenant,asset,delivery_id) WHERE delivery_id IS NOT NULL')
    conn.execute('''CREATE TABLE IF NOT EXISTS findings (
        tenant TEXT NOT NULL, purl TEXT NOT NULL, vuln_id TEXT NOT NULL,
        summary TEXT NOT NULL, severity TEXT NOT NULL, source TEXT NOT NULL,
        updated_at TEXT NOT NULL, PRIMARY KEY(tenant,purl,vuln_id))''')
    conn.execute('CREATE INDEX IF NOT EXISTS ix_finding_purl ON findings(tenant,purl)')
    conn.commit()
    return conn


def identity(component):
    if not isinstance(component, dict):
        return None
    # Never equate distinct versions. PURL is the preferred identity when present.
    if isinstance(component.get('purl'), str) and component['purl']:
        return 'purl:' + component['purl']
    fields = [component.get('group') or '', component.get('name') or '', component.get('version') or '']
    if not fields[1]:
        return None
    # Two assets may load the same artifact via separate classloaders: collapse only for inventory diff.
    return 'gnamever:' + json.dumps(fields, separators=(',', ':'), ensure_ascii=False)


def compare(a, b):
    old = {identity(c) for c in a.get('components', [])}
    new = {identity(c) for c in b.get('components', [])}
    old.discard(None)
    new.discard(None)
    return {'added': sorted(new - old), 'removed': sorted(old - new), 'unchangedCount': len(new & old)}


def evidence(component):
    values = {p.get('name'): p.get('value') for p in component.get('properties', [])
              if isinstance(p, dict) and isinstance(p.get('name'), str)}
    # Runtime evidence is observational; it never implies exploitability.
    state = values.get('runtimeSbom:runtimeEvidenceState', '')
    if state not in ('METHOD_EXECUTED', 'CLASS_LOADED', 'PRELOADED'):
        try:
            state = 'METHOD_EXECUTED' if int(values.get('runtimeSbom:observedMethodEntryCount', '0')) > 0 else 'CLASS_LOADED'
        except ValueError:
            state = 'UNKNOWN'
    try:
        calls = max(0, int(values.get('runtimeSbom:observedMethodEntryCount', '0')))
    except ValueError:
        calls = 0
    return state, calls


def latest_documents(conn, tenant):
    rows = conn.execute('''SELECT s.asset,s.id,s.created_at,s.document FROM snapshots s
        JOIN (SELECT asset,MAX(id) AS id FROM snapshots WHERE tenant=? GROUP BY asset) recent
        ON s.asset=recent.asset AND s.id=recent.id WHERE s.tenant=? ORDER BY s.asset''',
        (tenant, tenant)).fetchall()
    return [(asset, sid, created, json.loads(raw)) for asset, sid, created, raw in rows]


def findings_for(conn, tenant, purls):
    if not purls:
        return {}
    found = defaultdict(list)
    # Avoid SQLite variable count limits. Never include data from other tenants.
    for i in range(0, len(purls), 200):
        chunk = purls[i:i+200]
        qs = ','.join('?' for _ in chunk)
        rows = conn.execute('SELECT purl,vuln_id,summary,severity,source,updated_at FROM findings WHERE tenant=? AND purl IN ('+qs+')', [tenant]+chunk).fetchall()
        for purl, vid, summary, severity, source, updated in rows:
            found[purl].append({'id':vid,'summary':summary,'severity':severity,'source':source,'updatedAt':updated})
    return found


def inventory(conn, tenant):
    docs = latest_documents(conn, tenant)
    all_purls = sorted({c.get('purl') for _, _, _, d in docs for c in d.get('components', [])
                        if isinstance(c, dict) and isinstance(c.get('purl'),str) and c.get('purl')})
    vulnerabilities = findings_for(conn, tenant, all_purls)
    assets = []
    components = []
    total_findings = 0
    for asset, sid, created, doc in docs:
        counts = {'METHOD_EXECUTED':0,'CLASS_LOADED':0,'PRELOADED':0,'UNKNOWN':0}
        asset_findings = 0
        for c in doc.get('components', []):
            if not isinstance(c,dict):
                continue
            state, calls = evidence(c)
            counts[state] = counts.get(state,0)+1
            purl = c.get('purl') or ''
            matching = vulnerabilities.get(purl, [])
            asset_findings += len(matching)
            # This is a triage hint, not a vulnerability risk or reachable-code verdict.
            priority = 'review-executed' if matching and state=='METHOD_EXECUTED' else ('review-loaded' if matching else ('review-unobserved' if matching else 'none'))
            components.append({'asset':asset,'snapshotId':sid,'name':c.get('name',''),
                'group':c.get('group',''),'version':c.get('version',''),'purl':purl,
                'bomRef':c.get('bom-ref',''),'evidence':state,'methodCalls':calls,
                'findings':matching,'triage':priority})
        total_findings += asset_findings
        assets.append({'asset':asset,'snapshotId':sid,'createdAt':created,
            'components':len(doc.get('components',[])),'findings':asset_findings,'evidence':counts})
    return {'assets':assets,'components':components,'componentCount':len(components),
            'findingOccurrences':total_findings,'uniqueFindingCount':len({(c['purl'],v['id']) for c in components for v in c['findings']})}


def changes_for(conn, tenant, limit=100):
    assets = conn.execute('SELECT DISTINCT asset FROM snapshots WHERE tenant=? ORDER BY asset LIMIT 1000',(tenant,)).fetchall()
    alerts=[]
    for (asset,) in assets:
        rows=conn.execute('SELECT id,created_at,document FROM snapshots WHERE tenant=? AND asset=? ORDER BY id DESC LIMIT 2',(tenant,asset)).fetchall()
        if len(rows)<2: continue
        diff=compare(json.loads(rows[1][2]),json.loads(rows[0][2]))
        if diff['added'] or diff['removed']:
            alerts.append({'asset':asset,'from':rows[1][0],'to':rows[0][0],
                'createdAt':rows[0][1],**diff})
    return sorted(alerts,key=lambda x:x['to'],reverse=True)[:limit]


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, addr, handler, store, tokens):
        super().__init__(addr, handler)
        self.store = Path(store)
        self.store.mkdir(parents=True, exist_ok=True)
        self.conn = db_connect(self.store / 'history.sqlite3')
        self.lock = threading.Lock()
        # In-memory secrets only; never print or persist tokens.
        self.tokens = tokens

    def server_close(self):
        self.conn.close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    server_version = 'RuntimeSBOMCollector/0.16'

    def log_message(self, format, *args):
        # Exclude request path and headers to avoid logging identifiers or credentials.
        print('[collector] %s %s' % (self.client_address[0], (args[1] if len(args)>1 else 'request')), flush=True)

    def respond(self, status, data):
        payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def tenant(self):
        auth = self.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            self.respond(401, {'error': 'unauthorized'})
            return None
        provided = auth[7:]
        for token, tenant in self.server.tokens.items():
            if hmac.compare_digest(provided, token):
                return tenant
        self.respond(401, {'error': 'unauthorized'})
        return None

    def do_POST(self):
        route = urlsplit(self.path).path
        if route == '/api/v1/findings/import':
            return self.import_findings()
        if route != '/api/v1/sbom':
            return self.respond(404, {'error': 'not_found'})
        tenant = self.tenant()
        if tenant is None:
            return
        asset = self.headers.get('X-RuntimeSBOM-Asset', 'default')
        if not ASSET_RE.fullmatch(asset):
            return self.respond(400, {'error': 'invalid_asset'})
        delivery_id = self.headers.get('X-RuntimeSBOM-Delivery-ID')
        if delivery_id is not None and not DELIVERY_RE.fullmatch(delivery_id):
            return self.respond(400, {'error': 'invalid_delivery_id'})
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            return self.respond(411, {'error': 'content_length_required'})
        if size < 2 or size > MAX_BYTES:
            return self.respond(413, {'error': 'payload_limit'})
        raw = self.rfile.read(size)
        if len(raw) != size:
            return self.respond(400, {'error': 'truncated'})
        try:
            doc = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return self.respond(400, {'error': 'invalid_json'})
        if not isinstance(doc, dict) or doc.get('bomFormat') != 'CycloneDX' or doc.get('specVersion') != '1.6' or not isinstance(doc.get('components'), list) or not all(isinstance(c, dict) for c in doc['components']):
            return self.respond(422, {'error': 'invalid_bom_envelope'})
        sha = hashlib.sha256(raw).hexdigest()
        when = datetime.now(timezone.utc).isoformat()
        with self.server.lock:
            try:
                # Exactly-once *storage effect* for an immutable delivery ID.
                # Safe if the response is lost after SQLite commits: the sender can retry.
                if delivery_id is not None:
                    row = self.server.conn.execute(
                        'SELECT id,sha256,components FROM snapshots WHERE tenant=? AND asset=? AND delivery_id=?',
                        (tenant, asset, delivery_id)).fetchone()
                    if row is not None:
                        if not hmac.compare_digest(row[1], sha):
                            return self.respond(409, {'error': 'delivery_id_conflict'})
                        return self.respond(200, {'snapshotId': row[0], 'asset': asset,
                            'sha256': sha, 'components': row[2], 'deliveryId': delivery_id, 'duplicate': True})
                cur = self.server.conn.execute(
                    'INSERT INTO snapshots(tenant,asset,sha256,created_at,components,document,delivery_id) VALUES(?,?,?,?,?,?,?)',
                    (tenant, asset, sha, when, len(doc['components']), raw.decode('utf-8'), delivery_id))
                snapshot_id = cur.lastrowid
                self.server.conn.commit()
            except sqlite3.Error:
                self.server.conn.rollback()
                return self.respond(500, {'error': 'storage_failure'})
        return self.respond(201, {'snapshotId': snapshot_id, 'asset': asset, 'sha256': sha,
            'components': len(doc['components']), 'deliveryId': delivery_id, 'duplicate': False})

    def import_findings(self):
        tenant = self.tenant()
        if tenant is None: return
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            return self.respond(411, {'error':'content_length_required'})
        if size < 2 or size > MAX_BYTES:
            return self.respond(413, {'error':'payload_limit'})
        raw = self.rfile.read(size)
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return self.respond(400, {'error':'invalid_json'})
        if not isinstance(payload,dict) or not isinstance(payload.get('results'),list) or len(payload['results'])>5000:
            return self.respond(422, {'error':'invalid_findings'})
        validated=[]
        for item in payload['results']:
            if not isinstance(item,dict) or not isinstance(item.get('purl'),str) or not item['purl'].startswith('pkg:') or len(item['purl'])>1024 or not isinstance(item.get('vulns'),list) or len(item['vulns'])>100:
                return self.respond(422, {'error':'invalid_findings'})
            for vuln in item['vulns']:
                if not isinstance(vuln,dict) or not isinstance(vuln.get('id'),str) or not (1<=len(vuln['id'])<=128):
                    return self.respond(422, {'error':'invalid_findings'})
                summary=str(vuln.get('summary') or '')[:2048]
                severity=str(vuln.get('severity') or 'unknown')[:64]
                validated.append((item['purl'],vuln['id'],summary,severity))
        source=str(payload.get('source') or 'OSV')[:128]
        when=datetime.now(timezone.utc).isoformat()
        with self.server.lock:
            try:
                # Replace findings for every refreshed PURL, including results with no vulnerabilities.
                for item in payload['results']:
                    self.server.conn.execute('DELETE FROM findings WHERE tenant=? AND purl=?',(tenant,item['purl']))
                self.server.conn.executemany('INSERT OR REPLACE INTO findings(tenant,purl,vuln_id,summary,severity,source,updated_at) VALUES(?,?,?,?,?,?,?)',
                  [(tenant,purl,vid,summary,severity,source,when) for purl,vid,summary,severity in validated])
                self.server.conn.commit()
            except sqlite3.Error:
                self.server.conn.rollback()
                return self.respond(500, {'error':'storage_failure'})
        return self.respond(200, {'purls':len(payload['results']),'findings':len(validated)})

    def serve_dashboard(self, route):
        names={'/':'index.html','/dashboard':'index.html','/dashboard.js':'dashboard.js','/dashboard.css':'dashboard.css'}
        path=Path(__file__).resolve().parent/'web'/names[route]
        if not path.is_file(): return self.respond(404,{'error':'not_found'})
        body=path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if route in ('/','/dashboard') else ('text/javascript; charset=utf-8' if route.endswith('.js') else 'text/css; charset=utf-8'))
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        route = urlsplit(self.path).path
        if route in ('/', '/dashboard', '/dashboard.js', '/dashboard.css'):
            return self.serve_dashboard(route)
        tenant = self.tenant()
        if tenant is None:
            return
        parsed = urlsplit(self.path)
        params = parse_qs(parsed.query)
        asset = (params.get('asset') or ['default'])[0]
        if not ASSET_RE.fullmatch(asset):
            return self.respond(400, {'error': 'invalid_asset'})
        with self.server.lock:
            if parsed.path == '/api/v1/dashboard':
                data=inventory(self.server.conn,tenant)
                return self.respond(200, {'assets':data['assets'],'componentCount':data['componentCount'],
                   'findingOccurrences':data['findingOccurrences'],'uniqueFindingCount':data['uniqueFindingCount']})
            if parsed.path == '/api/v1/components':
                return self.respond(200, {'components':inventory(self.server.conn,tenant)['components']})
            if parsed.path == '/api/v1/alerts':
                return self.respond(200, {'alerts':changes_for(self.server.conn,tenant)})
            if parsed.path == '/api/v1/assets':
                rows = self.server.conn.execute('SELECT asset,MAX(id),COUNT(*) FROM snapshots WHERE tenant=? GROUP BY asset ORDER BY asset LIMIT 1000', (tenant,)).fetchall()
                return self.respond(200, {'assets': [{'asset':r[0], 'latestSnapshotId':r[1], 'snapshotCount':r[2]} for r in rows]})
            if parsed.path == '/api/v1/snapshots':
                rows = self.server.conn.execute('SELECT id,sha256,created_at,components FROM snapshots WHERE tenant=? AND asset=? ORDER BY id DESC LIMIT 100', (tenant, asset)).fetchall()
                return self.respond(200, {'asset': asset, 'snapshots': [{'id':r[0], 'sha256':r[1], 'createdAt':r[2], 'components':r[3]} for r in rows]})
            if parsed.path == '/api/v1/diff':
                try:
                    old_id = int((params.get('from') or [''])[0]); new_id = int((params.get('to') or [''])[0])
                except ValueError:
                    return self.respond(400, {'error': 'from_to_required'})
                rows = self.server.conn.execute('SELECT id,document FROM snapshots WHERE tenant=? AND asset=? AND id IN (?,?)', (tenant, asset, old_id, new_id)).fetchall()
                docs = {row[0]:json.loads(row[1]) for row in rows}
                if old_id not in docs or new_id not in docs:
                    return self.respond(404, {'error': 'snapshot_not_found'})
                return self.respond(200, {'asset': asset, 'from': old_id, 'to': new_id, **compare(docs[old_id], docs[new_id])})
        return self.respond(404, {'error': 'not_found'})


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--storage', default='collected')
    a = p.parse_args()
    token = os.environ.get('RUNTIMESBOM_TOKEN', '')
    if len(token) < 16:
        p.error('Set RUNTIMESBOM_TOKEN (minimum 16 characters)')
    tenant = os.environ.get('RUNTIMESBOM_TENANT', 'local')
    if not ASSET_RE.fullmatch(tenant):
        p.error('Invalid RUNTIMESBOM_TENANT')
    server = Server((a.host, a.port), Handler, a.storage, {token: tenant})
    try:
        print('Collector ready on %s:%d' % (a.host, server.server_port), flush=True)
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
