#!/usr/bin/env python3
"""Execute new HTTP workload, assert no phantom method execution with loading-only mode.
The JDK internal ASM validation build is local-test-only. No vendor WAS is used.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def observed(path):
    bom=json.loads(path.read_text())
    if bom.get('bomFormat')!='CycloneDX':raise ValueError('Not CycloneDX')
    return sum(int(x['value']) for x in bom.get('metadata',{}).get('properties',[])
               if x.get('name','').startswith('runtimeSbom:methodEntry:') and 'Worker#compute' in x['name'])

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--duration',type=float,default=1.5)
    p.add_argument('--concurrency',type=int,default=4)
    a=p.parse_args()
    if not (.5 <= a.duration <= 120 and 1 <= a.concurrency <= 32):p.error('unsafe limits')
    out=ROOT/'results/phase18/http-loopback'
    if out.exists():shutil.rmtree(out)
    out.mkdir(parents=True)
    cmd=[sys.executable,'scripts/http-benchmark-phase13.py','--exports',
         '--duration',str(a.duration),'--concurrency',str(a.concurrency),
         '--out-dir','results/phase18/http-loopback']
    log=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=150)
    (out/'test-run.log').write_text(log.stdout)
    if log.returncode:raise RuntimeError('HTTP test failed: '+log.stdout[-1500:])
    summary=json.loads((out/'summary.json').read_text())
    load=observed(out/'loaded-only.sbom.json')
    asm=observed(out/'asm-traced.sbom.json')
    if load != 0 or asm < 1:
        raise RuntimeError('Method entry evidence mismatch: loaded-only=%d asm=%d'%(load,asm))
    if not all(x['errors']==0 for x in summary['modes'].values()):
        raise RuntimeError('HTTP errors observed in one or more modes')
    report={'schemaVersion':1,'test':'JDK21_INTERNAL_ASM_LOOPBACK_ONLY',
            'testOnly':True,'realTomcat':False,'realSpringBoot':False,
            'loadingOnlyObservedMethods':load,'asmObservedMethods':asm,
            'httpErrors':0, 'status':'PASS','productionDeployment':'HOLD',
            'modes':{m:{'successTps':v['successTps'],'p95':v['latencyMs']['p95'],'p99':v['latencyMs']['p99']} for m,v in summary['modes'].items()}}
    (out/'proof.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
