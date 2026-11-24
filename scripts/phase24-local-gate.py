#!/usr/bin/env python3
"""Offline verification with intentionally expected HOLD for official distribution.
Produces a truthful reproducible report instead of silently substituting JDK ASM.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'results/phase24'

def run(label,args,timeout=180,expect=0):
    start=time.monotonic()
    try:
        p=subprocess.run(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                         text=True,timeout=timeout)
        rc=p.returncode; content=p.stdout
    except subprocess.TimeoutExpired as exc:
        rc=124
        content='Timed out after %ds; test not counted as pass\n'%timeout
    except OSError as exc:
        rc=127;content=repr(exc)
    (OUT/(label+'.log')).write_text(content,encoding='utf-8')
    return {'name':label,'status':'PASS' if rc==expect else 'FAIL',
            'exitCode':rc,'expectedExit':expect,'elapsedSeconds':round(time.monotonic()-start,2),
            'log':'results/phase24/'+label+'.log'}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--skip-legacy',action='store_true',help='Fast local tests; does not rerun phase23 collector/ASM/HTTP tests')
    a=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    tasks=[]
    if not a.skip_legacy:
        tasks.append(run('phase23-regression',[sys.executable,'scripts/phase23-local-gate.py'],300))
        try:
            old=json.loads((ROOT/'results/phase23/local-gate.json').read_text())
            if old.get('offlineValidation')!='PASS':tasks[-1]['status']='FAIL'
        except (OSError,ValueError):tasks[-1]['status']='FAIL'
    tasks.append(run('new-24-unit-tests',[sys.executable,'-m','unittest','discover','-s','tests',
                                            '-p','test_phase24_*.py','-v'],45))
    tasks.append(run('workflow-contract',[sys.executable,'scripts/phase24-ci-contract.py'],15))
    tasks.append(run('official-preflight-expected-hold',[sys.executable,'scripts/phase24-check-binary.py'],20,3))
    tasks.append(run('official-manifest-expected-hold',[sys.executable,'scripts/phase24-staging-manifest.py'],20,3))
    def outcome(file,key):
        try:return json.loads((ROOT/file).read_text()).get(key)
        except (OSError,ValueError):return None
    if outcome('results/phase24/binary-preflight.json','status')!='HOLD':tasks[-2]['status']='FAIL'
    if outcome('results/phase24/staging-manifest.json','stagingReview')!='HOLD':tasks[-1]['status']='FAIL'
    verdict='PASS' if all(x['status']=='PASS' for x in tasks) else 'FAIL'
    result={'stage':24,'version':'1.0.0-rc16','checkedAtUtc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'offlineValidation':verdict,'groups':tasks,
            'sdk':'JDK 21 test-only internal ASM; Java 8 target bytecode',
            'mavenOfficialAsmBuild':'NOT_EXECUTED_MAVEN_AND_NETWORK_UNAVAILABLE',
            'liveSpringBootTomcat':'NOT_EXECUTED_OFFICIAL_AGENT_UNAVAILABLE',
            'liveJeusWeblogicAix':'NOT_EXECUTED_VENDOR_ENVIRONMENT_UNAVAILABLE',
            'githubActions':'CONFIGURED_NOT_EXECUTED_IN_THIS_CONTAINER',
            'stagingReview':'HOLD','productionDeployment':'HOLD'}
    (OUT/'local-gate.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'stage':24,'offlineValidation':verdict,'groupsPassed':sum(x['status']=='PASS' for x in tasks),
                      'groupCount':len(tasks),'stagingReview':'HOLD','productionDeployment':'HOLD'},indent=2))
    return 0 if verdict=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
