#!/usr/bin/env python3
"""Re-run ONLY offline tests possible in this environment; never approves a release."""
import datetime as dt
import json,os,signal,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'results/phase22'
CHECKS=[
 ('new-gate-and-binary-negative-tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_phase22_*.py','-v'],45),
 ('jdk21-internal-asm-regression',['sh','scripts/verify-jdk-asm.sh'],100),
 ('http-provenance-fixture',[sys.executable,'scripts/phase21-http-provenance.py','--mode','jdk-internal','--requests','48','--concurrency','6','--out-dir','results/phase22/local-http'],100),
 ('collector-regression',[sys.executable,'-m','unittest','discover','-s','collector/tests','-p','test_*.py','-v'],100),
]

def invoke(name,cmd,timeout):
    OUT.mkdir(parents=True,exist_ok=True)
    log=OUT/(name+'.log')
    with log.open('w') as f:
        try:
            p=subprocess.Popen(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            try: rc=p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL);p.wait();rc=-1
                f.write('TIMEOUT after '+str(timeout)+' seconds\n')
        except OSError as ex:
            f.write(repr(ex)+'\n');rc=-2
    return {'group':name,'status':'PASS' if rc==0 else 'FAIL','exitCode':rc,'log':str(log.relative_to(ROOT))}

def main():
    items=[]
    for name,cmd,limit in CHECKS:
        result=invoke(name,cmd,limit);items.append(result)
        print(name,result['status'],flush=True)
    # Fail-closed expected rejection: NO release binary, NO actual WAS evidence.
    gate=invoke('official-release-rejection',[sys.executable,'scripts/phase22-evidence-gate.py'],20)
    record=json.loads((OUT/'release-gate.json').read_text()) if (OUT/'release-gate.json').is_file() else {}
    gate['status']='PASS' if gate['exitCode']==3 and record.get('stagingReview')=='HOLD' and record.get('productionDeployment')=='HOLD' else 'FAIL'
    gate['test']='EXPECTED_HOLD_WITHOUT_OFFICIAL_ARTIFACT'
    items.append(gate)
    status='PASS' if all(i['status']=='PASS' for i in items) else 'FAIL'
    result={'schemaVersion':1,'stage':22,'version':'1.0.0-rc16',
            'checkedAtUtc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'offlineValidation':status,'checks':items,
            'runtimeEnvironment':'JDK21 internal ASM - NOT official distributable',
            'officialMavenBuild':'NOT_RUN_MAVEN_AND_NETWORK_UNAVAILABLE',
            'jdk8_11_17_21':'NOT_RUN_ONLY_JDK21_AVAILABLE',
            'springBootAndTomcat':'NOT_RUN_OFFICIAL_BUILD_UNAVAILABLE',
            'enterpriseWAS':'NOT_RUN_NO_JEUS_WEBLOGIC_AIX',
            'stagingReview':'HOLD','productionDeployment':'HOLD'}
    (OUT/'local-gate.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'offlineValidation':status,'passed':sum(i['status']=='PASS' for i in items),
                      'required':len(items),'stagingReview':'HOLD'},indent=2))
    return 0 if status=='PASS' else 1
if __name__=='__main__':sys.exit(main())
