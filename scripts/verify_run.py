#!/usr/bin/env python3
"""Run RTL co-simulation and IP export for a synthesized design."""
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
    if not (run/'project/solution/syn/report/ffn_csynth.xml').exists():
        raise RuntimeError('Synthesis report is required before RTL verification')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    verification=run/('verification_'+stamp); verification.mkdir()
    script=verification/'verify.tcl'
    shutil.copy2(ROOT/'hls/verify.tcl',script)
    env=os.environ.copy(); env.update(FFN_RUN=str(run),FFN_DATA=str(ROOT/'data'))
    cmd=['vitis-run','--mode','hls','--tcl',str(script)]
    with (verification/'console.log').open('w') as log:
        result=subprocess.run(cmd,cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
    meta['rtl_verification']={'directory':verification.name,'returncode':result.returncode,
        'script_sha256':hashlib.sha256(script.read_bytes()).hexdigest()}
    meta.update(status='pass' if result.returncode==0 else 'failed',cosim_requested=True,export_requested=True)
    (run/'run.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('RTL_VERIFICATION',meta['status'],verification,flush=True)
    if result.returncode: print('\n'.join((verification/'console.log').read_text().splitlines()[-30:]))
    raise SystemExit(result.returncode)


if __name__=='__main__': main()
