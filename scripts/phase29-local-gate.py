#!/usr/bin/env python3
"""Local official SHA-pinned JAR gate, fail closed; never authorizes a production deployment."""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--quick',action='store_true',help='~20s fixture smoke; NOT sustained test')
    p.add_argument('--out',type=Path,default=ROOT/'results/phase29/local-gate.json')
    a=p.parse_args()
    # Long default: 3x30s per condition, plus restarts; still not a 24h test.
    per_window='1' if a.quick else '30'
    windows='2' if a.quick else '3'
    steps=[
       ('phase29_unit_tests',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_phase29_validation.py','-v']),
       ('phase29_outage_backlog_replay',[sys.executable,'scripts/phase29-outage-replay.py',
              '--offline-jvms','3','--outage-seconds','0.2' if a.quick else '30']),
       ('phase29_windowed_http',[sys.executable,'scripts/phase29-sustained.py',
              '--warmup','0.5' if a.quick else '3','--windows',windows,
              '--window-seconds',per_window,'--concurrency','4']),
       ('collector_regression',[sys.executable,'-m','unittest','discover','-s','collector/tests','-p','test_*.py','-v']),
    ]
    report={'phase':29,'status':'FAIL','productionDeployment':'HOLD',
            'quick':a.quick,'scope':'Official rc16 JAR, local JVM and reference Collector; no live WAS',
            'createdUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':[]}
    for name,cmd in steps:
        print('RUN',name,flush=True)
        try:
            result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,
                   timeout=300 if a.quick else 900)
            check={'name':name,'status':'PASS' if result.returncode==0 else 'FAIL',
                   'returnCode':result.returncode,'outputTail':(result.stdout+'\n'+result.stderr)[-2800:]}
        except Exception as e:check={'name':name,'status':'FAIL','error':repr(e)}
        report['checks'].append(check)
        print(check['status'],name,flush=True)
        if check['status'] == 'FAIL':
            print('PHASE29_CHECK_FAILURE: '+name, file=sys.stderr, flush=True)
            print(check.get('outputTail', check.get('error', 'no diagnostic available')), file=sys.stderr, flush=True)
            if name == 'phase29_outage_backlog_replay':
                outage_path = ROOT/'results/phase29/outage-replay.json'
                if outage_path.is_file():
                    print('PHASE29_OUTAGE_REPORT: '+str(outage_path), file=sys.stderr, flush=True)
                    try:
                        details = json.loads(outage_path.read_text(encoding='utf-8'))
                        print('PHASE29_OUTAGE_FAILURE_DETAILS: '+json.dumps({
                            k:details.get(k) for k in ('failureStage','error','queueFilesAtFailure','pendingWhileOffline')},
                            ensure_ascii=False), file=sys.stderr, flush=True)
                    except (ValueError,OSError) as ex:
                        print('PHASE29_OUTAGE_REPORT_READ_ERROR: '+repr(ex), file=sys.stderr, flush=True)
    report['status']='PASS' if all(c['status']=='PASS' for c in report['checks']) else 'FAIL'
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('PHASE29',report['status'],'PRODUCTION HOLD',flush=True)
    return 0 if report['status']=='PASS' else 1

if __name__=='__main__':sys.exit(main())
