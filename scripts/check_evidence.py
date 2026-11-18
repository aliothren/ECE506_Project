#!/usr/bin/env python3
"""Reparse the published raw-report snapshot without vendor tools or local builds."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import collect_results

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = ROOT / 'results/hls_reports'
    manifest = json.loads((base / 'manifest.json').read_text())
    rows = list(csv.DictReader((ROOT / 'results/hls_results.csv').open()))
    if len(rows) != 12 or {r['config_id'] for r in rows} != set(manifest['configs']):
        raise ValueError('Incomplete configuration snapshot')
    checked = 0
    with tempfile.TemporaryDirectory(prefix='ffn-evidence-') as temp:
        collect_results.ROOT = Path(temp)
        for row in rows:
            cid = row['config_id']
            record = manifest['configs'][cid]
            if record['original_run'] != row['run']:
                raise ValueError('Run identity mismatch: ' + cid)
            dest = Path(temp) / row['run']
            for name, expected in record['sha256'].items():
                source = base / cid / name
                if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                    raise ValueError('Report hash mismatch: ' + str(source))
                copied = dest / ('console.log' if name == 'console_excerpt.txt' else name)
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, copied)
                checked += 1
            measured = collect_results.readrun(dest)
            # These statuses depend on bitstreams and the board attestation, checked separately.
            excluded = {'implementation_status', 'board_status'}
            for key, value in measured.items():
                if key not in excluded and str(value) != row.get(key, ''):
                    raise ValueError(f'{cid} {key}: table={row.get(key)!r}, raw report={value!r}')
            meta = json.loads((dest / 'run.json').read_text())
            for name in ('hls/ffn.cpp', 'hls/dense.h', 'hls/ffn_types.h'):
                if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != meta['source_files'][name]:
                    raise ValueError('Hardware source differs from measured source: ' + name)
    print(f'EVIDENCE_CHECK_PASS: {len(rows)} configurations; {checked} report hashes and table values')


if __name__ == '__main__':
    main()
