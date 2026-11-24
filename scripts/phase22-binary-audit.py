#!/usr/bin/env python3
"""Strict Java 8 / shaded ASM *structural* binary audit.

Does not establish artifact provenance or production readiness. Fails closed.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
from zipfile import ZipFile, BadZipFile

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / 'target/runtime-sbom-agent-1.0.0-rc16.jar'


def previous_audit(jar):
    spec=importlib.util.spec_from_file_location('phase22_previous_audit',ROOT/'scripts/phase18-audit-jar.py')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.audit(Path(jar))


def audit(jar):
    jar=Path(jar)
    base=previous_audit(jar)
    checks={'phase18StructuralChecks':base.get('status')=='PASS'}
    findings=[]
    class_counts={'agent':0, 'shadedAsm':0}
    if jar.is_file():
        try:
            with ZipFile(jar) as z:
                names=z.namelist()
                checks['noDuplicateZipEntries']=len(names)==len(set(names))
                # Root classes need to be compatible with Java 8. META-INF/versions/9+
                # classes, if any, are excluded because they never load on Java 8.
                for name in names:
                    if not name.endswith('.class') or name.startswith('META-INF/versions/'):
                        continue
                    if name.startswith('com/iruen/runtimesbom/'):
                        class_counts['agent']+=1
                    if name.startswith('com/iruen/shaded/asm/'):
                        class_counts['shadedAsm']+=1
                    data=z.read(name)
                    major=struct.unpack('>H',data[6:8])[0] if len(data)>8 and data[:4]==b'\xca\xfe\xba\xbe' else 65535
                    if major>52:
                        findings.append({'class':name,'major':major})
                checks['everyRootClassJava8Compatible']=len(findings)==0
                checks['shadedAsmClassesPresent']=class_counts['shadedAsm']>=7
                checks['agentClassesPresent']=class_counts['agent']>=7
        except (OSError,KeyError,BadZipFile,ValueError) as exc:
            checks['archiveReadable']=False
            findings.append({'error':str(exc)})
    else:
        checks['artifactAvailable']=False
    status='PASS' if all(checks.values()) else 'FAIL'
    return {'schemaVersion':1,'stage':22,'status':status,'artifact':str(jar),
            'sha256':base.get('sha256'),'checks':checks,'classCounts':class_counts,
            'incompatibleClasses':findings[:30],
            'previousAudit':base,
            'provenance':'NOT_ATTESTED',
            'scope':'Structural Java 8 / shaded-ASM compatibility only; not proof of official-source origin'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--agent',type=Path,default=AGENT)
    p.add_argument('--out',type=Path,default=ROOT/'results/phase22/binary-audit.json')
    a=p.parse_args()
    result=audit(a.agent)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'sha256':result['sha256'],
        'failed':[k for k,v in result['checks'].items() if not v],
        'provenance':result['provenance']},ensure_ascii=False))
    return 0 if result['status']=='PASS' else 2

if __name__=='__main__':sys.exit(main())
