#!/usr/bin/env python3
"""Validate board2 raw samples and bind results to the deployed release hashes."""
import csv
import hashlib
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/board2_20261118'


def percentile(values,p):
    a=sorted(values);x=(len(a)-1)*p;lo=int(x);hi=min(lo+1,len(a)-1)
    return a[lo]+(a[hi]-a[lo])*(x-lo)


def validate_samples(path,summary):
    with path.open() as f: rows=list(csv.DictReader(f))
    expected=[(r,i,i%64) for r in range(3) for i in range(1000)]
    actual=[tuple(int(row[k]) for k in ('round','iteration','input_index')) for row in rows]
    if actual!=expected or any(r['correct']!='1' or int(r['elapsed_ns'])<=0 for r in rows):
        raise ValueError('Incorrect/incomplete samples: '+str(path))
    values=[int(r['elapsed_ns']) for r in rows]
    med=statistics.median(values);p95=percentile(values,.95)
    if not summary['correct'] or summary['calls']!=3000 or abs(summary['median_ns']-med)>1e-6 or abs(summary['p95_ns']-p95)>1e-6:
        raise ValueError('Summary does not match raw samples: '+str(path))
    return {'calls':3000,'median_us':med/1000,'p95_us':p95/1000,
            'min_us':min(values)/1000,'max_us':max(values)/1000,
            'round_median_us':[statistics.median(values[r*1000:(r+1)*1000])/1000 for r in range(3)]}


def main():
    configs={};table=[];boot=None;cpu_hash=None
    for cid in ('B11','K44'):
        folder=BASE/cid
        read=lambda name:json.loads((folder/name).read_text())
        state=read('remote_run.json');manifest=read('manifest.json');env=read('board_environment.json')
        board=read('board_results.json');cpu=read('cpu_results.json');validation=read('board_validation.json')
        health=read('board_health_after.json');profile=read('board_profile.json')
        if state.get('failure') or not state.get('kernel_stopped_utc') or not all(x in state['completed'] for x in ('validate','benchmark','close','cpu')):
            raise ValueError('Run is incomplete: '+cid)
        if env['hostname']!='pynq2' or env['machine']!='armv7l' or health['fpga_manager']!='operating' or health['guard']['state']!='closed':
            raise ValueError('Unexpected board/final state')
        if boot is not None and boot!=env['boot_id']:raise ValueError('Different board boots')
        boot=env['boot_id']
        release=cid+'_'+manifest['run']+'_'+manifest['package_revision']
        archive=ROOT/'deploy'/(release+'.zip')
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=state['zip_sha256']:
            raise ValueError('Archive differs from uploaded bytes')
        if manifest['package_revision']!='audit3' or manifest['config']['config_id']!=cid:
            raise ValueError('Unexpected release')
        local_manifest=json.loads((ROOT/'deploy'/release/'manifest.json').read_text())
        if manifest!=local_manifest:raise ValueError('Remote manifest differs')
        if board['metadata']['bit_sha256']!=manifest['sha256']['ffn.bit'] or board['metadata']['pl_clock_mhz']!=100:
            raise ValueError('Bitstream/clock mismatch')
        data=board['metadata']['data_manifest']
        if data!=validation['metadata']['data_manifest'] or data!=cpu['metadata']['data_manifest']:
            raise ValueError('Fixture manifests differ')
        expected=[(r['name'],r['inferences']) for r in data['cases']]
        actual=[(r['case'],r['inferences']) for r in validation['results']]
        if actual!=expected or sum(r['inferences'] for r in validation['results'])!=206 or not all(r['correct'] for r in validation['results']):
            raise ValueError('Correctness suite incomplete')
        if 'CPU_REFERENCE_PASS: 206 inferences, both layers' not in (folder/'cpu_run.log').read_text():
            raise ValueError('CPU reference not checked')
        source_hash=cpu['metadata']['source_sha256']
        if source_hash!=manifest['sha256']['reference/ffn_cpu.cpp'] or (cpu_hash is not None and cpu_hash!=source_hash):
            raise ValueError('Different CPU reference sources')
        cpu_hash=source_hash
        fstats=validate_samples(folder/'board_raw.csv',board)
        cstats=validate_samples(folder/'cpu_raw.csv',cpu)
        with (folder/'board_profile_raw.csv').open() as f:prows=list(csv.DictReader(f))
        if len(prows)!=100 or any(r['correct']!='1' for r in prows) or not profile['correct']:
            raise ValueError('Diagnostic profile incomplete')
        for key,val in profile['median_ns'].items():
            if abs(statistics.median(float(r[key]) for r in prows)-val)>1e-5:raise ValueError('Profile summary mismatch')
        for kind,stats in [('FPGA_host',fstats),('CPU_compute',cstats)]:
            table.append({'config_id':cid,'path':kind,'calls':stats['calls'],'median_us':stats['median_us'],
                          'p95_us':stats['p95_us'],'min_us':stats['min_us'],'max_us':stats['max_us']})
        configs[cid]={'status':'pass','run':manifest['run'],'package_revision':manifest['package_revision'],
                      'zip_sha256':state['zip_sha256'],'bit_sha256':manifest['sha256']['ffn.bit'],
                      'hwh_sha256':manifest['sha256']['ffn.hwh'],'host_sha256':manifest['sha256']['ffn_host.py'],
                      'correctness_inferences':206,'fpga_host':fstats,'cpu_compute':cstats,
                      'profile':profile,'load_us':board['load_ns']/1000,
                      'normal_close':True,'kernel_stopped_utc':state['kernel_stopped_utc'],
                      'evidence_directory':str(folder.relative_to(ROOT)),
                      'evidence_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}}
    if configs['B11']['host_sha256']!=configs['K44']['host_sha256']:raise ValueError('Host comparison differs')
    result={'status':'pass','board':2,'hostname':'pynq2','date':'2026-11-18','boot_id':boot,
            'pl_clock_mhz':100,'cpu_clock_mhz':configs['K44']['profile']['cpu_clock_mhz'],
            'configs':configs,'fpga_host_speedup_B11_over_K44':configs['B11']['fpga_host']['median_us']/configs['K44']['fpga_host']['median_us'],
            'fpga_host_over_cpu_time_ratio':{c:configs[c]['fpga_host']['median_us']/configs[c]['cpu_compute']['median_us'] for c in configs},
            'boundaries':{'FPGA_host':'Python input copy/flush, control/execute/poll/status, output invalidate/copy; parameters resident',
                          'CPU_compute':'Compiled scalar C++ computation on resident arrays; no file I/O or validation',
                          'profile':'100 extra calls with per-phase timestamps, separate from primary 3000-call measurement'},
            'scope':'One PYNQ-Z2 reservation and boot; no Linux isolation/affinity tuning; no board hardware cycle counter'}
    (ROOT/'results/board_results.json').write_text(json.dumps(result,indent=2)+'\n')
    with (ROOT/'results/board_results.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
    for row in table:print(row)
    print('BOARD_RESULTS_CHECK_PASS; end-to-end B11/K44:',result['fpga_host_speedup_B11_over_K44'])

if __name__=='__main__':main()
