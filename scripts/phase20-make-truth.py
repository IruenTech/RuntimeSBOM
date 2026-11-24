#!/usr/bin/env python3
"""Build independent expected identity from fixture JAR bytes + known Java workload.

Never reads an Agent-generated SBOM. Count expectations come from fixture program
(Phase19ProvenanceWorkload: 3+4+5+2; NestedArchiveSmoke: 7)."""
import argparse
import hashlib
import json
from pathlib import Path

PURL='pkg:maven/com.example.fixture/fixture-core@1.2.3'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def item(source,digest,n,state):
    return {'purl':PURL, 'sha256':digest, 'sourceSuffix':source,
            'methodEntries':n,'evidenceState':state}

def build(root):
    provenance=root/'target/phase19-provenance'; nested=root/'target/phase9-nested'
    old, new=sha(provenance/'old-fixture.jar'),sha(provenance/'new-fixture.jar')
    nested_sha=sha(nested/'fixture-core-1.2.3.jar')
    jobs={
      'provenance': {'name':'four-loader-two-JAR-provenance',
                     'groundTruthSource':'Phase19ProvenanceWorkload.java call plan + fixture JAR SHA-256',
                     'expected':[item('old-fixture.jar',old,3,'METHOD_EXECUTED'),
                                 item('old-fixture.jar',old,2,'METHOD_EXECUTED'),
                                 item('new-fixture.jar',new,4,'METHOD_EXECUTED'),
                                 item('new-fixture.jar',new,0,'CLASS_LOADED')]},
      'boot':{'name':'synthetic-BOOT-INF-lib','groundTruthSource':'NestedArchiveSmoke.java + nested fixture JAR SHA-256',
              'expected':[item('boot-application.jar!/BOOT-INF/lib/fixture-core-1.2.3.jar!',nested_sha,7,'METHOD_EXECUTED')]},
      'war':{'name':'synthetic-WEB-INF-lib','groundTruthSource':'NestedArchiveSmoke.java + nested fixture JAR SHA-256',
              'expected':[item('sample.war!/WEB-INF/lib/fixture-core-1.2.3.jar!',nested_sha,7,'METHOD_EXECUTED')]}}
    for doc in jobs.values():
        doc.update({'schemaVersion':1, 'scopeTerms':['fixture','pkg:maven/com.example.fixture/']})
    return jobs


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    p.add_argument('--out-dir',type=Path,default=Path('results/phase20'))
    a=p.parse_args()
    files=build(a.root.resolve());a.out_dir.mkdir(parents=True,exist_ok=True)
    for name, doc in files.items():
        path=a.out_dir/('truth-'+name+'.json');path.write_text(json.dumps(doc,indent=2)+'\n',encoding='utf-8')
        print(path)

if __name__=='__main__':main()
