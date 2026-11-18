#!/usr/bin/env python3
"""Run isolated, source-snapshotted HLS experiments; never overwrite prior runs."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('configs', nargs='+')
    parser.add_argument('--cosim', action='store_true')
    parser.add_argument('--export', action='store_true', dest='export_ip')
    args=parser.parse_args()
    rows={r['config_id']:r for r in csv.DictReader((ROOT/'experiments.csv').open())}
    if not shutil.which('vitis-run'): parser.error('Source Vitis 2025.1 settings64.sh first')
    if not (ROOT/'data/manifest.json').exists(): parser.error('Generate data first')
    if any(c not in rows for c in args.configs): parser.error('Unknown configuration')
    for cid in args.configs:
        cfg=rows[cid]
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        run=ROOT/'runs'/cid/stamp
        src=run/'source'
        src.mkdir(parents=True)
        for folder in ('hls','reference'):
            shutil.copytree(ROOT/folder,src/folder,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(ROOT/'spec.md',src/'spec.md')
        files={str(p.relative_to(src)):hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(src.rglob('*')) if p.is_file()}
        source_hash=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
        data=ROOT/'data'
        # Record and verify immutable inputs without duplicating large files per run.
        manifest=json.loads((data/'manifest.json').read_text())
        for name,digest in manifest['sha256'].items():
            if hashlib.sha256((data/name).read_bytes()).hexdigest()!=digest:
                raise RuntimeError('Data hash mismatch: '+name)
        shutil.copy2(data/'manifest.json',run/'data_manifest.json')
        metadata={'config':cfg,'source_hash':source_hash,'source_files':files,
                  'started_utc':stamp,'cosim_requested':args.cosim,'export_requested':args.export_ip,
                  'status':'running','command':['vitis-run','--mode','hls','--tcl',str(src/'hls/run.tcl')]}
        path=run/'run.json'
        path.write_text(json.dumps(metadata,indent=2)+'\n')
        env=os.environ.copy()
        env.update(FFN_SOURCE=str(src),FFN_RUN=str(run),FFN_DATA=str(data),FFN_P=cfg['P'],FFN_Q=cfg['Q'],
                   FFN_LAYOUT={'cyclic_banked':'0','scalar':'0','unpartitioned':'1','packed':'2'}[cfg['weight_layout']],
                   FFN_PIPELINE='1' if cfg['compute_pipeline']=='on' else '0',
                   FFN_COSIM=str(int(args.cosim)),FFN_EXPORT=str(int(args.export_ip)))
        print(f'START {cid}: {run}',flush=True)
        with (run/'console.log').open('w') as log:
            result=subprocess.run(metadata['command'],cwd=run,env=env,stdout=log,stderr=subprocess.STDOUT)
        metadata.update(status='pass' if result.returncode==0 else 'failed',returncode=result.returncode,
                        finished_utc=datetime.now(timezone.utc).isoformat())
        path.write_text(json.dumps(metadata,indent=2)+'\n')
        print(f'FINISH {cid}: {metadata["status"]}',flush=True)
        if result.returncode:
            print('\n'.join((run/'console.log').read_text(errors='replace').splitlines()[-35:]),flush=True)
            return result.returncode
    return 0


if __name__=='__main__': sys.exit(main())
