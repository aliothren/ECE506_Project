#!/usr/bin/env python3
"""Collect HLS, RTL and implementation metrics from completed runs."""
import csv
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


def readrun(run):
    meta=json.loads((run/'run.json').read_text())
    cfg=meta['config']
    result={k:cfg[k] for k in ('config_id','P','Q','weight_layout','compute_pipeline')}
    result.update(run=str(run.relative_to(ROOT)),source_hash=meta['source_hash'],
                  status=meta['status'],csim_status='pending',synth_status='pending',
                  cosim_status='pending' if meta['cosim_requested'] else 'not_requested')
    hardware={k:v for k,v in meta['source_files'].items()
              if k in ('hls/ffn.cpp','hls/dense.h','hls/ffn_types.h')}
    result['hardware_source_hash']=hashlib.sha256(json.dumps(hardware,sort_keys=True).encode()).hexdigest()
    log=(run/'console.log').read_text(errors='replace') if (run/'console.log').exists() else ''
    if 'CSim done with 0 errors' in log: result['csim_status']='pass'
    report=run/'project/solution/syn/report'
    top=report/'ffn_csynth.xml'
    if top.exists():
        t=ET.parse(top).getroot()
        result['synth_status']='pass' if 'Finished Command csynth_design' in log else 'report_generated'
        result['tool_version']=t.findtext('ReportVersion/Version')
        result['estimated_clock_ns']=t.findtext('PerformanceEstimates/SummaryOfTimingAnalysis/EstimatedClockPeriod')
        for key in ('BRAM_18K','DSP','LUT','FF'):
            result[key]=t.findtext('AreaEstimates/Resources/'+key)
        memory_block=(report/'ffn_csynth.rpt').read_text().split('    * Memory:')[1].split('    * FIFO:')[0]
        memories=[]
        for line in memory_block.splitlines():
            cells=[s.strip() for s in line.strip().strip('|').split('|')]
            if not re.search(r'w[12](?:_|$)',cells[0]): continue
            if len(cells)!=10: raise RuntimeError('Unknown memory table format')
            memories.append({'name':cells[0],'module':cells[1],'BRAM_18K':int(cells[2]),
                             'words':int(cells[6]),'bits':int(cells[7]),'banks':int(cells[8])})
        if not memories: raise RuntimeError('Missing weight memory evidence')
        if any('RAM_1P_BRAM' not in m['module'] for m in memories):
            raise RuntimeError('Weight memory changed from requested single-port BRAM')
        expected_banks=(2*int(cfg['P']) if cfg['weight_layout']=='packed' else
                        2 if cfg['weight_layout'] in ('scalar','unpartitioned') else
                        2*int(cfg['P'])*int(cfg['Q']))
        assert sum(m['banks'] for m in memories)==expected_banks
        assert sum(m['words']*m['bits']*m['banks'] for m in memories)==262144
        result.update(weight_banks_total=expected_banks,
                      weight_BRAM_18K=sum(m['BRAM_18K'] for m in memories),
                      weight_word_bits=','.join(str(n) for n in sorted({m['bits'] for m in memories})),
                      actual_memory_type='RAM_1P_BRAM')
        (run/'memory_mapping.json').write_text(json.dumps(memories,indent=2)+'\n')
        def latency(path):
            return ET.parse(path).findtext('PerformanceEstimates/SummaryOfOverallLatency/Worst-caseLatency')
        result['compute_cycles']=latency(report/'ffn_compute_csynth.xml')
        for label,prefix in [('fc1','dense_64_128_true'),('fc2','dense_128_64_false')]:
            layers=[p for p in report.glob(prefix+'*csynth.xml') if 'Pipeline' not in p.name]
            if len(layers)!=1: raise RuntimeError('Ambiguous layer report: '+str(layers))
            result[label+'_cycles']=latency(layers[0])
            ii=[]
            for p in report.glob(prefix+'*csynth.xml'):
                for e in ET.parse(p).iter():
                    if e.tag=='INPUT_GROUP' and e.findtext('PipelineII'):
                        ii.append(e.findtext('PipelineII'))
            if len(ii)>1: raise RuntimeError('Ambiguous input loop II')
            result[label+'_main_ii']=ii[0] if ii else ''
    cosim=run/'project/solution/sim/report/ffn_cosim.rpt'
    if cosim.exists():
        txt=cosim.read_text()
        if re.search(r'\|\s*Verilog\s*\|\s*Pass\s*\|',txt): result['cosim_status']='pass'
        elif 'Fail' in txt: result['cosim_status']='failed'
    transactions=run/'project/solution/sim/report/verilog/result.transaction.rpt'
    if result['cosim_status']=='pass' and transactions.exists():
        measured=re.findall(r'transaction\s+(\d+):\s+(\d+)\s+(\S+)',transactions.read_text())
        # ffn_test.cpp RTL mode: two error calls, then four LOAD/RUN/RUN groups.
        if len(measured)!=14: raise RuntimeError('Unexpected RTL transaction sequence')
        loads=[int(lat) for idx,lat,_ in measured if int(idx) in (2,5,8,11)]
        inference=[int(lat) for idx,lat,_ in measured if int(idx)>1 and int(idx) not in (2,5,8,11)]
        result.update(rtl_load_min_cycles=min(loads),rtl_load_max_cycles=max(loads),
                      rtl_inference_min_cycles=min(inference),rtl_inference_max_cycles=max(inference))
    result['memory_port_warnings']=len(re.findall(r'WARNING: \[HLS 200-885\]',log))
    result['implementation_status']='not_run'
    m=run/'implementation/implementation_metrics.csv'
    if m.exists():
        metrics=next(csv.DictReader(m.open()))
        result.update(setup_wns_ns=metrics['setup_wns_ns'],hold_whs_ns=metrics['hold_whs_ns'])
        result['implementation_status']='pass' if (run/'overlay/ffn.bit').exists() else 'not_released'
        util=run/'implementation/utilization.rpt'
        if util.exists():
            names={'Slice LUTs':'impl_LUT','Slice Registers':'impl_FF',
                   'DSPs':'impl_DSP','Block RAM Tile':'impl_BRAM_tiles'}
            for line in util.read_text().splitlines():
                cells=[s.strip() for s in line.strip().strip('|').split('|')]
                if len(cells)>1 and cells[0] in names:
                    result[names[cells[0]]]=float(cells[1])
            if 'impl_BRAM_tiles' in result:
                result['impl_BRAM_18K_equiv']=2*result['impl_BRAM_tiles']
    result['board_status']='not_run'
    board_file=ROOT/'results/board_results.json'
    if board_file.exists() and (run/'overlay/ffn.bit').exists():
        board=json.loads(board_file.read_text())
        evidence=board.get('configs',{}).get(result['config_id'])
        if evidence and board.get('status')=='pass' and evidence.get('status')=='pass':
            if evidence['run']==run.name and evidence['bit_sha256']==hashlib.sha256((run/'overlay/ffn.bit').read_bytes()).hexdigest():
                result['board_status']='pass'
    return result


