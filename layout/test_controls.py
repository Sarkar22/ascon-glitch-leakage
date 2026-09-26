# SPDX-License-Identifier: Apache-2.0
"""Unit tests of the sign-off negative controls and the RC bracket (no EDA tools needed).

  python3 -m unittest layout/test_controls.py
"""
import json
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_pex  # noqa: E402
import make_pex_rc  # noqa: E402
import neg_controls as nc  # noqa: E402
import rc_check  # noqa: E402

GL_V = """module dut_T (CLK, VGND, VPWR, as0, as1, bs1, y);
 input CLK; input VGND; input VPWR; input as0; input as1; input bs1; output y;
 sky130_fd_sc_hd__dfxtp_1 ff_b (.CLK(clknet_0_CLK),
    .D(bs1),
    .VGND(VGND),
    .VNB(VGND),
    .VPB(VPWR),
    .VPWR(VPWR),
    .Q(bs1_q));
 sky130_fd_sc_hd__dfxtp_1 ff_a (.CLK(clknet_0_CLK),
    .D(as0),
    .VGND(VGND),
    .VNB(VGND),
    .VPB(VPWR),
    .VPWR(VPWR),
    .Q(as0_q));
 sky130_fd_sc_hd__and2_1 g_x (.A(as0_q),
    .B(bs1_q),
    .VGND(VGND),
    .VNB(VGND),
    .VPB(VPWR),
    .VPWR(VPWR),
    .X(y));
 sky130_fd_sc_hd__and2_1 g_w (.A(as1),
    .B(bs1_q),
    .VGND(VGND),
    .VNB(VGND),
    .VPB(VPWR),
    .VPWR(VPWR),
    .X(w));
 sky130_fd_sc_hd__decap_3 PHY_0 (.VGND(VGND),
    .VNB(VGND),
    .VPB(VPWR),
    .VPWR(VPWR));
endmodule
"""

GRAPH = {
    "cell_types": {
        "sky130_fd_sc_hd__dfxtp_1": {"inputs": ["D"], "output": "Q", "sequential": True},
        "sky130_fd_sc_hd__and2_1": {"inputs": ["A", "B"], "output": "X", "sequential": False}},
    "cells": [
        {"name": "ff_b", "type": "sky130_fd_sc_hd__dfxtp_1",
         "pins": {"CLK": "CLK", "D": "bs1", "Q": "bs1_q"}},
        {"name": "ff_a", "type": "sky130_fd_sc_hd__dfxtp_1",
         "pins": {"CLK": "CLK", "D": "as0", "Q": "as0_q"}},
        {"name": "g_x", "type": "sky130_fd_sc_hd__and2_1",
         "pins": {"A": "as0_q", "B": "bs1_q", "X": "y"}},
        {"name": "g_w", "type": "sky130_fd_sc_hd__and2_1",
         "pins": {"A": "as1", "B": "bs1_q", "X": "w"}}],
    "nets": {"as0": {"domain": "s0"}, "as1": {"domain": "s1"}, "bs1": {"domain": "s1"},
             "as0_q": {"domain": "s0"}, "as1_q": {"domain": "s1"}, "bs1_q": {"domain": "s1"},
             "y": {"domain": "cross"}, "w": {"domain": "s1"}},
}

NETGEN_MATCH_LOG = """Subcircuit summary:
Circuit 1: sky130_fd_sc_hd__and2_1         |Circuit 2: sky130_fd_sc_hd__and2_1
Final result: Circuits match uniquely.
Cell pin lists are equivalent.
Final result: Circuits match uniquely.
"""
NETGEN_MATCH_OUT = """Circuit 1 contains 4 devices, Circuit 2 contains 4 devices.
Circuit 1 contains 9 nets,    Circuit 2 contains 9 nets.
Circuit 1 contains 96 devices, Circuit 2 contains 96 devices.
Circuit 1 contains 109 nets,    Circuit 2 contains 109 nets.
Final result:
Circuits match uniquely.
"""
NETGEN_FAIL_LOG = """Final result: Circuits match uniquely.
Netlists do not match.
Final result: Netlists do not match.
"""
NETGEN_FAIL_OUT = (
    "Circuit 1 contains 671 devices, Circuit 2 contains 647 devices. *** MISMATCH ***\n"
    "Circuit 1 contains 384 nets,    Circuit 2 contains 372 nets. *** MISMATCH ***\n")

