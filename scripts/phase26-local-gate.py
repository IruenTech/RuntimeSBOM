#!/usr/bin/env python3
"""Phase26 truthful offline gate; does not represent a GitHub Actions run."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'results/phase26/local'
CHECKS=[
  ('diagnostics-units',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_phase26_*.py','-v'],30),
  ('boot3-metadata',['sh','scripts/phase26-springboot3-metadata-test.sh'],120),
  ('asm-entry-test',['sh','scripts/verify-jdk-asm.sh'],120),
  ('boot3-instrumentation-fixture',['sh','scripts/phase26-boot3-agent-smoke.sh','jdk-internal'],150),
  ('phase25-regression',[sys.executable,'scripts/phase25-local-gate.py','--fast'],120),
]

def main():
  OUT.mkdir(parents=True,exist_ok=True)
  rows=[]
  for name, cmd, timeout in CHECKS:
    start=time.monotonic()
    try:
      proc=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,timeout=timeout)
      rc=proc.returncode; content=proc.stdout
    except subprocess.TimeoutExpired:
      rc=124;content='Local verification exceeded timeout'
    except OSError as exc:
      rc=127;content=str(exc)
    (OUT/(name+'.log')).write_text(content,encoding='utf-8')
    rows.append({'name':name,'status':'PASS' if rc==0 else 'FAIL','exitCode':rc,
                 'durationSec':round(time.monotonic()-start,2),
                 'log':'results/phase26/local/'+name+'.log'})
  status='PASS' if all(x['status']=='PASS' for x in rows) else 'FAIL'
  r={'stage':26,'checkedAtUtc':dt.datetime.now(dt.timezone.utc).isoformat(),
     'scope':'JDK21_OFFLINE_WITH_TEST_ONLY_ASM', 'status':status,'groups':rows,
     'officialShadedAgentBuild':'NOT_VERIFIED_IN_THIS_ENVIRONMENT',
     'githubActions':'NOT_RUN_FROM_THIS_ENVIRONMENT',
     'actualJava8_11_17':'NOT_VERIFIED_IN_THIS_ENVIRONMENT',
     'actualSpringBoot2_3_Tomcat':'NOT_RUN_FROM_THIS_ENVIRONMENT',
     'stagingReview':'HOLD','productionDeployment':'HOLD'}
  (OUT/'gate.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
  print(json.dumps({'status':status,'passedGroups':sum(x['status']=='PASS' for x in rows),
                    'totalGroups':len(rows),'stagingReview':'HOLD'},indent=2))
  return 0 if status=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
