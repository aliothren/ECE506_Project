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

