#!/usr/bin/env python3
"""Opt-in repeatable 3-mode benchmark. Test-only internal-ASM mode is not release evidence.

Runs a baseline JVM, loading-only agent and ASM-traced agent. Captures process-level
wall clock (includes JVM startup and SBOM emission) and workload elapsedNs (from
inside main). Not a production WAS/TPS/GC measurement.
"""
import argparse, json, os, re, shutil, statistics, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARSER = argparse.ArgumentParser()
PARSER.add_argument('--agent', required=True)
PARSER.add_argument('--exports', action='store_true', help='use JDK internal ASM in test-only build')
PARSER.add_argument('--iterations', type=int, default=150000)
PARSER.add_argument('--repeats', type=int, default=5)
PARSER.add_argument('--out', default='results/phase10/benchmark.json')
PARSER.add_argument('--max-median-overhead-percent', type=float, default=None, help='opt-in performance gate; not a general product SLA')
args = PARSER.parse_args()
if args.iterations < 100 or args.repeats < 3: PARSER.error('iterations >= 100 and repeats >= 3 required')
agent = (ROOT / args.agent).resolve()
if not agent.is_file(): PARSER.error('agent missing: %s' % agent)
out = (ROOT / args.out).resolve(); out.parent.mkdir(parents=True, exist_ok=True)
appdir = ROOT/'target/phase10-benchmark/classes'; appdir.mkdir(parents=True, exist_ok=True)
javac_target = ['-source', '8', '-target', '8'] if '1.8' in subprocess.run(['javac', '-version'], capture_output=True, text=True).stdout + subprocess.run(['javac', '-version'], capture_output=True, text=True).stderr else ['--release', '8']
subprocess.run(['javac'] + javac_target + ['-d', str(appdir), str(ROOT/'src/test/java/example/Worker.java'), str(ROOT/'src/test/java/example/BenchmarkWorkload.java')], check=True)
java = ['java'] + (['--add-exports=java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED'] if args.exports else [])
pat = re.compile(r'BENCHMARK iterations=(\d+) checksum=(\d+) elapsedNs=(\d+)')
metrics_pat = re.compile(r'BENCHMETRICS cpuNs=(-?\d+) heapDeltaBytes=(-?\d+) gcCount=(\d+) gcMs=(\d+)')
records = {x:[] for x in ('baseline', 'loaded-only', 'asm-traced')}
# Interleave modes per round to minimize systemic time drift; JVMs are distinct.
for round_no in range(args.repeats):
    for mode in records:
        cmd = list(java)
        if mode != 'baseline':
            trace = ',tracePackages=example' if mode == 'asm-traced' else ''
            opts = 'output=%s,interval=0,resourceProbe=false%s' % (out.parent / ('bench-%s-%s.json' % (mode,round_no)), trace)
            cmd += ['-javaagent:%s=%s' % (agent,opts)]
        cmd += ['-cp', str(appdir), 'example.BenchmarkWorkload', str(args.iterations)]
        begin = time.perf_counter_ns()
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        wall = time.perf_counter_ns() - begin
        if p.returncode: raise RuntimeError('Mode %s failed: %s' % (mode, (p.stderr+p.stdout)[-3000:]))
        m = pat.search(p.stdout)
        if not m: raise RuntimeError('Benchmark output missing in '+mode+': '+p.stdout)
        metrics=metrics_pat.search(p.stdout)
        record={'iteration':round_no,'elapsedNs':int(m.group(3)), 'wallNs':wall,'checksum':int(m.group(2))}
        if metrics: record.update(dict(zip(('cpuNs','heapDeltaBytes','gcCount','gcMs'),map(int,metrics.groups()))))
        records[mode].append(record)
checksums = {v['checksum'] for runs in records.values() for v in runs}
if len(checksums)!=1: raise RuntimeError('workload checksums differ: '+str(checksums))
median = {mode:statistics.median(v['elapsedNs'] for v in runs) for mode,runs in records.items()}
base=median['baseline']
overhead={mode:round((value/base-1)*100,2) for mode,value in median.items() if mode!='baseline'}
result={'category':'isolated-jvm-synthetic-workload','releaseEvidence':not args.exports,'runtime':subprocess.run(['java','-version'],capture_output=True,text=True).stderr.splitlines()[0], 'iterations':args.iterations,'repeats':args.repeats,'medianWorkloadNs':median,'overheadPercentVsBaseline':overhead,'measurements':records,'limitations':['JVM startup excluded from workload elapsedNs but included in wallNs','single-host synthetic workload, not a real WAS benchmark','no statistically established production SLA','JDK internal ASM test build is not official ASM release verification']}
if args.max_median_overhead_percent is not None:
    result['thresholdPercent']=args.max_median_overhead_percent
    result['thresholdPass']=overhead['asm-traced'] <= args.max_median_overhead_percent
out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'medianWorkloadNs':median,'overheadPercentVsBaseline':overhead,'report':str(out)},indent=2))
if result.get('thresholdPass') is False:sys.exit(3)
