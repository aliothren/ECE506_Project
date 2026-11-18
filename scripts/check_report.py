#!/usr/bin/env python3
"""Check report references, source structure and measured tables."""
import csv
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    path = ROOT / 'report/ffn_report.tex'
    source = path.read_text()
    text = re.sub(r'(?<!\\)%[^\n]*', '', source)
    stack = []
    for match in re.finditer(r'\\(begin|end)\{([^}]+)\}', text):
        action, name = match.groups()
        if action == 'begin':
            stack.append(name)
        else:
            require(bool(stack) and stack.pop() == name, 'Mismatched TeX environment: ' + name)
    require(not stack, 'Unclosed TeX environments')
    depth = 0
    for match in re.finditer(r'(?<!\\)[{}]', text):
        depth += 1 if match.group() == '{' else -1
        require(depth >= 0, 'Unexpected closing brace')
    require(depth == 0, 'Unclosed braces')
    labels = re.findall(r'\\label\{([^}]+)\}', text)
    require(len(labels) == len(set(labels)), 'Duplicate labels')
    require(set(re.findall(r'\\(?:ref|eqref)\{([^}]+)\}', text)) <= set(labels), 'Unresolved labels')
    cited = {item.strip() for group in re.findall(r'\\cite\{([^}]+)\}', text) for item in group.split(',')}
    require(cited <= set(re.findall(r'\\bibitem\{([^}]+)\}', text)), 'Unresolved citations')
    figures = re.findall(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}', text)
    require(bool(figures) and all((ROOT / 'figures' / name).is_file() for name in figures), 'Missing figures')
    tables = re.findall(r'\\begin\{table\}.*?\\end\{table\}', text, re.S)

    def table_rows(label):
        found = [t for t in tables if '\\label{' + label + '}' in t]
        require(len(found) == 1, 'Missing/ambiguous table: ' + label)
        rows = {}
        for line in found[0].splitlines():
            if '&' in line and line.rstrip().endswith('\\\\'):
                cells = [c.strip() for c in line.rstrip()[:-2].split('&')]
                rows[cells[0]] = cells[1:]
        return rows

    hls = list(csv.DictReader((ROOT / 'results/hls_results.csv').open()))
    htable = table_rows('tab:hls')
    rtl = table_rows('tab:rtl')
    geometry = table_rows('tab:geometry')
    for row in hls:
        cid = row['config_id']
        expected = [row['P'], row['Q'], row['fc1_main_ii'] or '--']
        expected += [f'{int(row[k]):,}' for k in ('compute_cycles', 'BRAM_18K', 'DSP', 'LUT', 'FF')]
        require(htable.get(cid) == expected, 'HLS table mismatch: ' + cid)
        if row['cosim_status'] == 'pass':
            expected = [f'{int(row[k]):,}' for k in ('rtl_inference_min_cycles', 'rtl_load_min_cycles')]
            require(rtl.get(cid) == expected, 'RTL table mismatch: ' + cid)
        if cid in geometry:
            memories = json.loads((ROOT / 'results/hls_reports' / cid / 'memory_mapping.json').read_text())
            require(len({(m['words'], m['bits']) for m in memories}) == 1, 'Nonuniform memory geometry')
            expected = [str(int(row['weight_banks_total']) // 2), f"{memories[0]['words']:,}",
                        str(memories[0]['bits']), row['weight_BRAM_18K']]
            require(geometry[cid] == expected, 'Geometry table mismatch: ' + cid)
    impl = table_rows('tab:impl')
    for row in csv.DictReader((ROOT / 'results/implementation_results.csv').open()):
        expected = [f'{int(float(row[k])):,}' for k in ('impl_LUT', 'impl_FF', 'impl_DSP', 'impl_BRAM_tiles')]
        expected += [f'{float(row[k]):.3f}' for k in ('setup_wns_ns', 'hold_whs_ns')]
        require(impl.get(row['config_id']) == expected, 'Implementation table mismatch')
    board = table_rows('tab:board')
    for row in csv.DictReader((ROOT / 'results/board_results.csv').open()):
        cid = row['config_id']
        label = cid + ': Python/FPGA host' if row['path'] == 'FPGA_host' else 'C++ CPU after ' + cid
        expected = [format(Decimal(row[k]).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP), ',.3f')
                    for k in ('median_us', 'p95_us', 'max_us')]
        require(board.get(label) == expected, 'Board table mismatch: ' + label)
    coverage = table_rows('tab:coverage')
    cases = json.loads((ROOT / 'data/manifest.json').read_text())['cases']
    counts = {c['name']: c['inferences'] for c in cases}
    for key, label in [('zero', 'Zero'), ('bias_only', 'Bias only'), ('routing', 'Routing'),
                       ('extremes', 'Extremes'), ('cancellation', 'Cancellation'), ('rounding', 'Rounding')]:
        require(coverage[label][0] == str(counts[key]), 'Coverage table mismatch: ' + key)
    require(coverage['Total'][0] == str(sum(counts.values())), 'Wrong coverage total')
    require(coverage['Random (seeds 506, 507, 508)'][0] == str(sum(v for k, v in counts.items() if k.startswith('random_'))), 'Wrong random-case count')

    for manifest_path in (ROOT / 'deploy').glob('*_release1/manifest.json'):
        manifest = json.loads(manifest_path.read_text())
        for name, digest in manifest['sha256'].items():
            if name.endswith('.py') or name == 'ffn_board.ipynb':
                require(hashlib.sha256((ROOT / 'board' / name).read_bytes()).hexdigest() == digest,
                        'Board runtime differs from tested release: ' + name)
    record = {'status': 'pass', 'file': str(path.relative_to(ROOT)),
              'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'environments_and_braces_balanced': True, 'labels_citations_figures_resolve': True,
              'hls_rtl_memory_implementation_coverage_tables_match': True,
              'board_table_matches_raw_validated_summary': True,
              'release_runtime_source_hashes_match': True}
    (ROOT / 'results/report_source_validation.json').write_text(json.dumps(record, indent=2) + '\n')
    print('REPORT_SOURCE_CHECK_PASS: structure, references, six data tables and board runtime hashes')


if __name__ == '__main__':
    main()
