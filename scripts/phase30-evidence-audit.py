#!/usr/bin/env python3
"""Audit supplied Phase29 GitHub artifacts without treating results as operational approval.

Supports the six ZIPs downloaded directly from GitHub Actions. No network requests.
"""
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

APPS=('spring-boot2','spring-boot3','tomcat9','tomcat10')
PURL='pkg:maven/org.apache.commons/commons-lang3@3.14.0'
HEX64=re.compile(r'^[0-9a-f]{64}$')

def read(zippath, entry):
    with zipfile.ZipFile(zippath) as z:
        return json.loads(z.read(entry).decode('utf-8'))

def props(c):
    return {p.get('name'):p.get('value') for p in c.get('properties',[])}

def find_runtime(bom):
    rows=[]
    for component in bom.get('components',[]):
        if component.get('purl')!=PURL:continue
        p=props(component)
        if p.get('runtimeSbom:runtimeEvidenceState')!='METHOD_EXECUTED': continue
        count=int(p.get('runtimeSbom:observedMethodEntryCount','0'))
        h=next((x.get('content') for x in component.get('hashes',[]) if x.get('alg')=='SHA-256'),None)
        if count>0 and h:
            rows.append({'loader':p.get('runtimeSbom:classLoader'), 'hits':count,'sha256':h})
    return rows

def audit(folder):
    failures=[]
    report=read(folder/'phase29-staging-review-report.zip','review.json')
    local=read(folder/'phase29-official-local-rehearsal.zip','local-gate.json')
    outage=read(folder/'phase29-official-local-rehearsal.zip','outage-replay.json')
    perf=read(folder/'phase29-official-local-rehearsal.zip','sustained.json')
    expected=report.get('agentSha256')
    if not isinstance(expected,str) or not HEX64.fullmatch(expected):failures.append('MISSING_OR_INVALID_AGENT_SHA')
    if report.get('stagingReview')!='ELIGIBLE_FOR_HUMAN_REVIEW' or report.get('productionDeployment')!='HOLD' or report.get('failures'):
        failures.append('PHASE29_REVIEW_NOT_ELIGIBLE')
    if local.get('status')!='PASS' or local.get('agentSha256') not in (None,expected):
        failures.append('PHASE29_LOCAL_GATE_INVALID')
    if outage.get('status')!='PASS' or outage.get('agentSha256')!=expected:
        failures.append('PHASE29_OUTAGE_INVALID')
    if outage.get('queueFilesAfterRecovery')!=0 or outage.get('expectedSnapshots')!=4:
        failures.append('PHASE29_OUTAGE_DELIVERY_INCOMPLETE')
    if perf.get('status')!='PASS':failures.append('PHASE29_SHORT_PERF_NOT_PASS')
    per_app={}; dep_hashes=set()
    for app in APPS:
        name='phase29-real-was-'+app+'.zip'
        lifecycle=read(folder/name,'lifecycle.json')
        dep=lifecycle.get('expectedDependencySha256')
        dep_hashes.add(dep)
        if lifecycle.get('agentSha256')!=expected or lifecycle.get('status')!='PASS' or len(lifecycle.get('cycles',[]))!=2:
            failures.append('INVALID_LIFECYCLE_'+app)
        entry='tomcat-sbom.json' if app.startswith('tomcat') else 'boot-run2/sbom.json'
        actual=find_runtime(read(folder/name,entry))
        if not any(x['sha256']==dep and x['hits']>0 for x in actual):
            failures.append('SBOM_PROVENANCE_MISMATCH_'+app)
        if not HEX64.fullmatch(dep or ''):failures.append('INVALID_DEPENDENCY_SHA_'+app)
        # Tomcat evidence archives include the unpacked actual dependency JAR bytes.
        # Compare those bytes rather than trusting only a self-reported SBOM digest.
        embedded_jar_sha=None
        if app.startswith('tomcat'):
            jar_entry='isolated-catalina-base/webapps/sbom-demo/WEB-INF/lib/commons-lang3-3.14.0.jar'
            with zipfile.ZipFile(folder/name) as archive_zip:
                embedded_jar_sha=hashlib.sha256(archive_zip.read(jar_entry)).hexdigest()
            if embedded_jar_sha!=dep:failures.append('ACTUAL_EMBEDDED_JAR_SHA_MISMATCH_'+app)
        loaders=[x['loader'] for x in actual]
        cycles=lifecycle.get('cycles',[])
        if app.startswith('tomcat'):
            if len(cycles)==2 and not cycles[1].get('newLoaderIds'):
                failures.append('NO_NEW_LOADER_'+app)
            # NB the previous loader in the SBOM is historical; it is not proof of a live object.
        per_app[app]={'status':lifecycle.get('status'), 'cycleMethodEntries':[
            sum(x.get('observedMethodEntries',0) for x in c.get('executionEvidence',[]) if x.get('sha256')==dep)
            for c in cycles], 'dependencySha256':dep,'embeddedArchiveSha256Verified':(embedded_jar_sha==dep) if embedded_jar_sha else None,'sbomObservedLoaders':loaders}
    if len(dep_hashes)!=1:failures.append('DEPENDENCY_SHA_DIFFERS_ACROSS_WAS')
    comparison=perf.get('summary',{}).get('comparison',{})
    return {
        'phase':30, 'type':'phase29-evidence-intake',
        'result':'PASS' if not failures else 'HOLD', 'productionDeployment':'HOLD',
        'agentSha256':expected, 'dependencySha256':next(iter(dep_hashes)) if len(dep_hashes)==1 else None,
        'reportedPhase29Review':report.get('stagingReview'),
        'collectorOutageSeconds':outage.get('outageSeconds'),
        'collectorDeliveredSnapshots':outage.get('expectedSnapshots'),
        'shortSyntheticAsmTpsDeltaPercent':comparison.get('asmTpsDeltaPercent'),
        'was':per_app,
        'classloaderGarbageCollectionVerified':False,
        'sustainedWasLoadVerified':False,
        'failures':failures,
        'scope':'Audit of uploaded Phase29 evidence; no official JAR bytes or live memory capture in these six ZIPs'
    }

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-dir',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:
        report=audit(args.artifact_dir)
    except (OSError,KeyError,ValueError,zipfile.BadZipFile,TypeError) as exc:
        report={'phase':30,'type':'phase29-evidence-intake','result':'HOLD','productionDeployment':'HOLD','failures':[str(exc)]}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('PHASE30 PHASE29 EVIDENCE:',report['result'],'PRODUCTION HOLD')
    if report.get('failures'):print(report['failures'],file=sys.stderr)
    return 0 if report['result']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
