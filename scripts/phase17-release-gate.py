#!/usr/bin/env python3
"""Phase17 gates: run fresh checks; never infer vendor compatibility from synthetic loaders.

Default checks run on JDK21; official mode explicitly requires Maven/ASM dependencies.
A passing *offline* suite never changes the production decision from HOLD.
"""
import argparse
import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'results/phase17'


def run(name, argv, timeout=160):
    try:
        result = subprocess.run(argv, cwd=str(ROOT), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors='replace', timeout=timeout)
        status = 'PASS' if result.returncode == 0 else 'FAIL'
        content = result.stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        status = 'FAIL'; content = repr(exc)
    (OUTPUT / (name + '.log')).write_text(content, encoding='utf-8')
    return {'check':name, 'status':status, 'log':'results/phase17/'+name+'.log', 'command':argv}


def decide(checks, official, vendor, real_was):
    """No count of offline passes implies a vendor JVM production approval."""
    complete = bool(checks) and all(x['status']=='PASS' for x in checks)
    return {
      'offlineValidation':'PASS' if complete else 'FAIL',
      'officialAsmBuild': official,
      'jdk8_11_17_21': 'NOT_VERIFIED',
      'liveTomcatSpringBoot': real_was,
      'enterpriseWAS':vendor,
      'stagingReview':'REQUEST_REVIEW' if complete and official=='PASS' else 'HOLD',
      'productionDeployment':'HOLD',
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--official',action='store_true', help='attempt official ASM Maven build and execution')
    args=parser.parse_args()
    OUTPUT.mkdir(parents=True,exist_ok=True)
    checks=[run('jdk21-internal-asm', ['sh','scripts/verify-jdk-asm.sh']),
            run('multi-app-classloaders', ['sh','scripts/phase17-loader-test.sh','jdk-internal']),
            run('nested-jar-war', ['sh','scripts/verify-nested-archives.sh','jdk-internal']),
            run('persistent-delivery-collector', ['sh','scripts/phase16-queue-tests.sh']),
            run('phase17-validator-regressions', ['python3','-m','unittest','discover','-s','tests','-p','test_phase17_*.py','-v']),
            run('shutdown-drain-race', ['sh','scripts/phase17-shutdown-race.sh'])]
    official='NOT_RUN'
    if args.official:
        if shutil.which('mvn'):
            verify=run('official-asm-build-and-smoke', ['sh','scripts/verify-official-asm.sh'], timeout=240)
            checks.append(verify)
            if verify['status']=='PASS':
                isolated=run('official-asm-multiloader', ['sh','scripts/phase17-loader-test.sh','official'])
                checks.append(isolated)
                official='PASS' if isolated['status']=='PASS' else 'FAIL'
            else:official='FAIL'
        else: official='MAVEN_UNAVAILABLE'
    decision=decide(checks,official,{'JEUS':'NOT_RUN','WebLogic':'NOT_RUN','IBM_AIX':'NOT_RUN'},'NOT_RUN')
    report={'schemaVersion':1,'version':'1.0.0-rc16',
            'utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'verificationMode':'OFFLINE_WITH_JDK_INTERNAL_ASM'+('_PLUS_OFFICIAL_ATTEMPT' if args.official else ''),
            'environmentLimitations':[
                'The internal ASM test jar is NOT a distributable official ASM binary.',
                'A simulated custom class loader is not a real JEUS/WebLogic class loader.',
                'Only Java 21 runtime is available locally; Java 8/11/17 are unverified.',
                'Production rollout is not approved without official ASM, real WAS, and vendor JVM evidence.'
            ],'checks':checks,**decision}
    (OUTPUT/'gate.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':sum(x['status']=='PASS' for x in checks),
                      'officialAsmBuild':official,'offlineValidation':decision['offlineValidation'],
                      'productionDeployment':'HOLD'},indent=2))
    return 0 if all(x['status']=='PASS' for x in checks) else 1


if __name__=='__main__': raise SystemExit(main())
