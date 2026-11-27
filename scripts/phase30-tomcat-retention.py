#!/usr/bin/env python3
"""Disposable localhost Tomcat redeploy + GC/JCMD histogram + NMT staging probe.

No production deployment, no remote WAS controls, no proof of leak-freedom.
Requires: Linux JDK with jcmd, Maven, approved Tomcat, and the Phase29 project.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP_CHOICES=('tomcat9','tomcat10')
ROW=re.compile(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)',re.M)
META=re.compile(r'[-+]\s*Metaspace\s*\([^)]*?committed=(\d+)KB',re.I)

def load_phase29():
    spec=importlib.util.spec_from_file_location('phase29_lifecycle',ROOT/'scripts/phase29-was-lifecycle.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def count_webapp_loaders(histogram):
    matches=[]
    for count, size, classname in ROW.findall(histogram):
        if classname in ('org.apache.catalina.loader.ParallelWebappClassLoader',
                         'org.apache.catalina.loader.WebappClassLoader'):
            matches.append((classname,int(count),int(size)))
    if not matches:
        # The tool output may omit the class when there is no live webapp loader;
        # this is not an error during undeploy, but active-phase checks require >= 1.
        return 0
    return sum(count for _, count, _ in matches)

def metaspace_committed_kb(nmt):
    m=META.search(nmt)
    return int(m.group(1)) if m else None

def jcmd(pid, command, timeout=60):
    result=subprocess.run(['jcmd',str(pid),*command],capture_output=True,text=True,timeout=timeout)
    if result.returncode:
        raise RuntimeError('jcmd %s failed: %s'%(command,'\n'.join((result.stdout+result.stderr).splitlines()[-7:])))
    return result.stdout

def sample(pid,base,cycle):
    gc=jcmd(pid,['GC.run'])
    # Histogram itself may trigger collection; only strong reachable references are counted.
    hist=jcmd(pid,['GC.class_histogram'])
    nmt=jcmd(pid,['VM.native_memory','summary','scale=KB'])
    (base/('histogram-%02d.txt'%cycle)).write_text(hist,encoding='utf-8')
    (base/('nmt-%02d.txt'%cycle)).write_text(nmt,encoding='utf-8')
    return {'cycle':cycle,'reachableWebappClassLoaderInstances':count_webapp_loaders(hist),
            'metaspaceCommittedKiB':metaspace_committed_kb(nmt),
            'gcCommandSucceeded':bool(gc.strip())}

def run(app,home,output,cycles,requests,sha, max_growth_kib):
    p29=load_phase29()
    expected=os.environ.get('RUNTIMESBOM_EXPECTED_SHA256')
    if not expected or expected!=sha or not re.fullmatch('[0-9a-f]{64}',sha):
        raise RuntimeError('Expected exact official Agent SHA must come from prior verified Phase26 evidence')
    p29.exact_binary()
    if not shutil.which('mvn') or not shutil.which('jcmd'):
        raise RuntimeError('Maven and JDK jcmd required')
    output.mkdir(parents=True,exist_ok=True)
    archive=p29.compile_app(app,output)
    dep=p29.archive_utils.expected_from_archive(archive)['dependencySha256']
    port=p29.phase14.free_port()
    home=Path(home).resolve()
    base=output/'isolated-catalina-base'
    war=p29.phase14.prepare_tomcat(home,base,archive,port)
    sbom=output/'tomcat-sbom.json'
    logfile=output/'tomcat-server.log'
    opts=('output=%s,interval=1,resourceProbe=true,engine=asm,sampleEvery=1,'
          'tracePackages=org.apache.commons.lang3'%sbom)
    env=dict(os.environ,CATALINA_HOME=str(home),CATALINA_BASE=str(base),
             CATALINA_OPTS='-XX:NativeMemoryTracking=summary -javaagent:%s=%s'%(p29.JAR,opts))
    url='http://127.0.0.1:%d/sbom-demo/health/sbom'%port
    summary=[]
    with logfile.open('wb') as f:
        proc=subprocess.Popen(['sh',str(home/'bin/catalina.sh'),'run'],cwd=ROOT,
             stdout=f,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        try:
            p29.phase14.until_ready(url,proc)
            last_loaders=set()
            for index in range(1,cycles+1):
                if index>1:
                    war.unlink()
                    expanded=base/'webapps/sbom-demo'
                    deadline=time.monotonic()+45
                    while expanded.exists() and time.monotonic()<deadline:
                        if proc.poll() is not None:raise RuntimeError('Tomcat stopped during undeploy')
                        time.sleep(.4)
                    if expanded.exists():raise RuntimeError('WAR undeploy timed out')
                    shutil.copy2(archive,war)
                    p29.phase14.until_ready(url,proc,deadline_seconds=90)
                p29.request(url,requests)
                entries=p29.wait_evidence(sbom, previous=last_loaders or None, timeout=45)
                p29.assert_exact_dependency_evidence(entries,dep)
                new_loaders={x['loader'] for x in entries}-last_loaders
                if not new_loaders:raise RuntimeError('No new WAR classloader execution evidence')
                last_loaders={x['loader'] for x in entries}
                # After replaying HTTP requests, force a reachable-object histogram.
                reading=sample(proc.pid,output,index)
                reading['newLoaderIds']=sorted(new_loaders)
                reading['methodEntriesForNewLoader']=sum(x['observedMethodEntries'] for x in entries if x['loader'] in new_loaders)
                summary.append(reading)
                (output/'intermediate.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
        finally:
            p29.stop_process(proc)
    fails=[]
    if len(summary)!=cycles:fails.append('INCOMPLETE_REDEPLOY_CYCLES')
    if any(r['reachableWebappClassLoaderInstances']!=1 for r in summary):
        fails.append('PREVIOUS_LOADER_POSSIBLY_RETAINED_OR_HISTOGRAM_UNEXPECTED')
    if any(r['metaspaceCommittedKiB'] is None for r in summary):fails.append('NMT_METASPACE_UNAVAILABLE')
    growth=None
    if len(summary)>=2 and all(r['metaspaceCommittedKiB'] is not None for r in summary):
        # Growth from second sample reduces startup warmup bias.
        growth=summary[-1]['metaspaceCommittedKiB']-summary[1]['metaspaceCommittedKiB']
        if growth>max_growth_kib:fails.append('METASPACE_GROWTH_EXCEEDS_STAGING_THRESHOLD')
    return {'phase':30,'app':app,'status':'PASS' if not fails else 'HOLD',
            'productionDeployment':'HOLD','agentSha256':sha,'dependencySha256':dep,
            'cyclesRequested':cycles,'cyclesCompleted':len(summary),'snapshots':summary,
            'metaspaceGrowthKiBFromSecondCycle':growth,
            'stagingGrowthThresholdKiB':max_growth_kib,'failures':fails,
            'meaning':'Forced GC/histogram checks reachable instances at sample time; not proof of absence of leaks or 24h stability'}

def main():
    pa=argparse.ArgumentParser(description=__doc__)
    pa.add_argument('--app',required=True,choices=APP_CHOICES)
    pa.add_argument('--tomcat-home',type=Path,required=True)
    pa.add_argument('--cycles',type=int,default=6)
    pa.add_argument('--requests',type=int,default=40)
    pa.add_argument('--max-metaspace-growth-kib',type=int,default=16384)
    pa.add_argument('--out-dir',type=Path,default=ROOT/'results/phase30/tomcat')
    a=pa.parse_args()
    if not 3<=a.cycles<=100 or not 1<=a.requests<=10000 or a.max_metaspace_growth_kib<0:pa.error('invalid cycles/requests/growth')
    output=(a.out_dir/a.app).resolve()
    output.mkdir(parents=True,exist_ok=True)
    try:
        report=run(a.app,a.tomcat_home,output,a.cycles,a.requests,
                   os.environ.get('RUNTIMESBOM_EXPECTED_SHA256',''),a.max_metaspace_growth_kib)
    except Exception as exc:
        report={'phase':30,'app':a.app,'status':'HOLD','productionDeployment':'HOLD',
                'cyclesRequested':a.cycles,'failures':['PROBE_FAILED'], 'error':repr(exc)}
    (output/'retention.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('PHASE30 TOMCAT',a.app,report['status'],'PRODUCTION HOLD',flush=True)
    if report.get('failures'):print(report['failures'],report.get('error',''),file=sys.stderr)
    return 0 if report['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
