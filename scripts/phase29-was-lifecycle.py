#!/usr/bin/env python3
"""Staging ONLY: real Spring Boot process restarts or Tomcat 9/10 WAR redeploy.

Requires Maven, and for Tomcat an approved installation. Loopback-bound, isolated
CATALINA_BASE. Never touches a live Catalina base or a remote WAS. Does NOT prove
that an old Tomcat WebappClassLoader is garbage-collected; use JFR/heap analysis.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAR=ROOT/'target/runtime-sbom-agent-1.0.0-rc16.jar'
SHA=os.environ.get('RUNTIMESBOM_EXPECTED_SHA256', 'ed5613c7d515d877b57bb6844ddb4bb66c919af74648ac10bb9960d99e406f4a')
spec=importlib.util.spec_from_file_location('phase14',ROOT/'scripts/phase14-live-was.py')
phase14=importlib.util.module_from_spec(spec);spec.loader.exec_module(phase14)
PURL='pkg:maven/org.apache.commons/commons-lang3@3.14.0'
archive_spec=importlib.util.spec_from_file_location('phase21archive',ROOT/'scripts/phase21-archive-evidence.py')
archive_utils=importlib.util.module_from_spec(archive_spec);archive_spec.loader.exec_module(archive_utils)


def exact_binary():
    if not JAR.is_file() or hashlib.sha256(JAR.read_bytes()).hexdigest()!=SHA:
        raise RuntimeError('Exact official rc16 shaded JAR missing or hash mismatch')


def evidence(path):
    if not path.is_file():raise RuntimeError('Missing SBOM: '+str(path))
    bom=json.loads(path.read_text(encoding='utf-8'))
    if bom.get('bomFormat')!='CycloneDX':raise RuntimeError('Invalid CycloneDX file')
    found=[]
    for c in bom.get('components',[]):
        if c.get('purl')!=PURL:continue
        props={p.get('name'):p.get('value') for p in c.get('properties',[])}
        count=int(props.get('runtimeSbom:observedMethodEntryCount','0'))
        if count>0 and props.get('runtimeSbom:runtimeEvidenceState')=='METHOD_EXECUTED':
            found.append({'loader':props.get('runtimeSbom:classLoader'),
                          'observedMethodEntries':count,'purl':PURL,
                          'sha256':next((h.get('content') for h in c.get('hashes',[])
                                          if h.get('alg')=='SHA-256'),None)})
    if not found or any(not x['sha256'] for x in found):
        raise RuntimeError('Commons Lang3 PURL, SHA256, or METHOD_EXECUTED missing in '+str(path))
    return found


def wait_evidence(sbom, previous=None, timeout=25):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            items=evidence(sbom)
            loaders={x['loader'] for x in items}
            if previous is None or bool(loaders-set(previous)):
                return items
        except (OSError,ValueError,RuntimeError,json.JSONDecodeError):
            pass
        time.sleep(.3)
    raise RuntimeError('Timed out waiting for new execution evidence in '+str(sbom))


def request(url,n):
    for _ in range(n):
        with urllib.request.urlopen(url,timeout=3) as r:
            if r.status!=200 or r.read(200).decode('utf-8').strip()!='mobs-emitnur':
                raise RuntimeError('Unexpected HTTP response from '+url)


def stop_process(proc):
    if proc.poll() is not None:return
    # Process group is owned by this script alone; never touch pre-existing services.
    try:os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:return
    try:proc.wait(timeout=16)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)


def compile_app(app,output_dir):
    basedir=ROOT/phase14.APPS[app][0]
    job=subprocess.run(['mvn','-B','-DskipTests','clean','package'],cwd=basedir,
                       capture_output=True,text=True,timeout=300)
    (output_dir/'build.log').write_text(job.stdout+'\n'+job.stderr,encoding='utf-8')
    if job.returncode:
        raise RuntimeError('Maven application build failed; inspect '+str(output_dir/'build.log'))
    archive=basedir/phase14.APPS[app][1]
    if not archive.is_file():raise RuntimeError('Missing packaged application '+str(archive))
    return archive


def assert_exact_dependency_evidence(entries, expected):
    mismatches=[v['sha256'] for v in entries if v['sha256'].lower()!=expected.lower()]
    if mismatches:
        raise RuntimeError('Actual dependency JAR SHA-256 does not match SBOM: %s'%mismatches)


def boot_restart(app,archive,output_dir,port,requests, expected):
    rows=[]
    for index in (1,2):
        base=output_dir/('boot-run%d'%index);base.mkdir(parents=True,exist_ok=True)
        sbom=base/'sbom.json'; log=base/'server.log'
        opt=('output=%s,interval=1,resourceProbe=true,engine=asm,sampleEvery=1,'
             'tracePackages=org.apache.commons.lang3'%sbom)
        cmd=['java','-javaagent:%s=%s'%(JAR,opt),'-jar',str(archive),
             '--server.address=127.0.0.1','--server.port=%d'%port]
        with log.open('wb') as f:
            proc=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=ROOT,start_new_session=True)
            try:
                phase14.until_ready('http://127.0.0.1:%d/health/sbom'%port,proc)
                request('http://127.0.0.1:%d/health/sbom'%port,requests)
                observed=wait_evidence(sbom)
                assert_exact_dependency_evidence(observed,expected)
                rows.append({'pid':proc.pid,'cycle':index,'executionEvidence':observed})
            finally:stop_process(proc)
    if rows[0]['pid']==rows[1]['pid']:
        raise RuntimeError('PID unexpectedly reused; restart proof inconclusive')
    return rows


def tomcat_redeploy(app,archive,home,output_dir,port,requests, expected):
    base=output_dir/'isolated-catalina-base'
    webapp=phase14.prepare_tomcat(home,base,archive,port)
    sbom=output_dir/'tomcat-sbom.json'
    log=output_dir/'tomcat-server.log'
    opt=('output=%s,interval=1,resourceProbe=true,engine=asm,sampleEvery=1,'
         'tracePackages=org.apache.commons.lang3'%sbom)
    env=dict(os.environ,CATALINA_HOME=str(Path(home).resolve()),CATALINA_BASE=str(base),
             CATALINA_OPTS='-javaagent:%s=%s'%(JAR,opt))
    url='http://127.0.0.1:%d/sbom-demo/health/sbom'%port
    with log.open('wb') as f:
        proc=subprocess.Popen(['sh',str(Path(home).resolve()/'bin/catalina.sh'),'run'],
             cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        try:
            phase14.until_ready(url,proc)
            request(url,requests)
            first=wait_evidence(sbom)
            assert_exact_dependency_evidence(first,expected)
            first_loaders={v['loader'] for v in first}
            # Only manipulate isolated temporary Catalina base, never an existing installation.
            webapp.unlink()
            expanded=base/'webapps/sbom-demo'
            # Catalina's HostConfig performs undeploy; wait for it to remove exploded directory.
            deadline=time.monotonic()+30
            while time.monotonic()<deadline and expanded.exists():
                if proc.poll() is not None:raise RuntimeError('Tomcat exited while undeploying')
                time.sleep(.35)
            if expanded.exists():
                raise RuntimeError('WAR undeploy not observed within 30s; stop rather than force-delete running webapp')
            shutil.copy2(archive,webapp)
            phase14.until_ready(url,proc,deadline_seconds=90)
            request(url,requests)
            second=wait_evidence(sbom,previous=first_loaders,timeout=35)
            assert_exact_dependency_evidence(second,expected)
            new_loaders={v['loader'] for v in second}-first_loaders
            if not new_loaders:
                raise RuntimeError('New WAR classloader evidence was not observed after redeploy')
            return [{'cycle':1,'loaderIds':sorted(first_loaders),'executionEvidence':first},
                    {'cycle':2,'newLoaderIds':sorted(new_loaders),'executionEvidence':second}]
        finally:
            stop_process(proc)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--app',required=True,choices=sorted(phase14.APPS))
    ap.add_argument('--tomcat-home',default='')
    ap.add_argument('--requests',type=int,default=25)
    ap.add_argument('--out-dir',type=Path,default=ROOT/'results/phase29/live')
    args=ap.parse_args()
    if not 1<=args.requests<=10000:ap.error('requests 1..10000')
    if not sys.platform.startswith('linux'):ap.error('Staging lifecycle runner currently supports Linux only')
    exact_binary()
    if not shutil.which('mvn'):ap.error('Maven needed to compile staged real Spring/Tomcat application')
    root=(ROOT/args.out_dir/args.app).resolve()
    root.mkdir(parents=True,exist_ok=True)
    report={'stage':29,'test':'real-was-lifecycle','app':args.app,'agentSha256':SHA,
            'status':'FAIL','productionDeployment':'HOLD','scope':'localhost-only isolated staging application'}
    try:
        archive=compile_app(args.app,root)
        expected=archive_utils.expected_from_archive(archive)['dependencySha256']
        report['expectedDependencySha256']=expected
        openport=phase14.free_port()
        if args.app.startswith('spring'):
            report['cycles']=boot_restart(args.app,archive,root,openport,args.requests,expected)
        else:
            if not args.tomcat_home:raise RuntimeError('Requires --tomcat-home staging installation')
            report['cycles']=tomcat_redeploy(args.app,archive,args.tomcat_home,root,openport,args.requests,expected)
        report['status']='PASS'
        report['note']='Tomcat different loader IDs do not establish loader garbage collection; check JFR/heap manually'
    except Exception as e:
        report['error']=repr(e)
    (root/'lifecycle.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(args.app,report['status'],'PRODUCTION HOLD',flush=True)
    if report['status']!='PASS':
        print(report['error'],file=sys.stderr);return 1
    return 0

if __name__=='__main__':sys.exit(main())
