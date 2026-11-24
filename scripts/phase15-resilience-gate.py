#!/usr/bin/env python3
"""Offline validation only. Does NOT certify ASM, JEUS, WebLogic or AIX."""
import json, pathlib, subprocess, time, sys
root=pathlib.Path(__file__).resolve().parents[1]
results=root/'results'/'phase15'
results.mkdir(parents=True,exist_ok=True)
def run(label,command):
    p=subprocess.run(command,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
    (results/(label+'.log')).write_text(p.stdout)
    return {'name':label,'passed':p.returncode==0,'returncode':p.returncode,'command':command}
tests=[]
tests.append(run('offline-baseline',['sh','scripts/validate-offline.sh']))
if tests[-1]['passed']:
    tests.append(run('compile-resilience',['javac','--release','8','-cp','target/offline-validation/classes','-d','target/offline-validation/classes','src/test/java/com/iruen/runtimesbom/Phase15ResilienceTest.java']))
    if tests[-1]['passed']:
        tests.append(run('http-fault-injection',['java','-cp','target/offline-validation/classes','com.iruen.runtimesbom.Phase15ResilienceTest']))
    for iteration in ('1','2'):
        out=root/'target'/'offline-validation'/('restart-'+iteration+'.json')
        if out.exists():out.unlink()
        t=run('jvm-run-'+iteration,['java','-javaagent:target/offline-validation/agent-validation-only.jar=output='+str(out)+',interval=0','-cp','target/offline-validation/demo.jar','example.Demo'])
        if t['passed']:
            try:
                bom=json.loads(out.read_text())
                t['passed']=bom['bomFormat']=='CycloneDX' and bom['specVersion']=='1.6' and isinstance(bom['components'],list)
                t['componentCount']=len(bom['components'])
            except Exception as e:t['passed']=False;t['error']=str(e)
        tests.append(t)
report={'version':'1.0.0-rc6','date':'2026-11-24','scope':'JDK21 Java8-target offline; ASM replaced by test stub','tests':tests,
        'officialAsmBuild':'NOT_RUN','springBootTomcatLive':'NOT_RUN','jeusWeblogicAix':'NOT_RUN','releaseDecision':'HOLD'}
(results/'gate.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'passed':sum(t['passed'] for t in tests),'total':len(tests),'releaseDecision':'HOLD'},indent=2))
sys.exit(0 if all(t['passed'] for t in tests) else 1)
