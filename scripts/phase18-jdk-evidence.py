#!/usr/bin/env python3
"""Records tested JDK and exact official binary SHA-256, after live smoke checks succeed."""
import argparse, hashlib, json, re, subprocess, datetime
from pathlib import Path
from importlib.machinery import SourceFileLoader
ROOT=Path(__file__).resolve().parent.parent

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--jar',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if not (ROOT/'target/phase18-official-verification/sbom.json').exists(): p.error('official smoke SBOM missing')
    ver=subprocess.run(['java','-version'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,check=True).stdout
    m=re.search(r'version "(?:1\.)?(\d+)',ver)
    if not m: p.error('cannot identify Java version')
    major=int(m.group(1))
    if major not in (8,11,17,21):p.error('unsupported JDK for acceptance matrix')
    audit_script=SourceFileLoader('audit_phase18',str(ROOT/'scripts/phase18-audit-jar.py')).load_module()
    audit=audit_script.audit(a.jar)
    if audit['status']!='PASS':p.error('official agent audit did not pass')
    bom=json.loads((ROOT/'target/phase18-official-verification/sbom.json').read_text())
    if bom.get('bomFormat')!='CycloneDX':p.error('SBOM missing or invalid')
    found=any(x.get('name','').startswith('runtimeSbom:methodEntry:') and int(x.get('value','0'))>0
            for x in bom.get('metadata',{}).get('properties',[]))
    if not found:p.error('method entry evidence missing')
    report={'schemaVersion':1,'status':'PASS','evidenceMode':'OFFICIAL_SHADED_RUNTIME',
            'timestampUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'jdkMajor':major,'officialJarSha256':audit['sha256'],
            'methodEvidence':True,'artifactAudit':'PASS'}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
