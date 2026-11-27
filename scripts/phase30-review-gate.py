#!/usr/bin/env python3
"""Fail-closed Phase30 human review gate. NEVER approves production deployment."""
import argparse
import json
import os
import sys
from pathlib import Path

APPS=('tomcat9','tomcat10')

def decision(phase29,retention,expected_sha, min_cycles=6):
    failures=[]
    if not isinstance(expected_sha,str) or len(expected_sha)!=64:
        failures.append('OFFICIAL_BINARY_SHA_MISSING')
    if not isinstance(phase29,dict) or phase29.get('stagingReview')!='ELIGIBLE_FOR_HUMAN_REVIEW' or phase29.get('agentSha256')!=expected_sha:
        failures.append('PHASE29_REVIEW_NOT_VERIFIED_FOR_THIS_BINARY')
    for app in APPS:
        item=retention.get(app)
        if not isinstance(item,dict):
            failures.append('MISSING_'+app.upper());continue
        if item.get('status')!='PASS' or item.get('agentSha256')!=expected_sha:
            failures.append('INVALID_'+app.upper());continue
        samples=item.get('snapshots',[])
        if item.get('cyclesCompleted',0)<min_cycles or len(samples)!=item.get('cyclesCompleted'):
            failures.append('INSUFFICIENT_CYCLES_'+app.upper());continue
        if any(not s.get('newLoaderIds') or s.get('methodEntriesForNewLoader',0)<1 for s in samples):
            failures.append('LOADER_OR_METHOD_EVIDENCE_INCOMPLETE_'+app.upper())
        if any(s.get('gcCommandSucceeded') is not True for s in samples):
            failures.append('GC_COMMAND_EVIDENCE_MISSING_'+app.upper())
        if any(s.get('reachableWebappClassLoaderInstances')!=1 for s in samples):
            failures.append('GC_REACHABILITY_NOT_ESTABLISHED_'+app.upper())
        if any(s.get('metaspaceCommittedKiB') is None for s in samples):
            failures.append('METASPACE_DATA_MISSING_'+app.upper())
        if item.get('failures'):
            failures.append('PROBE_REPORTED_FAILURE_'+app.upper())
    return {'phase':30,'stagingReview':'HOLD' if failures else 'ELIGIBLE_FOR_HUMAN_REVIEW',
            'productionDeployment':'HOLD','agentSha256':expected_sha,'failures':failures,
            'note':'Jcmd snapshots only; no guarantee of leak-free operation or production readiness'}

def load(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return None

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase29-review',type=Path,required=True)
    p.add_argument('--tomcat-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--min-cycles',type=int,default=6)
    a=p.parse_args()
    inputs={app:load(a.tomcat_dir/('phase30-'+app+'-retention')/'retention.json') for app in APPS}
    result=decision(load(a.phase29_review),inputs,os.environ.get('RUNTIMESBOM_EXPECTED_SHA256'),a.min_cycles)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('PHASE30 REVIEW:',result['stagingReview'],'PRODUCTION HOLD',flush=True)
    if result['failures']:print('BLOCKERS:',result['failures'],file=sys.stderr)
    return 0 if not result['failures'] else 1

if __name__=='__main__':raise SystemExit(main())
