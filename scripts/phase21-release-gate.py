#!/usr/bin/env python3
"""Fail-closed Phase21 release gate: fixture pass != official WAS approval.

PASS on local fixtures is never sufficient; requires the exact same official
shaded Agent SHA-256 in independent JDK/WAS evidence and archive cross-checks.
Even success is ELIGIBLE_FOR_STAGING_REVIEW, never production approval.
"""
from __future__ import annotations
import argparse
import importlib.util
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
APPS=('spring-boot2','spring-boot3','tomcat9','tomcat10')
JDKS=(8,11,17,21)


def import_script(filename,name):
    s=importlib.util.spec_from_file_location(name,ROOT/'scripts'/filename)
    m=importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def load(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (ValueError,OSError):return None


def evaluate(agent,jdk_dir,live_dir,fixture_path):
    agent=Path(agent)
    audit=import_script('phase18-audit-jar.py','phase21audit').audit(agent)
    sha=audit.get('sha256')
    fixture=load(fixture_path)
    checks={}
    checks['localHttpProvenanceFixture']=bool(fixture and fixture.get('status')=='PASS'
        and fixture.get('realTomcatSpringBootTest') is False
        and fixture.get('samePurlDifferentJarSha256') is True
        and all(fixture.get('results',{}).get(mode,{}).get('truePositives')==3
                and fixture['results'][mode].get('falsePositives')==0
                and fixture['results'][mode].get('falseNegatives')==0
                for mode in ('loaded-only','asm-traced')))
    checks['officialShadedJarAudit']=audit.get('status')=='PASS'
    for jdk in JDKS:
        ev=load(Path(jdk_dir)/f'jdk-{jdk}.json')
        checks[f'jdk{jdk}']=bool(ev and ev.get('status')=='PASS'
            and ev.get('evidenceMode')=='OFFICIAL_SHADED_RUNTIME'
            and ev.get('officialJarSha256')==sha
            and ev.get('jdkMajor')==jdk and ev.get('methodEvidence') is True
            and ev.get('artifactAudit')=='PASS')
    for app in APPS:
        ev=load(Path(live_dir)/app/'phase21-summary.json')
        checks[app]=bool(ev and ev.get('status')=='PASS'
            and ev.get('evidenceMode')=='OFFICIAL_SHADED_RUNTIME'
            and ev.get('officialJarSha256')==sha
            and ev.get('archiveEvidenceMatches') is True
            and len(str(ev.get('embeddedDependencySha256','')))==64
            and ev.get('humanProductionApproval')=='REQUIRED')
    passed=[name for name,ok in checks.items() if ok]
    blockers=[name for name,ok in checks.items() if not ok]
    review='ELIGIBLE_FOR_STAGING_REVIEW' if not blockers else 'HOLD'
    return {'schemaVersion':1,'stage':21,'releaseVersion':'1.0.0-rc16',
            'officialJarSha256':sha,'checks':{k:('PASS' if v else 'MISSING_OR_INVALID') for k,v in checks.items()},
            'successfulChecks':len(passed),'requiredChecks':len(checks),
            'blockingReasons':blockers,'stagingReview':review,
            'productionDeployment':'HOLD',
            'limitations':['Field evidence files are not cryptographically attested; independent operator review required.',
                           'JEUS, WebLogic and AIX need separate real-environment tests.',
                           'Passing this gate cannot by itself authorize production use.']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--agent',type=Path,default=ROOT/'target/runtime-sbom-agent-1.0.0-rc16.jar')
    p.add_argument('--jdk-dir',type=Path,default=ROOT/'results/phase21/jdk')
    p.add_argument('--live-dir',type=Path,default=ROOT/'results/phase21/live')
    p.add_argument('--fixture',type=Path,default=ROOT/'results/phase21/http-provenance/summary.json')
    p.add_argument('--out',type=Path,default=ROOT/'results/phase21/release-gate.json')
    p.add_argument('--strict',action='store_true')
    args=p.parse_args()
    report=evaluate(args.agent,args.jdk_dir,args.live_dir,args.fixture)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'stagingReview':report['stagingReview'],'productionDeployment':'HOLD',
                      'successfulChecks':report['successfulChecks'],'requiredChecks':report['requiredChecks'],
                      'blockingReasons':report['blockingReasons']},indent=2))
    return 3 if args.strict and report['stagingReview']=='HOLD' else 0

if __name__=='__main__':raise SystemExit(main())
