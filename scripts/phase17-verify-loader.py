#!/usr/bin/env python3
"""Fail if multiple classloaders merge, fake execution is recorded, or evidence is absent."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(report, fixture):
    bom = json.loads(Path(report).read_text(encoding='utf-8'))
    assert bom['bomFormat'] == 'CycloneDX'
    metadata = {p['name']: p['value'] for p in bom['metadata']['properties']}
    assert metadata['runtimeSbom:agentVersion'] == '1.0.0-rc16'
    assert metadata['runtimeSbom:jvmVersion']
    assert int(metadata['runtimeSbom:classLoaderVisible']) >= 2
    assert int(metadata['runtimeSbom:classLoaderIsolated']) >= 1
    assert int(metadata['runtimeSbom:transformFailures']) == 0
    components = [c for c in bom['components'] if c.get('purl') ==
                  'pkg:maven/com.example.fixture/fixture-core@1.2.3']
    assert len(components) == 3, 'expected 3 loader-scoped components, got %s' % len(components)
    by_loader = {}
    for comp in components:
        props = {p['name']: p['value'] for p in comp['properties']}
        key = props['runtimeSbom:classLoader']
        assert key not in by_loader, 'loader identity collapsed'
        assert props['runtimeSbom:metadataConfidence']
        assert comp['hashes'][0]['content'] == hashlib.sha256(Path(fixture).read_bytes()).hexdigest()
        by_loader[key] = props
    counts = sorted(int(p['runtimeSbom:observedMethodEntryCount']) for p in by_loader.values())
    states = sorted(p['runtimeSbom:runtimeEvidenceState'] for p in by_loader.values())
    assert counts == [0, 3, 5], 'unexpected method entry counts: %r' % counts
    assert states == ['CLASS_LOADED', 'METHOD_EXECUTED', 'METHOD_EXECUTED'], states
    report = {'status':'PASS','runtime':'JDK21 internal ASM test fixture or official ASM (see test invocation)',
              'loaderCount':len(components),'methodCounts':counts,'states':states,
              'visibleLoaderCount':int(metadata['runtimeSbom:classLoaderVisible']),
              'isolatedLoaderCount':int(metadata['runtimeSbom:classLoaderIsolated'])}
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('sbom')
    parser.add_argument('fixture')
    parser.add_argument('--out')
    args = parser.parse_args()
    result = verify(args.sbom, args.fixture)
    if args.out:
        out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
