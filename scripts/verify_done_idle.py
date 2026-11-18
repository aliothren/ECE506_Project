#!/usr/bin/env python3
"""Exercise completion-before-idle on the actual exported AXI-Lite control RTL."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
run=Path(sys.argv[1]).resolve();dest=run/'done_idle_verification';dest.mkdir(exist_ok=False)
inputs={'tb_done_idle.v':ROOT/'tests/rtl/tb_done_idle.v',
        'ffn_control_s_axi.v':run/'project/solution/syn/verilog/ffn_control_s_axi.v',
        'reset_vendor_netlist.v':run/'control_verification/reset_vendor_netlist.v'}
for name,p in inputs.items():shutil.copy2(p,dest/name)
commands=[['xvlog','--relax']+list(inputs),
          ['xelab','--relax','-L','unisims_ver','-L','unimacro_ver','-L','secureip','tb_done_idle','glbl','-s','done_idle_tb'],
          ['xsim','done_idle_tb','-runall']]
for label,cmd in zip(['compile','elaborate','simulation'],commands):
    with (dest/(label+'.log')).open('w') as log:
        subprocess.run(cmd,cwd=dest,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
if 'DONE_IDLE_TEST_PASS:' not in (dest/'simulation.log').read_text():raise RuntimeError('Missing pass marker')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record={'status':'pass','scope':'Actual AXI-Lite control RTL, controlled done/idle timing, vendor reset netlist',
        'bit_sha256':digest(run/'overlay/ffn.bit'),'hwh_sha256':digest(run/'overlay/ffn.hwh'),
        'commands':commands,'files_sha256':{n:digest(dest/n) for n in inputs}}
(dest/'done_idle_verification.json').write_text(json.dumps(record,indent=2)+'\n')
print('DONE_IDLE_VERIFICATION_PASS',run.parent.name)
