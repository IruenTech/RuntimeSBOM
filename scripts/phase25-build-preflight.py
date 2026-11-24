#!/usr/bin/env python3
"""Check that the *real* ASM 9.7.1 Maven release path is configured.

A PASS configuration does not mean a successful Maven build. No fallback to
jdk.internal.org.objectweb.asm is permitted for a release binary.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
NS = {'m': 'http://maven.apache.org/POM/4.0.0'}


def check_pom(path):
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        ns = NS if root.tag.startswith('{') else {'m': ''}
        def q(name): return 'm:' + name if ns['m'] else name
        deps = root.findall('./' + q('dependencies') + '/' + q('dependency'), ns)
        asm = [(d.findtext(q('groupId'), namespaces=ns), d.findtext(q('artifactId'), namespaces=ns),
                d.findtext(q('version'), namespaces=ns)) for d in deps]
        plugins = root.findall('./' + q('build') + '/' + q('plugins') + '/' + q('plugin'), ns)
        shade = [p for p in plugins if p.findtext(q('artifactId'),namespaces=ns) == 'maven-shade-plugin']
        compiler = [p for p in plugins if p.findtext(q('artifactId'),namespaces=ns) == 'maven-compiler-plugin']
        shade_text = ET.tostring(shade[0],encoding='unicode') if shade else ''
        release = root.findtext('./' + q('properties') + '/' + q('maven.compiler.release'), namespaces=ns)
        return {
            'explicitOfficialAsm971': asm.count(('org.ow2.asm','asm','9.7.1')) == 1,
            'noOtherAsmVersions': all(g != 'org.ow2.asm' or (a,v) == ('asm','9.7.1') for g,a,v in asm),
            'compilerRelease8': release == '8' and bool(compiler),
            'shadingRelocation': 'org.objectweb.asm' in shade_text and 'com.iruen.shaded.asm' in shade_text,
            'premainManifest': 'Premain-Class' in shade_text and 'com.iruen.runtimesbom.RuntimeSbomAgent' in shade_text,
            'noJdkInternalAsmDependency': not any('jdk.internal.org.objectweb.asm' in v for v in (shade_text,ET.tostring(root,encoding='unicode'))),
        }
    except (OSError,ET.ParseError,ValueError) as exc:
        return {'pomParsed':False, 'errorType':type(exc).__name__}


def execute(pom=ROOT/'pom.xml', mvn_path=None, java_path=None, require_toolchain=False):
    checks=check_pom(pom)
    if mvn_path is None: mvn_path=shutil.which('mvn')
    if java_path is None: java_path=shutil.which('java')
    runtime={'mavenInstalled':bool(mvn_path), 'javaInstalled':bool(java_path)}
    if mvn_path:
        try:
            p=subprocess.run([mvn_path,'-version'],capture_output=True,text=True,timeout=12)
            runtime['mavenExecutable']=p.returncode==0
        except (OSError,subprocess.TimeoutExpired):runtime['mavenExecutable']=False
    ok=all(v is True for k,v in checks.items() if k!='errorType') and 'errorType' not in checks
    if require_toolchain:ok=ok and all(runtime.values())
    return {'stage':25,'agentVersion':'1.0.0-rc16','status':'READY_FOR_OFFICIAL_BUILD' if ok else 'HOLD',
            'pomChecks':checks,'runtimeChecks':runtime,'officialMavenBuildExecuted':False,
            'productionDeployment':'HOLD', 'note':'Static configuration/toolchain check, NOT an official ASM binary test'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pom',type=Path,default=ROOT/'pom.xml')
    parser.add_argument('--out',type=Path,default=ROOT/'results/phase25/build-preflight.json')
    parser.add_argument('--require-toolchain',action='store_true')
    args=parser.parse_args()
    result=execute(args.pom,require_toolchain=args.require_toolchain)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='READY_FOR_OFFICIAL_BUILD' else 3

if __name__=='__main__':raise SystemExit(main())
