`timescale 1ns/1ps
module tb_reset;
  reg clk = 0;
  always #5 clk = ~clk;
  reg ext_n = 0;
  reg aux_released_n = 1;
  wire asserted_periph_n, released_periph_n, released_bus_n;
  ffn_system_reset_0 asserted_wiring(
    .slowest_sync_clk(clk), .ext_reset_in(ext_n), .aux_reset_in(1'b0),
    .mb_debug_sys_rst(1'b0), .dcm_locked(1'b1),
    .peripheral_aresetn(asserted_periph_n));
  ffn_system_reset_0 released_wiring(
    .slowest_sync_clk(clk), .ext_reset_in(ext_n), .aux_reset_in(aux_released_n),
    .mb_debug_sys_rst(1'b0), .dcm_locked(1'b1),
    .peripheral_aresetn(released_periph_n), .interconnect_aresetn(released_bus_n));
  reg read_valid = 0;
  wire asserted_arready, asserted_rvalid, released_arready, released_rvalid;
  wire [31:0] released_rdata;
  reg released_read_seen = 0;
  always @(posedge clk) begin
    if (released_rvalid) begin
      if (released_rdata[2] !== 1'b1) $fatal(1, "Incorrect AP_CTRL idle response");
      released_read_seen <= 1;
    end
  end
  ffn_control_s_axi asserted_ctrl(
    .ACLK(clk), .ARESET(~asserted_periph_n), .ACLK_EN(1'b1),
    .AWADDR(7'd0), .AWVALID(1'b0), .WDATA(32'd0), .WSTRB(4'd0),
    .WVALID(1'b0), .BREADY(1'b1), .ARADDR(7'd0), .ARVALID(read_valid),
    .ARREADY(asserted_arready), .RVALID(asserted_rvalid), .RREADY(1'b1),
    .ap_done(1'b0), .ap_ready(1'b0), .ap_idle(1'b1));
  ffn_control_s_axi released_ctrl(
    .ACLK(clk), .ARESET(~released_periph_n), .ACLK_EN(1'b1),
    .AWADDR(7'd0), .AWVALID(1'b0), .WDATA(32'd0), .WSTRB(4'd0),
    .WVALID(1'b0), .BREADY(1'b1), .ARADDR(7'd0), .ARVALID(read_valid),
    .ARREADY(released_arready), .RVALID(released_rvalid), .RDATA(released_rdata), .RREADY(1'b1),
    .ap_done(1'b0), .ap_ready(1'b0), .ap_idle(1'b1));
  initial begin
    repeat(40) @(negedge clk);
    ext_n = 1;
    repeat(300) @(negedge clk);
    if (asserted_periph_n !== 1'b0) $fatal(1, "Asserted auxiliary input did not hold reset");
    if (released_periph_n !== 1'b1 || released_bus_n !== 1'b1)
      $fatal(1, "Inactive auxiliary input failed to release reset");
    $display("PASS: active-low auxiliary input holds reset; inactive-high input releases peripheral and interconnect reset");
    read_valid = 1;
    repeat(20) @(negedge clk);
    read_valid = 0;
    if (asserted_arready !== 1'b0 || asserted_rvalid !== 1'b0)
      $fatal(1, "AXI interface responded while held in reset");
    if (!released_read_seen) $fatal(1, "Released AXI read never completed");
    $display("AXI_RESET_TEST_PASS: AP_CTRL read blocked during reset; completed after release with idle bit set");
    ext_n = 0;
    repeat(40) @(negedge clk);
    if (released_periph_n !== 1'b0) $fatal(1, "External reset failed to assert");
    ext_n = 1;
    repeat(300) @(negedge clk);
    if (released_periph_n !== 1'b1) $fatal(1, "External reset failed to release");
    aux_released_n = 0;
    repeat(40) @(negedge clk);
    if (released_periph_n !== 1'b0) $fatal(1, "Auxiliary reset failed to assert");
    aux_released_n = 1;
    repeat(300) @(negedge clk);
    if (released_periph_n !== 1'b1) $fatal(1, "Auxiliary reset failed to release");
    $display("RESET_TEST_PASS: external and auxiliary reset assertion/recovery verified using vendor simulation netlist");
    $finish;
  end
  initial begin
    #20000;
    $fatal(1, "Reset verification timed out");
  end
endmodule
