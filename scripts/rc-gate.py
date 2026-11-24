#!/usr/bin/env python3
"""A conservative RC evidence gate; absent test results never become PASS."""
import argparse, json, os, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
ap=argparse.ArgumentParser()
ap.add_argument('--mode',choices=['offline','official'],default='offline')
ap.add_argument('--output',default='results/phase10/rc-gate.json')
ap.add_argument('--run-live',action='store_true',help='opt-in: launch Spring Boot and, if CATALINA_HOME supplied, Tomcat')
a=ap.parse_args()
steps=[]
def step(name,command,required=True,reason=None):
    if command is None:
        steps.append({'name':name,'status':'NOT_RUN','required':required,'reason':reason or 'No execution attempted'})
        return
    try:
        p=subprocess.run(command,cwd=str(ROOT),capture_output=True,text=True,timeout=300)
        steps.append({'name':name,'status':'PASS' if p.returncode==0 else 'FAIL','required':required,'exitCode':p.returncode,'logTail':(p.stdout+'\n'+p.stderr)[-3000:]})
    except (FileNotFoundError,subprocess.TimeoutExpired) as ex:
        steps.append({'name':name,'status':'FAIL','required':required,'reason':str(ex)})
if a.mode=='official':
    step('official ASM shaded agent + method execution + nested archive', ['sh','scripts/verify-official-asm.sh'])
else:
    step('JDK 21 internal ASM validation (test-only)', ['sh','scripts/verify-jdk-asm.sh'])
    step('synthetic nested Boot/WAR archive', ['sh','scripts/verify-nested-archives.sh','jdk-internal'])
if a.mode=='offline':
    step('offline core + collector regression (10 tests)', ['sh','scripts/validate-offline.sh'])
else:
    step('Python collector regression', ['python3','-m','unittest','discover','-s','collector/tests','-v'])
step('classloader separation regression',['sh','scripts/test-classloader-offline.sh'])
if a.mode=='official' and a.run_live:
    step('live Spring Boot 2 HTTP+SBOM',['sh','scripts/verify-live-spring-boot2.sh'])
    step('live Tomcat 9 HTTP+SBOM',['sh','scripts/verify-live-tomcat9.sh'] if os.environ.get('CATALINA_HOME') else None,reason='CATALINA_HOME absent')
else:
    step('live Spring Boot 2 HTTP+SBOM',None,reason='requires --mode official --run-live')
    step('live Tomcat 9 HTTP+SBOM',None,reason='requires --mode official --run-live, CATALINA_HOME')
step('vendor JEUS / WebLogic / AIX',None,reason='vendor environments not available')
step('JDK 8,11,17,21 matrix',None,reason='run GitHub Actions matrix for multi-JDK evidence')
# This deliberately requires official gates + live test + cross-JDK evidence, not merely offline success.
release_ready=(a.mode=='official' and a.run_live and all(s['status']=='PASS' for s in steps))
report={'version':'1.0.0-rc16','mode':a.mode,'generatedAtEpoch':int(time.time()),'releaseReady':release_ready,'decision':('ELIGIBLE FOR REVIEW - all recorded checks passed' if release_ready else 'HOLD - missing required official ASM, multi-JDK, live WAS or vendor evidence'),'checks':steps}
path=(ROOT/a.output).resolve();path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print('RC report:',path)
for s in steps: print('%-8s %s' % (s['status'],s['name']))
print('Release decision:',report['decision'])
if any(s['status']=='FAIL' and s['required'] for s in steps):sys.exit(1)
