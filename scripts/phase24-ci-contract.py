#!/usr/bin/env python3
"""Lightweight static CI workflow contract check, without third-party modules.
This is a *sanity check* of the workflow text, not proof Actions actually ran.
"""
from __future__ import annotations
import argparse,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
WORKFLOW=ROOT/'.github/workflows/phase24-official-asm-staging.yml'

REQUIRED={
    'hasOfficialBuild':'official-build:',
    'hasJdkMatrix':'jdk-matrix:',
    'hasWasMatrix':'was-matrix:',
    'hasReview':'review:',
    'actualJdk8':"jdk: ['8', '11', '17', '21']",
    'springBoot2':'spring-boot2',
    'springBoot3':'spring-boot3',
    'tomcat9':'tomcat9',
    'tomcat10':'tomcat10',
    'doesMavenBuild':'phase22-official-build.sh',
    'usesSameArtifact':'phase24-official-exact-binary',
    'checksBinaryBeforeRun':'phase24-check-binary.py',
    'exactManifest':'phase24-staging-manifest.py',
    'rc15':'runtime-sbom-agent-1.0.0-rc16.jar',
    'explicitReviewDependencies':'needs: [official-build, jdk-matrix, was-matrix]',
}

def audit(text):
    checks={k:(v in text) for k,v in REQUIRED.items()}
    checks['noDirectProductionDeployment']=not re.search(r'(?m)^\s*environment:\s*production|\b(?:kubectl\s+apply|helm\s+upgrade|gh\s+release\s+create)\b',text,re.I)
    checks['noOldReleaseArtifact']='runtime-sbom-agent-1.0.0-rc14.jar' not in text
    # Fail workflow if it pretends a dry run is a live WAS test.
    checks['runsLiveWas']=bool(re.search(r'python3\s+scripts/phase21-staging-live\.py',text))
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks}

def main():
    p=argparse.ArgumentParser();p.add_argument('--workflow',type=Path,default=WORKFLOW)
    p.add_argument('--out',type=Path,default=ROOT/'results/phase24/ci-contract.json');a=p.parse_args()
    try:r=audit(a.workflow.read_text(encoding='utf-8'))
    except OSError:r={'status':'FAIL','checks':{'fileAvailable':False}}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
    return 0 if r['status']=='PASS' else 3
if __name__=='__main__':raise SystemExit(main())
