#!/usr/bin/env python3
"""Conservative Phase 14 release candidate gate; no stale/synthetic surrogate evidence."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
APPS=('spring-boot2','spring-boot3','tomcat9','tomcat10')


def data(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError,ValueError,TypeError):
        return None


def gate(official,matrix,apps, thresholds):
    checks=[]
    def add(name,passed,details=''):
        checks.append({'check':name,'status':'PASS' if passed else 'NOT_VERIFIED_OR_FAILED','details':details})
    valid_official=isinstance(official,dict) and official.get('version')=='1.0.0-rc16' and official.get('status')=='PASS' and official.get('evidenceType')=='official-shaded-asm-executed' and official.get('asmDependency')=='org.ow2.asm:asm:9.7.1' and official.get('agentClassMajorVersion')==52 and official.get('workerMethodEntries')==12
    add('official ASM 9.7.1 shaded Java 8 agent executes',valid_official)
    versions=('8','11','17','21')
    valid_matrix=isinstance(matrix,dict) and matrix.get('evidenceType')=='multi-jdk-official' and matrix.get('version')=='1.0.0-rc16' and all(matrix.get('jdk',{}).get(ver)=='PASS' for ver in versions)
    add('JDK 8/11/17/21 official execution matrix',valid_matrix)
    for app in APPS:
        report=apps.get(app)
        valid=isinstance(report,dict) and report.get('version')=='1.0.0-rc16' and report.get('status')=='PASS' and report.get('evidenceType')=='actual-live-was' and report.get('application')==app
        if valid:
            try:
                base=report['modes']['baseline']['http']
                trace=report['modes']['asm-traced']['http']
                evidenced=report['modes']['asm-traced']['evidence']
                valid=(base['requests']>0 and trace['requests']>0 and base['errors']==0 and trace['errors']==0
                       and evidenced['purlFound'] and evidenced['methodExecuted']
                       and base['latencyMs']['p95']>0 and trace['latencyMs']['p95']>0
                       and trace['successTps']>0 and base['successTps']>0)
            except (TypeError,KeyError,ValueError): valid=False
        add('%s real HTTP + exact PURL + executed methods'%app,valid)
        if valid:
            tps=(1-trace['successTps']/base['successTps'])*100
            p95=(trace['latencyMs']['p95']/base['latencyMs']['p95']-1)*100
            target=tps<=thresholds['maxTpsDropPercent'] and p95<=thresholds['maxP95IncreasePercent']
            add('%s staging performance threshold'%app,target,'TPS drop %.2f%%, P95 increase %.2f%%'%(tps,p95))
    # This gate does not cover vendor JVM production deployment approvals.
    approved=all(x['status']=='PASS' for x in checks)
    return {'version':'1.0.0-rc16','releaseCandidateDecision':'STAGING_RC_ELIGIBLE' if approved else 'HOLD',
            'productionDeploymentDecision':'NOT_APPROVED',
            'thresholdPolicy':thresholds,'checks':checks,
            'limits':['The staging performance limits are proposed project gates, not standardized acceptance criteria.',
                      'Local proof does not cover real JEUS/WebLogic, IBM AIX, multi-hour production loads, or JVM interoperability.',
                      'Evidence JSON is locally generated and not cryptographically attested.']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--official',default='results/phase14/official-asm.json')
    p.add_argument('--matrix',default='results/phase14/jdk-matrix.json')
    p.add_argument('--live-dir',default='results/phase14/live')
    p.add_argument('--out',default='results/phase14/release-gate.json')
    p.add_argument('--max-tps-drop',type=float,default=10.0)
    p.add_argument('--max-p95-increase',type=float,default=20.0)
    a=p.parse_args()
    if not (0<=a.max_tps_drop<=100 and 0<=a.max_p95_increase<=500):p.error('invalid acceptance thresholds')
    result=gate(data(ROOT/a.official),data(ROOT/a.matrix),
        {app:data(ROOT/a.live_dir/app/'summary.json') for app in APPS},
        {'maxTpsDropPercent':a.max_tps_drop,'maxP95IncreasePercent':a.max_p95_increase})
    output=ROOT/a.out;output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'releaseCandidateDecision':result['releaseCandidateDecision'],
         'productionDeploymentDecision':result['productionDeploymentDecision'],
         'passed':sum(x['status']=='PASS' for x in result['checks']), 'checks':len(result['checks'])},indent=2))
    # Never treat missing evidence as successful simply because the report was written.
    return 0 if result['releaseCandidateDecision']=='STAGING_RC_ELIGIBLE' else 3

if __name__=='__main__':raise SystemExit(main())
