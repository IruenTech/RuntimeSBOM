#!/usr/bin/env python3
"""Independent deployment inventory cross-check for BOOT-INF/lib and WEB-INF/lib.

Every archive-present component is *potentially loadable* but not necessarily
loaded/executed at runtime. A static-only result is NOT a runtime false negative.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import unquote
from zipfile import ZipFile, BadZipFile

PREFIXES=('BOOT-INF/lib/','WEB-INF/lib/')
MAX_ARCHIVE=512*1024*1024
MAX_INNER=64*1024*1024
MAX_ITEMS=20000


def props(component):
    return {x.get('name'):x.get('value') for x in component.get('properties', []) if isinstance(x, dict)}


def scan_inner(raw):
    if len(raw)>MAX_INNER:raise ValueError('inner JAR exceeds configured size cap')
    with ZipFile(io.BytesIO(raw)) as archive:
        files=[x for x in archive.infolist() if x.filename.startswith('META-INF/maven/') and x.filename.endswith('/pom.properties') and x.file_size<=65536]
        if len(files)>200: return None
        for info in files:
            text=archive.read(info).decode('ISO-8859-1',errors='replace')
            values={}
            for line in text.splitlines():
                line=line.strip()
                if not line or line.startswith(('#','!')):continue
                if '=' in line:
                    k,v=line.split('=',1);values[k.strip()]=v.strip()
            if all(values.get(k) for k in ('groupId','artifactId','version')):
                return 'pkg:maven/{}/{}@{}'.format(values['groupId'],values['artifactId'],values['version'])
    return None


def inventory(archive_path):
    if archive_path.stat().st_size>MAX_ARCHIVE:raise ValueError('outer archive exceeds configured size cap')
    rows=[]
    with ZipFile(archive_path) as z:
        entries=z.infolist()
        if len(entries)>MAX_ITEMS:raise ValueError('archive has too many entries')
        for info in entries:
            if not (info.filename.startswith(PREFIXES) and info.filename.lower().endswith('.jar')):continue
            if info.is_dir() or info.file_size>MAX_INNER:continue
            payload=z.read(info)
            try:purl=scan_inner(payload)
            except (BadZipFile,ValueError,RuntimeError):purl=None
            rows.append({'sourceSuffix':archive_path.name+'!/'+info.filename+'!',
                         'archiveEntry':info.filename,'purl':purl,
                         'sha256':hashlib.sha256(payload).hexdigest(),
                         'packageMetadataDetected':purl is not None})
    return rows


def compare(packaged, sbom):
    if sbom.get('bomFormat')!='CycloneDX':raise ValueError('Invalid CycloneDX input')
    observed=[]
    for c in sbom.get('components',[]):
        p=props(c);source=unquote(str(p.get('runtimeSbom:source','')).replace('\\','/')).rstrip('/')
        digest=next((x.get('content','') for x in c.get('hashes',[]) if x.get('alg')=='SHA-256'),'')
        observed.append({'source':source,'purl':c.get('purl'), 'sha256':digest,
                         'evidence':p.get('runtimeSbom:runtimeEvidenceState')})
    records=[]
    for row in packaged:
        candidates=[c for c in observed if c['source'].endswith(row['sourceSuffix'])]
        exact=[c for c in candidates if c['sha256']==row['sha256'] and c['purl']==row['purl']]
        if exact:
            status='OBSERVED_EXACT_IDENTITY'
        elif candidates:status='OBSERVED_IDENTITY_MISMATCH'
        else:status='PACKAGED_NOT_OBSERVED'
        records.append({**row,'status':status,'observedStates':sorted({c['evidence'] for c in exact if c['evidence']})})
    counts=dict(Counter(r['status'] for r in records))
    return {'schemaVersion':1,'scope':'DEPLOYMENT_PACKAGE_STATIC_INVENTORY_NOT_RUNTIME_GROUND_TRUTH',
            'archiveComponents':len(packaged),'knownMavenCoordinates':sum(bool(x['purl']) for x in packaged),
            'statusCounts':counts,'components':records,
            'interpretation':'PACKAGED_NOT_OBSERVED is not a false negative: the application might never load that JAR.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--sbom',type=Path)
    parser.add_argument('--out',type=Path)
    a=parser.parse_args()
    rows=inventory(a.archive)
    report=compare(rows,json.loads(a.sbom.read_text())) if a.sbom else {
        'schemaVersion':1,'scope':'STATIC_ONLY','archiveComponents':len(rows),'components':rows}
    if a.out:
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='components'},indent=2))

if __name__=='__main__':main()
