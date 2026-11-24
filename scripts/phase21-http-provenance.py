#!/usr/bin/env python3
"""Real local HTTP calls + genuine class loading + ASM fixture instrumentation.

This is a JDK HttpServer synthetic test, NOT Spring Boot/Tomcat. It exercises
multiple JAR SHA-256 values for the same PURL, multiple class loaders, and
method-entry evidence only for loaders able to see the Agent Recorder.
Ground truth is constructed from HTTP request counts and JAR bytes, NOT SBOM.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'integration'
EXPECTED_PURL = 'pkg:maven/com.example.fixture/fixture-core@1.2.3'


def load_accuracy():
    name = 'phase20_accuracy_runtime'
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts/phase20-accuracy.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def command(argv, log=None, **kwargs):
    p = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=80, **kwargs)
    if log:
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        Path(log).write_text(p.stdout+'\n'+p.stderr, encoding='utf-8')
    if p.returncode:
        raise RuntimeError('command failed: '+ ' '.join(map(str,argv))+'\n'+(p.stdout+p.stderr)[-2500:])
    return p


def compile_fixture(out):
    old = out/'old'; new = out/'new'; runner=out/'runner'
    for dirname in ('old','new','runner'):
        (out/dirname).mkdir(parents=True, exist_ok=True)
    command(['javac','--release','8','-d',str(old),str(SOURCE/'fixture-src/fixture/lib/Helper.java')])
    alt = out/'alternate/fixture/lib/Helper.java'
    alt.parent.mkdir(parents=True,exist_ok=True)
    alt.write_text((SOURCE/'fixture-src/fixture/lib/HelperAlternate.java.template').read_text())
    command(['javac','--release','8','-d',str(new),str(alt)])
    command(['javac','--release','8','-d',str(runner),str(SOURCE/'Phase21HttpProvenanceServer.java')])
    digest = {}
    metadata=(SOURCE/'fixture-src/META-INF/maven/com.example.fixture/fixture-core/pom.properties')
    for variant, directory in [('old',old),('new',new)]:
        meta=directory/'META-INF/maven/com.example.fixture/fixture-core/pom.properties'
        meta.parent.mkdir(parents=True,exist_ok=True)
        meta.write_bytes(metadata.read_bytes())
        archive=out/(variant+'-fixture.jar')
        command(['jar','cf',str(archive),'-C',str(directory),'.'])
        digest[variant]=hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest['old']==digest['new']:
        raise AssertionError('Fixtures must have different hashes')
    return {key:out/(key+'-fixture.jar') for key in ('old','new')},digest,runner


def choose_agent(mode):
    if mode=='jdk-internal':
        expected=ROOT/'target/jdk-asm-verification/agent-test-only.jar'
        if not expected.is_file():command(['sh','scripts/verify-jdk-asm.sh'],ROOT/'results/phase21/internal-asm-setup.log')
        return expected,['--add-exports=java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED']
    if mode=='official':
        expected=ROOT/'target/runtime-sbom-agent-1.0.0-rc16.jar'
        if not expected.is_file():raise RuntimeError('official ASM jar unavailable (HOLD): run Maven build on a connected staging host')
        p=command([sys.executable,'scripts/phase18-audit-jar.py',str(expected)],ROOT/'results/phase21/binary-audit.log')
        audit=json.loads(p.stdout)
        if audit.get('status')!='PASS':raise RuntimeError('official binary failed packaging audit')
        return expected,[]
    raise AssertionError(mode)


def request(url, timeout=3.0):
    start=time.perf_counter_ns()
    with urllib.request.urlopen(url,timeout=timeout) as response:
        body=response.read(200).decode('utf-8')
        status=response.status
    return status,body,(time.perf_counter_ns()-start)/1e6


def percentile(sorted_values,p):
    if not sorted_values:return None
    i=(len(sorted_values)-1)*p/100
    low=int(i); high=min(low+1,len(sorted_values)-1)
    return round(sorted_values[low]+(sorted_values[high]-sorted_values[low])*(i-low),4)


def wait_ready(proc,url):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        if proc.poll() is not None:
            raise RuntimeError('HTTP JVM exited before ready: '+str(proc.returncode))
        try:
            status,body,_=request(url+'/health',0.4)
            if status==200 and body=='ok':return
        except (OSError,TimeoutError,urllib.error.URLError):
            time.sleep(0.1)
    raise RuntimeError('HTTP JVM readiness timeout')


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        return s.getsockname()[1]


def build_truth(digests,reqs,trace):
    item=lambda key,n,s: {'purl':EXPECTED_PURL,'sha256':digests[key],
                          'sourceSuffix':key+'-fixture.jar','methodEntries':n,'evidenceState':s}
    return {'schemaVersion':1,'name':'phase21-http-same-purl-different-jar-isolated-loader',
            'groundTruthSource':'independent HTTP accepted request count x known per-request Java call plan + fixture JAR hashes',
            'scopeTerms':['old-fixture.jar','new-fixture.jar','pkg:maven/com.example.fixture/'],
            'expected':[
                item('old',reqs if trace else 0,'METHOD_EXECUTED' if trace else 'CLASS_LOADED'),
                item('new',2*reqs if trace else 0,'METHOD_EXECUTED' if trace else 'CLASS_LOADED'),
                item('new',0,'CLASS_LOADED')
            ]}


def run_one(mode,variant,agent,vm_flags,fixture,digests,runner,reqs,concurrency,out):
    target=out/variant;target.mkdir(parents=True,exist_ok=True)
    sbom=target/'sbom.json';port=free_port()
    options='output='+str(sbom)+',interval=0,resourceProbe=false,sampleEvery=1'
    if variant=='asm-traced':options+=',tracePackages=fixture.lib'
    args=['java']+vm_flags+['-javaagent:'+str(agent)+'='+options,
          '-cp',str(runner),'Phase21HttpProvenanceServer',str(port),str(fixture['old']),str(fixture['new'])]
    log=target/'jvm.log'; base='http://127.0.0.1:'+str(port)
    timings=[]
    with log.open('w') as stream:
        proc=subprocess.Popen(args,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        try:
            wait_ready(proc,base)
            start=time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                results=list(pool.map(lambda _:request(base+'/work'),range(reqs)))
            elapsed=time.monotonic()-start
            if any(status!=200 or data!='checksum=25' for status,data,_ in results):
                raise RuntimeError('HTTP response unexpected or checksum mismatch')
            timings=sorted([t for _,_,t in results])
            status,stats,_=request(base+'/stats')
            if status!=200 or stats!=f'completed={reqs};errors=0':
                raise RuntimeError('server counter mismatch: '+stats)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill();proc.wait(timeout=4)
    if proc.returncode!=143 and proc.returncode not in (-15,0):
        # Typical SIGTERM is 143, with Python reporting -15 on Linux.
        raise RuntimeError('JVM exit unexpected '+str(proc.returncode))
    if not sbom.is_file():raise RuntimeError('SBOM not written on JVM shutdown; log '+str(log))
    truth=build_truth(digests,reqs,variant=='asm-traced')
    (target/'ground-truth.json').write_text(json.dumps(truth,indent=2)+'\n',encoding='utf-8')
    accuracy=load_accuracy().evaluate(truth,json.loads(sbom.read_text(encoding='utf-8')))
    (target/'accuracy.json').write_text(json.dumps(accuracy,indent=2)+'\n',encoding='utf-8')
    if not accuracy['strictFixturePass']:
        raise RuntimeError('HTTP origin/loader/execution evidence mismatch: '+str(accuracy))
    perf={'requests':reqs,'successfulRequests':reqs,'errors':0,
          'durationSeconds':round(elapsed,4),'successTps':round(reqs/elapsed,4),
          'latencyMs':{'p50':percentile(timings,50),'p95':percentile(timings,95),'p99':percentile(timings,99)},
          'purpose':'local HTTP synthetic fixture; not a production WAS performance measurement'}
    (target/'http-metrics.json').write_text(json.dumps(perf,indent=2)+'\n',encoding='utf-8')
    return {'accuracyReport':str(target/'accuracy.json'), 'http':perf,
            'truePositives':accuracy['truePositives'],'falsePositives':accuracy['falsePositives'],
            'falseNegatives':accuracy['falseNegatives'],'executionEvidenceExact':accuracy['executionEvidenceExact']}


def run(args):
    out=(ROOT/args.out_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    if args.mode=='jdk-internal' and (not sys.platform.startswith('linux') or sys.version_info<(3,8)):
        raise RuntimeError('Development fixture requires Linux and Python 3.8+')
    agent,vm_flags=choose_agent(args.mode)
    fixture,digests,runner=compile_fixture(out/'build')
    runs={}
    for variant in ('loaded-only','asm-traced'):
        runs[variant]=run_one(args.mode,variant,agent,vm_flags,fixture,digests,runner,
                              args.requests,args.concurrency,out)
        print('PASS',variant,'TP=',runs[variant]['truePositives'],'FP=',runs[variant]['falsePositives'],flush=True)
    summary={'schemaVersion':1,'stage':21,'mode':args.mode,
             'status':'PASS','executionEnvironment':'Java builtin loopback HTTP server',
             'realTomcatSpringBootTest':False,
             'agentSha256':hashlib.sha256(agent.read_bytes()).hexdigest(),
             'groundTruth':'fixture files + HTTP checksums/request counts; never generated from SBOM',
             'samePurlDifferentJarSha256':digests['old']!=digests['new'],
             'testRequestsPerMode':args.requests,'isolatedLoaderHasNoExecutionClaim':True,
             'results':runs,'stagingReview':'HOLD', 'productionDeployment':'HOLD'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','scope':summary['executionEnvironment'],
                      'distinctJarHashes':summary['samePurlDifferentJarSha256'],
                      'officialAsm':args.mode=='official',
                      'stagingReview':'HOLD','summary':str(out/'summary.json')},indent=2))
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['jdk-internal','official'],default='jdk-internal')
    parser.add_argument('--requests',type=int,default=80)
    parser.add_argument('--concurrency',type=int,default=8)
    parser.add_argument('--out-dir',default='results/phase21/http-provenance')
    args=parser.parse_args()
    if not 1<=args.requests<=20000 or not 1<=args.concurrency<=32:
        parser.error('requests must be 1..20000; concurrency 1..32')
    run(args)

if __name__=='__main__':main()
