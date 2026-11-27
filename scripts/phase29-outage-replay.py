#!/usr/bin/env python3
"""Official ASM Agent + reference Collector: multi-JVM outage, backlog replay, collector restart.

Uses only localhost, a private temporary directory and the exact previously verified rc16 JAR.
This is a bounded integration test, NOT proof of 24h production resilience.
"""
import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAR = ROOT / 'target/runtime-sbom-agent-1.0.0-rc16.jar'
SHA = os.environ.get('RUNTIMESBOM_EXPECTED_SHA256', 'ed5613c7d515d877b57bb6844ddb4bb66c919af74648ac10bb9960d99e406f4a')
TOKEN = 'phase29-local-ephemeral-token-for-testing'
sys.path.insert(0, str(ROOT / 'collector'))
from server import Server, Handler


def reserve_offline_port():
    """Keep the selected port reserved while Collector is intentionally offline.

    A closed ephemeral probe port can be acquired by another process on shared
    CI runners.  A bound, non-listening socket keeps connections refused and
    prevents another server from taking that address during the outage phase.
    """
    hold = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    hold.bind(('127.0.0.1', 0))
    return hold


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(65536), b''):
            h.update(data)
    return h.hexdigest()


def get_assets(port_number):
    request = urllib.request.Request('http://127.0.0.1:%d/api/v1/assets' % port_number,
        headers={'Authorization':'Bearer ' + TOKEN})
    with urllib.request.urlopen(request, timeout=4) as res:
        return {v['asset']:v['snapshotCount'] for v in json.load(res)['assets']}


def start_server(port_number, data_dir):
    server = Server(('127.0.0.1', port_number), Handler, data_dir, {TOKEN:'phase29'})
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return server, worker


def close_server(server, worker):
    server.shutdown()
    worker.join(timeout=5)
    server.server_close()


def compile_demo():
    target = ROOT/'target/phase29-outage/classes'
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(['javac','--release','8','-d',str(target),
        str(ROOT/'src/test/java/example/Worker.java'),
        str(ROOT/'src/test/java/example/Demo.java')], check=True, timeout=30)
    return target


