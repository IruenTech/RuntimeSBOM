#!/usr/bin/env python3
"""Phase 20 local regression gate: rigorous fixture accuracy, never production approval."""
import datetime as dt
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'results'/'phase20';OUT.mkdir(parents=True,exist_ok=True)
CHECKS=[
 ('fixture-identity-execution',['sh','scripts/phase20-fixture-gate.sh','jdk-internal'],160),
 ('accuracy-negative-controls',['python3','-m','unittest','discover','-s','tests','-p','test_phase20_*.py','-v'],40),
 ('collector-and-delivery',['sh','scripts/phase16-queue-tests.sh'],160),
 ('loopback-http-observation',['python3','scripts/phase18-http-proof.py','--duration','0.5','--concurrency','2'],90),
 ('loader-regression',['sh','scripts/phase17-loader-test.sh','jdk-internal'],100),
 ('release-approval-negative-tests',['python3','-m','unittest','discover','-s','tests','-p','test_phase18_approval.py','-v'],40),
]

def invoke(name,cmd,timeout):
    log_path=OUT/(name+'.log')
    with log_path.open('w',encoding='utf-8') as stream:
        try:
            child=subprocess.Popen(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                                   start_new_session=True)
            try:
                code=child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGKILL)
                child.wait()
                code=-1
                stream.write('\nFAIL: command timed out after %s seconds\n'%timeout)
        except OSError as exc:
            code=-1
            stream.write('\nFAIL: %r\n'%exc)
    return {'group':name,'status':'PASS' if code==0 else 'FAIL','exitCode':code,
            'log':'results/phase20/'+name+'.log'}


def main():
    checks=[]
    for name,cmd,timeout in CHECKS:
        check=invoke(name,cmd,timeout);checks.append(check)
        print(name,check['status'],flush=True)
    acceptance=invoke('official-and-live-acceptance',[
        'python3','scripts/phase18-acceptance.py',
        '--agent','target/runtime-sbom-agent-1.0.0-rc16.jar',
        '--jdk-dir','results/phase20/jdk-matrix',
        '--live-dir','results/phase20/live',
        '--out','results/phase20/acceptance.json'],30)
    acc=OUT/'acceptance.json'
    data=json.loads(acc.read_text(encoding='utf-8')) if acc.is_file() else {}
    acceptance['status']='PASS' if (acceptance['exitCode']==3 and
            data.get('stagingReview')=='HOLD' and data.get('productionDeployment')=='HOLD') else 'FAIL'
    acceptance['validation']='REQUIRES_HOLD_WITHOUT_OFFICIAL_AND_LIVE_EVIDENCE'
    checks.append(acceptance)
    suite='PASS' if all(x['status']=='PASS' for x in checks) else 'FAIL'
    fixture_path=OUT/'fixture-summary-jdk-internal.json'
    fixture=json.loads(fixture_path.read_text()) if fixture_path.exists() else None
    result={'schemaVersion':1,'stage':20,'version':'1.0.0-rc16',
            'createdAtUtc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'testMode':'JDK21_INTERNAL_ASM_TEST_ONLY','checks':checks,
            'fixtureAccuracy':fixture,'localValidation':suite,
            'officialAsmMavenBuild':'NOT_RUN_NETWORK_AND_MAVEN_UNAVAILABLE',
            'actualSpringBootTomcat':'NOT_RUN_BUILD_DEPENDENCIES_UNAVAILABLE',
            'jdk8_11_17_21':'NOT_RUN_ONLY_JDK21_INSTALLED',
            'jeusWeblogicAix':'NOT_RUN_NO_VENDOR_JVMS',
            'stagingReview':'HOLD','productionDeployment':'HOLD'}
    (OUT/'gate.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'localValidation':suite,'groupsPassed':sum(x['status']=='PASS' for x in checks),
                      'groupsTotal':len(checks),'fixtureTP':fixture.get('TP') if fixture else None,
                      'stagingReview':'HOLD','productionDeployment':'HOLD'},indent=2))
    return 0 if suite=='PASS' else 1

if __name__=='__main__':sys.exit(main())
