`timescale 1ns/1ps
module tb_reset;
  reg clk = 0;
  always #5 clk = ~clk;
  reg ext_n = 0;
  reg aux_fixed_n = 1;
  wire old_periph_n, fixed_periph_n, fixed_bus_n;
  ffn_system_reset_0 old_wiring(
    .slowest_sync_clk(clk), .ext_reset_in(ext_n), .aux_reset_in(1'b0),
    .mb_debug_sys_rst(1'b0), .dcm_locked(1'b1),
    .peripheral_aresetn(old_periph_n));
  ffn_system_reset_0 fixed_wiring(
    .slowest_sync_clk(clk), .ext_reset_in(ext_n), .aux_reset_in(aux_fixed_n),
    .mb_debug_sys_rst(1'b0), .dcm_locked(1'b1),
    .peripheral_aresetn(fixed_periph_n), .interconnect_aresetn(fixed_bus_n));
  reg read_valid = 0;
  wire old_arready, old_rvalid, fixed_arready, fixed_rvalid;
  wire [31:0] fixed_rdata;
  reg fixed_read_seen = 0;
  always @(posedge clk) begin
    if (fixed_rvalid) begin
      if (fixed_rdata[2] !== 1'b1) $fatal(1, "Incorrect AP_CTRL idle response");
      fixed_read_seen <= 1;
    end
  end
  ffn_control_s_axi old_ctrl(
    .ACLK(clk), .ARESET(~old_periph_n), .ACLK_EN(1'b1),
    .AWADDR(7'd0), .AWVALID(1'b0), .WDATA(32'd0), .WSTRB(4'd0),
    .WVALID(1'b0), .BREADY(1'b1), .ARADDR(7'd0), .ARVALID(read_valid),
    .ARREADY(old_arready), .RVALID(old_rvalid), .RREADY(1'b1),
    .ap_done(1'b0), .ap_ready(1'b0), .ap_idle(1'b1));
  ffn_control_s_axi fixed_ctrl(
    .ACLK(clk), .ARESET(~fixed_periph_n), .ACLK_EN(1'b1),
    .AWADDR(7'd0), .AWVALID(1'b0), .WDATA(32'd0), .WSTRB(4'd0),
    .WVALID(1'b0), .BREADY(1'b1), .ARADDR(7'd0), .ARVALID(read_valid),
    .ARREADY(fixed_arready), .RVALID(fixed_rvalid), .RDATA(fixed_rdata), .RREADY(1'b1),
    .ap_done(1'b0), .ap_ready(1'b0), .ap_idle(1'b1));
  initial begin
    repeat(40) @(negedge clk);
    ext_n = 1;
    repeat(300) @(negedge clk);
    if (old_periph_n !== 1'b0) $fatal(1, "Old wiring did not reproduce stuck reset");
    if (fixed_periph_n !== 1'b1 || fixed_bus_n !== 1'b1)
      $fatal(1, "Corrected wiring failed to release reset");
    $display("PASS: old auxiliary tie-low holds reset; corrected tie-high releases peripheral and interconnect reset");
    read_valid = 1;
    repeat(20) @(negedge clk);
    read_valid = 0;
    if (old_arready !== 1'b0 || old_rvalid !== 1'b0)
      $fatal(1, "Old held-reset AXI interface unexpectedly responded");
    if (!fixed_read_seen) $fatal(1, "Corrected AXI read never completed");
    $display("AXI_RESET_TEST_PASS: old AP_CTRL read blocked; corrected AP_CTRL read completed with idle bit set");
    ext_n = 0;
    repeat(40) @(negedge clk);
    if (fixed_periph_n !== 1'b0) $fatal(1, "External reset failed to assert");
    ext_n = 1;
    repeat(300) @(negedge clk);
    if (fixed_periph_n !== 1'b1) $fatal(1, "External reset failed to release");
    aux_fixed_n = 0;
    repeat(40) @(negedge clk);
    if (fixed_periph_n !== 1'b0) $fatal(1, "Auxiliary reset failed to assert");
    aux_fixed_n = 1;
    repeat(300) @(negedge clk);
    if (fixed_periph_n !== 1'b1) $fatal(1, "Auxiliary reset failed to release");
    $display("RESET_TEST_PASS: external and auxiliary reset assertion/recovery verified using vendor simulation netlist");
    $finish;
  end
  initial begin
    #20000;
    $fatal(1, "Reset verification timed out");
  end
endmodule
