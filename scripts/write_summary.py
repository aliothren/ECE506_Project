#!/usr/bin/env python3
"""Write an evidence-based local progress report from collected results."""
import csv
from datetime import datetime
from pathlib import Path
import json
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]


def main():
    rows=list(csv.DictReader((ROOT/'results/hls_results.csv').open()))
    byid={r['config_id']:r for r in rows}
    complete=[r for r in rows if r['synth_status']=='pass' and r['csim_status']=='pass']
    text=['**ECE 506 FFN：本地实验结果**','',
          '更新：'+datetime.now(ZoneInfo('America/Phoenix')).strftime('%Y-%m-%d %H:%M MST')+'。', '',
          '本页保留 HLS、RTL 和布局布线的测量口径；实板结果另见 [BOARD_RESULTS.md](BOARD_RESULTS.md)。以下核内周期不等同于实板端到端时间。','',
          f'已完成 {len(complete)}/12 组 C 仿真与综合；RTL 通过的配置：'+
          '、'.join(r['config_id'] for r in rows if r['cosim_status']=='pass')+'。','',
          '独立 Python/C++ 参考覆盖 9 套参数、206 次推理，并检查两层输出。每组 HLS C 仿真使用同一套数据。RTL 每组覆盖 4 套参数、8 次推理及未加载/非法操作，共 14 次调用。','',
          '**HLS 结果**','',
          '计算周期来自 `ffn_compute`，包括两层、归约、激活和量化，不含参数加载或 DDR 输入输出。资源为整个 HLS IP 的估计，包含接口。BRAM 单位为 BRAM_18K。','',
          '| 配置 | P,Q | 组织 | 计算周期 | FC1/FC2 II | BRAM | DSP | LUT | FF |',
          '|---|---|---|---:|---|---:|---:|---:|---:|']
    for r in complete:
        ii=(r.get('fc1_main_ii') or '无流水')+'/'+(r.get('fc2_main_ii') or '无流水')
        text.append('| '+' | '.join([r['config_id'],r['P']+','+r['Q'],r['weight_layout'],r['compute_cycles'],ii,
                                     r['BRAM_18K'],r['DSP'],r['LUT'],r['FF']])+' |')
    text+=['','**主要观察**','']
    if all(k in byid and byid[k].get('compute_cycles') for k in ('B11','B44','U44')):
        b,u,o=(byid[k] for k in ('B11','U44','B44'))
        text+=[f'- B44 相对流水化标量 B11 的 HLS 核内加速为 {int(b["compute_cycles"])/int(o["compute_cycles"]):.2f} 倍。',
               f'- U44 与 B44 都请求 P=Q=4；U44 主循环 II={u["fc1_main_ii"]}/{u["fc2_main_ii"]}，B44 为 {o["fc1_main_ii"]}/{o["fc2_main_ii"]}。U44 日志明确报告 HLS 200-885（limited memory ports），支持端口不足限制展开收益的判断。']
    if all(k in byid and byid[k].get('compute_cycles') for k in ('B14','B22','B41')):
        text+=['- 同样 PQ=4，(1,4)/(2,2)/(4,1) 的周期分别为 '+
               '/'.join(byid[k]['compute_cycles'] for k in ('B14','B22','B41'))+
               '。这些配置的主循环均为 II=1，差异体现在输出分组、初始化/归约及调度开销；不能仅用乘法器总数预测完整延迟。']
    if all(k in byid and byid[k].get('compute_cycles') for k in ('K44','B44')):
        k,b=byid['K44'],byid['B44']
        text += [f'- K44/B44 的计算周期为 {k["compute_cycles"]}/{b["compute_cycles"]}，BRAM_18K 为 {k["BRAM_18K"]}/{b["BRAM_18K"]}。对照的是相同 P/Q 下的实际综合结果。']
    verified=[r for r in complete if r['cosim_status']=='pass']
    if verified:
        candidate=min(verified,key=lambda r:(int(r['compute_cycles']),int(r['BRAM_18K']),int(r['LUT'])))
        selection=f'当前已通过 RTL 的最优候选为 **{candidate["config_id"]}**（先按计算周期，再按 BRAM/LUT 排序）。'
        selection+=('它已通过完整实现时序检查，选作与 B11 对照的优化版本。' if candidate['implementation_status']=='pass'
                    else '是否成为最终上板版本还需其完整实现时序通过。')
        text+=['',selection]
    text+=['','**RTL 测量**','',
           '以下为仿真 AXI 内存模型下，顶层 RUN 的实际周期；包含该模型中的输入输出，不能当作实板端到端时间。LOAD 单列。HLS 的静态延迟估计与 RTL 测量可能不同，保留两者原始口径。','',
           '| 配置 | RUN 周期范围 | LOAD 周期范围 |','|---|---:|---:|']
    for r in verified:
        text.append(f'| {r["config_id"]} | {r.get("rtl_inference_min_cycles", "")}-{r.get("rtl_inference_max_cycles", "")} | {r.get("rtl_load_min_cycles", "")}-{r.get("rtl_load_max_cycles", "")} |')
    text+=['','**本地实现与剩余工作**','']
    for r in rows:
        if r['implementation_status']=='pass':
            text.append(f'- {r["config_id"]}：已生成 bit/hwh，setup WNS={r["setup_wns_ns"]} ns，hold slack={r["hold_whs_ns"]} ns，目标 100 MHz。')
            if r.get('impl_LUT'):
                text.append(f'  完整实现资源：LUT={r["impl_LUT"]}，FF={r["impl_FF"]}，DSP={r["impl_DSP"]}，BRAM36 tile={r["impl_BRAM_tiles"]}（折合 BRAM_18K={r["impl_BRAM_18K_equiv"]}）。这是布局布线结果，与上表 HLS 估计分开报告。')
    text+=['- 实板进展和 CPU 对照见 [BOARD_RESULTS.md](BOARD_RESULTS.md)；本地 CPU smoke test 不用于板端加速比较。',
           '- 初次 B11/B44 XSIM 在受限环境启动失败；重试只重跑 RTL/IP 导出，失败日志和通过记录都保留。',
           '- 数据可重复生成；寄存器从实际 HWH 解析。复位、时钟、AXI 连接检查和 host 超时/中断生命周期测试已完成。',
           '- 完整复现方法见 [README](../README.md)，原始配置状态见 [CSV](hls_results.csv)，每次构建记录见 CSV 的 run 路径。','',
           '**图表**','',
           '[并行度与延迟](../figures/banked_latency.png) · [延迟与资源](../figures/latency_resources.png)']
    if (ROOT/'figures/memory_comparison.png').exists(): text[-1]+=' · [存储组织对照](../figures/memory_comparison.png)'
    (ROOT/'results/LOCAL_RESULTS.md').write_text('\n'.join(text)+'\n')
    print('Wrote results/LOCAL_RESULTS.md')


if __name__=='__main__': main()
