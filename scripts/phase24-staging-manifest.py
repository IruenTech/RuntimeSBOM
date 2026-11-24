#!/usr/bin/env python3
"""Stage 24: binding of exact official ASM Agent, eight runtime SBOMs, and
independent CI test evidence into a digest-indexed *staging* review manifest.

SHA-256 detects accidental mixing and modification after collection; it is NOT
cryptographic CI attestation. Production deployment is always HOLD.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
VERSION = '1.0.0-rc16'
JDKS = (8, 11, 17, 21)
APPS = ('spring-boot2', 'spring-boot3', 'tomcat9', 'tomcat10')


def module(filename, name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def digest(file):
    h = hashlib.sha256()
    with Path(file).open('rb') as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def files_required(root):
    root = Path(root)
    paths = [root/'target'/('runtime-sbom-agent-'+VERSION+'.jar'),
             root/'results/phase22/build.json',
             root/'results/phase22/binary-audit.json']
    for j in JDKS:
        paths += [root/f'results/phase22/jdk/jdk-{j}.json',
                  root/f'results/phase22/jdk/jdk-{j}-sbom.json']
    for app in APPS:
        d = root/f'results/phase22/live/{app}'
        paths += [d/'phase21-summary.json',
                  d/'loaded-only/sbom.json', d/'asm-traced/sbom.json',
                  d/'loaded-only/http.json', d/'asm-traced/http.json',
                  d/'baseline/http.json',
                  d/'loaded-only-archive-verification.json',
                  d/'asm-traced-archive-verification.json']
    return paths


def sbom_runtime_checks(path, tool_version=VERSION, major=None, require_method=True):
    checks = {}
    try:
        bom = json.loads(Path(path).read_text(encoding='utf-8'))
        quality = module('phase23-sbom-quality.py', 'p24_quality').assess(bom, require_method)
        p = {v['name']: v['value'] for v in bom['metadata']['properties']}
        versions = [v.get('version') for v in bom['metadata']['tools']['components']
                    if v.get('name') == 'RuntimeSBOM-Agent']
        checks['observationQuality'] = quality['status'] == 'PASS' and quality['quality'] == 'OBSERVED_PARTIAL'
        checks['exactAgentVersion'] = p.get('runtimeSbom:agentVersion') == tool_version and tool_version in versions
        checks['notSampled'] = p.get('runtimeSbom:sampleEvery') == '1'
        checks['attributedMethodEvidence'] = int(p.get('runtimeSbom:attributedMethodEntries', '0')) > 0
        if major is not None:
            v = p.get('runtimeSbom:jvmVersion', '')
            expected = str(major) if major != 8 else '1.8'
            checks['actualJvmMajor'] = v.startswith(expected+'.') or v == expected or v.startswith(expected+'-')
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        checks['sbomReadable'] = False
    return checks


def evaluate(root=ROOT):
    root = Path(root)
    inputs = files_required(root)
    missing = [str(p.relative_to(root)) for p in inputs if not p.is_file()]
    checks = {'requiredEvidenceFilesPresent': not missing}
    reasons = []
    if missing:
        reasons.append('Missing official-runtime files: '+', '.join(missing[:8]))
    jar = root/'target'/('runtime-sbom-agent-'+VERSION+'.jar')
    jar_sha = digest(jar) if jar.is_file() else None
    # Import existing strict binary + performance gate only when the project root matches.
    # For synthetic test fixture directories, file inventory is still evaluated, but
    # cannot turn into PASS without actual official audit in the real source tree.
    if root.resolve() == ROOT.resolve():
        base_gate = module('phase22-evidence-gate.py', 'p24_base')
        base = base_gate.validate(jar, root/'results/phase22/jdk',root/'results/phase22/live',
                                  root/'results/phase22/build.json')
        checks['baseExactBinaryReview'] = base['stagingReview'] == 'ELIGIBLE_FOR_HUMAN_REVIEW'
        if not checks['baseExactBinaryReview']:
            reasons.extend(base['blockingReasons'])
    else:
        checks['baseExactBinaryReview'] = False
        reasons.append('Synthetic root cannot substitute an actual verified official build')
    for j in JDKS:
        bom = root/f'results/phase22/jdk/jdk-{j}-sbom.json'
        sub = sbom_runtime_checks(bom,major=j)
        checks['jdk%dQuality' % j] = bool(sub) and all(sub.values())
        if not checks['jdk%dQuality' % j]: reasons.append('JDK %d SBOM quality/version mismatch: %s' % (j,sub))
    for app in APPS:
        base = root/f'results/phase22/live/{app}'
        sub = sbom_runtime_checks(base/'asm-traced/sbom.json')
        checks[app+'Quality'] = bool(sub) and all(sub.values())
        if not checks[app+'Quality']:reasons.append(app+' observed quality/version mismatch: '+str(sub))
    indices = {}
    for p in inputs:
        if p.is_file():
            if p.is_symlink():
                checks['noSymlinks'] = False
                reasons.append('Evidence file is a symlink: '+str(p))
                continue
            indices[str(p.relative_to(root))] = {'sha256':digest(p), 'bytes':p.stat().st_size}
    checks.setdefault('noSymlinks',True)
    if jar_sha:
        build = root/'results/phase22/build.json'
        try:
            b=json.loads(build.read_text())
            checks['buildProofMatchesJar'] = (b.get('artifactSha256')==jar_sha
                                               and b.get('status')=='PASS'
                                               and b.get('version')==VERSION)
        except (OSError,ValueError):
            checks['buildProofMatchesJar'] = False
        if not checks['buildProofMatchesJar']:
            reasons.append('Build proof SHA/version does not match exact release JAR')
    else:
        checks['buildProofMatchesJar'] = False
        reasons.append('Official shaded JAR absent')
    result = 'ELIGIBLE_FOR_HUMAN_REVIEW' if all(checks.values()) else 'HOLD'
    return {
        'schemaVersion': 1, 'stage':24, 'version':VERSION,
        'createdAtUtc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'runnerContext':{key:os.environ.get(key) for key in ('GITHUB_SHA','GITHUB_RUN_ID','GITHUB_WORKFLOW')},
        'officialJarSha256':jar_sha,
        'checks':checks,'missingEvidence':missing,'blockingReasons':reasons,
        'inputs':indices,
        'stagingReview':result,'productionDeployment':'HOLD',
        'provenanceLevel':'UNSIGNED_HASH_MANIFEST',
        'limitations':[
            'File hashes and JSON fields provide integrity linkage, not authentication of test operator',
            'Observability quality does not establish completeness of instrumented method coverage',
            'Staging acceptance does not validate JEUS, WebLogic, or AIX production environments',
            'Production release requires independent authorization and signed provenance'
        ]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=ROOT/'results/phase24/staging-manifest.json')
    a=parser.parse_args()
    r=evaluate()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'stage':r['stage'],'stagingReview':r['stagingReview'],
                      'productionDeployment':'HOLD','evidenceFiles':len(r['inputs']),
                      'firstBlockers':r['blockingReasons'][:5]},ensure_ascii=False,indent=2))
    return 0 if r['stagingReview']=='ELIGIBLE_FOR_HUMAN_REVIEW' else 3

if __name__=='__main__':raise SystemExit(main())
