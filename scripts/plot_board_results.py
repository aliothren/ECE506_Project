#!/usr/bin/env python3
"""Plot measured board results and diagnostic phases; PNG only."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
r=json.loads((ROOT/'results/board_results.json').read_text())
b,k=(r['configs'][x] for x in ('B11','K44'))
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,ax=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
values=[b['fpga_host']['median_us'],k['fpga_host']['median_us'],b['cpu_compute']['median_us'],k['cpu_compute']['median_us']]
p95=[b['fpga_host']['p95_us'],k['fpga_host']['p95_us'],b['cpu_compute']['p95_us'],k['cpu_compute']['p95_us']]
positions=np.arange(4)
bars=ax[0].bar(positions,values,color=['#506b9b','#d17a34','#537f65','#537f65'],width=.65)
ax[0].scatter(positions,p95,marker='_',s=180,color='black',label='95th percentile',zorder=3)
for x,y in zip(positions,values): ax[0].text(x,max(y,p95[x])+45,f'{y:.1f}',ha='center',fontsize=10)
ax[0].set_xticks(positions,['B11\nFPGA host','K44\nFPGA host','CPU after\nB11','CPU after\nK44'])
ax[0].set_ylabel('Time per input (microseconds)')
ax[0].set_ylim(0,1400);ax[0].set_title('Measured latency: median of 3,000 calls')
ax[0].legend(frameon=False,loc='upper right');ax[0].grid(axis='y',alpha=.2);ax[0].set_axisbelow(True)
parts=[('input_copy_flush_ns','Input copy / flush','#7894bd'),
       ('control_and_execution_ns','Control + execution','#d69b5a'),
       ('output_invalidate_copy_ns','Output invalidate / copy','#81a48c')]
bottom=np.zeros(2)
for key,label,color in parts:
    v=np.array([c['profile']['median_ns'][key]/1000 for c in (b,k)])
    ax[1].bar([0,1],v,bottom=bottom,label=label,color=color,width=.6)
    for i,y in enumerate(v): ax[1].text(i,bottom[i]+y/2,f'{y:.1f}',ha='center',va='center')
    bottom+=v
ax[1].set_xticks([0,1],['B11','K44']);ax[1].set_ylim(0,1550)
ax[1].set_ylabel('Sum of per-phase medians (microseconds)')
ax[1].set_title('Diagnostic phase timings: 100 extra calls')
ax[1].legend(frameon=False,fontsize=9,loc='upper right');ax[1].grid(axis='y',alpha=.2);ax[1].set_axisbelow(True)
fig.suptitle('PYNQ-Z2 board2: PL 100 MHz, CPU 650 MHz, PYNQ 2.5\nFPGA includes Python/control/cache work; CPU measures compiled C++ computation',fontsize=12)
fig.savefig(ROOT/'figures/board_latency.png',dpi=180)
print('Wrote figures/board_latency.png')
