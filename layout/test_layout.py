# SPDX-License-Identifier: Apache-2.0
"""Unit tests of the layout/PEX helpers (no OpenLane, Magic or ngspice needed).

  python3 -m unittest layout/test_layout.py
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_pex  # noqa: E402
import summarize  # noqa: E402

FLAT = """* NGSPICE file created from dut_T_flat.ext - technology: sky130A

.subckt dut_T_flat CLK VGND VPWR a
+ y VSUBS
X0 n1# a VGND VGND sky130_fd_pr__nfet_01v8 ad=0.169 pd=1.82 as=0.0878 ps=0.92 w=0.65 l=0.15
X1 n1# a VPWR VPWR sky130_fd_pr__pfet_01v8_hvt ad=0.26 pd=2.52 as=0.135 ps=1.27 w=1 l=0.15
X2 VPWR VGND VPWR VPWR sky130_fd_pr__pfet_01v8_hvt ad=0.226 pd=2.26 as=0 ps=0 w=0.87 l=2.89
X3 y n1# VGND VGND sky130_fd_pr__nfet_01v8 ad=0.169 pd=1.82 as=0.0878 ps=0.92 w=0.65 l=0.15
C0 a n1# 0.0518f
C1 n1# VGND 1.2f $ **FLOATING
C2 y VPWR 8.41e-19
C3 VPWR VGND 2p
C4 a CLK 0.001f
.ends
"""

GEN_V = """module dut_T (input wire CLK, input wire a, output wire y
`ifdef USE_POWER_PINS
    , inout wire VPWR
`endif
);
    wire q;
    sky130_fd_sc_hd__dfxtp_1 ff_q (
`ifdef USE_POWER_PINS
        .VPWR(VPWR), .VGND(VGND), .VPB(VPWR), .VNB(VGND),
`endif
        .CLK(CLK), .D(a), .Q(q));
    sky130_fd_sc_hd__inv_1 g_y (.A(q), .Y(y));
endmodule
"""

FINAL_V = """module dut_T (CLK, a, y);
 input CLK; input a; output y;
 sky130_fd_sc_hd__dfxtp_1 ff_q (.CLK(clknet_0_CLK), .D(a), .Q(q));
 sky130_fd_sc_hd__inv_1 g_y (.A(q), .Y(y));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_0_CLK (.A(CLK), .X(clknet_0_CLK));
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_1 ();
 sky130_fd_sc_hd__decap_3 PHY_0 ();
