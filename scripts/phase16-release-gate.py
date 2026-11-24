#!/usr/bin/env python3
"""Phase 16 reproducible verification with truthful, fail-closed release decision.
No local offline result is treated as official ASM/real enterprise WAS certification.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'results' / 'phase16'
OUTPUT.mkdir(parents=True, exist_ok=True)


def run(label, command, timeout=180):
    try:
        p = subprocess.run(command, cwd=str(ROOT), stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=timeout)
        status = 'PASS' if p.returncode == 0 else 'FAIL'
        log = p.stdout
        returncode = p.returncode
    except (subprocess.TimeoutExpired, OSError) as exc:
        status = 'FAIL'
        log = str(exc)
        returncode = -1
    (OUTPUT/(label+'.log')).write_text(log,encoding='utf-8')
    return {'name':label,'status':status,'exitCode':returncode,
            'log':'results/phase16/'+label+'.log'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--official', action='store_true',
                   help='attempt official ASM 9.7.1 Maven build + real execution test')
    args = p.parse_args()
    results=[]
    results.append(run('offline-queue-and-collector', ['sh','scripts/phase16-queue-tests.sh']))
    if results[-1]['status']=='PASS':
        results.append(run('compile-phase15-resilience', ['javac','--release','8',
            '-cp','target/offline-validation/classes','-d','target/offline-validation/classes',
            'src/test/java/com/iruen/runtimesbom/Phase15ResilienceTest.java']))
        if results[-1]['status']=='PASS':
            results.append(run('phase15-http-regression',
                ['java','-cp','target/offline-validation/classes','com.iruen.runtimesbom.Phase15ResilienceTest']))
    results.append(run('jdk21-internal-asm', ['sh','scripts/verify-jdk-asm.sh']))
    if results[-1]['status']=='PASS':
        results.append(run('synthetic-nested-archives',
            ['sh','scripts/verify-nested-archives.sh','jdk-internal']))
    official = 'NOT_RUN'
    if args.official:
        if shutil.which('mvn'):
            result = run('official-asm-build', ['sh','scripts/verify-official-asm.sh'], timeout=240)
            results.append(result)
            official = result['status']
        else:
            official = 'NOT_RUN_MAVEN_MISSING'
    elif not shutil.which('mvn'):
        official = 'NOT_RUN_MAVEN_MISSING'
    report={
      'version':'1.0.0-rc16',
      'dateUtc':datetime.now(timezone.utc).isoformat(),
      'validationEnvironment':'Host JDK; offline transport tests use NON-INSTRUMENTING ASM stub; method execution uses JDK21 INTERNAL ASM.',
      'checks':results,
      'officialAsmBuild':official,
      'jdkRuntimeMatrix':{'8':'NOT_RUN','11':'NOT_RUN','17':'NOT_RUN','21':'INTERNAL_ASM_ONLY'},
      'liveSpringBootTomcat':'NOT_RUN',
      'enterpriseWAS':{'JEUS':'NOT_RUN','WebLogic':'NOT_RUN','AIX':'NOT_RUN'},
      'releaseDecision':'HOLD'
    }
    (OUTPUT/'gate.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'passed':sum(x['status']=='PASS' for x in results),
          'total':len(results),'officialAsmBuild':official,'releaseDecision':'HOLD'},indent=2))
    return 0 if all(x['status']=='PASS' for x in results) else 1


if __name__=='__main__':
    sys.exit(main())
