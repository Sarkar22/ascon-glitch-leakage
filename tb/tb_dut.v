// SPDX-License-Identifier: Apache-2.0
// Generic testbench for the generated S-box DUTs (build/<V>/dut.v).
//
// tb/run_iverilog.py compiles it with a generated wrapper `dut_vec` (vector ports din/dout
// in ports.json order), the sky130_fd_sc_hd functional Verilog models, and
//   -Ptb.N_IN=<inputs> -Ptb.N_OUT=<outputs> -Ptb.N_CYC=<rows>
// and runs it with +vec=<stimulus file, one row per line, $readmemb order din[N_IN-1:0]>
// and +out=<dump file>. Timing (10 ns period): rising edge E_c at 10c+5 ns captures row c,
// the ports switch to row c+1 at E_c+3 ns, and the output ports of window c are written
// at E_c+9 ns (one line per window, dout[N_OUT-1:0] as %b).
`timescale 1ns / 1ps
`default_nettype none
module tb;
    parameter N_IN = 1;
    parameter N_OUT = 1;
    parameter N_CYC = 1;

    reg CLK = 1'b0;
    reg [N_IN-1:0] din;
    wire [N_OUT-1:0] dout;
    reg [N_IN-1:0] vec [0:N_CYC-1];
    reg [8*512-1:0] vec_file, out_file;
    integer fd, c;

    dut_vec u (.CLK(CLK), .din(din), .dout(dout));

    initial begin
        if (!$value$plusargs("vec=%s", vec_file) || !$value$plusargs("out=%s", out_file)) begin
            $display("usage: vvp <sim> +vec=<file> +out=<file>");
            $finish;
        end
        $readmemb(vec_file, vec);
        fd = $fopen(out_file, "w");
        din = vec[0];
        #5;
        for (c = 0; c < N_CYC; c = c + 1) begin
            CLK = 1'b1;                                   // E_c: input registers take row c
            #3 din = (c + 1 < N_CYC) ? vec[c + 1] : vec[N_CYC - 1];
            #2 CLK = 1'b0;
            #4 $fwrite(fd, "%b\n", dout);                 // window c
            #1;
        end
        $fclose(fd);
        $finish;
    end
endmodule
`default_nettype wire
