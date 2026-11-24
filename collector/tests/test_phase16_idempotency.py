"""Real collector tests for retry-safe, tenant/asset scoped delivery idempotency."""
import concurrent.futures
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Server, Handler, db_connect

TOKEN = 'phase16-test-token-123456789'
DELIVERY = 'a'*32


class IdempotentCollectorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = Server(('127.0.0.1', 0), Handler, self.tmp.name, {TOKEN:'tenant-alpha', 'second-tenant-token':'tenant-beta'})
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/api/v1/sbom'

    def tearDown(self):
        self.server.shutdown()
        self.worker.join(timeout=5)
        self.server.server_close()
        self.tmp.cleanup()

    def send(self, ident=DELIVERY, asset='was-01', version='1', token=TOKEN):
        body = json.dumps({'bomFormat':'CycloneDX','specVersion':'1.6',
            'components':[{'type':'library','name':'test','version':version}]}).encode()
        headers = {'Authorization':'Bearer '+token,'X-RuntimeSBOM-Asset':asset,
            'Content-Type':'application/vnd.cyclonedx+json'}
        if ident is not None:
            headers['X-RuntimeSBOM-Delivery-ID'] = ident
        req = Request(self.url, data=body, headers=headers, method='POST')
        try:
            with urlopen(req, timeout=5) as resp:
                return resp.status, json.load(resp)
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def count(self, tenant='tenant-alpha', asset='was-01'):
        with self.server.lock:
            return self.server.conn.execute(
                'SELECT COUNT(*) FROM snapshots WHERE tenant=? AND asset=?',
                (tenant,asset)).fetchone()[0]

    def test_retry_same_receipt_and_payload_conflict(self):
        first, body = self.send()
        second, repeated = self.send()
        self.assertEqual((first,second),(201,200))
        self.assertEqual(body['snapshotId'], repeated['snapshotId'])
        self.assertTrue(repeated['duplicate'])
        self.assertEqual(self.count(),1)
        conflict, payload = self.send(version='modified')
        self.assertEqual(conflict,409)
        self.assertEqual(payload['error'],'delivery_id_conflict')
        self.assertEqual(self.count(),1)
        self.assertEqual(self.send(ident='b'*32)[0],201)
        self.assertEqual(self.count(),2)
        self.assertEqual(self.send(ident=DELIVERY,asset='was-02')[0],201)
        self.assertEqual(self.count(asset='was-02'),1)
        self.assertEqual(self.send(ident=DELIVERY,token='second-tenant-token')[0],201)
        self.assertEqual(self.count('tenant-beta'),1)
        self.assertEqual(self.send(ident='unsafe:delivery')[0],400)

    def test_concurrent_idempotency(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: self.send(),range(12)))
        self.assertEqual([r[0] for r in responses].count(201),1)
        self.assertEqual([r[0] for r in responses].count(200),11)
        self.assertEqual(len({r[1]['snapshotId'] for r in responses}),1)
        self.assertEqual(self.count(),1)

    def test_backward_compatible_migration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.sqlite3'
            db = sqlite3.connect(path)
            db.execute('''CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL, asset TEXT NOT NULL,
                sha256 TEXT NOT NULL, created_at TEXT NOT NULL, components INTEGER NOT NULL,
                document TEXT NOT NULL)''')
            db.execute("INSERT INTO snapshots(tenant,asset,sha256,created_at,components,document) VALUES ('old','app','h','y',0,'{}')")
            db.commit(); db.close()
            upgraded = db_connect(path)
            try:
                self.assertIn('delivery_id', [r[1] for r in upgraded.execute('PRAGMA table_info(snapshots)')])
                self.assertEqual(upgraded.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0],1)
            finally:
                upgraded.close()


if __name__ == '__main__':
    unittest.main()
