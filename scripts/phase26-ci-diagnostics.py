#!/usr/bin/env python3
"""Phase26: preserve actionable diagnoses of *real* CI failures.

A diagnostic is NOT proof that a build or a live-WAS run succeeded.
Supports Maven build logs and the Phase14 live test's server log/SBOM.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
ANSI = re.compile(r'\x1b\[[0-9;]*m')
RULES = (
    ('MAVEN_UNAVAILABLE', r'(?:mvn: command not found|mvn: not found|Maven required|MAVEN_MISSING)',
     'Install Maven (or run via GitHub Actions setup-java) and retry.'),
    ('DEPENDENCY_OR_PLUGIN', r'(?:Non-resolvable parent POM|Could not (?:resolve|find) artifact|PluginResolutionException|Could not resolve dependencies|Failed to collect dependencies)',
     'Inspect first Maven [ERROR] cause and repository access; do not substitute dependencies.'),
    ('DNS_OR_TLS', r'(?:UnknownHostException|Temporary failure in name resolution|Name or service not known|PKIX path building failed|SSLHandshakeException)',
     'Check Maven repository DNS, HTTPS trust, and organizational proxy.'),
    ('JDK_COMPATIBILITY', r'(?:UnsupportedClassVersionError|invalid target release|release version \d+ not supported|Source option \d+ is no longer supported|class file has wrong version)',
     'Confirm compile/run Java versions and release target (Boot2 Java 8, Boot3 Java 17).'),
    ('JAVA_COMPILATION', r'(?:COMPILATION ERROR|Compilation failure|Failed to execute goal.*maven-compiler-plugin|cannot find symbol|package [\w.]+ does not exist|\[ERROR\].*\.java:\[\d+)',
     'Read first compiler diagnostic; fix source/API mismatch before running the WAS.'),
    ('MAVEN_TEST_FAILURE', r'(?:There are test failures|maven-surefire-plugin.*failed|Failed to execute goal.*surefire)',
     'Inspect target/surefire-reports and fix tests; do not bypass with an approval flag.'),
    ('MAVEN_PACKAGING', r'(?:Failed to execute goal.*(?:spring-boot-maven-plugin|maven-jar-plugin|maven-war-plugin)|repackage failed)',
     'Inspect the packaging plugin exception and confirm main class/artifact layout.'),
    ('ASM_CLASSLOADER', r'(?:java\.lang\.VerifyError|NoClassDefFoundError|ClassNotFoundException|LinkageError)',
     'Inspect Agent/ASM shading and class loader accessibility; preserve server.log.'),
    ('MISSING_RUNTIME_PURL', r'(?:Missing exact commons-lang3 Maven PURL|MISSING_PURL)',
     'Inspect nested JAR metadata extraction and class-source path.'),
    ('MISSING_METHOD_EXECUTION', r'(?:actual METHOD_EXECUTED evidence|MISSING_METHOD_EXECUTION)',
     'Inspect tracePackages, transformer logs, and Recorder evidence attribution.'),
    ('HTTP_STARTUP', r'(?:server exited early|health endpoint timeout|Connection refused|Address already in use)',
     'Inspect server.log for startup stacktrace and JVM options.'),
)

def redact(line: str):
    # Artifact logs may contain private Maven repository URLs or HTTP tokens.
    line=re.sub(r'(https?://)[^@/\s:]+:[^@/\s]+@',r'\1[REDACTED]@',line,flags=re.I)
    line=re.sub(r'(?i)\b(password|access_token|api_key|secret|authorization)\b(\s*[=:]\s*)[^\s,;]+',
                r'\1\2[REDACTED]',line)
    return line

def classify_text(s: str):
    s = ANSI.sub('', s)
    codes = [{'code': code, 'recommendedAction': advice} for code, patt, advice in RULES if re.search(patt, s, re.I)]
    error_lines = [redact(line.strip()[:450]) for line in s.splitlines() if '[ERROR]' in line or 'Caused by:' in line or 'Exception in thread' in line]
    return {'classification': 'BUILD_OR_TEST_FAILED' if codes or 'BUILD FAILURE' in s or 'RuntimeError:' in s else
            'BUILD_SUCCESS' if 'BUILD SUCCESS' in s else 'INCONCLUSIVE',
            'codes': codes, 'mavenErrorExcerpts': error_lines[:18],
            'failureDetected': bool(codes or 'BUILD FAILURE' in s or 'RuntimeError:' in s)}

def inspect_file(path: Path):
    if not path.is_file():
        return {'available': False, 'relativeFile': str(path), 'classification': 'MISSING_LOG', 'codes': []}
    raw = path.read_bytes()
    obj = classify_text(raw.decode('utf-8', 'replace')[-2_000_000:])
    return {'available': True, 'relativeFile': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw), **obj}

def evidence_diagnostic(bom):
    """Report the actual root condition; never report PASS for an unrecognized component."""
    purl='pkg:maven/org.apache.commons/commons-lang3@3.14.0'
    comps=bom.get('components', []) if isinstance(bom,dict) else []
    exact=[c for c in comps if c.get('purl')==purl]
    suspected=[c for c in comps if 'commons-lang3' in ' '.join((
        str(c.get('name','')), str(next((x.get('value','') for x in c.get('properties',[]) if x.get('name')=='runtimeSbom:source'),''))
    ))]
    found=[]
    for c in exact:
        props={p.get('name'):p.get('value') for p in c.get('properties',[]) if isinstance(p,dict)}
        found.append({'name':c.get('name'),'purl':c.get('purl'),'state':props.get('runtimeSbom:runtimeEvidenceState'),
                      'count':int(props.get('runtimeSbom:observedMethodEntryCount') or 0)})
    codes=[]
    if not exact: codes.append('MISSING_PURL')
    elif not any(v['state']=='METHOD_EXECUTED' and v['count']>0 for v in found): codes.append('MISSING_METHOD_EXECUTION')
    return {'status':'PASS' if not codes else 'FAIL','codes':codes,'matchingComponents':found,
            'suspectedComponentNames':[c.get('name') for c in suspected][:8],
            'metadataOrInstrumentationRootCause':'PURL_METADATA' if 'MISSING_PURL' in codes else
                'METHOD_EVIDENCE' if 'MISSING_METHOD_EXECUTION' in codes else None}

def write_report(paths, sbom=None, out=None):
    entries=[inspect_file(Path(p)) for p in paths]
    ev=None
    if sbom is not None:
        try: ev=evidence_diagnostic(json.loads(Path(sbom).read_text(encoding='utf-8')))
        except (OSError,ValueError,TypeError) as exc:ev={'status':'INCONCLUSIVE','error':type(exc).__name__}
    report={'stage':26,'kind':'CI_DIAGNOSTICS_NOT_BUILD_PROOF','logs':entries,'sbomEvidence':ev,
            'productionDeployment':'HOLD','note':'Only actual CI logs establish Maven build status.'}
    if out:
        Path(out).parent.mkdir(parents=True,exist_ok=True)
        Path(out).write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--log',action='append',default=[])
    p.add_argument('--sbom',type=Path)
    p.add_argument('--out',type=Path,default=ROOT/'results/phase26/diagnostics.json')
    a=p.parse_args()
    report=write_report(a.log,a.sbom,a.out)
    print(json.dumps({'logStatus':[x['classification'] for x in report['logs']],
                      'evidenceStatus':report['sbomEvidence']['status'] if report['sbomEvidence'] else None,
                      'out':str(a.out)},ensure_ascii=False,indent=2))
    return 0 # diagnosis does not conceal the original job result
if __name__=='__main__':raise SystemExit(main())
