#!/usr/bin/env python3
"""Fail-closed cross-job staging report gate; never authorizes production deployment."""
import argparse
import json
import sys
from pathlib import Path
SHA='ed5613c7d515d877b57bb6844ddb4bb66c919af74648ac10bb9960d99e406f4a'
APPS=('spring-boot2','spring-boot3','tomcat9','tomcat10')


def verify(local_report, lives):
    failures=[]
    if not isinstance(local_report,dict) or local_report.get('phase')!=29 or local_report.get('status')!='PASS':
        failures.append('LOCAL_GATE_MISSING_OR_FAILED')
    else:
        checks=local_report.get('checks',[])
        wanted={'phase29_unit_tests','phase29_outage_backlog_replay','phase29_windowed_http','collector_regression'}
        if set(x.get('name') for x in checks)!=wanted or not all(x.get('status')=='PASS' for x in checks):
            failures.append('LOCAL_CHECKS_INCOMPLETE')
    for app in APPS:
        d=lives.get(app)
        if not isinstance(d,dict):
            failures.append('MISSING_%s'%app);continue
        if d.get('app')!=app or d.get('stage')!=29 or d.get('agentSha256')!=SHA or d.get('status')!='PASS':
            failures.append('INVALID_%s'%app);continue
        cycles=d.get('cycles',[])
        if not isinstance(cycles,list) or len(cycles)!=2:
            failures.append('MISSING_CYCLES_%s'%app);continue
        for i,cycle in enumerate(cycles):
            if not isinstance(cycle,dict) or not cycle.get('executionEvidence'):
                failures.append('MISSING_METHOD_EVIDENCE_%s_%d'%(app,i+1));break
            if not any(v.get('purl')=='pkg:maven/org.apache.commons/commons-lang3@3.14.0'
                       and v.get('observedMethodEntries',0)>0 and v.get('sha256')
                       for v in cycle['executionEvidence']):
                failures.append('INVALID_PROVENANCE_%s_%d'%(app,i+1));break
        if app.startswith('tomcat') and not cycles[-1].get('newLoaderIds'):
            failures.append('NO_NEW_CLASSLOADER_%s'%app)
        if app.startswith('spring') and (not cycles[0].get('pid') or not cycles[1].get('pid') or cycles[0]['pid']==cycles[1]['pid']):
            failures.append('NO_JVM_RESTART_%s'%app)
    return {'stage':29,'agentSha256':SHA,'stagingReview':'HOLD' if failures else 'ELIGIBLE_FOR_HUMAN_REVIEW',
            'productionDeployment':'HOLD','failures':failures,'requiredApps':list(APPS),
            'note':'Even ELIGIBLE_FOR_HUMAN_REVIEW requires site-specific production approval'}


def load(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return None


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--local-gate',type=Path,required=True)
    ap.add_argument('--live-dir',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args()
    inputs={app:load(a.live_dir/('phase29-real-was-'+app)/'lifecycle.json') for app in APPS}
    result=verify(load(a.local_gate),inputs)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('PHASE29 REVIEW:',result['stagingReview'],'PRODUCTION HOLD',flush=True)
    if result['failures']:print('FAILURES:',', '.join(result['failures']),file=sys.stderr)
    return 0 if not result['failures'] else 1

if __name__=='__main__':sys.exit(main())
