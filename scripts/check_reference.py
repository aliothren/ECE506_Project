#!/usr/bin/env python3
"""Reproduce fixtures and validate the independent CPU reference locally."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=ROOT/'results'; out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ffn-data-') as temp:
        subprocess.run(['python3',str(ROOT/'reference/golden.py'),'--output',temp],check=True)
        assert (Path(temp)/'manifest.json').read_bytes()==(ROOT/'data/manifest.json').read_bytes()
    flags=['-std=c++17','-O1','-ftrapv','-Wall','-Wextra']
    subprocess.run(['g++',*flags,str(ROOT/'reference/ffn_cpu.cpp'),'-o',str(out/'ffn_cpu_checked')],check=True)
    result=subprocess.run([str(out/'ffn_cpu_checked'),str(ROOT/'data')],check=True,text=True,capture_output=True)
    (out/'reference_validation.txt').write_text(result.stdout)
    version=subprocess.run(['g++','--version'],check=True,text=True,capture_output=True).stdout
    record={'status':'pass','fixture_regeneration':'byte_identical','cpu_validation':result.stdout.strip(),
            'compiler':version,'flags':flags,'validation':'signed overflow traps (not a full UBSan run)',
            'execution_target':'local build host, not board',
            'source_sha256':hashlib.sha256((ROOT/'reference/ffn_cpu.cpp').read_bytes()).hexdigest()}
    (out/'reference_validation.json').write_text(json.dumps(record,indent=2)+'\n')
    print(result.stdout,end='')


if __name__=='__main__': main()
