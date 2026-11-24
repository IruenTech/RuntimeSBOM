#!/usr/bin/env python3
"""Stage 23 review evidence: Phase 22 exact-binary gate + per-run SBOM observability.
No synthetic/incomplete evidence can make productionDeployment anything but HOLD.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent

def load(filename,modname):
    spec=importlib.util.spec_from_file_location(modname,ROOT/'scripts'/filename)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[modname]=mod
    spec.loader.exec_module(mod)
    return mod

APPS=('spring-boot2','spring-boot3','tomcat9','tomcat10')
JDKS=(8,11,17,21)

def evaluate(base, sbom_dir, live_dir, assessor=None):
    evaluator=assessor or load('phase23-sbom-quality.py','quality_checker')
    checks={}
    issues=[]
    for major in JDKS:
        key='jdk'+str(major)
        path=Path(sbom_dir)/('jdk-%s-sbom.json'%major)
        checks[key]=audit_file(path,evaluator)
        if checks[key]!='OBSERVED_PARTIAL':issues.append('JDK %s quality does not establish unsampled, attributable method evidence'%major)
    for app in APPS:
        path=Path(live_dir)/app/'asm-traced/sbom.json'
        checks[app]=audit_file(path,evaluator)
        if checks[app]!='OBSERVED_PARTIAL':issues.append('%s quality does not establish unsampled, attributable method evidence'%app)
    valid=base.get('stagingReview')=='ELIGIBLE_FOR_HUMAN_REVIEW' and not issues
    return {'stage':23,'version':'1.0.0-rc16','baseEvidenceReview':base.get('stagingReview','HOLD'),
            'observabilityChecks':checks,'blockingReasons':issues,
            'stagingReview':'ELIGIBLE_FOR_HUMAN_REVIEW' if valid else 'HOLD',
            'productionDeployment':'HOLD',
            'limitations':'Observation status is not a quantitative completeness estimate; vendor WAS/AIX not certified'}

def audit_file(path,assessor):
    try:
        sbom=json.loads(path.read_text(encoding='utf-8'))
        result=assessor.assess(sbom,require_method=True)
        return result['quality'] if result['status']=='PASS' else 'INVALID'
    except (OSError,ValueError,UnicodeError):return 'MISSING'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,default=ROOT/'results/phase23/staging-gate.json')
    a=p.parse_args()
    baseGate=load('phase22-evidence-gate.py','stage22_gate')
    agent=ROOT/'target/runtime-sbom-agent-1.0.0-rc16.jar'
    base=baseGate.validate(agent,ROOT/'results/phase22/jdk',ROOT/'results/phase22/live',
                           ROOT/'results/phase22/build.json')
    result=evaluate(base,ROOT/'results/phase22/jdk',ROOT/'results/phase22/live')
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'stagingReview':result['stagingReview'],
                      'productionDeployment':result['productionDeployment'],
                      'baseEvidenceReview':result['baseEvidenceReview'],
                      'observabilityChecks':result['observabilityChecks']},indent=2))
    return 0 if result['stagingReview']=='ELIGIBLE_FOR_HUMAN_REVIEW' else 3
if __name__=='__main__':sys.exit(main())
