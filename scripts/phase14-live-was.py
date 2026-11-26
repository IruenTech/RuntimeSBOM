#!/usr/bin/env python3
"""Isolated loopback live-WAS HTTP integration: baseline, load-only, ASM-traced.

Requires a Maven-built official ASM shaded agent and a staging JDK. Never contacts
production or accepts a remote URL. Reports remain diagnostic until approved.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / 'target/runtime-sbom-agent-1.0.0-rc16.jar'
APPS = {
    'spring-boot2': ('integration/apps/spring-boot2', 'target/sbom-spring-demo-1.0.0.jar', 8),
    'spring-boot3': ('integration/apps/spring-boot3', 'target/sbom-spring-demo-1.0.0.jar', 17),
    'tomcat9': ('integration/apps/tomcat9-war', 'target/sbom-demo.war', 8),
    'tomcat10': ('integration/apps/tomcat10-war', 'target/sbom-demo.war', 11),
}


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def jdk_major():
    p = subprocess.run(['java', '-version'], capture_output=True, text=True, check=True)
    match = re.search(r'version "(?:1\.)?(\d+)', p.stderr + p.stdout)
    if not match:
        raise RuntimeError('Cannot determine JDK version')
    return int(match.group(1))


def process_sample(pid):
    """Linux /proc values only. Unsupported OS has nulls, never fabricated numbers."""
    try:
        status = Path('/proc/%d/status' % pid).read_text()
        rss = re.search(r'^VmRSS:\s+(\d+) kB', status, re.M)
        hwm = re.search(r'^VmHWM:\s+(\d+) kB', status, re.M)
        stat = Path('/proc/%d/stat' % pid).read_text().split(') ', 1)[1].split()
        # After stripping pid/(comm), state is offset 0, utime/stime are offset 11/12.
        ticks = os.sysconf('SC_CLK_TCK')
        return {'rssKiB': int(rss.group(1)) if rss else None,
                'peakRssKiB': int(hwm.group(1)) if hwm else None,
                'cpuTimeSeconds': round((int(stat[11]) + int(stat[12]))/ticks, 3)}
    except (OSError, ValueError, IndexError, AttributeError):
        return {'rssKiB': None, 'peakRssKiB': None, 'cpuTimeSeconds': None}


def watch_process(pid, done, rows):
    while not done.wait(0.2):
        rows.append({'t': time.time(), **process_sample(pid)})


def until_ready(url, child, deadline_seconds=75):
    deadline = time.monotonic()+deadline_seconds
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError('server exited early, rc=%s' % child.returncode)
        try:
            with urllib.request.urlopen(url, timeout=0.5) as r:
                if r.status == 200 and r.read(200).decode('utf-8').strip() == 'mobs-emitnur':
                    return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError('health endpoint timeout')


def stop(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=12)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def prepare_tomcat(home, base, war_path, port):
    if not home or not (Path(home)/'bin/catalina.sh').is_file():
        raise RuntimeError('CATALINA_HOME_TOMCATx must point to an extracted Tomcat installation')
    conf = base/'conf'
    shutil.copytree(Path(home)/'conf', conf)
    for name in ('logs','work','temp','webapps'):
        (base/name).mkdir(parents=True, exist_ok=True)
    target = base/'webapps/sbom-demo.war'
    shutil.copy2(war_path, target)
    xml = (conf/'server.xml').read_text()
    # Isolated base with dynamic connector; disable default shutdown port.
    xml, shutdown_changes = re.subn(r'<Server\s+port="8005"', '<Server port="-1"', xml, count=1)
    xml, connector_changes = re.subn(r'<Connector\s+port="8080"', '<Connector address="127.0.0.1" port="%d"' % port, xml, count=1)
    if shutdown_changes != 1 or connector_changes != 1:
        raise RuntimeError('Unexpected server.xml template; refusing to alter arbitrary Tomcat config')
    parsed=ET.fromstring(xml)
    active_connectors=parsed.findall('.//Connector')
    if len(active_connectors)!=1 or active_connectors[0].get('address')!='127.0.0.1':
        raise RuntimeError('Unexpected active Tomcat connectors; refusing unsafe test configuration')
    (conf/'server.xml').write_text(xml)
    return target


def gc_sample(pid):
    """Read portable JDK jstat counters when supported; no assumed values on failure."""
    if not shutil.which('jstat'):
        return {'availability':'jstat-unavailable'}
    try:
        p=subprocess.run(['jstat','-gc',str(pid)],capture_output=True,text=True,timeout=4)
        if p.returncode:
            return {'availability':'jstat-failed','reason':p.stderr[-160:]}
        rows=[line.split() for line in p.stdout.splitlines() if line.strip()]
        if len(rows)<2 or len(rows[0])!=len(rows[1]):
            return {'availability':'jstat-format-unsupported'}
        counters=dict(zip(rows[0],rows[1]))
        return {'availability':'jstat-gc', 'youngCollections':int(float(counters['YGC'])),
                'fullCollections':int(float(counters['FGC'])),
                'youngGcSeconds':float(counters['YGCT']), 'fullGcSeconds':float(counters['FGCT']),
                'heapOccupiedKiB':sum(float(counters[k]) for k in ('S0U','S1U','EU','OU') if k in counters)}
    except (ValueError,KeyError,OSError,subprocess.TimeoutExpired) as e:
        return {'availability':'jstat-failed','reason':type(e).__name__}


def get_props(bom):
    return lambda c: {p.get('name'):p.get('value') for p in c.get('properties', [])}


def evidence_from_sbom(bom_path):
    bom = json.loads(Path(bom_path).read_text())
    if bom.get('bomFormat') != 'CycloneDX':
        raise RuntimeError('Invalid CycloneDX output')
    selected = [c for c in bom.get('components', []) if c.get('purl')=='pkg:maven/org.apache.commons/commons-lang3@3.14.0']
    found = []
    for c in selected:
        p = get_props(bom)(c)
        if p.get('runtimeSbom:runtimeEvidenceState')=='METHOD_EXECUTED':
            found.append({'purl':c['purl'], 'observedMethodEntryCount':int(p.get('runtimeSbom:observedMethodEntryCount','0')), 'classLoader':p.get('runtimeSbom:classLoader')})
    return {'purlFound': bool(selected), 'methodExecuted': any(x['observedMethodEntryCount']>0 for x in found), 'observed':found}


def run_mode(args, archive, workdir, port, mode):
    out=workdir/mode
    out.mkdir(parents=True, exist_ok=True)
    sbom=out/'sbom.json'
    log=out/'server.log'
    agent_opt='-javaagent:%s=output=%s,interval=1,resourceProbe=true,sampleEvery=1' % (AGENT,sbom)
    if mode == 'asm-traced':
        agent_opt += ',tracePackages=org.apache.commons.lang3'
    env=os.environ.copy()
    if args.app.startswith('spring'):
        cmd=['java']
        if mode!='baseline': cmd.append(agent_opt)
        cmd.extend(['-jar',str(archive),'--server.address=127.0.0.1','--server.port=%d' % port])
        url='http://127.0.0.1:%d/health/sbom' % port
    else:
        home=Path(args.tomcat_home).resolve()
        base=out/'base'
        prepare_tomcat(home,base,archive,port)
        env['CATALINA_HOME']=str(home)
        env['CATALINA_BASE']=str(base)
        env['CATALINA_OPTS']=agent_opt if mode!='baseline' else ''
        cmd=['sh',str(home/'bin/catalina.sh'),'run']
        url='http://127.0.0.1:%d/sbom-demo/health/sbom' % port
    samples=[]
    with log.open('w') as f:
        child=subprocess.Popen(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,env=env)
        done=threading.Event()
        watch=threading.Thread(target=watch_process,args=(child.pid,done,samples),daemon=True)
        watch.start()
        try:
            until_ready(url,child)
            report=out/'http.json'
            p=subprocess.run([sys.executable,str(ROOT/'scripts/http-load.py'),'--url',url,'--duration',str(args.duration),
                 '--concurrency',str(args.concurrency),'--expect','mobs-emitnur','--out',str(report)],
                 capture_output=True,text=True,timeout=args.duration+45)
            if p.returncode: raise RuntimeError('load generator failed: '+(p.stderr+p.stdout)[-1200:])
            http=json.loads(report.read_text())
            gc=gc_sample(child.pid)
        except Exception as exc:
            raise RuntimeError('%s %s: %s; server log tail: %s' % (args.app,mode,exc,log.read_text(errors='replace')[-1200:]))
        finally:
            stop(child)
            done.set()
            watch.join(timeout=2)
    metrics={'availability':'linux-proc-only', 'gcStats':gc,'samples':len(samples),
             'rssPeakKiB':max([s['rssKiB'] for s in samples if s['rssKiB'] is not None], default=None),
             'cpuTimeSeconds':samples[-1]['cpuTimeSeconds'] if samples else None}
    (out/'process-samples.json').write_text(json.dumps({'pid':child.pid,'samples':samples},indent=2)+'\n')
    evidence=None
    if mode!='baseline':
        if not sbom.exists():raise RuntimeError('SBOM was not written at JVM shutdown for '+mode)
        evidence=evidence_from_sbom(sbom)
        if mode=='loaded-only' and evidence['methodExecuted']:
            raise RuntimeError('Loading-only mode must not claim executed methods')
        if mode=='asm-traced' and not (evidence['purlFound'] and evidence['methodExecuted']):
            import importlib.util
            spec=importlib.util.spec_from_file_location('phase26evidence',str(ROOT/'scripts/phase26-ci-diagnostics.py'))
            diagnostic=importlib.util.module_from_spec(spec);spec.loader.exec_module(diagnostic)
            cause=diagnostic.evidence_diagnostic(json.loads(sbom.read_text()))
            (out/'phase26-evidence-diagnostic.json').write_text(json.dumps(cause,indent=2)+'\n')
            raise RuntimeError('%s: commons-lang3 PURL/evidence requirement not met; %s' %
                               (','.join(cause['codes']) or 'UNCLASSIFIED',out/'phase26-evidence-diagnostic.json'))
    return {'http':http,'process':metrics,'evidence':evidence}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--app',choices=APPS,required=True)
    p.add_argument('--duration',type=float,default=3)
    p.add_argument('--concurrency',type=int,default=4)
    p.add_argument('--tomcat-home',default=os.environ.get('CATALINA_HOME',''))
    p.add_argument('--out-dir',default='results/phase14/live')
    a=p.parse_args()
    if a.duration<0.5 or a.duration>3600 or a.concurrency<1 or a.concurrency>64:p.error('duration/concurrency outside bounded test limits')
    required=APPS[a.app][2]
    if jdk_major()<required:p.error('%s requires Java %d+'%(a.app,required))
    if not AGENT.is_file():p.error('Official shaded agent missing; run mvn clean package first')
    from importlib.machinery import SourceFileLoader
    audit=SourceFileLoader('phase18audit',str(ROOT/'scripts/phase18-audit-jar.py')).load_module().audit(AGENT)
    if audit['status']!='PASS':p.error('Official shaded Agent packaging audit failed')
    if not shutil.which('mvn'):p.error('Maven required to build real Spring Boot/Tomcat example')
    workdir=(ROOT/a.out_dir/a.app).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    basedir=ROOT/APPS[a.app][0]
    build=subprocess.run(['mvn','-B','-DskipTests','clean','package'],cwd=basedir,capture_output=True,text=True,timeout=240)
    (workdir/'build.log').write_text(build.stdout+'\n'+build.stderr)
    if build.returncode:
        # Prior CI only displayed a Python RuntimeError and hid the Maven root cause
        # in a downloadable artifact. Make the relevant Maven errors visible in CI.
        import importlib.util
        spec=importlib.util.spec_from_file_location('phase26diag',str(ROOT/'scripts/phase26-ci-diagnostics.py'))
        diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)
        result=diag.inspect_file(workdir/'build.log')
        (workdir/'phase26-build-diagnostic.json').write_text(json.dumps(result,indent=2)+'\n')
        print('PHASE26_MAVEN_BUILD_DIAGNOSTIC:',json.dumps(result,ensure_ascii=False),flush=True)
        if result['mavenErrorExcerpts']:
            print('Maven errors (first 18):\n'+'\n'.join(result['mavenErrorExcerpts']),flush=True)
        raise RuntimeError('%s Maven build failed (diagnostic=%s); log=%s' %
                           (a.app,','.join(v['code'] for v in result['codes']) or 'UNCLASSIFIED',workdir/'build.log'))
    archive=basedir/APPS[a.app][1]
    if not archive.is_file():raise RuntimeError('Missing compiled app: '+str(archive))
    output={}
    for mode in ('baseline','loaded-only','asm-traced'):
        output[mode]=run_mode(a,archive,workdir,free_port(),mode)
        print('PASS',a.app,mode, 'tps=', output[mode]['http']['successTps'],flush=True)
    base=output['baseline']['http']; asm=output['asm-traced']['http']
    tps_delta=(asm['successTps']/base['successTps']-1)*100 if base['successTps']>0 else None
    p95_delta=(asm['latencyMs']['p95']/base['latencyMs']['p95']-1)*100 if base['latencyMs']['p95']>0 else None
    summary={'version':'1.0.0-rc16','evidenceType':'actual-live-was',
             'evidenceMode':'OFFICIAL_SHADED_RUNTIME',
             'officialJarSha256':hashlib.sha256(AGENT.read_bytes()).hexdigest(), 'application':a.app,'status':'PASS',
             'officialShadedAgent':str(AGENT),'modes':output,'comparison':{
             'tpsDeltaPercent':round(tps_delta,3) if tps_delta is not None else None,
             'p95DeltaPercent':round(p95_delta,3) if p95_delta is not None else None},
             'scope':'local staged HTTP application; not vendor JEUS/WebLogic/AIX and not production performance'}
    path=workdir/'summary.json'
    path.write_text(json.dumps(summary,indent=2)+'\n')
    print('PASS live-WAS integration:',path)

if __name__=='__main__':main()
