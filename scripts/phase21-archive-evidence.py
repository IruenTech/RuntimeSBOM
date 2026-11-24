#!/usr/bin/env python3
"""Validate runtime OSS identity against independently packaged JAR/WAR bytes.

This validator does not query a live server, nor does its PASS constitute proof
that the agent was built using official ASM. It checks evidence after a real
Spring Boot/Tomcat test; inputs must be retained for independent review.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, BadZipFile

PURL='pkg:maven/org.apache.commons/commons-lang3@3.14.0'
LIB='commons-lang3-3.14.0.jar'


def sha256(b):return hashlib.sha256(b).hexdigest()


def properties(c):
    result={}
    for p in c.get('properties',[]):
        if isinstance(p,dict) and p.get('name'):
            result[str(p['name'])]=p.get('value')
    return result


def hash_value(c):
    for h in c.get('hashes',[]):
        if h.get('alg')=='SHA-256':return str(h.get('content','')).lower()
    return ''


def expected_from_archive(archive):
    archive=Path(archive)
    with ZipFile(archive) as zipfile:
        # Constrain to actual dependency lib directories; ignore arbitrary embedded matches.
        candidates=[n for n in zipfile.namelist() if n in (
            'BOOT-INF/lib/'+LIB, 'WEB-INF/lib/'+LIB)]
        if len(candidates)!=1:
            raise ValueError('expected exactly one vendored commons-lang3-3.14.0.jar, found '+str(len(candidates)))
        record=zipfile.getinfo(candidates[0])
        if record.file_size>64*1024*1024:raise ValueError('dependency unexpectedly large')
        dependency=zipfile.read(candidates[0])
        return {'archiveName':archive.name,'archiveSha256':sha256(archive.read_bytes()),
                'dependencyPath':candidates[0],'dependencySha256':sha256(dependency),
                'dependencyBytes':len(dependency),'purl':PURL}


def verify(archive,sbom,mode='asm-traced'):
    if mode not in ('asm-traced','loaded-only'):
        raise ValueError('mode must be asm-traced or loaded-only')
    expected=expected_from_archive(archive)
    if sbom.get('bomFormat')!='CycloneDX' or sbom.get('specVersion')!='1.6':
        raise ValueError('invalid CycloneDX 1.6 input')
    components=[c for c in sbom.get('components',[]) if c.get('purl')==PURL]
    matches=[]
    for c in components:
        p=properties(c)
        src=str(p.get('runtimeSbom:source','')).replace('\\','/')
        if hash_value(c)!=expected['dependencySha256'] or LIB not in src:continue
        try:count=int(p.get('runtimeSbom:observedMethodEntryCount','-1'))
        except (ValueError,TypeError):count=-1
        matches.append({'name':c.get('name'),'source':src,'sha256':hash_value(c),
                        'loader':p.get('runtimeSbom:classLoader'),
                        'evidenceState':p.get('runtimeSbom:runtimeEvidenceState'),
                        'methodEntries':count})
    checks={
      'exactDependencyHashMatch':len(matches)==1,
      'sourceCarriesDependencyPath':len(matches)==1 and LIB in matches[0]['source'],
      'classLoaderTokenPresent':len(matches)==1 and bool(matches[0]['loader']),
      'noMismatchedPurlInstances':len(components)==len(matches),
      'executionStateCorrect': len(matches)==1 and (
          matches[0]['evidenceState']=='METHOD_EXECUTED' and matches[0]['methodEntries']>0
          if mode=='asm-traced' else
          matches[0]['evidenceState']=='CLASS_LOADED' and matches[0]['methodEntries']==0
      )}
    # If loading-only mode is active, no component is allowed to claim execution.
    if mode=='loaded-only':
        checks['noOtherMethodExecutedClaims']=all(
            properties(c).get('runtimeSbom:runtimeEvidenceState')!='METHOD_EXECUTED'
            for c in sbom.get('components',[]))
    return {'schemaVersion':1,'stage':21,'mode':mode,
            'status':'PASS' if all(checks.values()) else 'FAIL',
            'checks':checks,'expected':expected,'matchingComponents':matches,
            'scope':'archive-to-runtime evidence only; requires independent real WAS and official Agent validation',
            'limitations':['Matching SHA-256 is identity evidence, not official ASM provenance.',
                           'A selected method being called does not imply the entire library is vulnerable.',
                           'This check cannot establish the completeness of a runtime inventory.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',required=True,type=Path)
    p.add_argument('--sbom',required=True,type=Path)
    p.add_argument('--mode',choices=['asm-traced','loaded-only'],default='asm-traced')
    p.add_argument('--out',type=Path)
    args=p.parse_args()
    report=verify(args.archive,json.loads(args.sbom.read_text(encoding='utf-8')),args.mode)
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'mode':args.mode,'checks':report['checks']},indent=2))
    return 0 if report['status']=='PASS' else 3

if __name__=='__main__':raise SystemExit(main())