endmodule
"""


class TestMakePex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.flat = os.path.join(self.tmp.name, "flat.spice")
        with open(self.flat, "w") as f:
            f.write(FLAT)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_flat(self):
        name, ports, el = make_pex.parse_flat(self.flat)
        self.assertEqual(name, "dut_T_flat")
        self.assertEqual(ports, ["CLK", "VGND", "VPWR", "a", "y", "VSUBS"])
        self.assertEqual(len(el), 9)
        kind, nm, nodes, model, params = el[0]
        self.assertEqual((kind, nodes, model), ("X", ["n1#", "a", "VGND", "VGND"],
                                                "sky130_fd_pr__nfet_01v8"))
        self.assertIn("ad=0.169", params)
        self.assertEqual(el[5][2], ["n1#", "VGND"])          # the "$ **FLOATING" note is dropped
        self.assertEqual(el[5][4], ["1.2f"])

    def test_cap_values(self):
        self.assertAlmostEqual(make_pex.cap_value_fF("0.0518f"), 0.0518)
        self.assertAlmostEqual(make_pex.cap_value_fF("8.41e-19"), 8.41e-4)
        self.assertAlmostEqual(make_pex.cap_value_fF("2p"), 2000.0)

    def test_safe_names_unique_and_case_insensitive(self):
        m = make_pex.safe_names(["a_1#", "a_1_", "A_1#", "net/x"])
        self.assertEqual(m["a_1#"], "a_1_")
        self.assertEqual(len({v.lower() for v in m.values()}), 4)
        self.assertTrue(all(set(v) <= set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                          "0123456789_") for v in m.values()))

    def test_port_map_ties_substrate_and_rejects_unknown(self):
        want = ["CLK", "a", "y", "VPWR", "VGND"]
        conn = make_pex.port_map(["CLK", "VGND", "VPWR", "a", "y", "VSUBS"], want)
        self.assertEqual(conn["VSUBS"], "VGND")
        self.assertEqual(conn["a"], "a")
        with self.assertRaises(ValueError):
            make_pex.port_map(["CLK", "VGND", "VPWR", "a", "y", "junk"], want)
        with self.assertRaises(ValueError):
            make_pex.port_map(["CLK", "VGND", "VPWR", "a"], want)

    def test_cap_stats(self):
        _, _, el = make_pex.parse_flat(self.flat)
        tot, per = make_pex.cap_stats(el)
        self.assertEqual(tot["count"], 5)
        self.assertAlmostEqual(tot["VPWR_VGND"], 2000.0)
        self.assertAlmostEqual(tot["to_VGND"], 1.2)
        self.assertAlmostEqual(per["a"]["coupling"], 0.0528)
        self.assertAlmostEqual(per["n1#"]["ground"], 1.2)

    def test_build_port_order(self):
        """dut.sp keeps the pre-layout port order; supply-only devices can be dropped."""
        import json
        repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(os.path.join(repo, "build", "T"))
        with open(os.path.join(repo, "build", "T", "ports.json"), "w") as f:
            json.dump({"subckt": "dut_T", "ports": ["CLK", "a", "y", "VPWR", "VGND"],
                       "inputs": [{"name": "a"}], "outputs": [{"name": "y"}], "latency": 1}, f)
        with open(os.path.join(repo, "build", "T", "dut.sp"), "w") as f:
            f.write("Cw_a a VGND 1.500f\nCw_y y VGND 1.000f\n")
        old = make_pex.REPO
        make_pex.REPO = repo
        try:
            out = os.path.join(repo, "build", "T_pex")
            st = make_pex.build("T", self.flat, out, drop_supply=True,
                                netcap_csv=os.path.join(repo, "netcap.csv"))
        finally:
            make_pex.REPO = old
        with open(os.path.join(out, "dut.sp")) as f:
            text = f.read()
        self.assertIn(".subckt dut_T CLK a y VPWR VGND\n", text)
        body = text.split(".subckt dut_T ")[1]
        self.assertNotIn("#", body)
        self.assertNotIn("VSUBS", body)                    # the substrate port joined VGND
        self.assertIn("X0 n1_ a VGND VGND sky130_fd_pr__nfet_01v8", body)
        self.assertNotIn("\nX2 ", text)                    # the decap device was dropped
        self.assertEqual(st["supply_only_devices_dropped"], 1)
        self.assertEqual(st["n_devices"], 3)
        with open(os.path.join(out, "ports.json")) as f:
            p = json.load(f)
        self.assertEqual(p["ports"], ["CLK", "a", "y", "VPWR", "VGND"])
        self.assertEqual(p["variant"], "T_pex")
        self.assertIsNone(p["wire_cap_fF"])


class TestSummarize(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, text):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_parse_and_compare(self):
        gen = summarize.parse_verilog(self._write("gen.v", GEN_V))
        fin = summarize.parse_verilog(self._write("fin.v", FINAL_V))
        self.assertEqual(gen["ff_q"], ("sky130_fd_sc_hd__dfxtp_1",
                                       {"CLK": "CLK", "D": "a", "Q": "q"}))
        c = summarize.compare_netlists(gen, fin)
        self.assertTrue(c["logic_unchanged"])
        self.assertEqual(c["clk_pins_on_clock_tree_nets"], 1)
        self.assertEqual(c["added_instances"]["clock_buffer"], {"sky130_fd_sc_hd__clkbuf_16": 1})
        self.assertEqual(set(c["added_instances"]), {"clock_buffer", "tap", "decap"})

    def test_compare_detects_changes(self):
        gen = summarize.parse_verilog(self._write("gen.v", GEN_V))
        changed = FINAL_V.replace(".A(q), .Y(y)", ".A(q_buf), .Y(y)")
        fin = summarize.parse_verilog(self._write("fin.v", changed))
        c = summarize.compare_netlists(gen, fin)
        self.assertFalse(c["logic_unchanged"])
        self.assertEqual(c["changed_pins"], ["g_y.A: q -> q_buf"])


if __name__ == "__main__":
    unittest.main()
