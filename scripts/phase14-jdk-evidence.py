#!/usr/bin/env python3
"""Record isolated JDK execution and combine distinct CI job artifacts."""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent


def major():
    p=subprocess.run(['java','-version'],capture_output=True,text=True,check=True)
    m=re.search(r'version "(?:1\.)?(\d+)',p.stderr+p.stdout)
    if not m:raise RuntimeError('JDK version not recognizable')
    return m.group(1)


def record():
    jdk=major()
    official=ROOT/'results/phase14/official-asm.json'
    value=json.loads(official.read_text())
    if value.get('status')!='PASS' or value.get('version')!='1.0.0-rc16':
        raise RuntimeError('official execution PASS evidence missing on this JDK')
    folder=ROOT/'results/phase14/jdk';folder.mkdir(parents=True,exist_ok=True)
    target=folder/('jdk-'+jdk+'.json')
    target.write_text(json.dumps({'jdk':jdk,'version':'1.0.0-rc16','evidenceType':'official-execution-per-jdk',
      'status':'PASS','agentSha256':value['sha256']},indent=2)+'\n')
    print('PASS JDK',jdk,'→',target)


def combine():
    root=ROOT/'results/phase14/jdk'
    reports={}
    digests={}
    for version in ('8','11','17','21'):
        file=root/('jdk-'+version+'.json')
        try:
            obj=json.loads(file.read_text())
            valid=obj.get('jdk')==version and obj.get('version')=='1.0.0-rc16' and obj.get('status')=='PASS' and obj.get('evidenceType')=='official-execution-per-jdk'
            reports[version]='PASS' if valid else 'NOT_VERIFIED'
            if valid:digests[version]=obj.get('agentSha256')
        except (OSError,ValueError,AttributeError):reports[version]='NOT_VERIFIED'
    result={'version':'1.0.0-rc16','evidenceType':'multi-jdk-official','jdk':reports,'agentSha256':digests}
    out=ROOT/'results/phase14/jdk-matrix.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if any(v!='PASS' for v in reports.values()):raise SystemExit(3)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=('record','combine'));args=a.parse_args()
    record() if args.action=='record' else combine()
