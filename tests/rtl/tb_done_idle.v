`timescale 1ns/1ps
// Actual vendor reset netlist + actual HLS control RTL; no PS/DDR model.
module tb_done_idle;
  reg clk = 0;
  always #5 clk = ~clk;
  reg ext_n = 0;
  wire reset_n;
  ffn_system_reset_0 reset_controller(
    .slowest_sync_clk(clk), .ext_reset_in(ext_n), .aux_reset_in(1'b1),
    .mb_debug_sys_rst(1'b0), .dcm_locked(1'b1), .peripheral_aresetn(reset_n));
  reg [6:0] awaddr = 0, araddr = 0;
  reg [31:0] wdata = 0;
  reg [3:0] wstrb = 0;
  reg awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0;
  wire awready, wready, bvalid, arready, rvalid;
  wire [1:0] bresp, rresp;
  wire [31:0] rdata;
  wire [63:0] parameters, input_r, output_r;
  wire [31:0] operation;
  wire ap_start;
  reg ap_done = 0, ap_ready = 0, ap_idle = 1;
  reg [31:0] value;
  ffn_control_s_axi dut(
    .ACLK(clk), .ARESET(~reset_n), .ACLK_EN(1'b1),
    .AWADDR(awaddr), .AWVALID(awvalid), .AWREADY(awready),
    .WDATA(wdata), .WSTRB(wstrb), .WVALID(wvalid), .WREADY(wready),
    .BRESP(bresp), .BVALID(bvalid), .BREADY(bready),
    .ARADDR(araddr), .ARVALID(arvalid), .ARREADY(arready),
    .RDATA(rdata), .RRESP(rresp), .RVALID(rvalid), .RREADY(rready),
    .parameters(parameters), .input_r(input_r), .output_r(output_r), .operation(operation), .ap_return(32'd7),
    .ap_start(ap_start), .ap_done(ap_done), .ap_ready(ap_ready), .ap_idle(ap_idle));

  task axi_write;
    input [6:0] address;
    input [31:0] data;
    input [3:0] strobes;
    begin
      @(negedge clk); awaddr = address; awvalid = 1;
      @(posedge clk); while (!awready) @(posedge clk);
      @(negedge clk); awvalid = 0;
      // Separate address and data phases, then hold the response under backpressure.
      repeat(2) @(negedge clk);
      wdata = data; wstrb = strobes; wvalid = 1;
      @(posedge clk); while (!wready) @(posedge clk);
      @(negedge clk); wvalid = 0;
      wait(bvalid);
      repeat(3) begin
        @(negedge clk);
        if (bvalid !== 1'b1 || bresp !== 2'b00) $fatal(1, "Write response lost under backpressure");
      end
      bready = 1;
      @(posedge clk);
      @(negedge clk); bready = 0;
    end
  endtask

  task axi_read;
    input [6:0] address;
    output [31:0] data;
    begin
      @(negedge clk); araddr = address; arvalid = 1;
      @(posedge clk); while (!arready) @(posedge clk);
      @(negedge clk); arvalid = 0;
      wait(rvalid); data = rdata;
      repeat(3) begin
        @(negedge clk);
        if (rvalid !== 1'b1 || rresp !== 2'b00 || rdata !== data)
          $fatal(1, "Read response unstable under backpressure");
      end
      rready = 1;
      @(posedge clk);
      @(negedge clk); rready = 0;
    end
  endtask

  task run_handshake;
    input [31:0] count;
    begin
      axi_write(7'h3c, count, 4'hf);
      axi_write(7'h00, 32'h1, 4'hf);
      if (ap_start !== 1'b1 || operation !== count) $fatal(1, "Kernel start/count mismatch");
      ap_idle = 0;
      repeat(5) @(negedge clk);
      ap_done = 1; ap_ready = 1; ap_idle = 1;
      @(negedge clk); ap_done = 0; ap_ready = 0;
      repeat(3) @(negedge clk);
      if (ap_start !== 1'b0) $fatal(1, "Start did not clear on ready");
      axi_read(7'h00, value);
      if ((value & 32'h7) !== 32'h6) $fatal(1, "First status read must return done and idle");
      axi_read(7'h00, value);
      if ((value & 32'h7) !== 32'h4) $fatal(1, "Done did not clear on read");
    end
  endtask

  initial begin
    repeat(40) @(negedge clk); ext_n = 1;
    repeat(300) @(negedge clk);
    if (reset_n !== 1'b1) $fatal(1, "Reset did not release");
    axi_read(7'h00, value);
    if ((value & 32'h7) !== 32'h4) $fatal(1, "Initial control status incorrect");
    axi_write(7'h18, 32'h01234560, 4'hf);
    axi_write(7'h1c, 32'h89abcdef, 4'hf);
    axi_write(7'h24, 32'h02345678, 4'hf);
    axi_write(7'h28, 32'h76543210, 4'hf);
    if (parameters !== 64'h89abcdef01234560 || input_r !== 64'h7654321002345678)
      $fatal(1, "64-bit pointer word mapping incorrect");
    axi_read(7'h18, value); if (value !== 32'h01234560) $fatal(1, "parameters low readback");
    axi_read(7'h1c, value); if (value !== 32'h89abcdef) $fatal(1, "parameters high readback");
    axi_read(7'h24, value); if (value !== 32'h02345678) $fatal(1, "input_r low readback");
    axi_read(7'h28, value); if (value !== 32'h76543210) $fatal(1, "input_r high readback");
    axi_write(7'h18, 32'hffffffff, 4'b0010);
    if (parameters[31:0] !== 32'h0123ff60) $fatal(1, "Byte write enables incorrect");
    // Restore real 32-bit DDR addresses before exercising the host's launch sequence.
    axi_write(7'h18, 32'h01000000, 4'hf); axi_write(7'h1c, 0, 4'hf);
    axi_write(7'h24, 32'h02000000, 4'hf); axi_write(7'h28, 0, 4'hf);
    axi_write(7'h30, 32'h03000000, 4'hf); axi_write(7'h34, 0, 4'hf);
    if (output_r !== 64'h03000000) $fatal(1, "output pointer mapping");
    axi_read(7'h30, value); if (value !== 32'h03000000) $fatal(1, "output low readback");
    axi_read(7'h34, value); if (value !== 0) $fatal(1, "output high readback");
    run_handshake(1);
    run_handshake(0);
    // ap_done and ap_idle are separate registered status signals.
    // Hold idle low after completion to expose a host that incorrectly requires
    // both in the same read, including clear-on-read loss of the done flag.
    ap_idle=0;
    axi_write(7'h00, 1, 4'hf);
    ap_done=1; ap_ready=1;
    @(negedge clk); ap_done=0; ap_ready=0;
    repeat(3) @(negedge clk);
    axi_read(7'h00,value);
    if ((value & 6)!==2) $fatal(1,"Expected done before idle");
    axi_read(7'h00,value);
    if ((value & 6)!==0) $fatal(1,"Done must clear while idle is still low");
    ap_idle=1;
    repeat(3) @(negedge clk);
    axi_read(7'h00,value);
    if ((value & 6)!==4) $fatal(1,"Expected later idle without done");
    $display("DONE_IDLE_TEST_PASS: done precedes idle, done clears on read, later idle has no done bit");
    ext_n = 0;
    repeat(40) @(negedge clk);
    if (parameters !== 0 || input_r !== 0 || operation !== 0 || output_r !== 0 || ap_start !== 0)
      $fatal(1, "Reset did not clear control registers");
    ext_n = 1;
    repeat(300) @(negedge clk);
    axi_read(7'h00, value);
    if ((value & 32'h7) !== 32'h4) $fatal(1, "Control failed after reset recovery");
    $display("REGISTER_TEST_PASS: 64-bit pointers, byte strobes, operation, repeated start/done, clear-on-read, AXI backpressure, reset recovery");
    $finish;
  end
  initial begin
    #50000;
    $fatal(1, "Register verification timed out");
  end
endmodule
