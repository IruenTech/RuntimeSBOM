#!/usr/bin/env python3
"""Run offline tests and produce a truthful release report (official build still HOLD)."""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'results/phase25'

def run(name,cmd,expected,timeout=260):
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
        rc=p.returncode;message=p.stdout
    except subprocess.TimeoutExpired:rc=124;message='TIMEOUT: verification did not complete'
    except OSError as exc:rc=127;message='CANNOT EXECUTE: '+str(exc)
    (OUT/(name+'.log')).write_text(message,encoding='utf-8')
    result={'name':name,'exitCode':rc,'expectedExitCode':expected,'status':'PASS' if rc==expected else 'FAIL',
            'durationSeconds':round(time.monotonic()-start,2),'log':'results/phase25/'+name+'.log'}
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--fast',action='store_true',help='Skip prior ASM/HTTP/collector regression group; result is scoped')
    a=p.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    groups=[]
    if not a.fast:groups.append(run('phase24-regression',[sys.executable,'scripts/phase24-local-gate.py'],0,350))
    groups.append(run('phase25-tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_phase25_*.py','-v'],0,70))
    groups.append(run('preflight-config',[sys.executable,'scripts/phase25-build-preflight.py'],0,20))
    groups.append(run('official-binary-expected-hold',[sys.executable,'scripts/phase24-check-binary.py'],3,20))
    groups.append(run('staging-expected-hold',[sys.executable,'scripts/phase24-staging-manifest.py'],3,20))
    groups.append(run('review-expected-hold',[sys.executable,'scripts/phase25-review.py'],3,20))
    # Deterministically detect any fake-success report; not just a zero exit code.
    for filepath,key,want in [('results/phase24/binary-preflight.json','status','HOLD'),
                              ('results/phase24/staging-manifest.json','stagingReview','HOLD'),
                              ('results/phase25/release-review.json','stagingReview','HOLD')]:
        try:
            value=json.loads((ROOT/filepath).read_text())[key]
            if value!=want: groups[-1]['status']='FAIL'
        except (OSError,KeyError,ValueError):groups[-1]['status']='FAIL'
    overall='PASS' if all(g['status']=='PASS' for g in groups) else 'FAIL'
    report={'stage':25,'version':'1.0.0-rc16','checkedAtUtc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'offlineValidation':overall,'validationScope':'FAST_PARTIAL' if a.fast else 'COMPLETE_LOCAL',
            'groups':groups,'officialAsmMavenBuild':'NOT_EXECUTED_IN_THIS_ENVIRONMENT',
            'jdk8_11_17':'NOT_EXECUTED','realSpringBootTomcat':'NOT_EXECUTED',
            'jeusWeblogicAix':'NOT_EXECUTED','stagingReview':'HOLD','productionDeployment':'HOLD'}
    (OUT/'local-gate.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'offlineValidation':overall,'groupsPassed':sum(x['status']=='PASS' for x in groups),
                      'groupCount':len(groups),'stagingReview':'HOLD','productionDeployment':'HOLD'},indent=2))
    return 0 if overall=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
