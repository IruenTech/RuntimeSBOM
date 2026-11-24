#!/usr/bin/env python3
"""Structural audit of an Agent binary. Not a supply-chain attestation.

Missing shaded ASM or Java 8 compatibility is FAIL. The SHA-256 is useful for
linking field evidence to *exactly the same binary*, but it does not verify who
built the binary or the integrity of its dependencies.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from zipfile import ZipFile, BadZipFile

EXPECTED = {
    'com/iruen/runtimesbom/RuntimeSbomAgent.class',
    'com/iruen/runtimesbom/AsmTransformer.class',
    'com/iruen/runtimesbom/Recorder.class',
    'com/iruen/shaded/asm/ClassReader.class',
    'com/iruen/shaded/asm/ClassWriter.class',
    'com/iruen/shaded/asm/ClassVisitor.class',
    'com/iruen/shaded/asm/MethodVisitor.class',
}

def audit(path):
    p = Path(path)
    result = {'schemaVersion':1, 'artifact':str(p), 'status':'FAIL',
              'checks':{}, 'sha256':None, 'limitations':
              ['Structural packaging checks cannot attest official ASM provenance.',
               'Runtime smoke and independent JVM/WAS tests are separately required.']}
    if not p.is_file():
        result['error']='JAR missing'
        return result
    result['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    try:
        with ZipFile(p) as archive:
            names=set(archive.namelist())
            result['checks']['zipIntegrity'] = archive.testzip() is None
            result['checks']['requiredClasses'] = EXPECTED.issubset(names)
            result['checks']['noUnrelocatedAsm'] = not any(name.startswith('org/objectweb/asm/') for name in names)
            manifest=archive.read('META-INF/MANIFEST.MF').decode('utf-8',errors='replace')
            # Maven manifest continuation lines are unfolded per the JAR manifest specification.
            manifest=manifest.replace('\r\n ','').replace('\n ','')
            result['checks']['premainManifest'] = 'Premain-Class: com.iruen.runtimesbom.RuntimeSbomAgent' in manifest
            result['checks']['agentManifest'] = 'Agent-Class: com.iruen.runtimesbom.RuntimeSbomAgent' in manifest
            for name in ('com/iruen/runtimesbom/RuntimeSbomAgent.class',
                         'com/iruen/runtimesbom/AsmTransformer.class',
                         'com/iruen/shaded/asm/ClassReader.class'):
                if name not in names:
                    result['checks']['java8-'+name] = False
                    continue
                buf=archive.read(name)
                result['checks']['java8-'+name] = (len(buf)>8 and buf[:4]==b'\xca\xfe\xba\xbe'
                                        and struct.unpack('>H',buf[6:8])[0]<=52)
            # Ensure references in transformed bytecode were relocated; warn if old ASM class names remain.
            transformer=archive.read('com/iruen/runtimesbom/AsmTransformer.class') if 'com/iruen/runtimesbom/AsmTransformer.class' in names else b''
            result['checks']['transformerUsesShadedAsm'] = (b'com/iruen/shaded/asm/' in transformer
                    and b'org/objectweb/asm/' not in transformer)
            result['checks']['noTestInternalAsm'] = not any(b'jdk/internal/org/objectweb/asm/' in archive.read(name)
                    for name in ('com/iruen/runtimesbom/AsmTransformer.class',) if name in names)
    except (OSError,BadZipFile,KeyError,ValueError) as exc:
        result['error']=type(exc).__name__+': '+str(exc)
        return result
    result['status']='PASS' if all(result['checks'].values()) else 'FAIL'
    return result


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('jar',type=Path)
    ap.add_argument('--out',type=Path)
    args=ap.parse_args()
    result=audit(args.jar)
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'sha256':result['sha256'],
                      'failedChecks':[k for k,v in result['checks'].items() if not v],
                      'error':result.get('error')},indent=2))
    return 0 if result['status']=='PASS' else 2
if __name__=='__main__': sys.exit(main())
