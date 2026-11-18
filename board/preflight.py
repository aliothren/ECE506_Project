"""Read-only checks; this module never imports PYNQ or accesses PL registers."""
import hashlib
import json
from pathlib import Path
import struct

from interface import inspect_hwh


def bit_part(path):
    data = Path(path).read_bytes()
    pos = 2 + struct.unpack_from('>H', data)[0]
    if data[pos:pos+2] != b'\x00\x01':
        raise ValueError('Invalid bitstream header')
    pos += 2
    fields = {}
    for expected in b'abcd':
        if data[pos] != expected:
            raise ValueError('Invalid bitstream field')
        length = struct.unpack_from('>H', data, pos+1)[0]
        fields[chr(expected)] = data[pos+3:pos+3+length].rstrip(b'\x00').decode('ascii')
        pos += 3 + length
    if data[pos:pos+1] != b'e' or struct.unpack_from('>I', data, pos+1)[0] != len(data)-pos-5:
        raise ValueError('Truncated bitstream payload')
    return fields['b']


def preflight(package):
    package = Path(package).resolve()
    manifest = json.loads((package/'manifest.json').read_text())
    required = {'ffn.bit', 'ffn.hwh', 'ffn_host.py', 'interface.py', 'reset_checks.py',
                'preflight.py', 'session_guard.py', 'ffn_board.ipynb', 'run_cpu.py',
                'data/manifest.json', 'data/index.txt', 'reference/ffn_cpu.cpp',
                'reference/fixtures.h', 'audit/control_verification.json',
                'audit/done_idle_verification.json'}
    hashes = manifest.get('sha256', {})
    if not required.issubset(hashes):
        raise ValueError('Incomplete package manifest')
    for name, expected in hashes.items():
        path = (package/name).resolve()
        if package not in path.parents or not path.is_file():
            raise ValueError('Invalid or missing package member: '+name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Package hash mismatch: '+name)
    if manifest['part'] != 'xc7z020clg400-1' or manifest['target_clock_mhz'] != 100:
        raise ValueError('Wrong device or clock target')
    if bit_part(package/'ffn.bit') != '7z020clg400':
        raise ValueError('Wrong bitstream device')
    if any(float(manifest['implementation'][key]) < 0 for key in ('setup_wns_ns', 'hold_whs_ns')):
        raise ValueError('Implementation does not meet timing')
    interface = inspect_hwh(package/'ffn.hwh')
    expected = {'parameters': [0x18, 0x1c], 'input': [0x24, 0x28],
                'output': [0x30, 0x34], 'operation': 0x3c, 'return': 0x10}
    if interface != manifest['interface'] or interface['offsets'] != expected:
        raise ValueError('Unexpected control ABI')
    audit = json.loads((package/'audit/control_verification.json').read_text())
    if audit['status'] != 'pass' or audit['bit_sha256'] != hashes['ffn.bit'] or audit['hwh_sha256'] != hashes['ffn.hwh']:
        raise ValueError('Control verification does not match this overlay')
    completion = json.loads((package/'audit/done_idle_verification.json').read_text())
    if completion['status'] != 'pass' or completion['bit_sha256'] != hashes['ffn.bit'] or completion['hwh_sha256'] != hashes['ffn.hwh']:
        raise ValueError('Completion/idle verification does not match this overlay')
    total = 0
    for line in (package/'data/index.txt').read_text().splitlines():
        name, count = line.split()
        count = int(count)
        if count <= 0:
            raise ValueError('Empty fixture')
        for member, size in [('params.bin', 33152), ('input.bin', count*128),
                             ('hidden.bin', count*256), ('output.bin', count*128)]:
            relative = 'data/'+name+'/'+member
            if relative not in hashes or (package/relative).stat().st_size != size:
                raise ValueError('Invalid fixture: '+relative)
        total += count
    if total != 206:
        raise ValueError('Incomplete correctness suite')
    return manifest, interface
