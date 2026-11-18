#!/usr/bin/env python3
"""Export vendor reports and the configuration metadata needed to interpret them."""
import csv
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    rows = list(csv.DictReader((ROOT / 'results/hls_results.csv').open()))
    target = ROOT / 'results/hls_reports'
    if target.exists():
        raise SystemExit('Snapshot already exists; preserve it or explicitly archive it first.')
    if not rows or any(not (ROOT / r['run'] / 'run.json').exists() for r in rows):
        raise SystemExit('Complete local build directories are required to export evidence.')
    records = {}
    for row in rows:
        run = ROOT / row['run']
        files = [run / 'run.json', run / 'memory_mapping.json']
        report = run / 'project/solution/syn/report'
        files += sorted(p for p in report.iterdir()
                        if p.suffix in ('.rpt', '.xml') and
                        p.name.startswith(('ffn_csynth', 'ffn_compute_csynth', 'dense_')))
        if row['cosim_status'] == 'pass':
            files += [run / 'project/solution/sim/report/ffn_cosim.rpt',
                      run / 'project/solution/sim/report/verilog/result.transaction.rpt']
        if row['implementation_status'] == 'pass':
            files += sorted(p for p in (run / 'implementation').iterdir()
                            if p.suffix in ('.rpt', '.csv', '.txt'))
        hashes = {}
        for source in files:
            relative = source.relative_to(run)
            dest = target / row['config_id'] / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            if source.name == 'run.json':
                metadata=json.loads(source.read_text())
                fields=('config','source_hash','source_files','cosim_requested','export_requested','status')
                selected_metadata={key:metadata[key] for key in fields}
                selected_metadata['config'].pop('status',None)
                dest.write_text(json.dumps(selected_metadata,indent=2)+'\n')
            else:
                dest.write_bytes(source.read_bytes())
            hashes[relative.as_posix()] = hashlib.sha256(dest.read_bytes()).hexdigest()
        # C-simulation and synthesis evidence; RTL measurements are in the co-simulation reports.
        log = run / 'console.log'
        selected = [line for line in log.read_text(errors='replace').splitlines()
                    if re.search(r'FFN_TEST_PASS.*mode=full|CSim done|WARNING: \[HLS 200-885\]|Finished Command (?:csim_design|csynth_design)', line)]
        excerpt = target / row['config_id'] / 'console_excerpt.txt'
        excerpt.write_text('\n'.join(selected) + '\n')
        hashes[excerpt.name] = hashlib.sha256(excerpt.read_bytes()).hexdigest()
        records[row['config_id']] = {'original_run': row['run'], 'sha256': hashes,
                                     'original_console_sha256': hashlib.sha256(log.read_bytes()).hexdigest()}
    (target / 'manifest.json').write_text(json.dumps({
        'format_version': 1,
        'scope': 'Vendor reports copied verbatim; run.json contains selected configuration metadata; console_excerpt.txt contains C-simulation and synthesis log extracts.',
        'configs': records}, indent=2) + '\n')
    print('EXPORTED_EVIDENCE:', len(records), 'configurations')


if __name__ == '__main__':
    main()
