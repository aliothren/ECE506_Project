"""Check the FFN overlay reset wiring before packaging or touching hardware."""

def validate_reset_hwh(root):
    modules = {m.get('INSTANCE'): m for m in root.iter('MODULE')}

    def params(name):
        return {p.get('NAME'): p.get('VALUE') for p in modules[name].iter('PARAMETER')}

    def net(module, port):
        p = next((p for p in modules[module].findall('./PORTS/PORT') if p.get('NAME') == port))
        if not p.get('SIGNAME'):
            raise ValueError('Unconnected {}.{}'.format(module, port))
        return p.get('SIGNAME')

    def constant_on(signal):
        drivers = []
        for (name, module) in modules.items():
            if module.get('MODTYPE') == 'xlconstant' and net(name, 'dout') == signal:
                drivers.append(int(params(name)['CONST_VAL'], 0))
        if not len(drivers) == 1:
            raise ValueError('Expected a single constant driver on ' + signal)
        return drivers[0]
    rp = params('reset')
    aux_active = int(rp['C_AUX_RESET_HIGH'])
    aux_value = constant_on(net('reset', 'aux_reset_in'))
    if not aux_value != aux_active:
        raise ValueError('Auxiliary reset is permanently asserted: active={}, tied={}'.format(aux_active, aux_value))
    if not rp['C_EXT_RESET_HIGH'] == '0':
        raise ValueError('PS reset must be active-low')
    if not net('reset', 'ext_reset_in') == net('ps', 'FCLK_RESET0_N'):
        raise ValueError("Invalid overlay metadata: net('reset', 'ext_reset_in') == net('ps', 'FCLK_RESET0_N')")
    if not constant_on(net('reset', 'dcm_locked')) == 1:
        raise ValueError("Invalid overlay metadata: constant_on(net('reset', 'dcm_locked')) == 1")
    if not constant_on(net('reset', 'mb_debug_sys_rst')) == 0:
        raise ValueError("Invalid overlay metadata: constant_on(net('reset', 'mb_debug_sys_rst')) == 0")
    reset_net = net('reset', 'peripheral_aresetn')
    for (name, port) in (('ffn_0', 'ap_rst_n'), ('control_smc', 'aresetn'), ('memory_smc', 'aresetn')):
        if not net(name, port) == reset_net:
            raise ValueError('Incorrect reset wiring: ' + name)
    clock_net = net('ps', 'FCLK_CLK0')
    for (name, port) in (('reset', 'slowest_sync_clk'), ('ffn_0', 'ap_clk'), ('control_smc', 'aclk'), ('memory_smc', 'aclk'), ('ps', 'M_AXI_GP0_ACLK'), ('ps', 'S_AXI_HP0_ACLK')):
        if not net(name, port) == clock_net:
            raise ValueError('Incorrect clock wiring: ' + name)
    return {'aux_reset_active': aux_active, 'aux_reset_tied': aux_value, 'reset_net': reset_net, 'clock_net': clock_net}
