#!/usr/bin/env python3
"""Consolidate *actual* exact-binary staging evidence. Always fail closed."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

def read(path):
    try:
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else None
    except (OSError,ValueError,UnicodeError):return None

def evaluate(manifest,diagnostic=None,required_jobs=None):
    reasons=[]
    if not isinstance(manifest,dict):reasons.append('Exact-binary staging evidence manifest missing')
    elif manifest.get('stagingReview')!='ELIGIBLE_FOR_HUMAN_REVIEW':
        reasons.extend(manifest.get('blockingReasons',[])[:15])
        if not reasons:reasons.append('Staging verification was not eligible')
    if diagnostic and isinstance(diagnostic,dict):
        for item in diagnostic.get('inputs',[]):
            for detail in item.get('diagnoses',[]):reasons.append(detail['code']+': '+detail['recommendedAction'])
    if required_jobs is not None:
        for name in ('official-build','boot2-build-isolation','jdk-matrix','was-matrix'):
            result=required_jobs.get(name,{}).get('result') if isinstance(required_jobs,dict) else None
            if result!='success':reasons.append('Phase26 required job '+name+' not successful: '+str(result))
    eligible=bool(isinstance(manifest,dict) and manifest.get('stagingReview')=='ELIGIBLE_FOR_HUMAN_REVIEW' and not reasons)
    return {'stage':25,'version':'1.0.0-rc16','checkedAtUtc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'stagingReview':'ELIGIBLE_FOR_HUMAN_REVIEW' if eligible else 'HOLD',
            'productionDeployment':'HOLD','officialAgentSha256':manifest.get('officialJarSha256') if isinstance(manifest,dict) else None,
            'blockingReasons':reasons, 'nextAction':'Human approval and JEUS/WebLogic/AIX staging tests required' if eligible else 'Resolve diagnostics and collect real official build/JDK/WAS evidence',
            'note':'No automatic deployment is authorized by this result'}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--manifest',type=Path,default=ROOT/'results/phase24/staging-manifest.json')
    p.add_argument('--diagnostics',type=Path,default=ROOT/'results/phase25/ci-diagnostics.json')
    p.add_argument('--out',type=Path,default=ROOT/'results/phase25/release-review.json')
    a=p.parse_args()
    required_jobs=None
    if 'PHASE26_REQUIRED_JOBS' in os.environ:
        try:required_jobs=json.loads(os.environ['PHASE26_REQUIRED_JOBS'])
        except (ValueError,TypeError):required_jobs={}
    r=evaluate(read(a.manifest),read(a.diagnostics),required_jobs)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'stagingReview':r['stagingReview'],'productionDeployment':'HOLD','blockingReasons':r['blockingReasons'][:4]},indent=2,ensure_ascii=False))
    return 0 if r['stagingReview']=='ELIGIBLE_FOR_HUMAN_REVIEW' else 3

if __name__=='__main__':raise SystemExit(main())
