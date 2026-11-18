#!/usr/bin/env python3
"""Validate extracted release contents and reject accidental package mismatches."""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'board'))
from preflight import preflight


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('archives',nargs='+',type=Path)
    args=parser.parse_args()
    results=[]
    for archive in args.archives:
        with tempfile.TemporaryDirectory(prefix='ffn-release-') as tmp:
            with zipfile.ZipFile(archive) as z:
                if z.testzip() is not None:
                    raise RuntimeError('Corrupt ZIP')
                z.extractall(tmp)
            package=next(Path(tmp).iterdir())
            manifest,interface=preflight(package)
            for f in package.glob('*.py'):
                ast.parse(f.read_text(),filename=f.name)
            nb=json.loads((package/'ffn_board.ipynb').read_text())
            code_cells=[c for c in nb['cells'] if c['cell_type']=='code']
            for c in code_cells:
                if c['execution_count'] is not None or c['outputs']:
                    raise RuntimeError('Notebook contains execution evidence')
                compile(''.join(c['source']),'<notebook>','exec')
            # Import the files actually extracted from the ZIP, not the source-tree runner.
            program='from ffn_host import FFNSession; s=FFNSession("."); print(s.stage); s.close()'
            run=subprocess.run([sys.executable,'-O','-c',program],cwd=package,
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
            if run.returncode or run.stdout.strip()!='preflight':
                raise RuntimeError(run.stderr or run.stdout)
            rejected=[]
            def reject(label):
                try: preflight(package)
                except (ValueError,KeyError,FileNotFoundError): rejected.append(label)
                else: raise RuntimeError('Bad package accepted: '+label)
            bit=package/'ffn.bit'; data=bit.read_bytes()
            bit.write_bytes(data[:-1]); reject('truncated_or_corrupt_bit'); bit.write_bytes(data)
            host=package/'ffn_host.py'; data=host.read_bytes()
            host.write_bytes(data+b'\n# modified\n'); reject('modified_host'); host.write_bytes(data)
            path=package/'manifest.json'
            for label,change in [
                ('empty_hash_manifest',lambda m:m.update(sha256={})),
                ('wrong_part',lambda m:m.update(part='xczu3eg-sbva484-1-e')),
                ('wrong_clock',lambda m:m.update(target_clock_mhz=125)),
                ('negative_timing',lambda m:m['implementation'].update(setup_wns_ns='-0.1')),
                ('wrong_register_map',lambda m:m['interface']['offsets'].update(operation=0x38)),
                ('wrong_bit_audit_binding',lambda m:m['sha256'].update({'ffn.bit':'0'*64})),
            ]:
                bad=copy.deepcopy(manifest); change(bad)
                path.write_text(json.dumps(bad)); reject(label)
                path.write_text(json.dumps(manifest))
            preflight(package)
            results.append({'file':str(archive.relative_to(ROOT) if archive.is_absolute() else archive),
                            'config':manifest['config']['config_id'],'revision':manifest['package_revision'],
                            'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                            'hashed_files':len(manifest['sha256']), 'notebook_code_cells':len(code_cells),
                            'rejected_package_faults':rejected, 'board_tested':False})
    record={'status':'pass','archives':results,'physical_board_accessed':False}
    (ROOT/'results/release_validation.json').write_text(json.dumps(record,indent=2)+'\n')
    print('RELEASE_CHECK_PASS:',len(results),'archives; 8 package faults rejected per archive')


if __name__=='__main__': main()
