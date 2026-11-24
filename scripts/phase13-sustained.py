#!/usr/bin/env python3
"""Repeated local HTTP runs; summaries are diagnostic, not production SLAs."""
import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--rounds',type=int,default=3)
p.add_argument('--duration',type=float,default=10)
p.add_argument('--concurrency',type=int,default=8)
p.add_argument('--exports',action='store_true')
p.add_argument('--agent',default='target/jdk-asm-verification/agent-test-only.jar')
p.add_argument('--out-dir',default='results/phase13/sustained')
a=p.parse_args()
if not (2<=a.rounds<=20 and 2<=a.duration<=3600):p.error('rounds 2..20, duration 2..3600 required')
results=[]
for i in range(a.rounds):
    folder=Path(a.out_dir)/('round-%02d'%i)
    cmd=[sys.executable,'scripts/http-benchmark-phase13.py','--agent',a.agent,'--duration',str(a.duration),
         '--concurrency',str(a.concurrency),'--out-dir',str(folder)]
    if a.exports:cmd.append('--exports')
    subprocess.run(cmd,check=True)
    results.append(json.loads((folder/'summary.json').read_text()))
metrics={}
for mode in ('baseline','loaded-only','asm-traced'):
    metrics[mode]={key:{'median':round(statistics.median(r['modes'][mode][key] for r in results),3),
                        'min':round(min(r['modes'][mode][key] for r in results),3),
                        'max':round(max(r['modes'][mode][key] for r in results),3)}
                   for key in ('tps','successTps')}
    for key in ('p95','p99'):
        values=[r['modes'][mode]['latencyMs'][key] for r in results]
        metrics[mode][key+'Ms']={'median':round(statistics.median(values),3),'min':min(values),'max':max(values)}
result={'category':'repeated-local-HTTP-test-fixture','rounds':a.rounds,'durationPerModeSeconds':a.duration,
        'metrics':metrics,'warning':'Not Tomcat/Spring Boot or long-term leak evidence; modes are sequential and subject to drift.'}
out=Path(a.out_dir)/'aggregate.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
