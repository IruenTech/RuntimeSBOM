#!/usr/bin/env python3
"""Inspect Maven-shaded release agent only after its real execution test passes."""
import argparse
import hashlib
import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parent.parent


def inspect_jar(jar, smoke_sbom):
    with ZipFile(jar) as z:
        entries=set(z.namelist())
        assert 'com/iruen/shaded/asm/ClassReader.class' in entries, 'relocated official ASM absent'
        assert 'org/objectweb/asm/ClassReader.class' not in entries, 'unshaded ASM leaked'
        assert not any(x.startswith('jdk/internal/org/objectweb/asm/') for x in entries), 'internal ASM included'
        manifest=z.read('META-INF/MANIFEST.MF').decode('utf-8')
        assert 'Premain-Class: com.iruen.runtimesbom.RuntimeSbomAgent' in manifest
        compiled=z.read('com/iruen/runtimesbom/AsmTransformer.class')
        assert compiled[:4]==b'\xca\xfe\xba\xbe'
        major=struct.unpack('>H',compiled[6:8])[0]
        assert major==52, 'expected Java 8 class format, got %d'%major
    bom=json.loads(smoke_sbom.read_text())
    assert bom['bomFormat']=='CycloneDX'
    props={x['name']:x['value'] for x in bom['metadata']['properties']}
    assert int(props['runtimeSbom:transformFailures'])==0
    keys=[(k,int(v)) for k,v in props.items() if k.startswith('runtimeSbom:methodEntry:') and 'Worker#compute(I)I' in k]
    assert sum(v for _,v in keys)==12, 'wrong count of executed methods'
    root=ET.parse(ROOT/'pom.xml').getroot()
    ns={'m':'http://maven.apache.org/POM/4.0.0'}
    deps=[(d.findtext('m:groupId',namespaces=ns),d.findtext('m:artifactId',namespaces=ns),d.findtext('m:version',namespaces=ns)) for d in root.findall('.//m:dependencies/m:dependency',ns)]
    assert ('org.ow2.asm','asm','9.7.1') in deps
    return {'version':'1.0.0-rc16','status':'PASS','evidenceType':'official-shaded-asm-executed',
      'asmDependency':'org.ow2.asm:asm:9.7.1','jar':str(jar),'sha256':hashlib.sha256(jar.read_bytes()).hexdigest(),
      'agentClassMajorVersion':major,'workerMethodEntries':12,'transformFailures':0,
      'note':'Official ASM shaded JAR executed on this test host; does not demonstrate real WAS compatibility.'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--jar',default='target/runtime-sbom-agent-1.0.0-rc16.jar')
    p.add_argument('--sbom',default='target/official-asm-verification/sbom.json')
    p.add_argument('--out',default='results/phase16/official-asm.json')
    a=p.parse_args()
    result=inspect_jar(ROOT/a.jar,ROOT/a.sbom)
    out=ROOT/a.out;out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS official shaded ASM 9.7.1; SHA-256:',result['sha256'])

if __name__=='__main__':main()
