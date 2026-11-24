#!/usr/bin/env python3
"""Read-only field evidence capture: does not deploy or modify the running WAS.

On JEUS/WebLogic/AIX staging hosts an operator supplies a SBOM produced by the official
agent and a server log. Report states EVIDENCE_CAPTURED_PENDING_REVIEW, never approved.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import struct
from zipfile import ZipFile, BadZipFile
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--was', required=True, choices=['JEUS','WebLogic','Tomcat','SpringBoot','IBM-AIX-JVM'])
    p.add_argument('--asset', required=True)
    p.add_argument('--java', default='java', help='the exact Java executable used by WAS')
    p.add_argument('--sbom', required=True, type=Path)
    p.add_argument('--agent', required=True, type=Path, help='official shaded Agent JAR')
    p.add_argument('--expected-purl', required=True, help='known test library used by staged workload')
    p.add_argument('--server-log', type=Path, help='WAS startup log for separate review (hash only)')
    p.add_argument('--out',type=Path,default=Path('results/phase17/field-evidence.json'))
    a=p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',a.asset):p.error('invalid asset identifier')
    if not a.agent.is_file() or not a.sbom.is_file():p.error('SBOM and official Agent JAR must exist')
    if not a.agent.name.endswith('.jar'):p.error('expected Agent JAR')
    # Reject test-only internal ASM JARs and an unshaded build.
    try:
        with ZipFile(a.agent) as archive:
            names=set(archive.namelist())
            if 'com/iruen/shaded/asm/ClassReader.class' not in names or 'org/objectweb/asm/ClassReader.class' in names:
                p.error('Agent JAR is not the official relocated-ASM build')
            manifest=archive.read('META-INF/MANIFEST.MF').decode('utf-8')
            if 'Premain-Class: com.iruen.runtimesbom.RuntimeSbomAgent' not in manifest:
                p.error('Agent premain manifest missing')
            cls=archive.read('com/iruen/runtimesbom/AsmTransformer.class')
            if cls[:4]!=b'\xca\xfe\xba\xbe' or struct.unpack('>H',cls[6:8])[0]!=52:
                p.error('Agent bytecode is not Java 8 compatible')
    except (OSError,KeyError,BadZipFile,ValueError) as e:
        p.error('Cannot validate official Agent JAR: '+str(e))
    try:
        ver=subprocess.run([a.java,'-version'],timeout=12,capture_output=True,text=True)
        version=(ver.stdout+ver.stderr).splitlines()[:3]
    except (OSError,subprocess.TimeoutExpired) as e:
        p.error('cannot execute selected Java executable: '+str(e))
    bom=json.loads(a.sbom.read_text(encoding='utf-8'))
    if bom.get('bomFormat')!='CycloneDX':p.error('not a CycloneDX document')
    matches=[]
    for c in bom.get('components',[]):
        if c.get('purl') != a.expected_purl:continue
        props={x['name']:x['value'] for x in c.get('properties',[]) if 'name' in x and 'value' in x}
        matches.append({'component':c.get('name'), 'version':c.get('version'),
                        'classLoader':props.get('runtimeSbom:classLoader'),
                        'runtimeEvidenceState':props.get('runtimeSbom:runtimeEvidenceState'),
                        'methodEntryCount':props.get('runtimeSbom:observedMethodEntryCount')})
    evidence={'schemaVersion':1,'assetId':a.asset,'reportedEnvironment':a.was,
              'timestampUtc':dt.datetime.now(dt.timezone.utc).isoformat(),
              'javaVersionOutput':version,'agentJarSha256':sha(a.agent),
              'sbomSha256':sha(a.sbom),'serverLogSha256':sha(a.server_log) if a.server_log else None,
              'expectedPurl':a.expected_purl,'matchingComponents':matches,
              'status':'EVIDENCE_CAPTURED_PENDING_REVIEW' if matches else 'MISSING_EXPECTED_LIBRARY',
              'productionApproval':'HOLD',
              'caveat':'Operator-provided evidence is not independently attested or vendor-certified.'}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':evidence['status'],'matches':len(matches),
                     'productionApproval':'HOLD','report':str(a.out)},indent=2))
    return 0 if matches else 3

if __name__=='__main__':raise SystemExit(main())
