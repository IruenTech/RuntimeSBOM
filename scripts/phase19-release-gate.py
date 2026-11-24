#!/usr/bin/env python3
"""Phase19 local regression + fail-closed staging decision. Test-only ASM is never approved."""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'results/phase19';OUT.mkdir(parents=True,exist_ok=True)
CHECKS=[
 ('asm-jdk21-real-method-calls',['sh','scripts/verify-jdk-asm.sh'],100),
 ('exact-jar-loader-provenance',['sh','scripts/phase19-provenance-test.sh','jdk-internal'],90),
 ('legacy-loader-regression',['sh','scripts/phase17-loader-test.sh','jdk-internal'],90),
 ('http-loopback-positive-negative',['python3','scripts/phase18-http-proof.py','--duration','1.0','--concurrency','4'],150),
 ('boot-war-archive-regression',['sh','scripts/verify-nested-archives.sh','jdk-internal'],100),
 ('reliable-delivery-regression',['sh','scripts/phase16-queue-tests.sh'],160),
 ('attribution-index-unit',['sh','scripts/phase19-test-index.sh'],60),
 ('strict-release-gate-tests',['python3','-m','unittest','discover','-s','tests','-p','test_phase18_approval.py','-v'],60),
]

def execute(name,cmd,limit):
    try:
        p=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=limit)
        rc=p.returncode; details=p.stdout
    except (OSError,subprocess.TimeoutExpired) as exc:
        rc=-1;details=repr(exc)
    log=OUT/(name+'.log');log.write_text(details,encoding='utf-8')
    return {'name':name,'status':'PASS' if rc==0 else 'FAIL','returnCode':rc,
            'log':str(log.relative_to(ROOT))}

def main():
    results=[]
    for name,cmd,limit in CHECKS:
        row=execute(name,cmd,limit);results.append(row)
        print(name,row['status'],flush=True)
    # Force a fresh evidence review. Missing official JAR and real WAS must not be silently accepted.
    rc=execute('staging-acceptance',['python3','scripts/phase18-acceptance.py',
        '--agent','target/runtime-sbom-agent-1.0.0-rc16.jar',
        '--jdk-dir','results/phase19/jdk-matrix',
        '--live-dir','results/phase19/live',
        '--out','results/phase19/acceptance.json'],30)
    acceptance=json.loads((OUT/'acceptance.json').read_text()) if (OUT/'acceptance.json').exists() else {}
    allowed=('HOLD','ELIGIBLE_FOR_HUMAN_REVIEW')
    # The local self-test cannot generate trusted official ASM / real WAS evidence.
    rc['status']='PASS' if rc['returnCode']==3 and acceptance.get('stagingReview')=='HOLD' \
                    and acceptance.get('productionDeployment')=='HOLD' else 'FAIL'
    results.append(rc)
    status='PASS' if all(c['status']=='PASS' for c in results) else 'FAIL'
    report={'schemaVersion':1,'stage':19,'version':'1.0.0-rc16',
            'timestampUtc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'testMode':'JDK21_INTERNAL_ASM_TEST_ONLY',
            'checks':results,'localStatus':status,
            'officialAsmBuild':'NOT_RUN_MAVEN_NOT_INSTALLED',
            'springBootTomcatLive':'NOT_RUN_DEPENDENCIES_UNAVAILABLE',
            'jeusWeblogicAix':'NOT_RUN_VENDOR_ENVIRONMENT_UNAVAILABLE',
            'stagingReview':acceptance.get('stagingReview','HOLD'),
            'productionDeployment':'HOLD'}
    (OUT/'gate.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'status':status,'passed':sum(c['status']=='PASS' for c in results),
                      'groups':len(results),'productionDeployment':'HOLD'},indent=2))
    return 0 if status=='PASS' else 1

if __name__=='__main__':sys.exit(main())
