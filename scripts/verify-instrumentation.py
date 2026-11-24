#!/usr/bin/env python3
import json,sys
from pathlib import Path
bom_path,log_path=map(Path,sys.argv[1:3]); bom=json.loads(bom_path.read_text())
assert 'INSTRUMENTATION_SMOKE_PASS checksum=168' in log_path.read_text()
props={v['name']:v['value'] for v in bom['metadata']['properties']}
assert int(props['runtimeSbom:transformedClasses']) >= 1, props
assert int(props['runtimeSbom:transformFailures']) == 0, props
matches=[(k,int(v)) for k,v in props.items() if k.startswith('runtimeSbom:methodEntry:') and 'example.Worker#compute(I)I' in k]
assert matches and sum(v for _,v in matches)==12, matches
components=[c for c in bom['components'] if any(p['name']=='runtimeSbom:runtimeEvidenceState' and p['value']=='METHOD_EXECUTED' for p in c.get('properties',[]))]
assert components, 'expected METHOD_EXECUTED component'
print('PASS: official-output-shape CycloneDX JSON, 12 actual Worker.compute entries, transformFailures=0')
