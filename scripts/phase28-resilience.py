#!/usr/bin/env python3
"""Official shaded Agent: real collector offline -> durable spool -> JVM restart -> recovery.

Localhost and temporary storage only; no real WAS deployment claims.
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
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AGENT=ROOT/'target/runtime-sbom-agent-1.0.0-rc16.jar'
SHA='ed5613c7d515d877b57bb6844ddb4bb66c919af74648ac10bb9960d99e406f4a'
TOKEN='phase28-temporary-only-testing-token-12345'
sys.path.insert(0, str(ROOT/'collector'))
from server import Server, Handler


def get_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); return s.getsockname()[1]


def compile_demo():
    target=ROOT/'target/phase28-delivery/classes';target.mkdir(parents=True, exist_ok=True)
    subprocess.run(['javac','--release','8','-d',str(target),
                    str(ROOT/'src/test/java/example/Worker.java'),
                    str(ROOT/'src/test/java/example/Demo.java')],check=True)
    return target


def get_assets(port):
    req=urllib.request.Request('http://127.0.0.1:%d/api/v1/assets'%port,
                               headers={'Authorization':'Bearer '+TOKEN})
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)['assets']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'results/phase28/resilience.json')
    args=parser.parse_args()
    if not AGENT.is_file() or hashlib.sha256(AGENT.read_bytes()).hexdigest()!=SHA:
        raise SystemExit('Official rc16 binary SHA mismatch')
    classes=compile_demo()
    details={}
    try:
        with tempfile.TemporaryDirectory(prefix='phase28-collector-') as tmp:
            base=Path(tmp);queue=base/'queue'; port=get_port()
            url='http://127.0.0.1:%d/api/v1/sbom'%port
            def run_agent(asset, filename):
                out=base/filename
                opts=('output=%s,interval=0,resourceProbe=false,assetId=%s,queueDir=%s,'
                      'queueDrainInterval=15,httpTimeoutMs=500,collectorUrl=%s,engine=asm,tracePackages=example')\
                      %(out,asset,queue,url)
                command=['java','-javaagent:%s=%s'%(AGENT,opts),'-cp',str(classes),'example.Demo']
                result=subprocess.run(command,env=dict(os.environ,RUNTIMESBOM_TOKEN=TOKEN),
                                      stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
                if result.returncode or not out.is_file():
                    raise RuntimeError('JVM agent failed rc=%s log=%s'%(result.returncode,result.stdout[-1600:]))
                sbom=json.loads(out.read_text())
                hit=sum(int(p['value']) for c in sbom.get('components',[])
                        for p in c.get('properties',[])
                        if p.get('name')=='runtimeSbom:observedMethodEntryCount')
                compute_hits=sum(int(p['value']) for p in sbom.get('metadata',{}).get('properties',[])
                                 if p.get('name','').startswith('runtimeSbom:methodEntry:')
                                 and '#compute(' in p['name'])
                if compute_hits!=4:
                    raise RuntimeError('Expected 4 Worker.compute entries, got %d (all entries=%d)'%(compute_hits,hit))
                details['totalObservedMethodEntries']=hit
                return result
            run_agent('before-restart','first-sbom.json')
            pending=sorted(queue.glob('*.json'))
            if len(pending)!=1:raise RuntimeError('Expected one preserved spool entry, got %d'%len(pending))
            saved=pending[0].read_bytes()
            components=pending[0].name.split('-')
            delivery_id=components[1]
            details['pendingBeforeRecovery']=len(pending)
            # Collector comes online while a different JVM instance starts.
            srv=Server(('127.0.0.1',port),Handler,base/'collector',{TOKEN:'tenant28'})
            worker=threading.Thread(target=srv.serve_forever,daemon=True)
            worker.start()
            try:
                run_agent('after-restart','second-sbom.json')
                if list(queue.glob('*.json')):
                    raise RuntimeError('Spool not drained after collector recovery')
                assets=get_assets(port)
                actual={a['asset']:a['snapshotCount'] for a in assets}
                if actual!={'before-restart':1,'after-restart':1}:
                    raise RuntimeError('Unexpected restored assets %r'%actual)
                # Re-submit IDENTICAL ID/payload: collector must acknowledge without a new snapshot.
                req=urllib.request.Request(url,data=saved,method='POST',headers={
                    'Authorization':'Bearer '+TOKEN,
                    'Content-Type':'application/vnd.cyclonedx+json; version=1.6',
                    'X-RuntimeSBOM-Asset':'before-restart',
                    'X-RuntimeSBOM-Delivery-ID':delivery_id})
                with urllib.request.urlopen(req,timeout=6) as res:
                    details['duplicateRequestStatus']=res.status
                after={a['asset']:a['snapshotCount'] for a in get_assets(port)}
                if after!=actual:raise RuntimeError('Idempotency failed %r'%after)
                details.update({'pendingAfterRecovery':0,'assetSnapshotCounts':after,
                                'distinctDeliveryIds':srv.conn.execute('SELECT COUNT(DISTINCT delivery_id) FROM snapshots').fetchone()[0],
                                'methodEntryEvidencePerJvm':4})
            finally:
                srv.shutdown();worker.join(timeout=5);srv.server_close()
        report={'stage':28,'status':'PASS','scope':'official rc16 binary, local reference collector, 2 JVM processes',
                'tests':['offline spool','restart drain','idempotent replay'],
                'results':details,'agentSha256':SHA,'productionDeployment':'HOLD'}
    except Exception as e:
        report={'stage':28,'status':'FAIL','error':repr(e),'results':details,'productionDeployment':'HOLD'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PHASE28 RESILIENCE',report['status'],flush=True)
    if report['status']!='PASS':
        print(report['error'],file=sys.stderr);sys.exit(1)

if __name__=='__main__':main()
