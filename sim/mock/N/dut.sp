* SPDX-License-Identifier: Apache-2.0
* Mock DUT N (sim/mock/make_mock.py): 88 cells, 25 DFF
.subckt dut_N CLK xs0_0 xs0_1 xs0_2 xs0_3 xs0_4 xs1_0 xs1_1 xs1_2 xs1_3 xs1_4 r_0 r_1 r_2 r_3 r_4 ys0_0 ys0_1 ys0_2 ys0_3 ys0_4 ys1_0 ys1_1 ys1_2 ys1_3 ys1_4 VPWR VGND
Xu1_dfxtp CLK xs0_0 VGND VGND VPWR VPWR q0_0 sky130_fd_sc_hd__dfxtp_1
Xu2_dfxtp CLK xs0_1 VGND VGND VPWR VPWR q0_1 sky130_fd_sc_hd__dfxtp_1
Xu3_dfxtp CLK xs0_2 VGND VGND VPWR VPWR q0_2 sky130_fd_sc_hd__dfxtp_1
Xu4_dfxtp CLK xs0_3 VGND VGND VPWR VPWR q0_3 sky130_fd_sc_hd__dfxtp_1
Xu5_dfxtp CLK xs0_4 VGND VGND VPWR VPWR q0_4 sky130_fd_sc_hd__dfxtp_1
Xu6_dfxtp CLK xs1_0 VGND VGND VPWR VPWR q1_0 sky130_fd_sc_hd__dfxtp_1
Xu7_dfxtp CLK xs1_1 VGND VGND VPWR VPWR q1_1 sky130_fd_sc_hd__dfxtp_1
Xu8_dfxtp CLK xs1_2 VGND VGND VPWR VPWR q1_2 sky130_fd_sc_hd__dfxtp_1
Xu9_dfxtp CLK xs1_3 VGND VGND VPWR VPWR q1_3 sky130_fd_sc_hd__dfxtp_1
Xu10_dfxtp CLK xs1_4 VGND VGND VPWR VPWR q1_4 sky130_fd_sc_hd__dfxtp_1
Xu11_dfxtp CLK r_0 VGND VGND VPWR VPWR qr_0 sky130_fd_sc_hd__dfxtp_1
Xu12_dfxtp CLK r_1 VGND VGND VPWR VPWR qr_1 sky130_fd_sc_hd__dfxtp_1
Xu13_dfxtp CLK r_2 VGND VGND VPWR VPWR qr_2 sky130_fd_sc_hd__dfxtp_1
Xu14_dfxtp CLK r_3 VGND VGND VPWR VPWR qr_3 sky130_fd_sc_hd__dfxtp_1
Xu15_dfxtp CLK r_4 VGND VGND VPWR VPWR qr_4 sky130_fd_sc_hd__dfxtp_1
Xu16_xor2 q0_0 q0_4 VGND VGND VPWR VPWR a0_0 sky130_fd_sc_hd__xor2_1
Xu17_xor2 q0_4 q0_3 VGND VGND VPWR VPWR a4_0 sky130_fd_sc_hd__xor2_1
Xu18_xor2 q0_2 q0_1 VGND VGND VPWR VPWR a2_0 sky130_fd_sc_hd__xor2_1
Xu19_xor2 q1_0 q1_4 VGND VGND VPWR VPWR a0_1 sky130_fd_sc_hd__xor2_1
Xu20_xor2 q1_4 q1_3 VGND VGND VPWR VPWR a4_1 sky130_fd_sc_hd__xor2_1
Xu21_xor2 q1_2 q1_1 VGND VGND VPWR VPWR a2_1 sky130_fd_sc_hd__xor2_1
Xu22_and2b a0_0 q0_1 VGND VGND VPWR VPWR p00_0 sky130_fd_sc_hd__and2b_1
Xu23_and2b a0_0 q1_1 VGND VGND VPWR VPWR m01_0 sky130_fd_sc_hd__and2b_1
Xu24_xor2 m01_0 qr_0 VGND VGND VPWR VPWR p01_0 sky130_fd_sc_hd__xor2_1
Xu25_and2 a0_1 q1_1 VGND VGND VPWR VPWR p11_0 sky130_fd_sc_hd__and2_1
Xu26_and2 a0_1 q0_1 VGND VGND VPWR VPWR m10_0 sky130_fd_sc_hd__and2_1
Xu27_xor2 m10_0 qr_0 VGND VGND VPWR VPWR p10_0 sky130_fd_sc_hd__xor2_1
Xu28_xor2 p00_0 p01_0 VGND VGND VPWR VPWR z0_0 sky130_fd_sc_hd__xor2_1
Xu29_xor2 p11_0 p10_0 VGND VGND VPWR VPWR z1_0 sky130_fd_sc_hd__xor2_1
Xu30_and2b q0_1 a2_0 VGND VGND VPWR VPWR p00_1 sky130_fd_sc_hd__and2b_1
Xu31_and2b q0_1 a2_1 VGND VGND VPWR VPWR m01_1 sky130_fd_sc_hd__and2b_1
Xu32_xor2 m01_1 qr_1 VGND VGND VPWR VPWR p01_1 sky130_fd_sc_hd__xor2_1
Xu33_and2 q1_1 a2_1 VGND VGND VPWR VPWR p11_1 sky130_fd_sc_hd__and2_1
Xu34_and2 q1_1 a2_0 VGND VGND VPWR VPWR m10_1 sky130_fd_sc_hd__and2_1
Xu35_xor2 m10_1 qr_1 VGND VGND VPWR VPWR p10_1 sky130_fd_sc_hd__xor2_1
Xu36_xor2 p00_1 p01_1 VGND VGND VPWR VPWR z0_1 sky130_fd_sc_hd__xor2_1
Xu37_xor2 p11_1 p10_1 VGND VGND VPWR VPWR z1_1 sky130_fd_sc_hd__xor2_1
Xu38_and2b a2_0 q0_3 VGND VGND VPWR VPWR p00_2 sky130_fd_sc_hd__and2b_1
Xu39_and2b a2_0 q1_3 VGND VGND VPWR VPWR m01_2 sky130_fd_sc_hd__and2b_1
Xu40_xor2 m01_2 qr_2 VGND VGND VPWR VPWR p01_2 sky130_fd_sc_hd__xor2_1
Xu41_and2 a2_1 q1_3 VGND VGND VPWR VPWR p11_2 sky130_fd_sc_hd__and2_1
Xu42_and2 a2_1 q0_3 VGND VGND VPWR VPWR m10_2 sky130_fd_sc_hd__and2_1
Xu43_xor2 m10_2 qr_2 VGND VGND VPWR VPWR p10_2 sky130_fd_sc_hd__xor2_1
Xu44_xor2 p00_2 p01_2 VGND VGND VPWR VPWR z0_2 sky130_fd_sc_hd__xor2_1
Xu45_xor2 p11_2 p10_2 VGND VGND VPWR VPWR z1_2 sky130_fd_sc_hd__xor2_1
Xu46_and2b q0_3 a4_0 VGND VGND VPWR VPWR p00_3 sky130_fd_sc_hd__and2b_1
Xu47_and2b q0_3 a4_1 VGND VGND VPWR VPWR m01_3 sky130_fd_sc_hd__and2b_1
Xu48_xor2 m01_3 qr_3 VGND VGND VPWR VPWR p01_3 sky130_fd_sc_hd__xor2_1
Xu49_and2 q1_3 a4_1 VGND VGND VPWR VPWR p11_3 sky130_fd_sc_hd__and2_1
Xu50_and2 q1_3 a4_0 VGND VGND VPWR VPWR m10_3 sky130_fd_sc_hd__and2_1
Xu51_xor2 m10_3 qr_3 VGND VGND VPWR VPWR p10_3 sky130_fd_sc_hd__xor2_1
Xu52_xor2 p00_3 p01_3 VGND VGND VPWR VPWR z0_3 sky130_fd_sc_hd__xor2_1
Xu53_xor2 p11_3 p10_3 VGND VGND VPWR VPWR z1_3 sky130_fd_sc_hd__xor2_1
Xu54_and2b a4_0 a0_0 VGND VGND VPWR VPWR p00_4 sky130_fd_sc_hd__and2b_1
Xu55_and2b a4_0 a0_1 VGND VGND VPWR VPWR m01_4 sky130_fd_sc_hd__and2b_1
Xu56_xor2 m01_4 qr_4 VGND VGND VPWR VPWR p01_4 sky130_fd_sc_hd__xor2_1
Xu57_and2 a4_1 a0_1 VGND VGND VPWR VPWR p11_4 sky130_fd_sc_hd__and2_1
Xu58_and2 a4_1 a0_0 VGND VGND VPWR VPWR m10_4 sky130_fd_sc_hd__and2_1
Xu59_xor2 m10_4 qr_4 VGND VGND VPWR VPWR p10_4 sky130_fd_sc_hd__xor2_1
Xu60_xor2 p00_4 p01_4 VGND VGND VPWR VPWR z0_4 sky130_fd_sc_hd__xor2_1
Xu61_xor2 p11_4 p10_4 VGND VGND VPWR VPWR z1_4 sky130_fd_sc_hd__xor2_1
Xu62_xor2 a0_0 z0_1 VGND VGND VPWR VPWR b0_0 sky130_fd_sc_hd__xor2_1
Xu63_xor2 q0_1 z0_2 VGND VGND VPWR VPWR b0_1 sky130_fd_sc_hd__xor2_1
Xu64_xor2 a2_0 z0_3 VGND VGND VPWR VPWR b0_2 sky130_fd_sc_hd__xor2_1
Xu65_xor2 q0_3 z0_4 VGND VGND VPWR VPWR b0_3 sky130_fd_sc_hd__xor2_1
Xu66_xor2 a4_0 z0_0 VGND VGND VPWR VPWR b0_4 sky130_fd_sc_hd__xor2_1
Xu67_xor2 b0_1 b0_0 VGND VGND VPWR VPWR c1_0 sky130_fd_sc_hd__xor2_1
Xu68_xor2 b0_0 b0_4 VGND VGND VPWR VPWR c0_0 sky130_fd_sc_hd__xor2_1
Xu69_xor2 b0_3 b0_2 VGND VGND VPWR VPWR c3_0 sky130_fd_sc_hd__xor2_1
Xu70_inv b0_2 VGND VGND VPWR VPWR c2_0 sky130_fd_sc_hd__inv_1
Xu71_dfxtp CLK c0_0 VGND VGND VPWR VPWR ys0_0 sky130_fd_sc_hd__dfxtp_1
Xu72_dfxtp CLK c1_0 VGND VGND VPWR VPWR ys0_1 sky130_fd_sc_hd__dfxtp_1
Xu73_dfxtp CLK c2_0 VGND VGND VPWR VPWR ys0_2 sky130_fd_sc_hd__dfxtp_1
Xu74_dfxtp CLK c3_0 VGND VGND VPWR VPWR ys0_3 sky130_fd_sc_hd__dfxtp_1
Xu75_dfxtp CLK b0_4 VGND VGND VPWR VPWR ys0_4 sky130_fd_sc_hd__dfxtp_1
Xu76_xor2 a0_1 z1_1 VGND VGND VPWR VPWR b1_0 sky130_fd_sc_hd__xor2_1
Xu77_xor2 q1_1 z1_2 VGND VGND VPWR VPWR b1_1 sky130_fd_sc_hd__xor2_1
Xu78_xor2 a2_1 z1_3 VGND VGND VPWR VPWR b1_2 sky130_fd_sc_hd__xor2_1
Xu79_xor2 q1_3 z1_4 VGND VGND VPWR VPWR b1_3 sky130_fd_sc_hd__xor2_1
Xu80_xor2 a4_1 z1_0 VGND VGND VPWR VPWR b1_4 sky130_fd_sc_hd__xor2_1
Xu81_xor2 b1_1 b1_0 VGND VGND VPWR VPWR c1_1 sky130_fd_sc_hd__xor2_1
Xu82_xor2 b1_0 b1_4 VGND VGND VPWR VPWR c0_1 sky130_fd_sc_hd__xor2_1
Xu83_xor2 b1_3 b1_2 VGND VGND VPWR VPWR c3_1 sky130_fd_sc_hd__xor2_1
Xu84_dfxtp CLK c0_1 VGND VGND VPWR VPWR ys1_0 sky130_fd_sc_hd__dfxtp_1
Xu85_dfxtp CLK c1_1 VGND VGND VPWR VPWR ys1_1 sky130_fd_sc_hd__dfxtp_1
Xu86_dfxtp CLK b1_2 VGND VGND VPWR VPWR ys1_2 sky130_fd_sc_hd__dfxtp_1
Xu87_dfxtp CLK c3_1 VGND VGND VPWR VPWR ys1_3 sky130_fd_sc_hd__dfxtp_1
Xu88_dfxtp CLK b1_4 VGND VGND VPWR VPWR ys1_4 sky130_fd_sc_hd__dfxtp_1
Cw0 q0_0 VGND 1f
Cw1 q0_1 VGND 1f
Cw2 q0_2 VGND 1f
Cw3 q0_3 VGND 1f
Cw4 q0_4 VGND 1f
Cw5 q1_0 VGND 1f
Cw6 q1_1 VGND 1f
Cw7 q1_2 VGND 1f
Cw8 q1_3 VGND 1f
Cw9 q1_4 VGND 1f
Cw10 qr_0 VGND 1f
Cw11 qr_1 VGND 1f
Cw12 qr_2 VGND 1f
Cw13 qr_3 VGND 1f
Cw14 qr_4 VGND 1f
Cw15 a0_0 VGND 1f
Cw16 a4_0 VGND 1f
Cw17 a2_0 VGND 1f
Cw18 a0_1 VGND 1f
Cw19 a4_1 VGND 1f
Cw20 a2_1 VGND 1f
Cw21 p00_0 VGND 1f
Cw22 m01_0 VGND 1f
Cw23 p01_0 VGND 1f
Cw24 p11_0 VGND 1f
Cw25 m10_0 VGND 1f
Cw26 p10_0 VGND 1f
Cw27 z0_0 VGND 1f
Cw28 z1_0 VGND 1f
Cw29 p00_1 VGND 1f
Cw30 m01_1 VGND 1f
Cw31 p01_1 VGND 1f
Cw32 p11_1 VGND 1f
Cw33 m10_1 VGND 1f
Cw34 p10_1 VGND 1f
Cw35 z0_1 VGND 1f
Cw36 z1_1 VGND 1f
Cw37 p00_2 VGND 1f
Cw38 m01_2 VGND 1f
Cw39 p01_2 VGND 1f
Cw40 p11_2 VGND 1f
Cw41 m10_2 VGND 1f
Cw42 p10_2 VGND 1f
Cw43 z0_2 VGND 1f
Cw44 z1_2 VGND 1f
Cw45 p00_3 VGND 1f
Cw46 m01_3 VGND 1f
Cw47 p01_3 VGND 1f
Cw48 p11_3 VGND 1f
Cw49 m10_3 VGND 1f
Cw50 p10_3 VGND 1f
Cw51 z0_3 VGND 1f
Cw52 z1_3 VGND 1f
Cw53 p00_4 VGND 1f
Cw54 m01_4 VGND 1f
Cw55 p01_4 VGND 1f
Cw56 p11_4 VGND 1f
Cw57 m10_4 VGND 1f
Cw58 p10_4 VGND 1f
Cw59 z0_4 VGND 1f
Cw60 z1_4 VGND 1f
Cw61 b0_0 VGND 1f
Cw62 b0_1 VGND 1f
Cw63 b0_2 VGND 1f
Cw64 b0_3 VGND 1f
Cw65 b0_4 VGND 1f
Cw66 c1_0 VGND 1f
Cw67 c0_0 VGND 1f
Cw68 c3_0 VGND 1f
Cw69 c2_0 VGND 1f
Cw70 ys0_0 VGND 1f
Cw71 ys0_1 VGND 1f
Cw72 ys0_2 VGND 1f
Cw73 ys0_3 VGND 1f
Cw74 ys0_4 VGND 1f
Cw75 b1_0 VGND 1f
Cw76 b1_1 VGND 1f
Cw77 b1_2 VGND 1f
Cw78 b1_3 VGND 1f
Cw79 b1_4 VGND 1f
Cw80 c1_1 VGND 1f
Cw81 c0_1 VGND 1f
Cw82 c3_1 VGND 1f
Cw83 ys1_0 VGND 1f
Cw84 ys1_1 VGND 1f
Cw85 ys1_2 VGND 1f
Cw86 ys1_3 VGND 1f
Cw87 ys1_4 VGND 1f
.ends dut_N
