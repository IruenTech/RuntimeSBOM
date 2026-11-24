#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
sh scripts/validate-offline.sh > /dev/null 2>&1
java '-javaagent:target/offline-validation/agent-validation-only.jar=output=target/phase7-multiloader.json,interval=0,resourceProbe=false' -cp target/offline-validation/classes example.MultiLoader target/offline-validation/demo.jar >/dev/null 2>&1
python3 - <<'PY'
import json
with open('target/phase7-multiloader.json', encoding='utf-8') as f: bom=json.load(f)
components=[c for c in bom['components'] if 'demo.jar' in c.get('bom-ref','')]
assert len(components) >= 2, 'expected isolated component references for child classloaders'
assert len({c['bom-ref'] for c in components}) == len(components)
print('Classloader separation PASS: %d isolated entries' % len(components))
PY
