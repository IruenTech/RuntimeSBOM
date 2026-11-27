#!/usr/bin/env python3
"""Fail-closed binding of Phase29 checks to a successfully verified Phase26 JAR.

Never infer a SHA from an unchecked input alone.  Require the actual shaded
artifact, the official Maven build record, and structural audit to agree.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def verify(root=ROOT):
    jar = root/'target/runtime-sbom-agent-1.0.0-rc16.jar'
    proof = root/'results/phase22/build.json'
    audit_path = root/'results/phase22/binary-audit.json'
    if not all(p.is_file() for p in (jar, proof, audit_path)):
        raise ValueError('Missing Phase26 JAR, build.json, or binary-audit.json')
    digest = hashlib.sha256(jar.read_bytes()).hexdigest()
    build = json.loads(proof.read_text(encoding='utf-8'))
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    if build.get('status') != 'PASS' or build.get('mavenPackageSucceeded') is not True:
        raise ValueError('Phase26 Maven build proof was not PASS')
    if build.get('version') != '1.0.0-rc16' or build.get('asmDependency') != 'org.ow2.asm:asm:jar:9.7.1':
        raise ValueError('Phase26 Maven version/ASM identity mismatch')
    if not isinstance(audit.get('checks'),dict) or not all(audit['checks'].values()) or audit.get('status') != 'PASS':
        raise ValueError('Phase26 shaded binary audit is not PASS')
    if digest != build.get('artifactSha256') or digest != audit.get('sha256'):
        raise ValueError('Exact JAR hash differs from Phase26 build/audit evidence')
    return digest

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--github-env', type=Path)
    a = ap.parse_args()
    try:
        digest = verify()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print('PHASE29 FAIL CLOSED: '+str(exc),file=sys.stderr)
        return 1
    print('PASS Phase26 exact ASM JAR, Maven proof and audit SHA-256:',digest)
    if a.github_env:
        # GitHub runner supplies this path. Never add user-provided multiline text.
        with a.github_env.open('a',encoding='utf-8') as out:
            out.write('RUNTIMESBOM_EXPECTED_SHA256='+digest+'\n')
    return 0

if __name__=='__main__':sys.exit(main())
