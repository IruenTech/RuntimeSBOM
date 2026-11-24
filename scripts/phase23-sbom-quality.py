#!/usr/bin/env python3
"""Fail-closed assessment of the truthfulness of RuntimeSBOM observation labels.

Quality is evidence scope, NOT deployment approval. No positive method evidence
must be invented from a class-load observation. No absent entry is proof of non-use.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

REQUIRED=("runtimeSbom:observationQuality","runtimeSbom:observationLimitations",
          "runtimeSbom:attributedMethodEntries","runtimeSbom:traceMode",
          "runtimeSbom:unattributedMethodEntries","runtimeSbom:invalidMethodEventKeys",
          "runtimeSbom:transformFailures","runtimeSbom:classLoaderIsolated",
          "runtimeSbom:registrationDrops","runtimeSbom:droppedEvents",
          "runtimeSbom:traceDisabled","runtimeSbom:sampleEvery")
STATES={"LOADING_ONLY","DEGRADED","SAMPLED","NO_METHOD_HITS","OBSERVED_PARTIAL"}

def properties(items):
    result={}
    for item in items:
        if not isinstance(item,dict) or not isinstance(item.get('name'),str):
            raise ValueError('malformed property')
        name=item['name']
        if name in result: raise ValueError('duplicate property: '+name)
        if not isinstance(item.get('value'),str): raise ValueError('non-string property: '+name)
        result[name]=item['value']
    return result

def assess(bom, require_method=False):
    errors=[]
    if not isinstance(bom,dict) or bom.get('bomFormat')!='CycloneDX' or bom.get('specVersion')!='1.6':
        return {'status':'FAIL','quality':'UNKNOWN','errors':['not a CycloneDX 1.6 document'],'releaseDecision':'HOLD'}
    try:
        p=properties(bom['metadata']['properties'])
        missing=[key for key in REQUIRED if key not in p]
        if missing:raise ValueError('missing properties: '+', '.join(missing))
        mode=p['runtimeSbom:traceMode']; state=p['runtimeSbom:observationQuality']
        if mode not in ('METHOD_ENTRY_REQUESTED','LOADING_ONLY') or state not in STATES:
            raise ValueError('invalid trace mode or quality state')
        def count(key):
            v=p['runtimeSbom:'+key]
            if not v.isdigit():raise ValueError('non-negative integer required: '+key)
            return int(v)
        n=count('attributedMethodEntries')
        sample=count('sampleEvery')
        if sample<1:raise ValueError('sampleEvery must be positive')
        signals=['transformFailures','classLoaderIsolated','registrationDrops',
                 'droppedEvents','unattributedMethodEntries','invalidMethodEventKeys']
        degraded=any(count(k)>0 for k in signals)
        disabled=p['runtimeSbom:traceDisabled']
        if disabled not in ('true','false'):raise ValueError('invalid traceDisabled')
        degraded=degraded or disabled=='true'
        if mode=='LOADING_ONLY': calculated='LOADING_ONLY'
        elif degraded: calculated='DEGRADED'
        elif sample>1: calculated='SAMPLED'
        elif n==0: calculated='NO_METHOD_HITS'
        else: calculated='OBSERVED_PARTIAL'
        if calculated!=state: errors.append('quality state disagrees with evidence counters: expected '+calculated)
        components=bom.get('components',[])
        if not isinstance(components,list):raise ValueError('components must be a list')
        components_entries=0
        for i,c in enumerate(components):
            cp=properties(c.get('properties',[]))
            cstate=cp.get('runtimeSbom:runtimeEvidenceState')
            if cstate not in ('METHOD_EXECUTED','CLASS_LOADED','PRELOADED'):
                raise ValueError('component %d missing execution state' % i)
            count_val=cp.get('runtimeSbom:observedMethodEntryCount','')
            if not count_val.isdigit():raise ValueError('component %d invalid entry count' % i)
            entries=int(count_val);components_entries+=entries
            if (cstate=='METHOD_EXECUTED')!=(entries>0):
                errors.append('component %d claimed inconsistent method execution' % i)
            if mode=='LOADING_ONLY' and entries>0:
                errors.append('loading-only mode claimed executed method')
        if components_entries!=n:errors.append('component counters do not equal attributedMethodEntries')
        if require_method and (n==0 or mode=='LOADING_ONLY'):
            errors.append('positive usable method evidence required')
        quality=state
    except (KeyError,ValueError,TypeError,AttributeError) as exc:
        errors.append(str(exc));quality='UNKNOWN'
    return {'status':'PASS' if not errors else 'FAIL','quality':quality,
            'errors':errors,'releaseDecision':'HOLD',
            'note':'Data consistency only; does not establish execution completeness, provenance authenticity, or release approval'}

def main():
    a=argparse.ArgumentParser()
    a.add_argument('sbom',type=Path)
    a.add_argument('--out',type=Path)
    a.add_argument('--require-method',action='store_true')
    args=a.parse_args()
    try: result=assess(json.loads(args.sbom.read_text(encoding='utf-8')),args.require_method)
    except (OSError,ValueError) as exc:
        result={'status':'FAIL','quality':'UNKNOWN','errors':[str(exc)],'releaseDecision':'HOLD'}
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='PASS' else 3
if __name__=='__main__':raise SystemExit(main())
