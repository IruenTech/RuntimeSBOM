#!/usr/bin/env python3
"""Classify CI failures from real logs, preserving hashes but not raw secret-bearing logs.

This is a diagnostic helper, NOT a substitute for successful CI execution.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent.parent
RULES=(
    ('MAVEN_MISSING',r'(?:mvn: command not found|mvn: not found|Maven not installed)',
     'Install Maven and rerun the official release build.'),
    ('NETWORK_DNS',r'(?:Could not resolve host|Temporary failure in name resolution|UnknownHostException|Name or service not known)',
     'Allow DNS and HTTPS access to the approved Maven Central mirror; do not substitute test ASM.'),
    ('MAVEN_DEPENDENCY',r'(?:Could not (?:find|resolve) artifact|Could not resolve dependencies|Non-resolvable parent POM|DependencyResolutionException|Failed to collect dependencies)',
     'Verify repository access, pinned coordinates and dependency cache; retain Maven dependency tree.'),
    ('MAVEN_PLUGIN',r'(?:PluginResolutionException|No plugin found for prefix|Plugin .* could not be resolved)',
     'Check Maven plugin versions and repository/mirror configuration.'),
    ('JAVA_RELEASE',r'(?:release version \d+ not supported|invalid target release|invalid flag: --release|UnsupportedClassVersionError|has been compiled by a more recent version)',
     'Verify the active JDK and ensure all release classes target Java 8 (major <= 52).'),
    ('COMPILATION',r'(?:COMPILATION ERROR|cannot find symbol|package org\.objectweb\.asm does not exist|incompatible types:)',
     'Inspect compilation errors for API mismatches; keep official ASM 9.7.1 dependency.'),
    ('ASM_LINKAGE',r'(?:NoClassDefFoundError.*(?:asm|Recorder)|ClassNotFoundException.*(?:asm|Recorder)|NoSuchMethodError.*(?:asm|Recorder)|IllegalAccessError.*(?:asm|Recorder))',
     'Inspect ASM shading and ClassLoader visibility of the identical Recorder class.'),
    ('BYTECODE_VERIFICATION',r'(?:java\.lang\.VerifyError|VerifyError:|ClassFormatError|IncompatibleClassChangeError)',
     'Capture class name/JVM version; check ASM stack-map frames and fail-open transformation.'),
    ('ARTIFACT_IDENTITY',r'(?:SHA-256 mismatch|artifact SHA mismatch|different Agent binary|exactArtifactSha256.*false|shadedAsmClassesPresent.*false)',
     'Regenerate evidence using the identical original shaded Agent JAR.'),
    ('HTTP_STARTUP',r'(?:health endpoint timeout|server exited early|Connection refused|Address already in use)',
     'Inspect staging server logs, port conflicts and startup health checks; do not claim a live test passed.'),
    ('RESOURCE_TIMEOUT',r'(?:Timed out after|subprocess\.TimeoutExpired|The operation was canceled|exit code 124)',
     'Repeat on a controlled runner with recorded timeouts and resource limits.'),
)

def diagnose(text):
    matches=[]
    for code,pattern,action in RULES:
        if re.search(pattern,text,re.I|re.M):matches.append({'code':code,'recommendedAction':action})
    return {'status':'BLOCKED' if matches else 'INCONCLUSIVE',
            'diagnoses':matches,'recognizedFailureCount':len(matches),
            'officialBuildPassed':False,'productionDeployment':'HOLD'}


def evaluate(logs):
    items=[]
    for raw in logs:
        file=Path(raw)
        if not file.is_file():
            items.append({'path':str(file),'available':False,'status':'MISSING_LOG','diagnoses':[]})
            continue
        data=file.read_bytes()
        result=diagnose(data.decode('utf-8','replace')[-2_000_000:])
        items.append({'path':str(file),'available':True,
                      'logSha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),**result})
    return {'stage':25,'reportType':'CI_FAILURE_DIAGNOSTICS','inputs':items,
            'status':'ISSUES_IDENTIFIED' if any(x.get('recognizedFailureCount',0)>0 for x in items) else 'NO_CLASSIFIED_FAILURE',
            'officialBuildPassed':False,'productionDeployment':'HOLD',
            'note':'Log-pattern diagnosis only; no execution or official build is implied'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--log',action='append',required=True,type=Path)
    p.add_argument('--out',type=Path,default=ROOT/'results/phase25/ci-diagnostics.json')
    a=p.parse_args(); report=evaluate(a.log)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'stage':25,'status':report['status'],
                      'diagnosticCodes':[[d['code'] for d in x.get('diagnoses',[])] for x in report['inputs']]},indent=2))
    return 0 # Diagnostics must never hide an upstream step failure.

if __name__=='__main__':raise SystemExit(main())
