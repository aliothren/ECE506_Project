`timescale 1ns/1ps
// Actual synthesized FFN and actual vendor reset controller; bounded/stalling DDR model.
// This is not a model of PS7, SmartConnect, Linux, or CPU caches.
module tb_lifecycle;
  reg clk=0; always #5 clk=~clk;
  reg ext_n=0;
  wire reset_n;
  ffn_system_reset_0 reset_controller(.slowest_sync_clk(clk), .ext_reset_in(ext_n),
    .aux_reset_in(1'b1), .mb_debug_sys_rst(1'b0), .dcm_locked(1'b1), .peripheral_aresetn(reset_n));
  reg [6:0] awaddr=0, araddr=0;
  reg [31:0] wdata=0;
  reg [3:0] wstrb=0;
  reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
  wire awready,wready,bvalid,arready,rvalid;
  wire [1:0] bresp,rresp;
  wire [31:0] rdata;
  wire mav,marv,mwv,mwr,mrr,mbr;
  wire [63:0] maa,mara,mwd;
  wire [7:0] mal,marl,mws;
  wire [2:0] mas,mars;
  wire [1:0] mab,marb,malock,marlock;
  wire mwlast,maid,marid;
  reg mrv=0,mrlast=0,mbv=0;
  reg [63:0] mrd=0;
  reg read_active=0,write_active=0;
  reg [63:0] read_addr=0,write_addr=0;
  integer read_left=0,write_left=0,cycle=0,reads=0,writes=0,transactions=0;
  reg rid=0,bid=0;
  wire marr=reset_n && !read_active && !mrv && (cycle%4!=0);
  wire mawr=reset_n && !write_active && !mbv && (cycle%5!=0);
  assign mwr=reset_n && write_active && (cycle%3!=0);
  reg [63:0] memory[0:32767];
  reg [63:0] inputs_a[0:31],gold_a[0:31],inputs_b[0:15],gold_b[0:15];
  integer i, before_reads, before_writes;
  reg [31:0] value;
  ffn dut(.ap_clk(clk), .ap_rst_n(reset_n),
    .s_axi_control_AWADDR(awaddr), .s_axi_control_AWVALID(awvalid), .s_axi_control_AWREADY(awready),
    .s_axi_control_WDATA(wdata), .s_axi_control_WSTRB(wstrb), .s_axi_control_WVALID(wvalid), .s_axi_control_WREADY(wready),
    .s_axi_control_BRESP(bresp), .s_axi_control_BVALID(bvalid), .s_axi_control_BREADY(bready),
    .s_axi_control_ARADDR(araddr), .s_axi_control_ARVALID(arvalid), .s_axi_control_ARREADY(arready),
    .s_axi_control_RDATA(rdata), .s_axi_control_RRESP(rresp), .s_axi_control_RVALID(rvalid), .s_axi_control_RREADY(rready),
    .m_axi_gmem_AWVALID(mav), .m_axi_gmem_AWREADY(mawr), .m_axi_gmem_AWADDR(maa), .m_axi_gmem_AWID(maid),
    .m_axi_gmem_AWLEN(mal), .m_axi_gmem_AWSIZE(mas), .m_axi_gmem_AWBURST(mab), .m_axi_gmem_AWLOCK(malock),
    .m_axi_gmem_WVALID(mwv), .m_axi_gmem_WREADY(mwr), .m_axi_gmem_WDATA(mwd), .m_axi_gmem_WSTRB(mws), .m_axi_gmem_WLAST(mwlast),
    .m_axi_gmem_ARVALID(marv), .m_axi_gmem_ARREADY(marr), .m_axi_gmem_ARADDR(mara), .m_axi_gmem_ARID(marid),
    .m_axi_gmem_ARLEN(marl), .m_axi_gmem_ARSIZE(mars), .m_axi_gmem_ARBURST(marb), .m_axi_gmem_ARLOCK(marlock),
    .m_axi_gmem_RVALID(mrv), .m_axi_gmem_RREADY(mrr), .m_axi_gmem_RDATA(mrd), .m_axi_gmem_RLAST(mrlast),
    .m_axi_gmem_RID(rid), .m_axi_gmem_RUSER(1'b0), .m_axi_gmem_RRESP(2'b00),
    .m_axi_gmem_BVALID(mbv), .m_axi_gmem_BREADY(mbr), .m_axi_gmem_BRESP(2'b00), .m_axi_gmem_BID(bid), .m_axi_gmem_BUSER(1'b0));

  always @(posedge clk) begin
    cycle <= cycle+1;
    if (!reset_n) begin
      read_active<=0; write_active<=0; mrv<=0; mbv<=0;
    end else begin
      if (marv && marr) begin
        if (mars!==3 || marb!==1 || marlock!==0 || mara%8!=0)
          $fatal(1,"Unsupported read transaction");
        if (!((mara>=64'h10000 && mara+(marl+1)*8<=64'h18180) ||
              (mara>=64'h20000 && mara+(marl+1)*8<=64'h20080)))
          $fatal(1,"Read outside parameter/input allocation: %h len %d",mara,marl);
        if ((mara%4096)+(marl+1)*8>4096) $fatal(1,"Read crosses AXI 4K boundary");
        read_active<=1; read_addr<=mara; read_left<=marl+1; rid<=marid;
        transactions<=transactions+1;
      end
      if (mrv && mrr) begin
        mrv<=0; reads<=reads+1; read_addr<=read_addr+8; read_left<=read_left-1;
        if(read_left==1) read_active<=0;
      end
      if (!mrv && read_active && cycle%3!=0) begin
        mrd<=memory[read_addr>>3]; mrlast<=read_left==1; mrv<=1;
      end
      if (mav && mawr) begin
        if (mas!==3 || mab!==1 || malock!==0 || maa%8!=0 || maa<64'h30000 || maa+(mal+1)*8>64'h30080)
          $fatal(1,"Write outside output allocation or invalid protocol");
        write_active<=1; write_addr<=maa; write_left<=mal+1; bid<=maid;
      end
      if (mwv && mwr) begin
        if (mws!==8'hff || mwlast!==(write_left==1)) $fatal(1,"Invalid write strobe/last");
        memory[write_addr>>3]<=mwd; write_addr<=write_addr+8; write_left<=write_left-1; writes<=writes+1;
        if(write_left==1) begin write_active<=0; mbv<=1; end
      end
      if(mbv && mbr) mbv<=0;
    end
  end
  `include "axi_tasks.vh"
  task pointers;
    begin
      axi_write(7'h18,32'h10000,4'hf); axi_write(7'h1c,0,4'hf);
      axi_write(7'h24,32'h20000,4'hf); axi_write(7'h28,0,4'hf);
      axi_write(7'h30,32'h30000,4'hf); axi_write(7'h34,0,4'hf);
    end
  endtask
  task call_op;
    input [31:0] op,expected;
    integer polls;
    begin
      axi_read(0,value);
      if((value&32'h85)!==4) $fatal(1,"Not idle before launch: %h",value);
      axi_write(7'h3c,op,4'hf); axi_write(0,1,4'hf);
      polls=0; value=0;
      while((value&2)==0 && polls<20000) begin axi_read(0,value); polls=polls+1; end
      if((value&2)==0) $fatal(1,"Operation timeout");
      if((value&32'h85)!==4) $fatal(1,"Done without idle: %h",value);
      axi_read(7'h10,value);
      if(value!==expected) $fatal(1,"Wrong status op=%d returned=%d expected=%d",op,value,expected);
      axi_read(0,value); if(value&2) $fatal(1,"Done not clear-on-read");
    end
  endtask
  task reset_release;
    begin
      ext_n=0; repeat(40) @(negedge clk); ext_n=1; repeat(300) @(negedge clk);
      if(reset_n!==1) $fatal(1,"Reset never released");
      axi_read(7'h18,value); if(value!==0) $fatal(1,"Pointer not reset");
    end
  endtask
  task unloaded_guards;
    begin
      before_reads=reads; before_writes=writes;
      call_op(2,2); call_op(1,1);
      if(reads!=before_reads || writes!=before_writes || marv || mav)
        $fatal(1,"Guard operation accessed DDR");
    end
  endtask
  initial begin
    for(i=0;i<32768;i=i+1) memory[i]=64'hbad0bad0bad0bad0;
    $readmemh("params_a.hex",memory,8192,12335);
    $readmemh("inputs_a.hex",inputs_a); $readmemh("gold_a.hex",gold_a);
    $readmemh("inputs_b.hex",inputs_b); $readmemh("gold_b.hex",gold_b);
    reset_release(); unloaded_guards(); pointers();
    before_reads=reads; before_writes=writes;
    call_op(0,0);
    if(reads-before_reads!=4144 || writes!=before_writes) $fatal(1,"LOAD transfer count");
    for(i=0;i<16;i=i+1) memory[16384+i]=inputs_a[i];
    before_reads=reads; before_writes=writes;
    call_op(1,0);
    if(reads-before_reads!=16 || writes-before_writes!=16) $fatal(1,"RUN transfer count");
    for(i=0;i<16;i=i+1) if(memory[24576+i]!==gold_a[i]) $fatal(1,"First output mismatch word %d",i);
    for(i=0;i<16;i=i+1) memory[16384+i]=inputs_a[16+i];
    call_op(1,0);
    for(i=0;i<16;i=i+1) if(memory[24576+i]!==gold_a[16+i]) $fatal(1,"Repeated RUN mismatch");
    // BRAM contents survive reset; the valid bit must still forbid their reuse.
    reset_release(); unloaded_guards(); pointers();
    $readmemh("params_b.hex",memory,8192,12335);
    call_op(0,0);
    for(i=0;i<16;i=i+1) memory[16384+i]=inputs_b[i];
    call_op(1,0);
    for(i=0;i<16;i=i+1) if(memory[24576+i]!==gold_b[i]) $fatal(1,"Reload after reset mismatch");
    if(memory[24575]!==64'hbad0bad0bad0bad0 || memory[24592]!==64'hbad0bad0bad0bad0)
      $fatal(1,"Output canary corrupted");
    $display("LIFECYCLE_TEST_PASS: guards issue no DDR, LOAD/RUN/repeated RUN/reset/unloaded/reload, exact outputs, bounded DMA, AXI stalls; reads=%d writes=%d",reads,writes);
    $finish;
  end
  initial begin #5000000; $fatal(1,"Lifecycle watchdog"); end
endmodule
