# PYNQ-Z2 PYNQ overlay. Run with Vivado 2025.1 in batch mode.
# Linux/PYNQ already initializes the board's PS and DDR; this is not a boot image.
set ROOT [file normalize [file join [file dirname [info script]] ..]]
set RUN [file normalize $::env(FFN_BUILD_RUN)]
set BUILD $RUN/vivado
set REPORTS $RUN/implementation
set OVERLAY $RUN/overlay
set IP_REPO $RUN/project/solution/impl/ip
file mkdir $REPORTS $OVERLAY
if {![file exists $IP_REPO/component.xml]} {
    error "Run vitis-run --mode hls --tcl the selected HLS configuration with --export first"
}
set_param general.maxThreads 4
set_param board.repoPaths [list $ROOT/vivado/board_files]
create_project ffn_pynq_z2 $BUILD -part xc7z020clg400-1 -force
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
set_property target_language Verilog [current_project]
set_property ip_repo_paths [list $IP_REPO] [current_project]
update_ip_catalog
create_bd_design ffn_system

create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} [get_bd_cells ps]
set_property -dict [list \
    CONFIG.PCW_USE_M_AXI_GP0 {1} \
    CONFIG.PCW_USE_S_AXI_HP0 {1} \
    CONFIG.PCW_S_AXI_HP0_DATA_WIDTH {64} \
    CONFIG.PCW_EN_CLK0_PORT {1} \
    CONFIG.PCW_EN_RST0_PORT {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} \
    CONFIG.PCW_FCLK0_PERIPHERAL_CLKSRC {IO PLL}] [get_bd_cells ps]

set ffn_defs [get_ipdefs -all -filter {NAME == ffn}]
if {[llength $ffn_defs] != 1} { error "Expected one exported FFN IP: $ffn_defs" }
create_bd_cell -type ip -vlnv [get_property VLNV $ffn_defs] ffn_0
foreach cell {control_smc memory_smc} {
    create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 $cell
    set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] [get_bd_cells $cell]
}
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset
set_property CONFIG.C_AUX_RESET_HIGH {0} [get_bd_cells reset]
# Auxiliary reset is explicitly active-low and tied HIGH when unused.
# External polarity is inferred from PS FCLK_RESET0_N and checked after validation.
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const_one
set_property CONFIG.CONST_VAL {1} [get_bd_cells const_one]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const_zero
set_property CONFIG.CONST_VAL {0} [get_bd_cells const_zero]

connect_bd_intf_net [get_bd_intf_pins ps/M_AXI_GP0] [get_bd_intf_pins control_smc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins control_smc/M00_AXI] [get_bd_intf_pins ffn_0/s_axi_control]
connect_bd_intf_net [get_bd_intf_pins ffn_0/m_axi_gmem] [get_bd_intf_pins memory_smc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins memory_smc/M00_AXI] [get_bd_intf_pins ps/S_AXI_HP0]
connect_bd_net [get_bd_pins ps/FCLK_CLK0] \
    [get_bd_pins ps/M_AXI_GP0_ACLK] [get_bd_pins ps/S_AXI_HP0_ACLK] \
    [get_bd_pins ffn_0/ap_clk] [get_bd_pins control_smc/aclk] \
    [get_bd_pins memory_smc/aclk] [get_bd_pins reset/slowest_sync_clk]
connect_bd_net [get_bd_pins ps/FCLK_RESET0_N] [get_bd_pins reset/ext_reset_in]
connect_bd_net [get_bd_pins const_one/dout] [get_bd_pins reset/dcm_locked] [get_bd_pins reset/aux_reset_in]
connect_bd_net [get_bd_pins const_zero/dout] [get_bd_pins reset/mb_debug_sys_rst]
connect_bd_net [get_bd_pins reset/peripheral_aresetn] [get_bd_pins ffn_0/ap_rst_n] \
    [get_bd_pins control_smc/aresetn] [get_bd_pins memory_smc/aresetn]

# GP0 control aperture at 0x40000000; PYNQ-Z2 has 512 MiB DDR.
assign_bd_address -offset 0x40000000 -range 64K \
    -target_address_space [get_bd_addr_spaces ps/Data] [get_bd_addr_segs ffn_0/s_axi_control/Reg]
assign_bd_address -offset 0x00000000 -range 512M \
    -target_address_space [get_bd_addr_spaces ffn_0/Data_m_axi_gmem] \
    [get_bd_addr_segs ps/S_AXI_HP0/HP0_DDR_LOWOCM]
validate_bd_design
if {[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells reset]] != 0 || [get_property CONFIG.C_AUX_RESET_HIGH [get_bd_cells reset]] != 0} {
    error "Expected active-low external reset from ps/FCLK_RESET0_N"
}
save_bd_design
write_bd_tcl -force $REPORTS/ffn_system.tcl
set fp [open $REPORTS/address_clock.txt w]
puts $fp "Part: [get_property PART [current_project]]"
puts $fp "PL requested MHz: [get_property CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ [get_bd_cells ps]]"
puts $fp "PL actual MHz: [get_property CONFIG.PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ [get_bd_cells ps]]"
puts $fp "PL clock source: [get_property CONFIG.PCW_FCLK0_PERIPHERAL_CLKSRC [get_bd_cells ps]]"
foreach seg [get_bd_addr_segs -hierarchical] {
    puts $fp "$seg offset=[get_property OFFSET $seg] range=[get_property RANGE $seg]"
}
close $fp

set bd [get_files $BUILD/ffn_pynq_z2.srcs/sources_1/bd/ffn_system/ffn_system.bd]
generate_target all $bd
set wrapper [make_wrapper -files $bd -top]
add_files -norecurse $wrapper
set_property top ffn_system_wrapper [current_fileset]
update_compile_order -fileset sources_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {
    error "Synthesis failed: [get_property STATUS [get_runs synth_1]]"
}
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {![string match {*Complete*} [get_property STATUS [get_runs impl_1]]]} {
    error "Implementation failed: [get_property STATUS [get_runs impl_1]]"
}
open_run impl_1
report_timing_summary -delay_type min_max -report_unconstrained -file $REPORTS/timing_summary.rpt
report_utilization -file $REPORTS/utilization.rpt
report_utilization -hierarchical -file $REPORTS/utilization_hierarchical.rpt
report_drc -file $REPORTS/drc.rpt
report_clock_networks -file $REPORTS/clock_networks.rpt
set fp [open $REPORTS/implementation_metrics.csv w]
puts $fp "part,setup_wns_ns,hold_whs_ns"
puts $fp "xc7z020clg400-1,[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]],[get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]"
close $fp
if {[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]] < 0 || \
    [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]] < 0} {
    error "Timing failed; reports saved, overlay not released."
}
file copy -force $BUILD/ffn_pynq_z2.runs/impl_1/ffn_system_wrapper.bit $OVERLAY/ffn.bit
file copy -force $BUILD/ffn_pynq_z2.gen/sources_1/bd/ffn_system/hw_handoff/ffn_system.hwh $OVERLAY/ffn.hwh
write_hw_platform -fixed -include_bit -force -file $OVERLAY/ffn.xsa
puts "PYNQ_Z2_BUILD_PASS: overlay and implementation reports ready."
close_project
exit
