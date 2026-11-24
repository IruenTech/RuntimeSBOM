#!/usr/bin/env python3
"""Repeatable Phase18 local gate: PASS of PoC tests never means production approval."""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'results/phase18';OUT.mkdir(parents=True,exist_ok=True)
CHECKS=[
 ('jdk21-asm-smoke',['sh','scripts/verify-jdk-asm.sh'],120),
 ('http-no-false-positive',['python3','scripts/phase18-http-proof.py','--duration','1.2','--concurrency','4'],160),
 ('three-class-loaders',['sh','scripts/phase17-loader-test.sh','jdk-internal'],120),
 ('queue-collector',['sh','scripts/phase16-queue-tests.sh'],160),
 ('approval-gate-unit-tests',['python3','-m','unittest','discover','-s','tests','-p','test_phase18_approval.py','-v'],60),
]
checks=[]
for name,cmd,timeout in CHECKS:
    try:
        result=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              text=True,timeout=timeout)
        code=result.returncode; log=result.stdout
    except (OSError,subprocess.TimeoutExpired) as e:
        code=-1;log=repr(e)
    (OUT/(name+'.log')).write_text(log,encoding='utf-8')
    status='PASS' if code==0 else 'FAIL'
    checks.append({'name':name,'status':status,'returnCode':code,'log':str(OUT/(name+'.log'))})
    print(name,status,flush=True)
# Expected result for this machine: no official binary or real WAS execution -> HOLD.
acc=subprocess.run(['python3','scripts/phase18-acceptance.py'],cwd=ROOT,
                   stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
(OUT/'acceptance-command.log').write_text(acc.stdout)
report=json.loads((OUT/'acceptance.json').read_text())
failclosed=(report['stagingReview']=='HOLD' and report['productionDeployment']=='HOLD')
checks.append({'name':'missing-official-evidence-fails-closed',
               'status':'PASS' if failclosed and acc.returncode==3 else 'FAIL',
               'returnCode':acc.returncode})
result={'schemaVersion':1,'stage':18,'version':'1.0.0-rc16',
        'timestampUtc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'testMode':'JDK21_INTERNAL_ASM_TEST_ONLY',
        'checks':checks,'status':'PASS' if all(x['status']=='PASS' for x in checks) else 'FAIL',
        'officialAsmBuild':'NOT_RUN','actualSpringBootTomcat':'NOT_RUN',
        'jeusWeblogicAix':'NOT_RUN','productionDeployment':'HOLD'}
(OUT/'local-gate.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'localTests':result['status'],
                  'passed':sum(x['status']=='PASS' for x in checks),'total':len(checks),
                  'deployment':'HOLD'},indent=2))
raise SystemExit(0 if result['status']=='PASS' else 1)
