#!/usr/bin/env python3
"""Conservative RC gate: do not infer production readiness from synthetic tests."""
import argparse
import json
from pathlib import Path

ap=argparse.ArgumentParser()
ap.add_argument('--report',default='results/phase13/summary.json')
ap.add_argument('--out',default='results/phase13/rc-gate.json')
ap.add_argument('--official-asm-report',default='',help='path to evidence produced with official shaded ASM')
ap.add_argument('--spring-report',default='',help='actual running Spring Boot server test report')
ap.add_argument('--tomcat-report',default='',help='actual running Tomcat server test report')
ap.add_argument('--jdk-matrix-report',default='',help='JDK8/11/17/21 tests report')
a=ap.parse_args()
synthetic=Path(a.report)
checks=[]
def check(name,path,kind):
    p=Path(path) if path else None
    evidence=None
    if p and p.exists():
        try:evidence=json.loads(p.read_text())
        except (ValueError,OSError):pass
    valid=isinstance(evidence,dict) and evidence.get('status')=='PASS' and evidence.get('evidenceType')==kind
    checks.append({'name':name,'status':'PASS' if valid else 'NOT_VERIFIED','evidence':str(p) if valid else None})
if synthetic.exists():
    try:
        result=json.loads(synthetic.read_text())
        modes=result.get('modes',{})
        valid=result.get('testType')=='real-HTTP-local-fixture' and all(m in modes and modes[m]['requests']>0 and modes[m]['errors']==0 for m in ('baseline','loaded-only','asm-traced')) and modes['asm-traced'].get('observedWorkerComputeEntries',0)>0
    except (ValueError,KeyError,TypeError):valid=False
else:valid=False
checks.append({'name':'local HTTP instrumentation smoke','status':'PASS' if valid else 'NOT_VERIFIED','evidence':str(synthetic) if valid else None})
check('official ASM shaded agent execution',a.official_asm_report,'official-asm-shaded')
check('live Spring Boot request evidence',a.spring_report,'live-spring-boot')
check('live Tomcat request evidence',a.tomcat_report,'live-tomcat')
check('Java 8/11/17/21 matrix',a.jdk_matrix_report,'jdk-matrix')
report={'release':'1.0.0-rc4','status':'APPROVED' if all(c['status']=='PASS' for c in checks) else 'HOLD',
        'checks':checks,'policy':'No production approval without official shaded ASM, real WAS and JDK matrix evidence. JSON gate reports are not independently authenticated.'}
p=Path(a.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
