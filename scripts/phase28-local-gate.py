#!/usr/bin/env python3
"""Repeat all actual Phase28 local checks; fail closed, never approve production deployment."""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--quick',action='store_true',help='short local smoke; does not substitute for sustained test')
    args=parser.parse_args()
    duration='1' if args.quick else '5'
    repeats='1' if args.quick else '3'
    warmup='.5' if args.quick else '2'
    steps=[
      ('phase28_unit',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_phase28_validation.py','-v']),
      ('phase28_collector_recovery',[sys.executable,'scripts/phase28-resilience.py']),
      ('phase28_three_mode_performance',[sys.executable,'scripts/phase28-performance.py',
                                         '--duration',duration,'--warmup',warmup,'--repeats',repeats,'--concurrency','4'])
    ]
    report={'phase':28,'scope':'official rc16 shaded agent / Linux JDK 21 / localhost fixture',
            'runUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'quick':args.quick,'checks':[],'productionDeployment':'HOLD'}
    for name,command in steps:
        print('RUN',name,flush=True)
        try:
            p=subprocess.run(command,cwd=str(ROOT),capture_output=True,text=True,timeout=360)
            item={'name':name,'status':'PASS' if p.returncode==0 else 'FAIL','exitCode':p.returncode,
                  'logTail':(p.stdout+'\n'+p.stderr)[-2400:]}
        except Exception as ex:
            item={'name':name,'status':'FAIL','error':repr(ex)}
        report['checks'].append(item)
        print(item['status'],name,flush=True)
    report['status']='PASS' if all(x['status']=='PASS' for x in report['checks']) else 'FAIL'
    output=ROOT/'results/phase28/local-gate.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(report['status'],'PRODUCTION HOLD',flush=True)
    return 0 if report['status']=='PASS' else 1

if __name__=='__main__':sys.exit(main())
