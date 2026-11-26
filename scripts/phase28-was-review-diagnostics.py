#!/usr/bin/env python3
"""Read-only diagnostics for Phase26/28 WAS review gate.

Does not modify test results, approvals, SLO thresholds or runtime artifacts.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

DEFAULT_APPS = ('spring-boot2', 'spring-boot3', 'tomcat9', 'tomcat10')


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    try:
        obj = json.loads(Path(path).read_text(encoding='utf-8'))
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def evaluate(app, summary_path, agent_path=None, max_tps_drop=15., max_p95_rise=25.):
    checks = {}
    problems = []
    def check(key, ok, message):
        checks[key] = bool(ok)
        if not ok: problems.append(message)
    p = Path(summary_path)
    data = read_json(p)
    if data is None:
        check('summaryReadable', False, 'Missing or invalid JSON: '+str(p))
        return {'application':app, 'status':'UNVERIFIED', 'checks':checks,'problems':problems,
                'metrics':{},'summaryPath':str(p)}
    check('summaryReadable', True, '')
    check('summaryPass', data.get('status') == 'PASS', 'phase21 summary status is not PASS')
    check('applicationMatches', data.get('application') == app, 'Wrong application in phase21-summary.json')
    check('officialEvidenceMode', data.get('evidenceMode') == 'OFFICIAL_SHADED_RUNTIME',
          'Not official exact-binary runtime evidence')
    agent_sha = data.get('officialJarSha256')
    check('officialJarShaPresent', isinstance(agent_sha,str) and len(agent_sha)==64 and
          all(ch in '0123456789abcdefABCDEF' for ch in agent_sha), 'Official Agent SHA-256 missing/invalid')
    if agent_path is not None:
        agent_file=Path(agent_path)
        check('officialJarFilePresent', agent_file.is_file(), 'Official JAR not found: '+str(agent_file))
        if agent_file.is_file():
            check('officialJarShaMatchesFile', agent_sha == sha256_file(agent_file),
                  'Runtime official JAR SHA differs from downloaded binary')
    check('archiveEvidenceMatches', data.get('archiveEvidenceMatches') is True,
          'Application and embedded dependency archive verification mismatch')
    for key in ('applicationArchiveSha256','embeddedDependencySha256'):
        value=data.get(key)
        check(key+'Present', isinstance(value,str) and len(value)==64,
              key+' missing/invalid')
    modes = data.get('httpModes') if isinstance(data.get('httpModes'), dict) else {}
    extracted={}
    for mode in ('baseline','loaded-only','asm-traced'):
        m = modes.get(mode) if isinstance(modes.get(mode),dict) else {}
        http=m.get('http') if isinstance(m.get('http'),dict) else {}
        ev=m.get('evidence') if isinstance(m.get('evidence'),dict) else {}
        extracted[mode]={'tps':http.get('successTps'), 'errorRate':http.get('errorRate'),
                         'p95':http.get('latencyMs',{}).get('p95') if isinstance(http.get('latencyMs'),dict) else None,
                         'purlFound':ev.get('purlFound'), 'methodExecuted':ev.get('methodExecuted')}
        check(mode+'HttpSuccess', finite(http.get('successTps')) and http['successTps']>0,
              mode+' missing/invalid HTTP successTps')
        # Existing base gate tests selected HTTP performance fields; this adds troubleshooting context.
        if 'errorRate' in http:
            check(mode+'HttpErrorFree', finite(http['errorRate']) and http['errorRate']==0,
                  mode+' HTTP request errors present')
    check('asmPurlFound', extracted['asm-traced']['purlFound'] is True,
          'ASM trace did not resolve commons-lang3 Maven PURL')
    check('asmMethodExecuted', extracted['asm-traced']['methodExecuted'] is True,
          'ASM trace has no METHOD_EXECUTED evidence')
    check('loadingOnlyNoMethodExecuted', extracted['loaded-only']['methodExecuted'] is False,
          'Loading-only run unexpectedly contains METHOD_EXECUTED')
    cmp=data.get('comparison') if isinstance(data.get('comparison'),dict) else {}
    tps=cmp.get('tpsDeltaPercent')
    p95=cmp.get('p95DeltaPercent')
    check('tpsDeltaPresent', finite(tps), 'TPS delta unavailable/not finite')
    check('p95DeltaPresent', finite(p95), 'P95 delta unavailable/not finite')
    if finite(tps):
        check('tpsSlo', tps >= -max_tps_drop,
              'TPS SLO exceeded: measured %s%%, minimum allowed -%s%%' % (tps,max_tps_drop))
    if finite(p95):
        check('p95Slo', p95 <= max_p95_rise,
              'P95 SLO exceeded: measured +%s%%, maximum allowed +%s%%' % (p95,max_p95_rise))
    # Diagnostic alone does not grant release approval; original fail-closed review remains the authority.
    result='DIAGNOSTIC_CHECKS_PASS' if all(checks.values()) else 'DIAGNOSTIC_FAILURE'
    return {'application':app,'status':result,'summaryPath':str(p), 'checks':checks,
            'problems':problems, 'metrics':{'modes':extracted,'tpsDeltaPercent':tps,'p95DeltaPercent':p95,
            'tpsMinimumPercent':-max_tps_drop,'p95MaximumPercent':max_p95_rise},
            'officialJarSha256':agent_sha,'note':'Read-only diagnostic; cannot authorize staging or production.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app',action='append',choices=DEFAULT_APPS,
                   help='App(s) to diagnose; default is all four')
    p.add_argument('--live-dir',type=Path,default=Path('results/phase22/live'))
    p.add_argument('--agent',type=Path,default=Path('target/runtime-sbom-agent-1.0.0-rc16.jar'))
    p.add_argument('--out',type=Path,default=Path('results/phase28/was-review-diagnostics.json'))
    a=p.parse_args()
    apps=tuple(a.app) if a.app else DEFAULT_APPS
    agent=a.agent if a.agent.is_file() else None
    reports={app:evaluate(app,a.live_dir/app/'phase21-summary.json',agent) for app in apps}
    payload={'status':'DIAGNOSTICS_ONLY','reports':reports}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for app,result in reports.items():
        print(app, result['status'])
        print('  delta:', result['metrics'].get('tpsDeltaPercent'),
              'TPS %,',result['metrics'].get('p95DeltaPercent'),'P95 %')
        for problem in result['problems']:print('  -',problem)
    print('Wrote diagnostic:',a.out)
    return 0  # Diagnostic output must not hide/falsely replace original gate failure.

if __name__=='__main__':raise SystemExit(main())
