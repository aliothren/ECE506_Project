# RTL verification and IP export of a synthesized design.
open_project $::env(FFN_RUN)/project
open_solution solution -flow_target vivado
cosim_design -rtl verilog -trace_level all -argv "$::env(FFN_DATA) rtl"
export_design -format ip_catalog -rtl verilog
exit