def writecsv(path,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)


def main():
    rows=[readrun(p.parent) for p in sorted((ROOT/'runs').glob('*/*/run.json'))]
    if not rows:
        raise SystemExit('No local HLS runs found; published result tables were left unchanged. '
                         'Use check_evidence.py to validate the published snapshot, or run HLS first.')
    out=ROOT/'results'; out.mkdir(exist_ok=True)
    latest={}
    for r in rows: latest[r['config_id']]=r
    rows=list(latest.values())
    writecsv(out/'hls_results.csv',rows)
    implemented=[{k:v for k,v in r.items() if k in ('config_id','run','source_hash','implementation_status',
                  'setup_wns_ns','hold_whs_ns','board_status') or k.startswith('impl_')}
                 for r in rows if r['implementation_status']=='pass']
    if implemented: writecsv(out/'implementation_results.csv',implemented)
    (out/'hls_results.json').write_text(json.dumps(rows,indent=2)+'\n')
    configs=list(csv.DictReader((ROOT/'experiments.csv').open()))
    for cfg in configs:
        r=latest.get(cfg['config_id'])
        if r:
            cfg['status']=('board_pass' if r['board_status']=='pass' else
                           'implementation_pass' if r['implementation_status']=='pass' else
                           'rtl_pass' if r['cosim_status']=='pass' else
                           'synth_pass' if r['synth_status']=='pass' else
                           'csim_pass' if r['csim_status']=='pass' else r['status'])
    writecsv(ROOT/'experiments.csv',configs)
    print('config  Csim   Synth  RTL    compute   II1 II2 BRAM DSP LUT')
    for r in rows:
        print(r['config_id'],r['csim_status'],r['synth_status'],r['cosim_status'],
              *[r.get(k,'-') for k in ('compute_cycles','fc1_main_ii','fc2_main_ii','BRAM_18K','DSP','LUT')])


if __name__=='__main__': main()
