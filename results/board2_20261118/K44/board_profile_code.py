# Executed in the already validated, allocated notebook session. No reset/reprogramming.
import csv
import json
import time
from pathlib import Path
from pynq import Clocks

session._available('allocated')
if not session.ready or not session.validation:
    raise RuntimeError('Require successful validation and loaded parameters before profiling')
np = session.np
x = np.fromfile(str(session.package/'data/random_506/input.bin'), dtype='<i2').reshape(64,64)
gold = np.fromfile(str(session.package/'data/random_506/output.bin'), dtype='<i2').reshape(64,64)
profile_rows=[]
for i in range(100):
    idx=i%64
    start=time.perf_counter()
    session.input[:]=x[idx].view('<u8')
    session.input.flush()
    after_input=time.perf_counter()
    status=session._call(1)
    after_call=time.perf_counter()
    session._expect(status==0,'Profiling RUN status failure')
    session.output.invalidate()
    result=session.output.view(np.int16).copy()
    after_output=time.perf_counter()
    session._expect(np.array_equal(result,gold[idx]),'Profiling output mismatch')
    profile_rows.append([i,idx,(after_input-start)*1e9,(after_call-after_input)*1e9,
                         (after_output-after_call)*1e9,(after_output-start)*1e9,1])
fields=['iteration','input_index','input_copy_flush_ns','control_and_execution_ns',
        'output_invalidate_copy_ns','total_ns','correct']
with (session.package/'board_profile_raw.csv').open('w',newline='') as f:
    writer=csv.writer(f);writer.writerow(fields);writer.writerows(profile_rows)
profile={'config':session.manifest['config']['config_id'],'samples':100,'correct':True,
         'scope':'Diagnostic phase timings with extra timestamps; separate from primary benchmark.',
         'median_ns':{fields[j]:float(np.median([r[j] for r in profile_rows])) for j in range(2,6)},
         'numpy_version':np.__version__,'cpu_clock_mhz':float(Clocks.cpu_mhz),
         'pl_clock_mhz':float(Clocks.fclk0_mhz)}
(session.package/'board_profile.json').write_text(json.dumps(profile,indent=2)+'\n')
print(json.dumps(profile,indent=2),flush=True)
