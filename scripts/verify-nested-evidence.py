#!/usr/bin/env python3
"""Evidence accuracy oracle for the synthetic WAR / Boot archive fixture."""
import hashlib
import json
import sys
from pathlib import Path

bom_path,log_path,jar_path,nested_path=map(Path,sys.argv[1:5])
bom=json.loads(bom_path.read_text())
assert bom['bomFormat']=='CycloneDX' and bom['specVersion']=='1.6'
assert 'NESTED_ARCHIVE_PASS calls=7' in log_path.read_text(),log_path.read_text()
props={p['name']:p['value'] for p in bom['metadata']['properties']}
assert int(props['runtimeSbom:transformFailures'])==0,props
assert int(props['runtimeSbom:transformedClasses'])>=1,props
hits=[int(p['value']) for p in bom['metadata']['properties'] if p['name'].startswith('runtimeSbom:methodEntry:') and 'fixture.lib.Helper#compute(I)I' in p['name']]
assert sum(hits)==7,hits
matches=[c for c in bom['components'] if c.get('purl')=='pkg:maven/com.example.fixture/fixture-core@1.2.3']
assert len(matches)==1,[ (x.get('name'),x.get('purl')) for x in bom['components']]
c=matches[0]; cp={p['name']:p['value'] for p in c.get('properties',[])}
assert nested_path.as_posix() in cp['runtimeSbom:source'],cp
assert cp['runtimeSbom:runtimeEvidenceState']=='METHOD_EXECUTED',cp
assert cp['runtimeSbom:observedMethodEntryCount']=='7',cp
hashes=c.get('hashes',[])
assert {'alg':'SHA-256','content':hashlib.sha256(jar_path.read_bytes()).hexdigest()} in hashes,hashes
print('PASS: expected PURL, nested CodeSource, exact SHA256, 7 instrumented entries, zero transformer errors')
