#!/usr/bin/env python3
"""Fail-closed release gate for the exact Agent SHA across 4 JDK and 4 WAS runs.

Evidence must be independently retained. Checks prevent accidental mixing of
artifacts and synthetic results; JSON alone is not a signed attestation.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
APPS=('spring-boot2','spring-boot3','tomcat9','tomcat10')
JDKS=(8,11,17,21)


def load_audit():
    spec=importlib.util.spec_from_file_location('phase22_audit',ROOT/'scripts/phase22-binary-audit.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError,UnicodeError):return None


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def validate(agent,jdk_dir,live_dir,build_report=None,max_tps_drop=15.,max_p95_rise=25.):
    agent=Path(agent)
    audit=load_audit().audit(agent)
    sha=audit['sha256']
    build=read_json(build_report) if build_report else None
    build_ok=(isinstance(build,dict) and build.get('status')=='PASS'
              and build.get('artifactSha256')==sha
              and build.get('asmDependency')=='org.ow2.asm:asm:jar:9.7.1'
              and build.get('mavenPackageSucceeded') is True)
    checks={'officialBinaryStructuralAudit':audit['status']=='PASS',
            'mavenBuildEvidence':build_ok}
    why=[]
    if audit['status']!='PASS':why.append('ASM-shaded release JAR structural audit unavailable/failed')
    if not build_ok:why.append('Maven build log/effective ASM dependency proof missing or SHA mismatch')
    jdk_dir=Path(jdk_dir)
    for major in JDKS:
        report=read_json(jdk_dir/f'jdk-{major}.json')
        ok=(isinstance(report,dict) and report.get('status')=='PASS'
            and report.get('evidenceMode')=='OFFICIAL_SHADED_RUNTIME'
            and report.get('officialJarSha256')==sha and report.get('jdkMajor')==major
            and report.get('methodEvidence') is True and report.get('artifactAudit')=='PASS')
        checks[f'jdk{major}']=ok
        if not ok:why.append(f'JDK {major} official same-binary runtime evidence missing/invalid')
    live_dir=Path(live_dir)
    for app in APPS:
        report=read_json(live_dir/app/'phase21-summary.json')
        modes=report.get('httpModes') if isinstance(report,dict) else None
        compare=report.get('comparison') if isinstance(report,dict) else None
        expected=modes.get('asm-traced',{}) if isinstance(modes,dict) else {}
        loaded=modes.get('loaded-only',{}) if isinstance(modes,dict) else {}
        baseline=modes.get('baseline',{}) if isinstance(modes,dict) else {}
        expected=expected if isinstance(expected,dict) else {}
        loaded=loaded if isinstance(loaded,dict) else {}
        baseline=baseline if isinstance(baseline,dict) else {}
        for value in (expected,loaded,baseline):
            if not isinstance(value.get('http'),dict):value['http']={}
            if not isinstance(value.get('evidence'),dict):value['evidence']={}
        good=(isinstance(report,dict) and report.get('status')=='PASS'
              and report.get('application')==app
              and report.get('evidenceMode')=='OFFICIAL_SHADED_RUNTIME'
              and report.get('officialJarSha256')==sha
              and report.get('archiveEvidenceMatches') is True
              and isinstance(report.get('applicationArchiveSha256'),str)
              and len(report['applicationArchiveSha256'])==64
              and isinstance(report.get('embeddedDependencySha256'),str)
              and len(report['embeddedDependencySha256'])==64
              and expected.get('evidence',{}).get('purlFound') is True
              and expected.get('evidence',{}).get('methodExecuted') is True
              and loaded.get('evidence',{}).get('methodExecuted') is False
              and finite(expected.get('http',{}).get('successTps'))
              and expected['http']['successTps']>0
              and finite(baseline.get('http',{}).get('successTps'))
              and baseline['http']['successTps']>0
              and isinstance(compare,dict)
              and finite(compare.get('tpsDeltaPercent'))
              and finite(compare.get('p95DeltaPercent'))
              and compare['tpsDeltaPercent']>=-max_tps_drop
              and compare['p95DeltaPercent']<=max_p95_rise)
        checks[app]=bool(good)
        if not good:why.append(f'{app} live HTTP and independent archive evidence missing/invalid/SLO failed')
    all_ok=all(checks.values())
    return {'schemaVersion':1,'stage':22,'version':'1.0.0-rc16',
            'checkedAtUtc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'officialJarSha256':sha,'checks':checks,'blockingReasons':why,
            'stagingReview':'ELIGIBLE_FOR_HUMAN_REVIEW' if all_ok else 'HOLD',
            'productionDeployment':'HOLD',
            'limitations':['JSON and SHA-256 linkage alone do not cryptographically authenticate a test operator',
                'Valid staged results do not establish JEUS/WebLogic/AIX compatibility',
                'Independent production change review and performance qualification remain required']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--agent',type=Path,default=ROOT/'target/runtime-sbom-agent-1.0.0-rc16.jar')
    p.add_argument('--jdk-dir',type=Path,default=ROOT/'results/phase22/jdk')
    p.add_argument('--live-dir',type=Path,default=ROOT/'results/phase22/live')
    p.add_argument('--build-evidence',type=Path,default=ROOT/'results/phase22/build.json')
    p.add_argument('--out',type=Path,default=ROOT/'results/phase22/release-gate.json')
    p.add_argument('--max-tps-drop',type=float,default=15.)
    p.add_argument('--max-p95-rise',type=float,default=25.)
    a=p.parse_args()
    if not(0<=a.max_tps_drop<=100 and 0<=a.max_p95_rise<=1000):p.error('invalid SLO bound')
    result=validate(a.agent,a.jdk_dir,a.live_dir,a.build_evidence,a.max_tps_drop,a.max_p95_rise)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'stagingReview':result['stagingReview'],
                      'productionDeployment':'HOLD',
                      'passed':sum(result['checks'].values()),
                      'required':len(result['checks']),
                      'blockingReasons':result['blockingReasons']},ensure_ascii=False,indent=2))
    return 0 if result['stagingReview']=='ELIGIBLE_FOR_HUMAN_REVIEW' else 3

if __name__=='__main__':sys.exit(main())
