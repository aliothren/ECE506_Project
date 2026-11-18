#!/usr/bin/env python3
"""Retry RTL simulation/export without repeating synthesis; preserve failed logs."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    run=args.run.resolve()
    meta=json.loads((run/'run.json').read_text())
    assert (run/'project/solution/syn/report/ffn_csynth.xml').exists()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    retry=run/('verification_'+stamp); retry.mkdir()
    if (run/'project/solution/sim/report').exists():
        shutil.copytree(run/'project/solution/sim/report',retry/'previous_reports')
    script=retry/'verify.tcl'
    shutil.copy2(ROOT/'hls/verify.tcl',script)
    env=os.environ.copy(); env.update(FFN_RUN=str(run),FFN_DATA=str(ROOT/'data'))
    cmd=['vitis-run','--mode','hls','--tcl',str(script)]
    with (retry/'console.log').open('w') as log:
        result=subprocess.run(cmd,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
    meta.setdefault('verification_attempts',[]).append({'directory':retry.name,'returncode':result.returncode,
        'script_sha256':hashlib.sha256(script.read_bytes()).hexdigest()})
    meta.update(status='pass' if result.returncode==0 else 'failed',cosim_requested=True,export_requested=True)
    (run/'run.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('RTL_RETRY',meta['status'],retry,flush=True)
    if result.returncode: print('\n'.join((retry/'console.log').read_text().splitlines()[-30:]))
    raise SystemExit(result.returncode)


if __name__=='__main__': main()