def invoke_agent(classes, queue, url, base, num):
    asset = 'outage-%02d' % num
    output = base / ('snapshot-%02d.json' % num)
    opts = ('output=%s,interval=0,resourceProbe=false,assetId=%s,queueDir=%s,'
            'queueDrainInterval=15,httpTimeoutMs=400,collectorUrl=%s,'
            'engine=asm,tracePackages=example') % (output, asset, queue, url)
    proc = subprocess.run(['java','-javaagent:%s=%s' % (JAR, opts),
                           '-cp',str(classes),'example.Demo'],cwd=ROOT,
                          env=dict(os.environ,RUNTIMESBOM_TOKEN=TOKEN),
                          text=True,capture_output=True,timeout=30)
    (base/('agent-%02d.log'%num)).write_text(proc.stdout+'\n'+proc.stderr,encoding='utf-8')
    if proc.returncode or not output.is_file():
        raise RuntimeError('JVM %d failed: exit=%s %s' % (num,proc.returncode,(proc.stdout+proc.stderr)[-1200:]))
    sbom = json.loads(output.read_text(encoding='utf-8'))
    count = sum(int(p['value']) for p in sbom.get('metadata',{}).get('properties',[])
                if p.get('name','').startswith('runtimeSbom:methodEntry:') and '#compute(' in p.get('name',''))
    if count!=4:
        raise RuntimeError('Incorrect method execution evidence for %s: %s' %(asset,count))
    return asset


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--offline-jvms',type=int,default=3)
    ap.add_argument('--outage-seconds',type=float,default=1)
    ap.add_argument('--out',type=Path,default=ROOT/'results/phase29/outage-replay.json')
    args = ap.parse_args()
    if not(1<=args.offline_jvms<=8 and 0<=args.outage_seconds<=3600):
        ap.error('offline-jvms 1..8, outage-seconds 0..3600')
    if not JAR.is_file() or sha(JAR)!=SHA:
        raise SystemExit('FAIL CLOSED: exact official rc16 agent absent or SHA-256 mismatch')
    report={'phase':29,'test':'multi_jvm_outage_restart_replay','agentSha256':SHA,
            'productionDeployment':'HOLD','scope':'JDK21 localhost reference collector, not live WAS',
            'status':'FAIL','offlineJvmCount':args.offline_jvms,'outageSeconds':args.outage_seconds}
    stage = 'compile_demo'
    held_socket = None
    try:
        classes = compile_demo()
        stage = 'prepare_outage'
        with tempfile.TemporaryDirectory(prefix='phase29-outage-') as tmp:
            base = Path(tmp)
            queue = base/'queue'
            db = base/'collector'
            held_socket = reserve_offline_port()
            port_number = held_socket.getsockname()[1]
            url = 'http://127.0.0.1:%d/api/v1/sbom' % port_number
            original = []
            try:
                for i in range(args.offline_jvms):
                    stage = 'offline_jvm_%d' % (i+1)
                    original.append(invoke_agent(classes,queue,url,base,i+1))
                    pending = sorted(queue.glob('*.json'))
                    if len(pending) != i+1:
                        raise RuntimeError('Backlog mismatch after JVM %d: got %d expected %d' % (i+1,len(pending),i+1))
                stage = 'capture_replay_payload'
                replay_file = sorted(queue.glob('*.json'))[0]
                replay_payload = replay_file.read_bytes()
                replay_id = replay_file.name.split('-')[1]
                report['pendingWhileOffline'] = len(list(queue.glob('*.json')))
                time.sleep(args.outage_seconds)

                # Release as late as possible, after all offline JVMs have exited.
                # No Agent runs between release and the reference Collector bind.
                stage = 'start_collector'
                held_socket.close()
                held_socket = None
                server, worker = start_server(port_number,db)
                try:
                    stage = 'online_jvm_drain'
                    online_asset = invoke_agent(classes,queue,url,base,args.offline_jvms+1)
                    stage = 'verify_drained_queue'
                    pending_after = list(queue.glob('*.json'))
                    if pending_after:
                        raise RuntimeError('Recovery left pending files: %d' % len(pending_after))
                    stage = 'verify_collector_snapshots'
                    assets = get_assets(port_number)
                    expected = {a:1 for a in original+[online_asset]}
                    if assets != expected:
                        raise RuntimeError('Collector missing snapshots: %s expected %s' % (assets,expected))
                    report['assetsAfterRecovery'] = assets
                    report['queueFilesAfterRecovery'] = 0
                finally:
                    close_server(server, worker)

                stage = 'restart_collector'
                server2, worker2 = start_server(port_number,db)
                try:
                    stage = 'verify_idempotent_replay'
                    req = urllib.request.Request(url,data=replay_payload,method='POST',headers={
                        'Authorization':'Bearer '+TOKEN,
                        'Content-Type':'application/vnd.cyclonedx+json; version=1.6',
                        'X-RuntimeSBOM-Asset': original[0],
                        'X-RuntimeSBOM-Delivery-ID': replay_id})
                    with urllib.request.urlopen(req,timeout=5) as resp:
                        report['replayHttpStatus'] = resp.status
                    after_restart = get_assets(port_number)
                    if after_restart != expected:
                        raise RuntimeError('Duplicate replay changed persisted snapshots: %s' % after_restart)
                    report['assetsAfterCollectorRestart'] = after_restart
                    report['expectedSnapshots'] = len(expected)
                    report['status'] = 'PASS'
                finally:
                    close_server(server2,worker2)
            except Exception:
                report['failureStage'] = stage
                report['queueFilesAtFailure'] = len(list(queue.glob('*.json')))
                # The temp directory is removed on exit, so retain bounded,
                # secret-free Agent stderr/stdout tails in the JSON artifact.
                report['agentLogTails'] = [
                    {'file': f.name, 'tail': f.read_text(encoding='utf-8',errors='replace')[-2500:]}
                    for f in sorted(base.glob('agent-*.log'))
                ]
                raise
            finally:
                if held_socket is not None:
                    held_socket.close()
    except Exception as exc:
        report['error'] = repr(exc)
        report.setdefault('failureStage',stage)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PHASE29 OUTAGE',report['status'],'PRODUCTION HOLD',flush=True)
    if report['status']!='PASS':
        print('PHASE29_OUTAGE_FAILURE_STAGE:',report['failureStage'],file=sys.stderr,flush=True)
        print('PHASE29_OUTAGE_ERROR:',report['error'],file=sys.stderr,flush=True)
        print('PHASE29_OUTAGE_REPORT:',args.out,file=sys.stderr,flush=True)
        return 1
    return 0

if __name__=='__main__':sys.exit(main())
