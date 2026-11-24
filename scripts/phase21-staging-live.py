#!/usr/bin/env python3
"""Stage21 official shaded Agent live application test with archive-bound identity.

Requires authorized local staging host, Maven, full official shaded Agent JAR,
actual Spring Boot or Tomcat and a real HTTP workload. Fail-closed on missing
inputs; does not create fake PASS evidence when prerequisites are absent.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
AGENT=ROOT/'target/runtime-sbom-agent-1.0.0-rc16.jar'
APP={
  'spring-boot2':ROOT/'integration/apps/spring-boot2/target/sbom-spring-demo-1.0.0.jar',
  'spring-boot3':ROOT/'integration/apps/spring-boot3/target/sbom-spring-demo-1.0.0.jar',
  'tomcat9':ROOT/'integration/apps/tomcat9-war/target/sbom-demo.war',
  'tomcat10':ROOT/'integration/apps/tomcat10-war/target/sbom-demo.war',
}


def load_script(filename,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/filename)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def process(args):
    dest=(ROOT/args.out_dir/args.app).resolve()
    dest.mkdir(parents=True,exist_ok=True)
    blockers=[]
    if not shutil.which('mvn'):blockers.append('Maven is not installed')
    if not AGENT.is_file():blockers.append('Official shaded Agent JAR is missing')
    if args.app.startswith('tomcat') and not args.tomcat_home: blockers.append('Tomcat installation is missing')
    if not blockers:
        audit=load_script('phase18-audit-jar.py','phase21audit').audit(AGENT)
        if audit['status']!='PASS':blockers.append('Official shaded Agent structural audit failed')
    if blockers:
        report={'stage':21,'application':args.app,'status':'HOLD','blockingReasons':blockers,
                'note':'No live WAS test was executed; fail-closed.'}
        (dest/'phase21-summary.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
        return 2
    cmd=[sys.executable,str(ROOT/'scripts/phase14-live-was.py'),'--app',args.app,
         '--duration',str(args.duration),'--concurrency',str(args.concurrency),
         '--out-dir',str(ROOT/args.out_dir)]
    if args.tomcat_home:cmd+=['--tomcat-home',args.tomcat_home]
    live=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                        text=True,timeout=900)
    (dest/'phase21-live-command.log').write_text(live.stdout)
    if live.returncode:
        raise RuntimeError('Live test failed: '+live.stdout[-3000:])
    phase14=json.loads((dest/'summary.json').read_text())
    if phase14.get('officialJarSha256')!=sha(AGENT):
        raise RuntimeError('Live result used a different Agent binary')
    evaluator=load_script('phase21-archive-evidence.py','phase21archive')
    reports={}
    for mode in ('loaded-only','asm-traced'):
        report=evaluator.verify(APP[args.app],json.loads((dest/mode/'sbom.json').read_text()),mode)
        (dest/(mode+'-archive-verification.json')).write_text(json.dumps(report,indent=2)+'\n')
        if report['status']!='PASS':raise RuntimeError('FAIL: packaged JAR identity vs SBOM '+mode)
        reports[mode]=report
    out={'stage':21,'application':args.app,'status':'PASS',
         'evidenceMode':'OFFICIAL_SHADED_RUNTIME','officialJarSha256':sha(AGENT),
         'applicationArchiveSha256':reports['asm-traced']['expected']['archiveSha256'],
         'embeddedDependencySha256':reports['asm-traced']['expected']['dependencySha256'],
         'archiveEvidenceMatches':True,'httpModes':phase14['modes'],
         'comparison':phase14['comparison'],'humanProductionApproval':'REQUIRED',
         'note':'Actual staged app evidence only; this does not certify JEUS/WebLogic/AIX.'}
    (dest/'phase21-summary.json').write_text(json.dumps(out,indent=2)+'\n')
    print('PASS staged application and independent archive identity: '+str(dest/'phase21-summary.json'))
    return 0


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--app',choices=sorted(APP),required=True)
    parser.add_argument('--tomcat-home',default='')
    parser.add_argument('--out-dir',type=Path,default=Path('results/phase21/live'))
    parser.add_argument('--duration',type=float,default=15)
    parser.add_argument('--concurrency',type=int,default=8)
    args=parser.parse_args()
    if not .5<=args.duration<=300 or not 1<=args.concurrency<=32:
        parser.error('invalid bounded test duration/concurrency')
    return process(args)

if __name__=='__main__':raise SystemExit(main())
