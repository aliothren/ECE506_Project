#!/usr/bin/env python3
"""Check actual generated HWH and regression-test rejection of broken wiring."""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'board'))
from interface import inspect_hwh


def main():
    p=argparse.ArgumentParser(); p.add_argument('hwh',type=Path); args=p.parse_args()
    actual=inspect_hwh(args.hwh)
    root=ET.parse(args.hwh).getroot()
    mutations=[('aux_asserted','const_one','parameter','CONST_VAL','0'),
               ('ip_reset_disconnected','ffn_0','port','ap_rst_n','wrong_reset'),
               ('ip_clock_disconnected','ffn_0','port','ap_clk','wrong_clock'),
               ('axi_disconnected','ffn_0','bus','m_axi_gmem','wrong_axi'),
               ('aux_polarity','reset','parameter','C_AUX_RESET_HIGH','1'),
               ('external_polarity','reset','parameter','C_EXT_RESET_HIGH','1'),
               ('locked_low','reset','port','dcm_locked','const_zero_dout'),
               ('interconnect_reset','control_smc','port','aresetn','wrong_reset'),
               ('hp_clock','ps','port','S_AXI_HP0_ACLK','wrong_clock'),
               ('data_width','ffn_0','parameter','C_M_AXI_GMEM_DATA_WIDTH','32'),
               ('wrong_clock','ps','parameter','PCW_FPGA0_PERIPHERAL_FREQMHZ','125'),
               ('disabled_hp','ps','parameter','PCW_USE_S_AXI_HP0','0'),
               ('pointer_offset','ffn_0','register','parameters_1','0x20'),
               ('control_base','ps','range','ffn_0','0x50000000')]
    passed=[]
    with tempfile.TemporaryDirectory(prefix='ffn-hwh-check-') as temp:
        for name,module,kind,key,value in mutations:
            bad=copy.deepcopy(root)
            m=next(m for m in bad.iter('MODULE') if m.get('INSTANCE')==module)
            if kind=='register':
                r=next(e for e in m.iter('REGISTER') if e.get('NAME').lower()==key)
                e=next(e for e in r.iter('PROPERTY') if e.get('NAME')=='ADDRESS_OFFSET')
                attr='VALUE'
            elif kind=='range':
                e=next(e for e in m.iter('MEMRANGE') if e.get('INSTANCE')==key)
                attr='BASEVALUE'
            else:
                tag,attr={'parameter':('PARAMETER','VALUE'),'port':('PORT','SIGNAME'),
                          'bus':('BUSINTERFACE','BUSNAME')}[kind]
                e=next(e for e in m.iter(tag) if e.get('NAME')==key)
            e.set(attr,value)
            path=Path(temp)/(name+'.hwh'); ET.ElementTree(bad).write(path)
            try: inspect_hwh(path)
            except (AssertionError,ValueError): passed.append(name)
            else: raise RuntimeError('Accepted invalid wiring: '+name)
    record={'status':'pass','hwh':str(args.hwh.resolve()),'interface':actual,'rejected_mutations':passed}
    cid=args.hwh.resolve().parents[2].name
    (ROOT/('results/interface_validation_'+cid+'.json')).write_text(json.dumps(record,indent=2)+'\n')
    print('INTERFACE_CHECK_PASS:',len(passed),'faults rejected')


if __name__=='__main__': main()
