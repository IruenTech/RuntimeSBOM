#!/usr/bin/env python3
"""Repeatable local verification only. Never converts a JDK-internal ASM run into release approval."""
from __future__ import annotations
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'results/phase23'

def call(label,cmd,timeout=100,expected=0):
    OUT.mkdir(parents=True,exist_ok=True)
    log=OUT/(label+'.log')
    with log.open('w',encoding='utf-8') as f:
        try:
            p=subprocess.Popen(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            try:rc=p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL);p.wait();rc=-9
        except OSError as exc:
            f.write(repr(exc)+'\n');rc=-2
    return {'name':label,'result':'PASS' if rc==expected else 'FAIL','exitCode':rc,'expectedExitCode':expected,
            'log':str(log.relative_to(ROOT))}

def main():
    checks=[]
    checks.append(call('quality-java-python-asm',['sh','scripts/phase23-quality-regression.sh'],100))
    checks.append(call('classloader-3-instances',['sh','scripts/phase17-loader-test.sh','jdk-internal'],50))
    checks.append(call('classloader-diagnostic',[sys.executable,'scripts/phase23-sbom-quality.py',
         'target/phase17-loader/loader-sbom.json','--out','results/phase23/loader-observability.json'],15))
    checks.append(call('http-loading-vs-execution',[sys.executable,'scripts/phase21-http-provenance.py',
         '--mode','jdk-internal','--requests','40','--concurrency','5','--out-dir','results/phase23/http'],100))
    checks.append(call('http-loading-quality',[sys.executable,'scripts/phase23-sbom-quality.py',
         'results/phase23/http/loaded-only/sbom.json','--out','results/phase23/loaded-quality.json'],15))
    checks.append(call('http-execution-quality',[sys.executable,'scripts/phase23-sbom-quality.py',
         'results/phase23/http/asm-traced/sbom.json','--require-method',
         '--out','results/phase23/traced-quality.json'],15))
    checks.append(call('collector-regression',[sys.executable,'-m','unittest','discover',
         '-s','collector/tests','-p','test_*.py','-v'],100))
    checks.append(call('legacy-exact-binary-negative-tests',[sys.executable,'-m','unittest','discover',
         '-s','tests','-p','test_phase22_*.py','-v'],60))
    checks.append(call('official-gate-expected-hold',[sys.executable,'scripts/phase23-staging-gate.py'],15,3))
    try:
        gate=json.loads((OUT/'staging-gate.json').read_text())
        if gate.get('stagingReview')!='HOLD' or gate.get('productionDeployment')!='HOLD':
            checks[-1]['result']='FAIL'
    except (OSError,ValueError):checks[-1]['result']='FAIL'
    verdict='PASS' if all(x['result']=='PASS' for x in checks) else 'FAIL'
    report={'stage':23,'version':'1.0.0-rc16','checkedAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'offlineValidation':verdict,'groups':checks,'officialAsmBuild':'NOT_RUN_MAVEN_UNAVAILABLE_DNS_FAILURE',
            'actualSpringBootTomcat':'NOT_RUN_PREREQUISITES_UNAVAILABLE',
            'jdk8_11_17_21':'NOT_RUN_ONLY_JDK21_INSTALLED',
            'jeusWeblogicAix':'NOT_RUN_VENDOR_INSTALLATIONS_UNAVAILABLE',
            'internalAsmJdk21':'TEST_ONLY_NOT_DISTRIBUTABLE',
            'stagingReview':'HOLD','productionDeployment':'HOLD'}
    (OUT/'local-gate.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'offlineValidation':verdict,'passedGroups':sum(x['result']=='PASS' for x in checks),
                      'groups':len(checks),'stagingReview':'HOLD','productionDeployment':'HOLD'},indent=2))
    return 0 if verdict=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
