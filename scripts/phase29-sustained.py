#!/usr/bin/env python3
"""Exact official rc16 agent: successive fixed-window HTTP, RSS/CPU/GC observability.

Runs a single JVM for all windows in each mode. Bounded localhost fixture, NOT a live WAS.
Memory growth is a REVIEW SIGNAL only, not proof of a leak or release approval.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AGENT=ROOT/'target/runtime-sbom-agent-1.0.0-rc16.jar'
SHA=os.environ.get('RUNTIMESBOM_EXPECTED_SHA256', 'ed5613c7d515d877b57bb6844ddb4bb66c919af74648ac10bb9960d99e406f4a')
MODES=('baseline','loaded-only','asm-traced')
spec=importlib.util.spec_from_file_location('phase28performance', ROOT/'scripts/phase28-performance.py')
perf=importlib.util.module_from_spec(spec)
spec.loader.exec_module(perf)


def summary(rows):
    values={m:[v for v in rows if v['mode']==m] for m in MODES}
    output={}
    for mode,items in values.items():
        if not items:
            raise ValueError('Missing windows for '+mode)
        rss=[v['rssKiB'] for v in items if v['rssKiB'] is not None]
        output[mode]={
            'windows':len(items),
            'httpErrors':sum(x['errors'] for x in items),
            'medianTps':round(statistics.median(x['successTps'] for x in items),2),
            'medianP95Ms':round(statistics.median(x['p95Ms'] for x in items),3),
            'medianP99Ms':round(statistics.median(x['p99Ms'] for x in items),3),
            'firstRssKiB':rss[0] if rss else None,
            'lastRssKiB':rss[-1] if rss else None,
            'rssEndMinusStartKiB':rss[-1]-rss[0] if len(rss)>1 else None,
            'rssSamplesAvailable':len(rss),
            'totalCpuSecondsWindow':round(sum(x['cpuSecondsWindow'] or 0 for x in items),3),
        }
    base=output['baseline']['medianTps'];traced=output['asm-traced']['medianTps']
    output['comparison']={'asmTpsDeltaPercent':round((traced/base-1)*100,2) if base>0 else None,
                          'note':'Not an operational capacity SLO; compare matched staged workload'}
    return output


def run_mode(args,mode):
    path=ROOT/'results/phase29/sustained'/mode
    path.mkdir(parents=True,exist_ok=True)
    sbom=path/'sbom.json'
    if sbom.exists():sbom.unlink()
    port=perf.port_available()
    cmd=['java','--add-modules','jdk.httpserver']
    if mode!='baseline':
        opts='output=%s,interval=0,resourceProbe=false'%sbom
        if mode=='asm-traced':opts+=',engine=asm,tracePackages=example,sampleEvery=1'
        cmd.append('-javaagent:%s=%s'%(AGENT,opts))
    cmd+=['-cp',str(ROOT/'target/phase29-sustained/classes'),'integration.HttpWorkloadServer',str(port)]
    log=path/'jvm.log';rows=[]
    with log.open('wb') as output:
        process=subprocess.Popen(cmd,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
        try:
            for _ in range(120):
                if process.poll() is not None:break
                if perf.health(port):break
                time.sleep(.1)
            if not perf.health(port):raise RuntimeError('Not ready: '+str(log))
            def load(name,duration):
                output_file=path/name
                proc=subprocess.run([sys.executable,str(ROOT/'scripts/http-load.py'),'--url',
                       'http://127.0.0.1:%d/work'%port,'--duration',str(duration),
                       '--concurrency',str(args.concurrency),'--out',str(output_file)],
                       cwd=ROOT,capture_output=True,text=True,timeout=duration+25)
                if proc.returncode:
                    raise RuntimeError('HTTP load failed: '+(proc.stdout+proc.stderr)[-900:])
                return json.loads(output_file.read_text())
            load('warmup.json',args.warmup)
            for idx in range(1,args.windows+1):
                before_cpu=perf.process_cpu_seconds(process.pid)
                before_gc=perf.jstat_gc(process.pid)
                sample=load('window-%03d.json'%idx,args.window_seconds)
                after_cpu=perf.process_cpu_seconds(process.pid)
                after_gc=perf.jstat_gc(process.pid)
                entry={'mode':mode,'window':idx,'durationSeconds':sample['durationSeconds'],
                      'requests':sample['requests'],'success':sample['success'],'errors':sample['errors'],
                      'successTps':sample['successTps'],
                      'p95Ms':sample['latencyMs']['p95'],'p99Ms':sample['latencyMs']['p99'],
                      'rssKiB':perf.process_rss_kib(process.pid),
                      'cpuSecondsWindow':round(after_cpu-before_cpu,4) if before_cpu is not None and after_cpu is not None else None,
                      'gcDelta':{k:round(after_gc[k]-before_gc[k],3) for k in before_gc if k in after_gc} if before_gc and after_gc else None}
                rows.append(entry)
                print('WINDOW',mode,idx,'TPS',entry['successTps'],'RSS KiB',entry['rssKiB'],flush=True)
                if entry['errors']:
                    raise RuntimeError('HTTP errors in mode=%s window=%s'%(mode,idx))
        finally:
            process.terminate()
            try:process.wait(timeout=14)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=6)
    hits=None
    if mode!='baseline':
        if not sbom.is_file():raise RuntimeError('Missing SBOM in '+mode)
        hits=perf.observed_hits(sbom)
        if mode=='loaded-only' and hits!=0:raise RuntimeError('False execution evidence in loading only mode')
        if mode=='asm-traced' and hits<=0:raise RuntimeError('Missing actual execution evidence in ASM mode')
    return rows,hits


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--warmup',type=float,default=10)
    ap.add_argument('--window-seconds',type=float,default=60)
    ap.add_argument('--windows',type=int,default=5)
    ap.add_argument('--concurrency',type=int,default=8)
    ap.add_argument('--out',type=Path,default=ROOT/'results/phase29/sustained.json')
    args=ap.parse_args()
    if not (.5<=args.warmup<=120 and .5<=args.window_seconds<=3600 and
            2<=args.windows<=60 and 1<=args.concurrency<=32):
        ap.error('warmup .5..120, window .5..3600, windows 2..60, concurrency 1..32')
    if not AGENT.is_file() or hashlib.sha256(AGENT.read_bytes()).hexdigest()!=SHA:
        raise SystemExit('FAIL CLOSED: official exact-binary sha256 mismatch')
    classes=ROOT/'target/phase29-sustained/classes'
    classes.mkdir(parents=True,exist_ok=True)
    subprocess.run(['javac','--release','8','-d',str(classes),
        str(ROOT/'src/test/java/example/Worker.java'),str(ROOT/'integration/HttpWorkloadServer.java')],check=True)
    report={'stage':29,'scope':'LOCAL Java HttpServer, JDK21, not Spring Boot/Tomcat or long-run WAS validation',
            'agentSha256':SHA,'productionDeployment':'HOLD',
            'params':vars(args).copy(),'windows':[],'status':'FAIL'}
    report['params']['out']=str(args.out)
    try:
        modes=list(MODES)
        random.Random(2900).shuffle(modes)
        for mode in modes:
            rows,hits=run_mode(args,mode)
            report['windows']+=rows
            report.setdefault('observedEntries',{})[mode]=hits
        report['summary']=summary(report['windows'])
        report['status']='PASS'
        report['interpretation']='RSS trend is not a leak diagnosis; no production approval granted'
    except Exception as exc:
        report['error']=repr(exc)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('PHASE29 SUSTAINED',report['status'],'PRODUCTION HOLD',flush=True)
    if report['status']!='PASS':
        print(report['error'],file=sys.stderr);return 1
    return 0

if __name__=='__main__':sys.exit(main())
