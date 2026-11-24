#!/usr/bin/env python3
"""Fail-closed RC9 evidence gate.

No test files -> HOLD. A passing synthetic/JDK-internal ASM smoke is NOT
accepted as official or real WAS evidence. Passing this gate only permits a
human staging review; it never authorizes production deployment.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from importlib.machinery import SourceFileLoader

ROOT=Path(__file__).resolve().parent.parent
APPS=('spring-boot2','spring-boot3','tomcat9','tomcat10')
JDKS=(8,11,17,21)


def read_json(path):
    if not path.is_file():return None
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (ValueError,OSError):return None


def accept(artifact, jdk_dir, live_dir, max_tps_regression=15.0, max_p95_increase=25.0):
    jar=Path(artifact)
    audit=SourceFileLoader('phase18_audit',str(ROOT/'scripts/phase18-audit-jar.py')).load_module().audit(jar)
    expected=audit.get('sha256')
    checks={'binaryAudit':audit['status']}
    why=[]
    if audit['status']!='PASS':why.append('Official shaded JAR structural audit missing/failed')
    for jdk in (8,11,17,21):
        item=read_json(Path(jdk_dir)/('jdk-%d.json'%jdk))
        ok=(bool(item) and item.get('status')=='PASS'
            and item.get('evidenceMode')=='OFFICIAL_SHADED_RUNTIME'
            and item.get('jdkMajor')==jdk and item.get('officialJarSha256')==expected
            and item.get('methodEvidence') is True and item.get('artifactAudit')=='PASS')
        checks['jdk-%d'%jdk]='PASS' if ok else 'MISSING_OR_INVALID'
        if not ok: why.append('Missing JDK %d execution evidence for the exact release binary'%jdk)
    for app in APPS:
        item=read_json(Path(live_dir)/app/'summary.json')
        modes=item.get('modes',{}) if isinstance(item,dict) else {}
        asm=modes.get('asm-traced',{})
        baseline=modes.get('baseline',{})
        http=asm.get('http',{})
        baseline_http=baseline.get('http',{})
        observed=asm.get('evidence',{})
        cmp=item.get('comparison',{}) if isinstance(item,dict) else {}
        ok=(bool(item) and item.get('application')==app and item.get('status')=='PASS'
            and item.get('evidenceType')=='actual-live-was'
            and item.get('evidenceMode')=='OFFICIAL_SHADED_RUNTIME'
            and item.get('officialJarSha256')==expected
            and observed.get('purlFound') is True and observed.get('methodExecuted') is True
            and isinstance(http.get('successTps'),(int,float)) and http['successTps']>0
            and isinstance(baseline_http.get('successTps'),(int,float)) and baseline_http['successTps']>0
            and isinstance(cmp.get('tpsDeltaPercent'),(int,float))
            and isinstance(cmp.get('p95DeltaPercent'),(int,float))
            and cmp['tpsDeltaPercent']>=-max_tps_regression
            and cmp['p95DeltaPercent']<=max_p95_increase)
        checks[app]='PASS' if ok else 'MISSING_INVALID_OR_SLO_FAIL'
        if not ok:why.append('Missing actual live WAS evidence / unacceptable performance for '+app)
    complete=all(x=='PASS' for x in checks.values())
    return {'schemaVersion':1,'stage':'18','timestampUtc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'releaseVersion':'1.0.0-rc16','officialJarSha256':expected,
            'checks':checks,'blockingReasons':why,
            'stagingReview':'ELIGIBLE_FOR_HUMAN_REVIEW' if complete else 'HOLD',
            'productionDeployment':'HOLD',
            'caveat':'JSON evidence is operator-supplied and not cryptographically attested; independent review and vendor testing remain mandatory.'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--agent',default=str(ROOT/'target/runtime-sbom-agent-1.0.0-rc16.jar'))
    p.add_argument('--jdk-dir',default=str(ROOT/'results/phase18/jdk-matrix'))
    p.add_argument('--live-dir',default=str(ROOT/'results/phase18/live'))
    p.add_argument('--out',default=str(ROOT/'results/phase18/acceptance.json'))
    p.add_argument('--max-tps-regression',type=float,default=15.)
    p.add_argument('--max-p95-increase',type=float,default=25.)
    a=p.parse_args()
    if not (0<=a.max_tps_regression<=100 and 0<=a.max_p95_increase<=1000):p.error('invalid SLO limits')
    report=accept(a.agent,a.jdk_dir,a.live_dir,a.max_tps_regression,a.max_p95_increase)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'stagingReview':report['stagingReview'],'productionDeployment':'HOLD',
                      'passes':sum(v=='PASS' for v in report['checks'].values()),
                      'required':len(report['checks']),'report':str(out)},indent=2))
    return 0 if report['stagingReview']=='ELIGIBLE_FOR_HUMAN_REVIEW' else 3

if __name__=='__main__':raise SystemExit(main())
