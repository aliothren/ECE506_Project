#!/usr/bin/env python3
"""Build a verified HLS run into a local PYNQ-Z2 overlay; no board access."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('run',type=Path)
    args=p.parse_args()
    run=args.run.resolve()
    meta=json.loads((run/'run.json').read_text())
    if meta['status']!='pass' or not meta['cosim_requested']:
        raise RuntimeError('Require successful HLS + RTL before implementation')
    if not (run/'project/solution/impl/ip/component.xml').exists():
        raise RuntimeError('Export HLS IP first')
    if (run/'vivado').exists():
        raise RuntimeError('Existing implementation: preserve it; use a new run for rebuilding')
    build_source=run/'implementation_source'; build_source.mkdir()
    shutil.copytree(ROOT/'vivado',build_source/'vivado')
    # Snapshot ROOT is implementation_source, which contains its own board presets.
    env=os.environ.copy(); env['FFN_BUILD_RUN']=str(run)
    command=['vivado','-mode','batch','-source',str(build_source/'vivado/build.tcl')]
    with (run/'vivado_console.log').open('w') as log:
        result=subprocess.run(command,env=env,cwd=run,stdout=log,stderr=subprocess.STDOUT)
    record={'command':command,'returncode':result.returncode,'board_tested':False,
            'finished_utc':datetime.now(timezone.utc).isoformat()}
    (run/'implementation_run.json').write_text(json.dumps(record,indent=2)+'\n')
    print('VIVADO_BUILD', 'pass' if result.returncode==0 else 'failed',run,flush=True)
    if result.returncode: print('\n'.join((run/'vivado_console.log').read_text().splitlines()[-35:]))
    raise SystemExit(result.returncode)


if __name__=='__main__': main()
