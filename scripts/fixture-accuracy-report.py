#!/usr/bin/env python3
"""Accuracy ONLY for constructed archives; no inference to production ecosystems."""
import hashlib,json
from pathlib import Path
root=Path('target/phase9-nested')
expected='pkg:maven/com.example.fixture/fixture-core@1.2.3'
reference_hash=hashlib.sha256((root/'fixture-core-1.2.3.jar').read_bytes()).hexdigest()
rows=[]
for category,entry in [('boot','BOOT-INF/lib/fixture-core-1.2.3.jar'),('war','WEB-INF/lib/fixture-core-1.2.3.jar')]:
    doc=json.loads((root/(category+'.json')).read_text())
    components=doc.get('components',[])
    truth=[c for c in components if c.get('purl')==expected]
    accurate=len(truth)==1 and any(h.get('content')==reference_hash for h in truth[0].get('hashes',[])) and entry in next((p['value'] for p in truth[0]['properties'] if p['name']=='runtimeSbom:source'),'')
    execution=len(truth)==1 and next((p['value'] for p in truth[0]['properties'] if p['name']=='runtimeSbom:observedMethodEntryCount'),None)=='7'
    rows.append({'fixture':category,'exact_purl_sha_and_origin':accurate,'exact_7_method_entries':execution})
result={'scope':'synthetic archives with a single known nested component; not a production accuracy estimate','fixture_count':len(rows),'purl_sha_origin_matches':sum(x['exact_purl_sha_and_origin'] for x in rows),'method_count_matches':sum(x['exact_7_method_entries'] for x in rows),'fixtures':rows}
Path('results/phase9-fixture-accuracy.json').write_text(json.dumps(result,indent=2)+'\n')
assert result['purl_sha_origin_matches']==2 and result['method_count_matches']==2,result
print(json.dumps(result,indent=2))
