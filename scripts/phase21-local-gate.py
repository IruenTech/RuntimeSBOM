#!/usr/bin/env python3
"""Reproducible stage21 local gate (explicitly NOT an official deployment gate)."""
import json
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'results/phase21/local-gate'


def execute(title,argv,timeout):
    started=time.monotonic()
    try:
        p=subprocess.run(argv,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                         text=True,timeout=timeout)
        return {'status':'PASS' if p.returncode==0 else 'FAIL','seconds':round(time.monotonic()-started,2),
                'exitCode':p.returncode,'log':str(OUT/(title+'.log')),'output':p.stdout}
    except subprocess.TimeoutExpired as ex:
        return {'status':'TIMEOUT','seconds':round(time.monotonic()-started,2),
                'exitCode':None,'log':str(OUT/(title+'.log')),'output':str(ex)}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    groups=[
      ('new-evidence-and-gate-tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_phase21_*.py','-v'],35),
      ('previous-accuracy-controls',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_phase20_*.py','-q'],35),
      ('collector-reliable-delivery',[sys.executable,'-m','unittest','discover','-s','collector/tests','-p','test_*.py','-q'],60),
      ('actual-loader-asm-fixture',['sh','scripts/phase19-provenance-test.sh','jdk-internal'],70),
      ('http-provenance',['python3','scripts/phase21-http-provenance.py','--mode','jdk-internal',
                          '--requests','80','--concurrency','8'],100)
    ]
    report={'schemaVersion':1,'stage':21,'scope':'JDK21 internal ASM / test-only fixture and Python regressions',
            'results':{},'officialAsmBuild':'NOT_EXECUTED','liveSpringBootTomcat':'NOT_EXECUTED',
            'productionDeployment':'HOLD'}
    for title,argv,limit in groups:
        print('RUN',title,flush=True)
        value=execute(title,argv,limit)
        (OUT/(title+'.log')).write_text(value.pop('output'),encoding='utf-8')
        report['results'][title]=value
        print(value['status'],title,'(',value['seconds'],'s)',flush=True)
    report['status']='PASS_LOCAL_ONLY' if all(v['status']=='PASS' for v in report['results'].values()) else 'FAIL'
    (ROOT/'results/phase21/local-gate.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'groupsPassed':sum(v['status']=='PASS' for v in report['results'].values()),
                      'groupsTotal':len(groups),'productionDeployment':'HOLD'},indent=2))
    return 0 if report['status']=='PASS_LOCAL_ONLY' else 2

if __name__=='__main__':raise SystemExit(main())
