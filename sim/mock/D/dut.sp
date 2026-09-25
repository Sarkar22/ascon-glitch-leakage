* SPDX-License-Identifier: Apache-2.0
* Mock DUT D (sim/mock/make_mock.py): 118 cells, 55 DFF
.subckt dut_D CLK xs0_0 xs0_1 xs0_2 xs0_3 xs0_4 xs1_0 xs1_1 xs1_2 xs1_3 xs1_4 r_0 r_1 r_2 r_3 r_4 ys0_0 ys0_1 ys0_2 ys0_3 ys0_4 ys1_0 ys1_1 ys1_2 ys1_3 ys1_4 VPWR VGND
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
Xu28_dfxtp CLK p00_0 VGND VGND VPWR VPWR Rp00_0 sky130_fd_sc_hd__dfxtp_1
Xu29_dfxtp CLK p01_0 VGND VGND VPWR VPWR Rp01_0 sky130_fd_sc_hd__dfxtp_1
Xu30_dfxtp CLK p11_0 VGND VGND VPWR VPWR Rp11_0 sky130_fd_sc_hd__dfxtp_1
Xu31_dfxtp CLK p10_0 VGND VGND VPWR VPWR Rp10_0 sky130_fd_sc_hd__dfxtp_1
Xu32_xor2 Rp00_0 Rp01_0 VGND VGND VPWR VPWR z0_0 sky130_fd_sc_hd__xor2_1
Xu33_xor2 Rp11_0 Rp10_0 VGND VGND VPWR VPWR z1_0 sky130_fd_sc_hd__xor2_1
Xu34_and2b q0_1 a2_0 VGND VGND VPWR VPWR p00_1 sky130_fd_sc_hd__and2b_1
Xu35_and2b q0_1 a2_1 VGND VGND VPWR VPWR m01_1 sky130_fd_sc_hd__and2b_1
Xu36_xor2 m01_1 qr_1 VGND VGND VPWR VPWR p01_1 sky130_fd_sc_hd__xor2_1
Xu37_and2 q1_1 a2_1 VGND VGND VPWR VPWR p11_1 sky130_fd_sc_hd__and2_1
Xu38_and2 q1_1 a2_0 VGND VGND VPWR VPWR m10_1 sky130_fd_sc_hd__and2_1
Xu39_xor2 m10_1 qr_1 VGND VGND VPWR VPWR p10_1 sky130_fd_sc_hd__xor2_1
Xu40_dfxtp CLK p00_1 VGND VGND VPWR VPWR Rp00_1 sky130_fd_sc_hd__dfxtp_1
Xu41_dfxtp CLK p01_1 VGND VGND VPWR VPWR Rp01_1 sky130_fd_sc_hd__dfxtp_1
Xu42_dfxtp CLK p11_1 VGND VGND VPWR VPWR Rp11_1 sky130_fd_sc_hd__dfxtp_1
Xu43_dfxtp CLK p10_1 VGND VGND VPWR VPWR Rp10_1 sky130_fd_sc_hd__dfxtp_1
Xu44_xor2 Rp00_1 Rp01_1 VGND VGND VPWR VPWR z0_1 sky130_fd_sc_hd__xor2_1
Xu45_xor2 Rp11_1 Rp10_1 VGND VGND VPWR VPWR z1_1 sky130_fd_sc_hd__xor2_1
Xu46_and2b a2_0 q0_3 VGND VGND VPWR VPWR p00_2 sky130_fd_sc_hd__and2b_1
Xu47_and2b a2_0 q1_3 VGND VGND VPWR VPWR m01_2 sky130_fd_sc_hd__and2b_1
Xu48_xor2 m01_2 qr_2 VGND VGND VPWR VPWR p01_2 sky130_fd_sc_hd__xor2_1
Xu49_and2 a2_1 q1_3 VGND VGND VPWR VPWR p11_2 sky130_fd_sc_hd__and2_1
Xu50_and2 a2_1 q0_3 VGND VGND VPWR VPWR m10_2 sky130_fd_sc_hd__and2_1
Xu51_xor2 m10_2 qr_2 VGND VGND VPWR VPWR p10_2 sky130_fd_sc_hd__xor2_1
Xu52_dfxtp CLK p00_2 VGND VGND VPWR VPWR Rp00_2 sky130_fd_sc_hd__dfxtp_1
Xu53_dfxtp CLK p01_2 VGND VGND VPWR VPWR Rp01_2 sky130_fd_sc_hd__dfxtp_1
Xu54_dfxtp CLK p11_2 VGND VGND VPWR VPWR Rp11_2 sky130_fd_sc_hd__dfxtp_1
Xu55_dfxtp CLK p10_2 VGND VGND VPWR VPWR Rp10_2 sky130_fd_sc_hd__dfxtp_1
Xu56_xor2 Rp00_2 Rp01_2 VGND VGND VPWR VPWR z0_2 sky130_fd_sc_hd__xor2_1
Xu57_xor2 Rp11_2 Rp10_2 VGND VGND VPWR VPWR z1_2 sky130_fd_sc_hd__xor2_1
Xu58_and2b q0_3 a4_0 VGND VGND VPWR VPWR p00_3 sky130_fd_sc_hd__and2b_1
Xu59_and2b q0_3 a4_1 VGND VGND VPWR VPWR m01_3 sky130_fd_sc_hd__and2b_1
Xu60_xor2 m01_3 qr_3 VGND VGND VPWR VPWR p01_3 sky130_fd_sc_hd__xor2_1
Xu61_and2 q1_3 a4_1 VGND VGND VPWR VPWR p11_3 sky130_fd_sc_hd__and2_1
Xu62_and2 q1_3 a4_0 VGND VGND VPWR VPWR m10_3 sky130_fd_sc_hd__and2_1
Xu63_xor2 m10_3 qr_3 VGND VGND VPWR VPWR p10_3 sky130_fd_sc_hd__xor2_1
Xu64_dfxtp CLK p00_3 VGND VGND VPWR VPWR Rp00_3 sky130_fd_sc_hd__dfxtp_1
Xu65_dfxtp CLK p01_3 VGND VGND VPWR VPWR Rp01_3 sky130_fd_sc_hd__dfxtp_1
Xu66_dfxtp CLK p11_3 VGND VGND VPWR VPWR Rp11_3 sky130_fd_sc_hd__dfxtp_1
Xu67_dfxtp CLK p10_3 VGND VGND VPWR VPWR Rp10_3 sky130_fd_sc_hd__dfxtp_1
Xu68_xor2 Rp00_3 Rp01_3 VGND VGND VPWR VPWR z0_3 sky130_fd_sc_hd__xor2_1
Xu69_xor2 Rp11_3 Rp10_3 VGND VGND VPWR VPWR z1_3 sky130_fd_sc_hd__xor2_1
Xu70_and2b a4_0 a0_0 VGND VGND VPWR VPWR p00_4 sky130_fd_sc_hd__and2b_1
Xu71_and2b a4_0 a0_1 VGND VGND VPWR VPWR m01_4 sky130_fd_sc_hd__and2b_1
Xu72_xor2 m01_4 qr_4 VGND VGND VPWR VPWR p01_4 sky130_fd_sc_hd__xor2_1
Xu73_and2 a4_1 a0_1 VGND VGND VPWR VPWR p11_4 sky130_fd_sc_hd__and2_1
Xu74_and2 a4_1 a0_0 VGND VGND VPWR VPWR m10_4 sky130_fd_sc_hd__and2_1
Xu75_xor2 m10_4 qr_4 VGND VGND VPWR VPWR p10_4 sky130_fd_sc_hd__xor2_1
Xu76_dfxtp CLK p00_4 VGND VGND VPWR VPWR Rp00_4 sky130_fd_sc_hd__dfxtp_1
Xu77_dfxtp CLK p01_4 VGND VGND VPWR VPWR Rp01_4 sky130_fd_sc_hd__dfxtp_1
Xu78_dfxtp CLK p11_4 VGND VGND VPWR VPWR Rp11_4 sky130_fd_sc_hd__dfxtp_1
Xu79_dfxtp CLK p10_4 VGND VGND VPWR VPWR Rp10_4 sky130_fd_sc_hd__dfxtp_1
Xu80_xor2 Rp00_4 Rp01_4 VGND VGND VPWR VPWR z0_4 sky130_fd_sc_hd__xor2_1
Xu81_xor2 Rp11_4 Rp10_4 VGND VGND VPWR VPWR z1_4 sky130_fd_sc_hd__xor2_1
Xu82_dfxtp CLK a0_0 VGND VGND VPWR VPWR Ra0_0 sky130_fd_sc_hd__dfxtp_1
Xu83_dfxtp CLK q0_1 VGND VGND VPWR VPWR Ra0_1 sky130_fd_sc_hd__dfxtp_1
Xu84_dfxtp CLK a2_0 VGND VGND VPWR VPWR Ra0_2 sky130_fd_sc_hd__dfxtp_1
Xu85_dfxtp CLK q0_3 VGND VGND VPWR VPWR Ra0_3 sky130_fd_sc_hd__dfxtp_1
Xu86_dfxtp CLK a4_0 VGND VGND VPWR VPWR Ra0_4 sky130_fd_sc_hd__dfxtp_1
Xu87_dfxtp CLK a0_1 VGND VGND VPWR VPWR Ra1_0 sky130_fd_sc_hd__dfxtp_1
Xu88_dfxtp CLK q1_1 VGND VGND VPWR VPWR Ra1_1 sky130_fd_sc_hd__dfxtp_1
Xu89_dfxtp CLK a2_1 VGND VGND VPWR VPWR Ra1_2 sky130_fd_sc_hd__dfxtp_1
Xu90_dfxtp CLK q1_3 VGND VGND VPWR VPWR Ra1_3 sky130_fd_sc_hd__dfxtp_1
Xu91_dfxtp CLK a4_1 VGND VGND VPWR VPWR Ra1_4 sky130_fd_sc_hd__dfxtp_1
Xu92_xor2 Ra0_0 z0_1 VGND VGND VPWR VPWR b0_0 sky130_fd_sc_hd__xor2_1
Xu93_xor2 Ra0_1 z0_2 VGND VGND VPWR VPWR b0_1 sky130_fd_sc_hd__xor2_1
Xu94_xor2 Ra0_2 z0_3 VGND VGND VPWR VPWR b0_2 sky130_fd_sc_hd__xor2_1
Xu95_xor2 Ra0_3 z0_4 VGND VGND VPWR VPWR b0_3 sky130_fd_sc_hd__xor2_1
Xu96_xor2 Ra0_4 z0_0 VGND VGND VPWR VPWR b0_4 sky130_fd_sc_hd__xor2_1
Xu97_xor2 b0_1 b0_0 VGND VGND VPWR VPWR c1_0 sky130_fd_sc_hd__xor2_1
Xu98_xor2 b0_0 b0_4 VGND VGND VPWR VPWR c0_0 sky130_fd_sc_hd__xor2_1
Xu99_xor2 b0_3 b0_2 VGND VGND VPWR VPWR c3_0 sky130_fd_sc_hd__xor2_1
Xu100_inv b0_2 VGND VGND VPWR VPWR c2_0 sky130_fd_sc_hd__inv_1
Xu101_dfxtp CLK c0_0 VGND VGND VPWR VPWR ys0_0 sky130_fd_sc_hd__dfxtp_1
Xu102_dfxtp CLK c1_0 VGND VGND VPWR VPWR ys0_1 sky130_fd_sc_hd__dfxtp_1
Xu103_dfxtp CLK c2_0 VGND VGND VPWR VPWR ys0_2 sky130_fd_sc_hd__dfxtp_1
Xu104_dfxtp CLK c3_0 VGND VGND VPWR VPWR ys0_3 sky130_fd_sc_hd__dfxtp_1
Xu105_dfxtp CLK b0_4 VGND VGND VPWR VPWR ys0_4 sky130_fd_sc_hd__dfxtp_1
Xu106_xor2 Ra1_0 z1_1 VGND VGND VPWR VPWR b1_0 sky130_fd_sc_hd__xor2_1
Xu107_xor2 Ra1_1 z1_2 VGND VGND VPWR VPWR b1_1 sky130_fd_sc_hd__xor2_1
Xu108_xor2 Ra1_2 z1_3 VGND VGND VPWR VPWR b1_2 sky130_fd_sc_hd__xor2_1
Xu109_xor2 Ra1_3 z1_4 VGND VGND VPWR VPWR b1_3 sky130_fd_sc_hd__xor2_1
Xu110_xor2 Ra1_4 z1_0 VGND VGND VPWR VPWR b1_4 sky130_fd_sc_hd__xor2_1
Xu111_xor2 b1_1 b1_0 VGND VGND VPWR VPWR c1_1 sky130_fd_sc_hd__xor2_1
Xu112_xor2 b1_0 b1_4 VGND VGND VPWR VPWR c0_1 sky130_fd_sc_hd__xor2_1
Xu113_xor2 b1_3 b1_2 VGND VGND VPWR VPWR c3_1 sky130_fd_sc_hd__xor2_1
Xu114_dfxtp CLK c0_1 VGND VGND VPWR VPWR ys1_0 sky130_fd_sc_hd__dfxtp_1
Xu115_dfxtp CLK c1_1 VGND VGND VPWR VPWR ys1_1 sky130_fd_sc_hd__dfxtp_1
Xu116_dfxtp CLK b1_2 VGND VGND VPWR VPWR ys1_2 sky130_fd_sc_hd__dfxtp_1
Xu117_dfxtp CLK c3_1 VGND VGND VPWR VPWR ys1_3 sky130_fd_sc_hd__dfxtp_1
Xu118_dfxtp CLK b1_4 VGND VGND VPWR VPWR ys1_4 sky130_fd_sc_hd__dfxtp_1
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
Cw27 Rp00_0 VGND 1f
Cw28 Rp01_0 VGND 1f
Cw29 Rp11_0 VGND 1f
Cw30 Rp10_0 VGND 1f
Cw31 z0_0 VGND 1f
Cw32 z1_0 VGND 1f
Cw33 p00_1 VGND 1f
Cw34 m01_1 VGND 1f
Cw35 p01_1 VGND 1f
Cw36 p11_1 VGND 1f
Cw37 m10_1 VGND 1f
Cw38 p10_1 VGND 1f
Cw39 Rp00_1 VGND 1f
Cw40 Rp01_1 VGND 1f
Cw41 Rp11_1 VGND 1f
Cw42 Rp10_1 VGND 1f
Cw43 z0_1 VGND 1f
Cw44 z1_1 VGND 1f
Cw45 p00_2 VGND 1f
Cw46 m01_2 VGND 1f
Cw47 p01_2 VGND 1f
Cw48 p11_2 VGND 1f
Cw49 m10_2 VGND 1f
Cw50 p10_2 VGND 1f
Cw51 Rp00_2 VGND 1f
Cw52 Rp01_2 VGND 1f
Cw53 Rp11_2 VGND 1f
Cw54 Rp10_2 VGND 1f
Cw55 z0_2 VGND 1f
Cw56 z1_2 VGND 1f
Cw57 p00_3 VGND 1f
Cw58 m01_3 VGND 1f
Cw59 p01_3 VGND 1f
Cw60 p11_3 VGND 1f
Cw61 m10_3 VGND 1f
Cw62 p10_3 VGND 1f
Cw63 Rp00_3 VGND 1f
Cw64 Rp01_3 VGND 1f
Cw65 Rp11_3 VGND 1f
Cw66 Rp10_3 VGND 1f
Cw67 z0_3 VGND 1f
Cw68 z1_3 VGND 1f
Cw69 p00_4 VGND 1f
Cw70 m01_4 VGND 1f
Cw71 p01_4 VGND 1f
Cw72 p11_4 VGND 1f
Cw73 m10_4 VGND 1f
Cw74 p10_4 VGND 1f
Cw75 Rp00_4 VGND 1f
Cw76 Rp01_4 VGND 1f
Cw77 Rp11_4 VGND 1f
Cw78 Rp10_4 VGND 1f
Cw79 z0_4 VGND 1f
Cw80 z1_4 VGND 1f
Cw81 Ra0_0 VGND 1f
Cw82 Ra0_1 VGND 1f
Cw83 Ra0_2 VGND 1f
Cw84 Ra0_3 VGND 1f
Cw85 Ra0_4 VGND 1f
Cw86 Ra1_0 VGND 1f
Cw87 Ra1_1 VGND 1f
Cw88 Ra1_2 VGND 1f
Cw89 Ra1_3 VGND 1f
Cw90 Ra1_4 VGND 1f
Cw91 b0_0 VGND 1f
Cw92 b0_1 VGND 1f
Cw93 b0_2 VGND 1f
Cw94 b0_3 VGND 1f
Cw95 b0_4 VGND 1f
Cw96 c1_0 VGND 1f
Cw97 c0_0 VGND 1f
Cw98 c3_0 VGND 1f
Cw99 c2_0 VGND 1f
Cw100 ys0_0 VGND 1f
Cw101 ys0_1 VGND 1f
Cw102 ys0_2 VGND 1f
Cw103 ys0_3 VGND 1f
Cw104 ys0_4 VGND 1f
Cw105 b1_0 VGND 1f
Cw106 b1_1 VGND 1f
Cw107 b1_2 VGND 1f
Cw108 b1_3 VGND 1f
Cw109 b1_4 VGND 1f
Cw110 c1_1 VGND 1f
Cw111 c0_1 VGND 1f
Cw112 c3_1 VGND 1f
Cw113 ys1_0 VGND 1f
Cw114 ys1_1 VGND 1f
Cw115 ys1_2 VGND 1f
Cw116 ys1_3 VGND 1f
Cw117 ys1_4 VGND 1f
.ends dut_D