LYRDB = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
 <items>
  <item>
   <category>'m1.2'</category>
   <cell>dut_T</cell>
   <values>
    <value>edge-pair: (24.87,12.1;24.87,12.5)/(24.8,12.5;24.8,12.1)</value>
   </values>
  </item>
  <item>
   <category>'via.4a'</category>
   <cell>dut_T</cell>
   <values>
    <value>edge-pair: (41.15,12.179;41.15,12.421)/(41.18,12.225;41.18,12.375)</value>
   </values>
  </item>
 </items>
</report-database>
"""


class TestMutations(unittest.TestCase):
    def test_instances(self):
        inst = nc.instances(GL_V)
        self.assertEqual([i[1] for i in inst], ["ff_b", "ff_a", "g_x", "g_w", "PHY_0"])
        self.assertEqual(inst[2][3]["B"], "bs1_q")
        a, b = inst[2][2]
        self.assertTrue(GL_V[a:b].startswith("sky130_fd_sc_hd__and2_1 g_x"))
        self.assertTrue(GL_V[a:b].endswith(";"))

    def test_share_swap_moves_one_share0_input(self):
        text, info = nc.share_swap(GL_V, GRAPH)
        # g_w (as1, bs1_q) is single-domain; g_x (as0_q: s0, bs1_q: s1) is the cross-domain gate
        self.assertEqual((info["instance"], info["pin"], info["from_net"], info["to_net"]),
                         ("g_x", "A", "as0_q", "as1_q"))
        self.assertIn(".A(as1_q)", text)
        self.assertNotIn(".A(as0_q)", text)
        self.assertEqual(len(text), len(GL_V))
        diff = [k for k, (p, q) in enumerate(zip(GL_V, text)) if p != q]
        self.assertEqual(len(diff), 1)                      # a single character: s0 -> s1
        self.assertEqual(len(nc.instances(text)), len(nc.instances(GL_V)))

    def test_share_swap_needs_a_counterpart(self):
        g = json.loads(json.dumps(GRAPH))
        del g["nets"]["as1_q"]
        with self.assertRaises(ValueError):
            nc.share_swap(GL_V, g)

    def test_gate_type_first_by_name(self):
        text, info = nc.gate_type(GL_V)
        self.assertEqual(info["instance"], "g_w")            # g_w sorts before g_x
        self.assertIn("sky130_fd_sc_hd__or2_1 g_w", text)
        self.assertIn("sky130_fd_sc_hd__and2_1 g_x", text)
        self.assertEqual(text.count("or2_1"), 1)

    def test_missing_ff_removes_whole_statement(self):
        text, info = nc.missing_ff(GL_V)
        self.assertEqual((info["instance"], info["D"], info["Q"]), ("ff_a", "as0", "as0_q"))
        names = [i[1] for i in nc.instances(text)]
        self.assertEqual(names, ["ff_b", "g_x", "g_w", "PHY_0"])
        self.assertNotIn(".D(as0)", text)
        self.assertIn(" sky130_fd_sc_hd__and2_1 g_x", text)   # neighbours untouched

    def test_make_mutants_writes_all_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "gl.v")
            with open(src, "w") as f:
                f.write(GL_V)
            old = nc.REPO
            os.makedirs(os.path.join(tmp, "build", "T"))
            with open(os.path.join(tmp, "build", "T", "graph.json"), "w") as f:
                json.dump(GRAPH, f)
            nc.REPO = tmp
            try:
                info = nc.make_mutants("T", src, os.path.join(tmp, "out"))
            finally:
                nc.REPO = old
            for case in nc.CASES:
                self.assertTrue(os.path.exists(os.path.join(tmp, "out", case + ".v")))
            self.assertEqual(info["missing_ff"]["instances"], 4)
            self.assertEqual(info["correct"]["instances"], 5)
            with open(os.path.join(tmp, "out", "correct.v")) as f:
                self.assertEqual(f.read(), GL_V)


class TestReports(unittest.TestCase):
    def test_parse_netgen(self):
        r = nc.parse_netgen(NETGEN_MATCH_LOG, NETGEN_MATCH_OUT)
        self.assertEqual(r["verdict"], "match")
        self.assertEqual(r["devices_layout_vs_netlist"], [96, 96])
        self.assertEqual(r["nets_layout_vs_netlist"], [109, 109])
        r = nc.parse_netgen(NETGEN_FAIL_LOG, NETGEN_FAIL_OUT)      # last final result counts
        self.assertEqual(r["verdict"], "mismatch")
        self.assertEqual(r["final_result"], "Netlists do not match")
        self.assertEqual(r["devices_layout_vs_netlist"], [671, 647])
        for bad in ("Final result: Top level cell failed pin matching.",
                    "Final result: Circuits match uniquely with property errors.", ""):
            self.assertEqual(nc.parse_netgen(bad)["verdict"], "mismatch")

    def test_parse_magic_drc(self):
        text = ("24.870 12.100 24.940 12.500 um\tMetal1 spacing < 0.14um (met1.2)\n"
                "41.095 12.400 41.125 12.430 um\tMetal1 overlap of Via1 < 0.03um\nCOUNT 2\n")
        items, count = nc.parse_magic_drc(text)
        self.assertEqual(count, 2)
        self.assertEqual(items[0]["box_um"], [24.87, 12.1, 24.94, 12.5])
        self.assertEqual(items[1]["rule"], "Metal1 overlap of Via1 < 0.03um")
        self.assertEqual(nc.parse_magic_drc("COUNT 0\n"), ([], 0))

    def test_parse_lyrdb(self):
        items = nc.parse_lyrdb(LYRDB)
        self.assertEqual([i["rule"] for i in items], ["m1.2", "via.4a"])
        self.assertEqual(items[0]["box_um"], [24.8, 12.1, 24.87, 12.5])
        self.assertEqual(nc.parse_lyrdb("<report-database><items/></report-database>"), [])

    def test_check_drc(self):
        inj = [{"name": "met1_spacing", "bbox_um": [24.3, 12.1, 25.37, 12.5]},
               {"name": "via1_enclosure", "bbox_um": [41.03, 12.075, 41.48, 12.525]}]
        items = nc.parse_lyrdb(LYRDB)
        c = nc.check_drc(items, inj)
        self.assertTrue(c["exactly_the_injected"])
        self.assertEqual(c["markers_by_structure"]["via1_enclosure"], {"n": 1, "rules": ["via.4a"]})
        stray = items + [{"box_um": [5.0, 5.0, 5.1, 5.1], "rule": "m1.1"}]
        self.assertFalse(nc.check_drc(stray, inj)["exactly_the_injected"])   # extra marker
        self.assertFalse(nc.check_drc(items[:1], inj)["exactly_the_injected"])  # one missed


RC_FLAT = """* NGSPICE file created from dut_T_flat.ext - technology: sky130A
.subckt dut_T_flat CLK VGND VPWR a y
X0 n1.t0 a.t0 VGND VGND sky130_fd_pr__nfet_01v8 ad=0.169 pd=1.82 as=0.0878 ps=0.92 w=0.65 l=0.15
X1 n1.t1 a.t1 VPWR VPWR sky130_fd_pr__pfet_01v8_hvt ad=0.26 pd=2.52 as=0.135 ps=1.27 w=1 l=0.15
X2 y n1.t2 VGND VGND sky130_fd_pr__nfet_01v8 ad=0.169 pd=1.82 as=0.0878 ps=0.92 w=0.65 l=0.15
X3 VPWR VGND VPWR VPWR sky130_fd_pr__pfet_01v8_hvt ad=0.226 pd=2.26 as=135 ps=1.3k w=0.87 l=2.89
R0 a a.t0 120.5
R1 a a.t1 1.2k
R2 n1.t0 n1.n0 30
R3 n1.n0 n1.t1 30
R4 n1.n0 n1.t2 300
C0 n1.n0 VGND 0.7f
.ends
"""
C_FLAT = """* NGSPICE file created from dut_T_flat.ext - technology: sky130A
.subckt dut_T_flat CLK VGND VPWR a y
X0 n1# a VGND VGND sky130_fd_pr__nfet_01v8 ad=0.169 pd=1.82 as=0.0878 ps=0.92 w=0.65 l=0.15
X1 n1# a VPWR VPWR sky130_fd_pr__pfet_01v8_hvt ad=0.26 pd=2.52 as=0.135 ps=1.27 w=1 l=0.15
X2 y n1# VGND VGND sky130_fd_pr__nfet_01v8 ad=0.169 pd=1.82 as=0.0878 ps=0.92 w=0.65 l=0.15
X3 VPWR VGND VPWR VPWR sky130_fd_pr__pfet_01v8_hvt ad=0.226 pd=2.26 as=0 ps=0 w=0.87 l=2.89
C0 n1# VGND 1.2f
C1 a n1# 0.06f
C2 y VPWR 0.004f
C3 VPWR VGND 2p
.ends
"""


class TestMakePexRc(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rc = os.path.join(self.tmp.name, "rc.spice")
        self.c = os.path.join(self.tmp.name, "c.spice")
        with open(self.rc, "w") as f:
            f.write(RC_FLAT)
        with open(self.c, "w") as f:
            f.write(C_FLAT)

    def tearDown(self):
        self.tmp.cleanup()

    def test_names_and_values(self):
        self.assertEqual(make_pex_rc.net_of("m01_0.n3"), "m01_0")
        self.assertEqual(make_pex_rc.net_of("a_75_69.t0"), "a_75_69")
        self.assertEqual(make_pex_rc.net_of("a_75_69#"), "a_75_69")
        self.assertEqual(make_pex_rc.net_of("VPWR"), "VPWR")
        self.assertAlmostEqual(make_pex_rc.ohms("1.2k"), 1200.0)
        self.assertAlmostEqual(make_pex_rc.ohms("4meg"), 4e6)
        self.assertAlmostEqual(make_pex_rc.ohms("300.5"), 300.5)

    def test_resistor_stats(self):
        _, _, el = make_pex.parse_flat(self.rc)
        r = make_pex_rc.resistor_stats(el)
        self.assertEqual(r["count"], 5)
        self.assertAlmostEqual(r["total_ohm"], 1680.5)
        self.assertEqual(r["nets_with_resistors"], 2)
        self.assertEqual(r["supply_nets_with_resistors"], [])

    def test_align_devices(self):
        _, _, rc = make_pex.parse_flat(self.rc)
        _, _, c = make_pex.parse_flat(self.c)
        out, changed = make_pex_rc.align_devices(rc, c)
        self.assertEqual(changed, ["X3"])
        x3 = [e for e in out if e[1] == "X3"][0]
        self.assertIn("as=0", x3[4])
        self.assertEqual([e[2] for e in out if e[0] == "X"], [e[2] for e in rc if e[0] == "X"])
        bad = [("X", "X0", ["n1.t0", "y", "VGND", "VGND"], "sky130_fd_pr__nfet_01v8", [])] + rc[1:]
        with self.assertRaises(ValueError):
            make_pex_rc.align_devices(bad, c)

    def test_network_nodes_own_name_first(self):
        _, _, rc = make_pex.parse_flat(self.rc)
        nodes = make_pex_rc.network_nodes(rc)
        self.assertEqual(nodes["a"], ["a", "a.t0", "a.t1"])
        self.assertEqual(nodes["n1"], ["n1.n0", "n1.t0", "n1.t1", "n1.t2"])
        self.assertEqual(nodes["VGND"], ["VGND"])

    def test_redistribute_conserves_capacitance_per_net_pair(self):
        _, _, rc = make_pex.parse_flat(self.rc)
        _, _, c = make_pex.parse_flat(self.c)
        out, st = make_pex_rc.redistribute(rc, c, min_split=0.01)
        caps = [e for e in out if e[0] == "C"]
        self.assertEqual(st["magic_rc_capacitors_dropped"], 1)
        self.assertAlmostEqual(st["magic_rc_capacitance_fF"], 0.7)
        pair = {}
        for _, _, (x, y), _, p in caps:
            k = tuple(sorted((make_pex_rc.net_of(x), make_pex_rc.net_of(y))))
            pair[k] = pair.get(k, 0.0) + make_pex.cap_value_fF(p[0])
        self.assertAlmostEqual(pair[("VGND", "n1")], 1.2)
        self.assertAlmostEqual(pair[("a", "n1")], 0.06)
        self.assertAlmostEqual(pair[("VPWR", "y")], 0.004)
        self.assertAlmostEqual(pair[("VGND", "VPWR")], 2000.0)

        def between(a, b):
            return [e for e in caps if {make_pex_rc.net_of(n) for n in e[2]} == {a, b}]

        self.assertEqual(len(between("n1", "VGND")), 4)     # rail: split over n1's four nodes
        self.assertEqual({e[2][0] for e in between("n1", "VGND")},
                         {"n1.n0", "n1.t0", "n1.t1", "n1.t2"})
        a_n1 = between("a", "n1")                            # coupling: one node of each net
        self.assertEqual(len(a_n1), 1)
        self.assertEqual(a_n1[0][2], ["a", "n1.n0"])        # the own-name node where there is one
        self.assertEqual(len(between("y", "VPWR")), 1)      # below 0.01 fF: not split
        self.assertAlmostEqual(st["rail_split_fF"], 1.2)
        self.assertAlmostEqual(st["coupling_one_node_fF"], 0.06)
        self.assertAlmostEqual(st["rail_to_rail_fF"], 2000.0)
        self.assertEqual(st["capacitors_written"], 7)
        self.assertEqual(len([e for e in out if e[0] == "R"]), 5)

    def test_build(self):
        repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(os.path.join(repo, "build", "T"))
        with open(os.path.join(repo, "build", "T", "ports.json"), "w") as f:
            json.dump({"subckt": "dut_T", "ports": ["CLK", "a", "y", "VPWR", "VGND"],
                       "inputs": [{"name": "a"}], "outputs": [{"name": "y"}], "latency": 1,
                       "description": "test (post-layout extraction)"}, f)
        with open(os.path.join(repo, "build", "T", "dut.sp"), "w") as f:
            f.write("Cw_a a VGND 1.500f\n")
        old = make_pex.REPO
        make_pex.REPO = repo
        try:
            out = os.path.join(repo, "runs", "T_rc")
            st = make_pex_rc.build("T", self.rc, self.c, out)
        finally:
            make_pex.REPO = old
        with open(os.path.join(out, "dut.sp")) as f:
            text = f.read()
        self.assertIn(".subckt dut_T CLK a y VPWR VGND\n", text)
        self.assertIn("R1 a a_t1 1.2k", text)
        self.assertNotIn("as=135", text)
        self.assertTrue(text.startswith("* SPDX-License-Identifier: Apache-2.0\n"))
        with open(os.path.join(out, "ports.json")) as f:
            p = json.load(f)
        self.assertEqual(p["variant"], "T_rc")
        self.assertEqual(p["pex"]["resistors"]["count"], 5)
        self.assertEqual(p["pex"]["device_parameters_taken_from_c_only"], ["X3"])
        self.assertAlmostEqual(st["caps_fF"]["VPWR_VGND"], 2000.0)
        self.assertAlmostEqual(st["caps_fF"]["to_VGND"], 1.2)

    def test_build_refuses_supply_resistance(self):
        text = RC_FLAT.replace("C0 n1.n0 VGND 0.7f", "R9 VGND VGND.t3 0.5")
        path = os.path.join(self.tmp.name, "rcs.spice")
        with open(path, "w") as f:
            f.write(text)
        with self.assertRaises(ValueError):
            make_pex_rc.build("T", path, self.c, os.path.join(self.tmp.name, "o"))


class TestRcCheck(unittest.TestCase):
    def test_rename(self):
        d = rc_check.rename({"peak_ns_after_edge": {"pex": 1, "pre": 2},
                             "best_shift_ns_pex_later": 0.1})
        self.assertEqual(d, {"peak_ns_after_edge": {"rc": 1, "c_only": 2},
                             "best_shift_ns_rc_later": 0.1})

    def test_waveform_identical_and_shifted(self):
        rng = np.random.default_rng(0)
        base = np.exp(-((np.arange(100) - 30) / 5.0) ** 2) * 100
        tc = base + rng.normal(0, 1, (40, 100)) + rng.integers(0, 2, (40, 1)) * base * 0.1
        labels = np.arange(40) % 2
        w = rc_check.waveform(tc, tc.copy(), labels, 0.01, 0.2)
        self.assertAlmostEqual(w["data_dependent_corr"], 1.0)
        self.assertEqual(w["max_abs_diff_uA"], 0.0)
        self.assertEqual(w["class_mean_diff"]["max_abs_rc_minus_c_uA"], 0.0)
        tr = np.roll(tc, 3, axis=1)                       # RC 30 ps later
        w = rc_check.waveform(tc, tr, labels, 0.01, 0.2)
        self.assertAlmostEqual(w["best_shift_ns_rc_later"], 0.03)
        self.assertGreater(w["data_dependent_corr_at_shift"], 0.99)

    def test_net_timing(self):
        graph = GRAPH
        names = np.array(["bs1_q", "as0_q", "y", "w"])

        def ev(shift):
            # cycles 0-3; latency 1 drops cycles 0 and 1; times in the window (pre = 0.2 ns)
            rows = []
            for cyc in range(4):
                rows += [(0, cyc, 0.5), (1, cyc, 0.52), (2, cyc, 0.9 + shift),
                         (2, cyc, 1.0 + shift), (3, cyc, 0.8 + shift)]
            net, cyc, t = map(np.array, zip(*rows))
            return {"net_names": names, "net": net, "cycle": cyc, "t_ns": t,
                    "rise": np.zeros(len(t)), "pre": 0.2, "period": 4.0, "latency": 1}

        r = rc_check.net_timing(ev(0.0), ev(0.05), graph)
        self.assertEqual(r["cycles"], 2)
        self.assertAlmostEqual(r["last_logic_crossing_ns"]["c_only"]["median"], 0.8)
        self.assertAlmostEqual(r["last_logic_crossing_ns"]["rc_minus_c"]["median"], 0.05)
        self.assertAlmostEqual(r["clk_to_q_rc_minus_c_ns"]["max"], 0.0)
        self.assertAlmostEqual(r["per_net_last_crossing_rc_minus_c_ns"]["median"], 0.05)
        self.assertEqual(r["logic_crossings"]["c_only"], 6)
        self.assertEqual(r["logic_crossings"]["net_cycles_with_different_count"], 0)


if __name__ == "__main__":
    unittest.main()
