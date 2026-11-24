#!/usr/bin/env python3
"""Launch baseline/load-only/ASM JDK21-internal test fixture; preserve reproducible evidence."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent

def run(args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=120, check=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--agent', default='target/jdk-asm-verification/agent-test-only.jar')
    p.add_argument('--exports', action='store_true', help='JDK21 internal ASM TEST ONLY')
    p.add_argument('--duration', type=float, default=3)
    p.add_argument('--concurrency', type=int, default=4)
    p.add_argument('--out-dir', default='results/phase13')
    args=p.parse_args()
    output=(ROOT/args.out_dir).resolve(); output.mkdir(parents=True, exist_ok=True)
    classes=ROOT/'target/phase13-http/classes'; classes.mkdir(parents=True, exist_ok=True)
    run(['javac','--release','8','-d',str(classes),'src/test/java/example/Worker.java','integration/HttpWorkloadServer.java'])
    agent=(ROOT/args.agent).resolve()
    if not agent.exists(): p.error('Agent not built. Run sh scripts/verify-jdk-asm.sh or mvn package')
    outcomes={}
    for mode in ('baseline','loaded-only','asm-traced'):
        with socket.socket() as s:
            s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
        cmd=['java']
        if args.exports: cmd.append('--add-exports=java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED')
        sbom=output/(mode+'.sbom.json')
        if mode!='baseline':
            options='output='+str(sbom)+',interval=1,resourceProbe=false,sampleEvery=1'
            if mode=='asm-traced': options+=',tracePackages=example'
            cmd.append('-javaagent:'+str(agent)+'='+options)
        cmd.extend(['-cp',str(classes),'integration.HttpWorkloadServer',str(port)])
        log=output/(mode+'.server.log')
        with log.open('w') as stream:
            proc=subprocess.Popen(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
            try:
                ready=False
                for _ in range(100):
                    if proc.poll() is not None: break
                    try:
                        with urllib.request.urlopen('http://127.0.0.1:%d/health'%port, timeout=0.4) as res:
                            ready=res.status==200
                            if ready: break
                    except Exception: time.sleep(.1)
                if not ready: raise RuntimeError('fixture did not start: '+mode+' '+log.read_text()[-1000:])
                report=output/(mode+'.http.json')
                run([sys.executable,'scripts/http-load.py','--url','http://127.0.0.1:%d/work'%port,
                     '--duration',str(args.duration),'--concurrency',str(args.concurrency),'--out',str(report)])
                outcomes[mode]=json.loads(report.read_text())
            finally:
                proc.terminate()
                try: proc.wait(timeout=8)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
        if mode!='baseline':
            if not sbom.exists(): raise RuntimeError('SBOM missing for '+mode)
            bom=json.loads(sbom.read_text())
            if bom.get('bomFormat')!='CycloneDX': raise RuntimeError('invalid SBOM '+mode)
            if mode=='asm-traced':
                properties={v['name']:v['value'] for v in bom['metadata']['properties']}
                observed=sum(int(v) for k,v in properties.items() if k.startswith('runtimeSbom:methodEntry:') and 'Worker#compute' in k)
                if observed<=0: raise RuntimeError('no method execution evidence in HTTP workload')
                outcomes[mode]['observedWorkerComputeEntries']=observed
    base=outcomes['baseline']
    result={'testType':'real-HTTP-local-fixture', 'notRealWAS':True, 'usesJdkInternalAsm':args.exports,
            'modes':outcomes,'relativeToBaseline':{mode:{
              'tpsDeltaPercent':round((data['successTps']/base['successTps']-1)*100,2) if base['successTps'] else None,
              'p95DeltaPercent':round((data['latencyMs']['p95']/base['latencyMs']['p95']-1)*100,2) if base['latencyMs']['p95'] else None}
              for mode,data in outcomes.items() if mode!='baseline'},
            'notes':['one sequential run per mode; noisy synthetic performance results',
                     'HTTP fixture uses JDK HttpServer and not actual Spring Boot or Tomcat',
                     'JDK internal ASM artifact must never be used in production']}
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'summary':str(output/'summary.json'), 'modes':{m:{'tps':v['tps'],'p95Ms':v['latencyMs']['p95'],'p99Ms':v['latencyMs']['p99']} for m,v in outcomes.items()}}, indent=2))

if __name__=='__main__': main()
