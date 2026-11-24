#!/usr/bin/env python3
"""Portable preflight for *downloaded* exact Agent and Maven build proof.
Only structural evidence; not a signature or supply-chain attestation.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
VERSION='1.0.0-rc16'

def load():
    spec=importlib.util.spec_from_file_location('audit_p24',ROOT/'scripts/phase22-binary-audit.py')
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    return mod

def inspect(agent, proof):
    agent=Path(agent);proof=Path(proof)
    a=load().audit(agent)
    try:b=json.loads(proof.read_text(encoding='utf-8'))
    except (OSError, ValueError, UnicodeError):b={}
    checks={'shadedAsmAudit':a.get('status')=='PASS',
            'buildProofPassed':b.get('status')=='PASS' and b.get('mavenPackageSucceeded') is True,
            'versionMatches':b.get('version')==VERSION,
            'resolvedOfficialAsm':b.get('asmDependency')=='org.ow2.asm:asm:jar:9.7.1',
            'exactArtifactSha256':bool(a.get('sha256')) and b.get('artifactSha256')==a.get('sha256')}
    return {'status':'PASS' if all(checks.values()) else 'HOLD',
            'checkedAgent':str(agent),'artifactSha256':a.get('sha256'),
            'checks':checks,'productionDeployment':'HOLD'}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--agent',type=Path,default=ROOT/f'target/runtime-sbom-agent-{VERSION}.jar')
    p.add_argument('--build-proof',type=Path,default=ROOT/'results/phase22/build.json')
    p.add_argument('--out',type=Path,default=ROOT/'results/phase24/binary-preflight.json')
    a=p.parse_args()
    r=inspect(a.agent,a.build_proof)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
    return 0 if r['status']=='PASS' else 3

if __name__=='__main__':raise SystemExit(main())
