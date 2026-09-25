* SPDX-License-Identifier: Apache-2.0
* Mock DUT U (sim/mock/make_mock.py): 27 cells, 10 DFF
.subckt dut_U CLK x_0 x_1 x_2 x_3 x_4 y_0 y_1 y_2 y_3 y_4 VPWR VGND
Xu1_dfxtp CLK x_0 VGND VGND VPWR VPWR q_0 sky130_fd_sc_hd__dfxtp_1
Xu2_dfxtp CLK x_1 VGND VGND VPWR VPWR q_1 sky130_fd_sc_hd__dfxtp_1
Xu3_dfxtp CLK x_2 VGND VGND VPWR VPWR q_2 sky130_fd_sc_hd__dfxtp_1
Xu4_dfxtp CLK x_3 VGND VGND VPWR VPWR q_3 sky130_fd_sc_hd__dfxtp_1
Xu5_dfxtp CLK x_4 VGND VGND VPWR VPWR q_4 sky130_fd_sc_hd__dfxtp_1
Xu6_xor2 q_0 q_4 VGND VGND VPWR VPWR a0_0 sky130_fd_sc_hd__xor2_1
Xu7_xor2 q_4 q_3 VGND VGND VPWR VPWR a4_0 sky130_fd_sc_hd__xor2_1
Xu8_xor2 q_2 q_1 VGND VGND VPWR VPWR a2_0 sky130_fd_sc_hd__xor2_1
Xu9_and2b a0_0 q_1 VGND VGND VPWR VPWR t_0 sky130_fd_sc_hd__and2b_1
Xu10_and2b q_1 a2_0 VGND VGND VPWR VPWR t_1 sky130_fd_sc_hd__and2b_1
Xu11_and2b a2_0 q_3 VGND VGND VPWR VPWR t_2 sky130_fd_sc_hd__and2b_1
Xu12_and2b q_3 a4_0 VGND VGND VPWR VPWR t_3 sky130_fd_sc_hd__and2b_1
Xu13_and2b a4_0 a0_0 VGND VGND VPWR VPWR t_4 sky130_fd_sc_hd__and2b_1
Xu14_xor2 a0_0 t_1 VGND VGND VPWR VPWR b_0 sky130_fd_sc_hd__xor2_1
Xu15_xor2 q_1 t_2 VGND VGND VPWR VPWR b_1 sky130_fd_sc_hd__xor2_1
Xu16_xor2 a2_0 t_3 VGND VGND VPWR VPWR b_2 sky130_fd_sc_hd__xor2_1
Xu17_xor2 q_3 t_4 VGND VGND VPWR VPWR b_3 sky130_fd_sc_hd__xor2_1
Xu18_xor2 a4_0 t_0 VGND VGND VPWR VPWR b_4 sky130_fd_sc_hd__xor2_1
Xu19_xor2 b_1 b_0 VGND VGND VPWR VPWR c1 sky130_fd_sc_hd__xor2_1
Xu20_xor2 b_0 b_4 VGND VGND VPWR VPWR c0 sky130_fd_sc_hd__xor2_1
Xu21_xor2 b_3 b_2 VGND VGND VPWR VPWR c3 sky130_fd_sc_hd__xor2_1
Xu22_inv b_2 VGND VGND VPWR VPWR c2 sky130_fd_sc_hd__inv_1
Xu23_dfxtp CLK c0 VGND VGND VPWR VPWR y_0 sky130_fd_sc_hd__dfxtp_1
Xu24_dfxtp CLK c1 VGND VGND VPWR VPWR y_1 sky130_fd_sc_hd__dfxtp_1
Xu25_dfxtp CLK c2 VGND VGND VPWR VPWR y_2 sky130_fd_sc_hd__dfxtp_1
Xu26_dfxtp CLK c3 VGND VGND VPWR VPWR y_3 sky130_fd_sc_hd__dfxtp_1
Xu27_dfxtp CLK b_4 VGND VGND VPWR VPWR y_4 sky130_fd_sc_hd__dfxtp_1
Cw0 q_0 VGND 1f
Cw1 q_1 VGND 1f
Cw2 q_2 VGND 1f
Cw3 q_3 VGND 1f
Cw4 q_4 VGND 1f
Cw5 a0_0 VGND 1f
Cw6 a4_0 VGND 1f
Cw7 a2_0 VGND 1f
Cw8 t_0 VGND 1f
Cw9 t_1 VGND 1f
Cw10 t_2 VGND 1f
Cw11 t_3 VGND 1f
Cw12 t_4 VGND 1f
Cw13 b_0 VGND 1f
Cw14 b_1 VGND 1f
Cw15 b_2 VGND 1f
Cw16 b_3 VGND 1f
Cw17 b_4 VGND 1f
Cw18 c1 VGND 1f
Cw19 c0 VGND 1f
Cw20 c3 VGND 1f
Cw21 c2 VGND 1f
Cw22 y_0 VGND 1f
Cw23 y_1 VGND 1f
Cw24 y_2 VGND 1f
Cw25 y_3 VGND 1f
Cw26 y_4 VGND 1f
.ends dut_U
