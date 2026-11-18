#!/usr/bin/env python3
"""Plot synthesized compute latency and resources; no fabricated board results."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def save(fig,name):
    out=ROOT/'figures'; out.mkdir(exist_ok=True)
    fig.savefig(out/(name+'.png'),dpi=180,bbox_inches='tight')
    plt.close(fig)


def main():
    rows={r['config_id']:r for r in csv.DictReader((ROOT/'results/hls_results.csv').open())
          if r['synth_status']=='pass' and r['csim_status']=='pass'}
    banked=[r for r in rows.values() if r['weight_layout']=='cyclic_banked']
    fig,ax=plt.subplots(figsize=(5.8,4.3))
    a=np.full((3,3),np.nan)
    vals=[1,2,4]
    for r in banked: a[vals.index(int(r['P'])),vals.index(int(r['Q']))]=int(r['compute_cycles'])
    im=ax.imshow(a,cmap='viridis_r')
    for i in range(3):
        for j in range(3):
            if not np.isnan(a[i,j]):
                rgb=im.cmap(im.norm(a[i,j]))[:3]
                luminance=sum(c*w for c,w in zip(rgb,(.2126,.7152,.0722)))
                ax.text(j,i,f'{int(a[i,j]):,}',ha='center',va='center',
                        color='white' if luminance<.45 else 'black')
    ax.set(xticks=range(3),xticklabels=vals,yticks=range(3),yticklabels=vals,
           xlabel='Q: input lanes',ylabel='P: output lanes',title='Complete FFN compute latency (HLS cycles)')
    fig.colorbar(im,ax=ax,label='Cycles')
    save(fig,'banked_latency')
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for ax,resource in zip(axes,['DSP','BRAM_18K']):
        for r in banked:
            x=int(r[resource]); y=int(r['compute_cycles'])
            ax.scatter(x,y,s=35)
            ax.annotate(r['config_id'],(x,y),xytext=(4,4),textcoords='offset points',fontsize=8)
        ax.set(xlabel=resource,ylabel='Complete compute cycles',yscale='log')
        ax.grid(alpha=.25)
    fig.suptitle('Banked designs: HLS latency / resource estimates')
    fig.tight_layout()
    save(fig,'latency_resources')
    if all(k in rows for k in ['U44','B44','K44']):
        labels=['U44','B44','K44']
        fig,axes=plt.subplots(1,3,figsize=(10,3.8))
        for ax,key,title in zip(axes,['compute_cycles','BRAM_18K','LUT'],['Compute cycles','BRAM_18K','LUT']):
            values=[int(rows[k][key]) for k in labels]
            bars=ax.bar(labels,values,color=['#b85c4a','#4384b2','#52946b'])
            ax.bar_label(bars,padding=3,fontsize=9)
            ax.set_title(title); ax.set_ylim(0,max(values)*1.2)
        fig.suptitle('P=Q=4: unpartitioned / banked / packed (HLS)')
        fig.tight_layout()
        save(fig,'memory_comparison')
    print('Figures generated from',len(rows),'synthesized configurations')


if __name__=='__main__': main()
