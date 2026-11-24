import json
from pathlib import Path
p = Path('target/demo-sbom.json')
bom = json.loads(p.read_text())
assert bom['bomFormat']=='CycloneDX' and bom['specVersion']=='1.6'
components = bom['components']
assert components, 'No libraries observed'
observed = [dict((p['name'],p['value']) for p in c['properties']) for c in components]
assert any(int(c['runtimeSbom:observedMethodEntryCount']) >= 4 for c in observed), observed
print('ASM method entry verification PASS')
