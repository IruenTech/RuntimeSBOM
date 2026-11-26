#!/usr/bin/env python3
"""Official shaded rc16 agent: bounded, localhost-only three-condition JVM HTTP benchmark.

Not an operational/WAS benchmark. Captures raw per-run data; never auto-approves releases.
"""
import argparse
import hashlib
import json
import os
import random
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAR = ROOT / 'target/runtime-sbom-agent-1.0.0-rc16.jar'
EXPECTED_SHA256 = 'ed5613c7d515d877b57bb6844ddb4bb66c919af74648ac10bb9960d99e406f4a'
MODES = ('baseline', 'loaded-only', 'asm-traced')


def port_available():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def process_cpu_seconds(pid):
    try:
        raw = Path('/proc/%d/stat' % pid).read_text()
        rest = raw[raw.rfind(')')+2:].split()
        ticks = int(rest[11]) + int(rest[12])
        return ticks / os.sysconf('SC_CLK_TCK')
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def process_rss_kib(pid):
    try:
        for line in Path('/proc/%d/status' % pid).read_text().splitlines():
            if line.startswith('VmRSS:'):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def jstat_gc(pid):
    try:
        r = subprocess.run(['jstat', '-gc', str(pid)], text=True, capture_output=True, timeout=3)
        if r.returncode: return None
        rows = r.stdout.strip().splitlines()
        if len(rows) < 2: return None
        fields = rows[0].split(); values = rows[-1].split()
        return {name: float(values[fields.index(name)]) for name in ('YGC', 'FGC', 'GCT') if name in fields}
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def health(port):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/health' % port, timeout=1) as r:
            return r.status == 200 and r.read() == b'ok'
    except Exception:
        return False


def observed_hits(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    hits = sum(int(p.get('value', '0')) for c in data.get('components', [])
               for p in c.get('properties', [])
               if p.get('name') == 'runtimeSbom:observedMethodEntryCount')
    return hits


def run_one(args, mode, index):
    port = port_available()
    place = ROOT / 'results/phase28' / ('run-%02d-%s' % (index, mode))
    place.mkdir(parents=True, exist_ok=True)
    sbom = place / 'sbom.json'
    if sbom.exists(): sbom.unlink()
    config = 'output=%s,interval=0,resourceProbe=false' % sbom
    if mode == 'asm-traced':
        config += ',engine=asm,tracePackages=example,sampleEvery=1'
    cmd = ['java', '--add-modules', 'jdk.httpserver']
    if mode != 'baseline':
        cmd.append('-javaagent:%s=%s' % (JAR, config))
    cmd += ['-cp', str(ROOT/'target/phase28-http/classes'), 'integration.HttpWorkloadServer', str(port)]
    log = place / 'jvm.log'
    with log.open('wb') as out:
        proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, cwd=str(ROOT))
        try:
            for _ in range(150):
                if proc.poll() is not None: break
                if health(port): break
                time.sleep(.1)
            else:
                raise RuntimeError('%s readiness timeout; see %s' % (mode, log))
            if not health(port): raise RuntimeError('%s startup error, see %s' % (mode, log))
            warmup = place/'warmup.json'
            subprocess.run([sys.executable, str(ROOT/'scripts/http-load.py'), '--url',
                            'http://127.0.0.1:%d/work' % port, '--duration', str(args.warmup),
                            '--concurrency', str(args.concurrency), '--out', str(warmup)],
                           cwd=str(ROOT), check=True, capture_output=True, text=True, timeout=max(20, args.warmup+15))
            begin_cpu = process_cpu_seconds(proc.pid)
            begin_gc = jstat_gc(proc.pid)
            peak_rss = [process_rss_kib(proc.pid)]
            stop = threading.Event()
            def poll_memory():
                while not stop.wait(.15):
                    memory = process_rss_kib(proc.pid)
                    if memory is not None: peak_rss.append(memory)
            thread = threading.Thread(target=poll_memory, daemon=True)
            thread.start()
            try:
                subprocess.run([sys.executable, str(ROOT/'scripts/http-load.py'), '--url',
                                'http://127.0.0.1:%d/work' % port, '--duration', str(args.duration),
                                '--concurrency', str(args.concurrency), '--out', str(place/'http.json')],
                               cwd=str(ROOT), check=True, capture_output=True, text=True,
                               timeout=max(20, args.duration+15))
            finally:
                stop.set();thread.join(timeout=2)
            end_cpu = process_cpu_seconds(proc.pid)
            end_gc = jstat_gc(proc.pid)
        finally:
            proc.terminate()
            try: proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(timeout=10)
    metrics = json.loads((place/'http.json').read_text())
    if metrics['errors'] != 0: raise RuntimeError('Errors in %s run %s' % (mode, index))
    if mode != 'baseline':
        if not sbom.exists(): raise RuntimeError('Missing SBOM %s' % sbom)
        count = observed_hits(sbom)
        if mode == 'loaded-only' and count != 0:
            raise RuntimeError('Unexpected method evidence in loading mode')
        if mode == 'asm-traced' and count <= 0:
            raise RuntimeError('ASM produced no method evidence')
    else: count = None
    data = {'run': index, 'mode': mode, 'requests': metrics['requests'],
            'success': metrics['success'], 'errors': metrics['errors'],
            'successTps': metrics['successTps'], 'p95Ms': metrics['latencyMs']['p95'],
            'p99Ms': metrics['latencyMs']['p99'],
            'observedMethodEntries': count,
            'cpuSecondsMeasuredWindow': (round(end_cpu-begin_cpu,4) if begin_cpu is not None and end_cpu is not None else None),
            'peakRssKiBObserved': max((x for x in peak_rss if x is not None), default=None),
            'gcDelta': ({k: round(end_gc[k]-begin_gc[k], 4) for k in begin_gc if k in end_gc} if begin_gc and end_gc else None),
            'httpJson': str(place.relative_to(ROOT)/'http.json'), 'jvmLog': str(log.relative_to(ROOT))}
    print('PASS', mode, 'round',index, 'TPS',data['successTps'], 'P95',data['p95Ms'],flush=True)
    return data


