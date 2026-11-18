#!/usr/bin/env python3
"""Verify actual run RTL + vendor reset netlist; no board connection."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'board'))
from interface import inspect_hwh


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    run = args.run.resolve()
    inspect_hwh(run/'overlay/ffn.hwh')
    dest = run/'control_verification'
    dest.mkdir(exist_ok=False)
    for f in (ROOT/'tests/rtl').iterdir():
        shutil.copy2(f, dest/f.name)
    reset = run/'vivado/ffn_pynq_z2.gen/sources_1/bd/ffn_system/ip/ffn_system_reset_0/ffn_system_reset_0_sim_netlist.v'
    shutil.copy2(reset, dest/'reset_vendor_netlist.v')
    rtl = run/'project/solution/syn/verilog'
    shutil.copytree(rtl, dest/'rtl')
    for f in rtl.glob('*.dat'):
        shutil.copy2(f, dest/f.name)  # Generated RTL resolves initialization files relative to cwd.
    for label, case, count in [('a', 'random_506', 32), ('b', 'random_507', 16)]:
        for output, member, words in [('params', 'params.bin', 4144), ('inputs', 'input.bin', count), ('gold', 'output.bin', count)]:
            data = (ROOT/'data'/case/member).read_bytes()[:words*8]
            (dest/(output+'_'+label+'.hex')).write_text(''.join('%016x\n' % word[0] for word in struct.iter_unpack('<Q', data)))
    commands = []
    def execute(cmd, log):
        commands.append(cmd)
        with (dest/log).open('w') as f:
            result = subprocess.run(cmd, cwd=dest, stdout=f, stderr=subprocess.STDOUT, timeout=300)
        if result.returncode:
            raise RuntimeError('Failed '+log+'; inspect '+str(dest/log))
    execute(['xvlog', '--relax', '-i', str(dest), 'reset_vendor_netlist.v'] +
            [str(f.relative_to(dest)) for f in sorted((dest/'rtl').glob('*.v'))] +
            ['tb_reset.v', 'tb_registers.v', 'tb_lifecycle.v'], 'compile.log')
    markers = {'reset': 'RESET_TEST_PASS:', 'registers': 'REGISTER_TEST_PASS:', 'lifecycle': 'LIFECYCLE_TEST_PASS:'}
    for name, marker in markers.items():
        execute(['xelab', '--relax', '--debug', 'typical', '-L', 'unisims_ver', '-L', 'unimacro_ver',
                 '-L', 'secureip', 'tb_'+name, 'glbl', '-s', name+'_tb'], 'elaborate_'+name+'.log')
        execute(['xsim', name+'_tb', '-runall'], 'simulation_'+name+'.log')
        if marker not in (dest/('simulation_'+name+'.log')).read_text():
            raise RuntimeError('Missing success marker: '+name)
    files = {str(f.relative_to(dest)): digest(f) for f in sorted(dest.rglob('*'))
             if f.is_file() and (f.suffix in ('.v', '.vh', '.hex', '.dat') or f.name.startswith(('compile', 'elaborate', 'simulation')))}
    record = {'status': 'pass', 'run': run.name, 'config': run.parent.name,
              'bit_sha256': digest(run/'overlay/ffn.bit'), 'hwh_sha256': digest(run/'overlay/ffn.hwh'),
              'scope': 'Actual HLS RTL and vendor reset netlist; behavioral bounded/stalling DDR. PS7/SmartConnect/Linux/caches not simulated.',
              'tests': list(markers), 'commands': commands, 'files_sha256': files}
    (dest/'control_verification.json').write_text(json.dumps(record, indent=2)+'\n')
    print('CONTROL_VERIFICATION_PASS', run.parent.name, dest)


if __name__ == '__main__':
    main()
