# Invoked by scripts/run_experiments.py with a frozen source snapshot.
set SRC $::env(FFN_SOURCE)
set RUN $::env(FFN_RUN)
set FLAGS "-DFFN_P=$::env(FFN_P) -DFFN_Q=$::env(FFN_Q) -DFFN_LAYOUT=$::env(FFN_LAYOUT) -DFFN_PIPELINE=$::env(FFN_PIPELINE)"
open_project $RUN/project
set_top ffn
add_files $SRC/hls/ffn.cpp -cflags $FLAGS -csimflags "-O3"
add_files -tb $SRC/hls/ffn_test.cpp -cflags $FLAGS -csimflags "-O3"
open_solution solution -flow_target vivado
set_part xc7z020clg400-1
create_clock -period 10 -name default
config_compile -pipeline_loops 0
config_array_partition -throughput_driven off
csim_design -O -argv "$::env(FFN_DATA)"
csynth_design
if {$::env(FFN_COSIM) == "1"} {
    cosim_design -rtl verilog -trace_level all -argv "$::env(FFN_DATA) rtl"
}
if {$::env(FFN_EXPORT) == "1"} {
    export_design -format ip_catalog -rtl verilog
}
exit
