#!/usr/bin/env python3
"""Strict gate: fail on missing instrumented method or wrong PURL (not merely JAR presence)."""
import json,sys
from pathlib import Path
if len(sys.argv)!=2: raise SystemExit('Usage: check-real-was-evidence.py sbom.json')
bom=json.loads(Path(sys.argv[1]).read_text())
assert bom['bomFormat']=='CycloneDX'
components=[c for c in bom.get('components',[]) if c.get('purl')=='pkg:maven/org.apache.commons/commons-lang3@3.14.0']
if not components: raise SystemExit('FAIL: no exact commons-lang3 Maven PURL (nested JAR resolution may be incomplete)')
executed=[]
for c in components:
    props={x['name']:x['value'] for x in c.get('properties',[])}
    if props.get('runtimeSbom:runtimeEvidenceState')=='METHOD_EXECUTED' and int(props.get('runtimeSbom:observedMethodEntryCount',0))>0:
        executed.append(c)
if not executed:raise SystemExit('FAIL: Maven component present but no observed method entry')
print('PASS: exact commons-lang3 3.14.0 PURL, METHOD_EXECUTED and positive method count')
