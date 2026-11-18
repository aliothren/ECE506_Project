"""Validate FFN overlay metadata without loading the FPGA."""
from pathlib import Path
import xml.etree.ElementTree as ET
from reset_checks import validate_reset_hwh

def inspect_hwh(path):
    root = ET.parse(path).getroot()
    reset = validate_reset_hwh(root)
    modules = {m.get('INSTANCE'): m for m in root.iter('MODULE')}

    def params(name):
        return {p.get('NAME'): p.get('VALUE') for p in modules[name].iter('PARAMETER')}

    def bus(name, port):
        value = next((p.get('BUSNAME') for p in modules[name].findall('./BUSINTERFACES/BUSINTERFACE') if p.get('NAME') == port))
        if not value or value == '__NOC__':
            raise ValueError('Disconnected ' + name + '.' + port)
        return value
    for (a, b, c, d) in [('ps', 'M_AXI_GP0', 'control_smc', 'S00_AXI'), ('control_smc', 'M00_AXI', 'ffn_0', 's_axi_control'), ('ffn_0', 'm_axi_gmem', 'memory_smc', 'S00_AXI'), ('memory_smc', 'M00_AXI', 'ps', 'S_AXI_HP0')]:
        if bus(a, b) != bus(c, d):
            raise ValueError('Incorrect AXI wiring')
    (hw, ps) = (params('ffn_0'), params('ps'))
    if not hw['C_M_AXI_GMEM_DATA_WIDTH'] == ps['PCW_S_AXI_HP0_DATA_WIDTH'] == '64':
        raise ValueError("Invalid overlay metadata: hw['C_M_AXI_GMEM_DATA_WIDTH'] == ps['PCW_S_AXI_HP0_DATA_WIDTH'] == '64'")
    if not ps['PCW_USE_M_AXI_GP0'] == ps['PCW_USE_S_AXI_HP0'] == '1':
        raise ValueError("Invalid overlay metadata: ps['PCW_USE_M_AXI_GP0'] == ps['PCW_USE_S_AXI_HP0'] == '1'")
    if not float(ps['PCW_FPGA0_PERIPHERAL_FREQMHZ']) == 100.0:
        raise ValueError("Invalid overlay metadata: float(ps['PCW_FPGA0_PERIPHERAL_FREQMHZ']) == 100.0")
    bits = int(hw['C_M_AXI_GMEM_ADDR_WIDTH'])
    if not bits in (32, 64):
        raise ValueError('Invalid overlay metadata: bits in (32, 64)')
    for (owner, target, low, high) in [('ps', 'ffn_0', 1073741824, 1073807359), ('ffn_0', 'ps', 0, 536870911)]:
        ranges = [r for r in modules[owner].iter('MEMRANGE') if r.get('INSTANCE') == target]
        if not len(ranges) == 1:
            raise ValueError('Invalid overlay metadata: len(ranges) == 1')
        if not int(ranges[0].get('BASEVALUE'), 16) == low:
            raise ValueError("Invalid overlay metadata: int(ranges[0].get('BASEVALUE'), 16) == low")
        if not int(ranges[0].get('HIGHVALUE'), 16) == high:
            raise ValueError("Invalid overlay metadata: int(ranges[0].get('HIGHVALUE'), 16) == high")
    regs = {r.get('NAME').lower(): int(next((p.get('VALUE') for p in r.findall('PROPERTY') if p.get('NAME') == 'ADDRESS_OFFSET')), 0) for r in modules['ffn_0'].iter('REGISTER')}
    if not regs['ctrl'] == 0:
        raise ValueError("Invalid overlay metadata: regs['ctrl'] == 0")
    offsets = {}
    for name in ('parameters', 'input', 'output'):
        suffix = '' if bits == 32 else '_1'
        key = next((k for k in (name, name + '_r') if k + suffix in regs))
        offsets[name] = [regs[key]] if bits == 32 else [regs[key + '_1'], regs[key + '_2']]
    offsets['operation'] = regs['operation']
    offsets['return'] = regs['ap_return']
    expected = {'parameters': [0x18, 0x1c], 'input': [0x24, 0x28],
                'output': [0x30, 0x34], 'operation': 0x3c, 'return': 0x10}
    if bits != 64 or offsets != expected:
        raise ValueError('Unexpected FFN register ABI')
    return {'reset': reset, 'address_bits': bits, 'data_bits': 64, 'offsets': offsets, 'ddr_bytes': 1 << 29, 'control_base': 1073741824}
