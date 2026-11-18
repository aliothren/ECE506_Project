#!/usr/bin/env python3
"""Compile and measure the CPU reference on the board; save boundary and environment."""
import csv
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import time

from preflight import preflight


def main():
    root=Path(__file__).resolve().parent
    manifest,_=preflight(root)
    if platform.machine() not in ('armv7','armv7l'):
        raise RuntimeError('CPU measurements must run on the PYNQ-Z2, not the build host')
    command=['g++','-std=c++17','-O3','reference/ffn_cpu.cpp','-o','ffn_cpu']
    environment={'system':platform.uname()._asdict(),'time':time.time(),
                 'compiler':subprocess.check_output(['g++','--version'],universal_newlines=True),
                 'compile_command':command,'data_manifest':json.loads((root/'data/manifest.json').read_text()),
                 'source_sha256':manifest['sha256']['reference/ffn_cpu.cpp'],
                 'cpuinfo':Path('/proc/cpuinfo').read_text(),
                 'frequency':{str(p):p.read_text().strip() for p in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_*') if p.is_file()}}
    subprocess.run(command,cwd=root,check=True)
    with (root/'cpu_run.log').open('w') as log:
        subprocess.run(['./ffn_cpu','data','cpu_raw.csv'],cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
    with (root/'cpu_raw.csv').open() as f:
        rows=list(csv.DictReader(f))
    expected=[(r,i,i%64) for r in range(3) for i in range(1000)]
    actual=[tuple(int(row[k]) for k in ('round','iteration','input_index')) for row in rows]
    if actual!=expected or any(row['correct']!='1' or int(row['elapsed_ns'])<=0 for row in rows):
        raise RuntimeError('Incomplete or incorrect CPU measurements')
    values=sorted(int(row['elapsed_ns']) for row in rows)
    # NumPy's default percentile uses linear interpolation.
    p=.95*(len(values)-1); lo=int(p)
    summary={'metadata':environment,'metric':'compiled scalar C++ CPU inference with parameters/input already in memory',
             'calls':len(values),'median_ns':statistics.median(values),
             'p95_ns':values[lo]+(values[lo+1]-values[lo])*(p-lo),'correct':True}
    (root/'cpu_results.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='metadata'},indent=2))


if __name__=='__main__': main()
