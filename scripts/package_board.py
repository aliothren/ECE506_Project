#!/usr/bin/env python3
"""Package an implemented, timing-clean run; never mark it as board-tested."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'board'))
from interface import inspect_hwh
from preflight import preflight


def main():
    p=argparse.ArgumentParser()
    p.add_argument('run',type=Path)
    p.add_argument('--revision',default='audit3')
    args=p.parse_args()
    run=args.run.resolve()
    meta=json.loads((run/'run.json').read_text())
    if meta['status']!='pass' or not meta['cosim_requested']:
        raise RuntimeError('Require a successful run including RTL cosimulation')
    metrics=next(csv.DictReader((run/'implementation/implementation_metrics.csv').open()))
    if metrics['part']!='xc7z020clg400-1' or not all(float(metrics[k])>=0 for k in ('setup_wns_ns','hold_whs_ns')):
        raise RuntimeError('Wrong target or failed timing')
    proof=json.loads((run/'control_verification/control_verification.json').read_text())
    if proof['status']!='pass':
        raise RuntimeError('Control/reset verification must pass first')
    interface=inspect_hwh(run/'overlay/ffn.hwh')
    cid=meta['config']['config_id']
    if not args.revision.isalnum():
        raise ValueError('Revision must be alphanumeric')
    dest=ROOT/'deploy'/(cid+'_'+run.name+'_'+args.revision)
    dest.mkdir(parents=True,exist_ok=False)
    for name in ('ffn.bit','ffn.hwh'):
        shutil.copy2(run/'overlay'/name,dest/name)
    for name in ('ffn_host.py','interface.py','reset_checks.py','preflight.py','session_guard.py',
                 'run_cpu.py','ffn_board.ipynb','README.md'):
        shutil.copy2(ROOT/'board'/name,dest/name)
    (dest/'audit').mkdir()
    for pattern in ('control_verification.json','simulation_*.log','tb_*.v','axi_tasks.vh'):
        for f in (run/'control_verification').glob(pattern):
            shutil.copy2(f,dest/'audit'/f.name)
    shutil.copy2(ROOT/('results/interface_validation_'+cid+'.json'),dest/'audit/interface_validation.json')
    shutil.copy2(run/'done_idle_verification/done_idle_verification.json',dest/'audit/done_idle_verification.json')
    shutil.copy2(run/'done_idle_verification/simulation.log',dest/'audit/simulation_done_idle.log')
    shutil.copy2(run/'done_idle_verification/tb_done_idle.v',dest/'audit/tb_done_idle.v')
    shutil.copytree(ROOT/'data',dest/'data')
    (dest/'reference').mkdir()
    for name in ('ffn_cpu.cpp','fixtures.h'):
        shutil.copy2(run/'source/reference'/name,dest/'reference'/name)
    files={str(f.relative_to(dest)):hashlib.sha256(f.read_bytes()).hexdigest()
           for f in sorted(dest.rglob('*')) if f.is_file()}
    configuration={k:v for k,v in meta['config'].items() if k!='status'}
    manifest={'config':configuration,'source_hash':meta['source_hash'],'run':run.name,
              'package_revision':args.revision,
              'part':metrics['part'],'target_clock_mhz':100,'board_tested':False,
              'implementation':metrics,'interface':interface,'sha256':files}
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    preflight(dest)
    with zipfile.ZipFile(str(dest)+'.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for f in sorted(dest.rglob('*')):
            if f.is_file(): archive.write(f,f.relative_to(dest.parent))
    print('PACKAGE_PASS:',str(dest)+'.zip')


if __name__=='__main__': main()
