#!/usr/bin/env python3
"""Assert real code-source+loader attribution and same-PURL/different-SHA conflict."""
import argparse, hashlib, json
from collections import defaultdict
from pathlib import Path

PURL='pkg:maven/com.example.fixture/fixture-core@1.2.3'
def props(c):return {p['name']:p['value'] for p in c.get('properties',[])}
def verify(sbom,old,new):
    document=json.loads(Path(sbom).read_text(encoding='utf-8'))
    assert document.get('bomFormat')=='CycloneDX' and document.get('specVersion')=='1.6'
    metadata=props(document['metadata'])
    assert metadata['runtimeSbom:attributionAlgorithm']=='source+loader+method'
    assert int(metadata['runtimeSbom:conflictingMavenPurls'])==1,metadata
    assert int(metadata['runtimeSbom:unattributedMethodEntries'])==0, metadata
    assert int(metadata['runtimeSbom:invalidMethodEventKeys'])==0,metadata
    components=[c for c in document['components'] if c.get('purl')==PURL]
    assert len(components)==4, 'expected 4 library instances, got %d'%len(components)
    old_hash=hashlib.sha256(Path(old).read_bytes()).hexdigest()
    new_hash=hashlib.sha256(Path(new).read_bytes()).hexdigest()
    assert old_hash != new_hash
    by_hash=defaultdict(list)
    refs=set()
    for c in components:
        p=props(c)
        assert p.get('runtimeSbom:purlHasDifferentHashes')=='true'
        assert p['runtimeSbom:metadataConfidence']=='pom.properties'
        assert c['bom-ref'] not in refs,'duplicate BOM reference'
        refs.add(c['bom-ref'])
        h=c['hashes'][0]['content']
        by_hash[h].append((int(p['runtimeSbom:observedMethodEntryCount']),p['runtimeSbom:runtimeEvidenceState'],p['runtimeSbom:classLoader']))
    assert len(by_hash)==2
    assert sorted(x[0] for x in by_hash[old_hash]) == [2,3],by_hash
    assert sorted(x[0] for x in by_hash[new_hash]) == [0,4],by_hash
    assert sum(x[0] for xs in by_hash.values() for x in xs)==9
    assert sorted(x[1] for x in by_hash[new_hash])==['CLASS_LOADED','METHOD_EXECUTED']
    return {'status':'PASS','mode':'synthetic-jvm-loader-test-not-vendor-was',
            'instances':len(components),'purl':PURL,'sha256Variants':2,'methodEntriesObserved':9,
            'methodEntriesNotObservedInIsolatedLoader':5,'unattributedMethodEntries':0,
            'perHashMethodCounts':{k:sorted(x[0] for x in v) for k,v in by_hash.items()}}

def main():
    p=argparse.ArgumentParser();p.add_argument('sbom');p.add_argument('oldjar');p.add_argument('newjar');p.add_argument('--out')
    a=p.parse_args();result=verify(a.sbom,a.oldjar,a.newjar)
    if a.out:
        dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