def summarize(rows):
    groups = {mode: [r for r in rows if r['mode'] == mode] for mode in MODES}
    summary = {}
    for mode, items in groups.items():
        summary[mode] = {'repeats':len(items),
                         'medianSuccessTps':round(statistics.median(x['successTps'] for x in items),2),
                         'medianP95Ms':round(statistics.median(x['p95Ms'] for x in items),3),
                         'medianP99Ms':round(statistics.median(x['p99Ms'] for x in items),3),
                         'totalHttpErrors':sum(x['errors'] for x in items)}
    base=summary['baseline']; traced=summary['asm-traced']
    impacts={'asmTpsChangePercent': round((traced['medianSuccessTps']/base['medianSuccessTps']-1)*100,2),
             'asmP95ChangePercent': round((traced['medianP95Ms']/base['medianP95Ms']-1)*100,2)}
    return summary, impacts


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--warmup',type=float,default=3)
    p.add_argument('--duration',type=float,default=10)
    p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--concurrency',type=int,default=4)
    p.add_argument('--out',type=Path,default=ROOT/'results/phase28/performance.json')
    args=p.parse_args()
    if not (.5<=args.warmup<=120 and .5<=args.duration<=3600 and 1<=args.repeats<=10 and 1<=args.concurrency<=32):
        p.error('warmup .5..120s, duration .5..3600s, repeats 1..10, concurrency 1..32')
    if not JAR.is_file() or hashlib.sha256(JAR.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise SystemExit('Exact official rc16 JAR missing or hash mismatch; FAIL CLOSED')
    classes=ROOT/'target/phase28-http/classes';classes.mkdir(parents=True,exist_ok=True)
    subprocess.run(['javac','--release','8','-d',str(classes),
                    str(ROOT/'src/test/java/example/Worker.java'),
                    str(ROOT/'integration/HttpWorkloadServer.java')],check=True)
    rows=[]
    try:
        for repeat in range(args.repeats):
            order=list(MODES);random.Random(2800+repeat).shuffle(order)
            for mode in order:rows.append(run_one(args,mode,repeat+1))
        summary, impacts = summarize(rows)
        report={'stage':28, 'scope':'Linux JDK21, local com.sun.net.httpserver fixture; no Tomcat/JEUS/WebLogic/AIX',
                'agentSha256':EXPECTED_SHA256,
                'testParameters':{'durationSecondsPerMode':args.duration,'warmupSeconds':args.warmup,
                                  'repeats':args.repeats,'concurrency':args.concurrency},
                'rawRuns':rows,'summary':summary,'comparison':impacts,
                'status':'PASS','productionDeployment':'HOLD',
                'interpretation':'synthetic non-representative performance; no automatic TPS threshold approval'}
    except Exception as e:
        report={'stage':28,'status':'FAIL','error':repr(e),'rawRuns':rows,'productionDeployment':'HOLD'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('STATUS',report['status'], 'PRODUCTION HOLD',flush=True)
    if report['status']!='PASS':
        print(report['error'],file=sys.stderr);sys.exit(1)

if __name__=='__main__':main()
