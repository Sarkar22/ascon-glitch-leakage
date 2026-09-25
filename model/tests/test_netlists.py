# SPDX-License-Identifier: Apache-2.0
"""Generated netlists: port contract, SPICE/Verilog/graph consistency, function, domains."""
import json
import os
import re
import unittest

import numpy as np

import _common
from _common import VARIANTS, variant_dir


def read_text(path):
    with open(path) as f:
        return f.read()


def read_json(path):
    return json.loads(read_text(path))


@unittest.skipUnless(_common.pdk_available(), "sky130A PDK not found (set PDK)")
class TestNetlists(unittest.TestCase):
    def load(self, v):
        d = variant_dir(v)
        ports, graph = (read_json(os.path.join(d, f)) for f in ("ports.json", "graph.json"))
        return d, ports, graph

    def test_port_contract(self):
        for v in VARIANTS:
            d, ports, graph = self.load(v)
            names = ["CLK"] + [p["name"] for p in ports["inputs"]] + [p["name"] for p in ports["outputs"]]
            self.assertEqual(ports["ports"], names + ["VPWR", "VGND"])
            self.assertEqual(ports["subckt"], "dut_" + v)
            self.assertEqual(ports["latency"], 2 if v in ("D", "DA") else 1)
            roles = {p["role"] for p in ports["inputs"]}
            self.assertEqual(roles, {"plain"} if v == "U" else {"share0", "share1", "rand"})
            for p in ports["inputs"] + ports["outputs"]:
                self.assertIn(p["bit"], range(5))
            self.assertEqual(ports["n_cells"], len(graph["cells"]))
            self.assertEqual(ports["n_dff"], len(graph["dffs"]))
            self.assertIsInstance(ports["wire_cap_fF"], float)
            # every input port feeds only flip-flop D pins (U, N, D) -- inputs are registered
            if v != "DA":
                for p in ports["inputs"]:
                    for cell, pin in graph["nets"][p["name"]]["fanout"]:
                        self.assertEqual(pin, "D")
                        self.assertTrue(cell.startswith("ff_"))

    def test_spice_matches_graph(self):
        import pdk
        pins = pdk.cell_pins_spice(["inv_1", "and2_1", "and2b_1", "xor2_1", "xnor2_1", "dfxtp_1"])
        for v in VARIANTS:
            d, ports, graph = self.load(v)
            text = read_text(os.path.join(d, "dut.sp")).replace("\n+ ", " ")
            sub = re.search(r"^\.subckt (\S+) (.*)$", text, re.M)
            self.assertEqual(sub.group(1), ports["subckt"])
            self.assertEqual(sub.group(2).split(), ports["ports"])
            cells = {c["name"]: c for c in graph["cells"]}
            inst = [l.split() for l in text.splitlines() if l.startswith("X")]
            self.assertEqual(len(inst), len(cells))
            for tok in inst:
                c = cells[tok[0][1:]]
                self.assertEqual(tok[-1], c["type"])
                short = c["type"].split("__")[1]
                want = [{"VGND": "VGND", "VNB": "VGND", "VPB": "VPWR", "VPWR": "VPWR"}.get(p) or c["pins"][p]
                        for p in pins[short]]
                self.assertEqual(tok[1:-1], want)
            caps = dict((l.split()[1], l.split()[3]) for l in text.splitlines() if l.startswith("Cw_"))
            for n, info in graph["nets"].items():
                self.assertAlmostEqual(float(caps[n].rstrip("f")), info["wire_cap_fF"], places=3)
                self.assertAlmostEqual(info["wire_cap_fF"], 1.0 + 0.5 * len(info["fanout"]))

    def test_verilog_matches_graph(self):
        for v in VARIANTS:
            d, ports, graph = self.load(v)
            text = read_text(os.path.join(d, "dut.v"))
            inst = re.findall(r"(sky130_fd_sc_hd__\w+) (\w+) \(\n(?:`ifdef.*?`endif\n)?\s*(.*?)\);", text, re.S)
            self.assertEqual(len(inst), len(graph["cells"]))
            for (typ, name, conns), c in zip(inst, graph["cells"]):
                self.assertEqual((typ, name), (c["type"], c["name"]))
                self.assertEqual(dict(re.findall(r"\.(\w+)\((\w+)\)", conns)), c["pins"])

    def test_function_exhaustive_with_latency(self):
        from ascon_sbox import SBOX_NP
        from netgraph import Graph
        from stimulus import make_stimulus
        for v in VARIANTS:
            g = Graph(variant_dir(v))
            stim, meta = make_stimulus(variant_dir(v), "exhaustive")
            self.assertEqual(len(stim), 32 if v == "U" else 32768)
            y = g.recombine(g.output_values(g.simulate(stim)))
            L = g.latency
            self.assertTrue((y[L:] == SBOX_NP[meta["x"][:-L]]).all(), v)
            yu = g.recombine(g.unrolled(stim)[:, g.output_idx])
            self.assertTrue((yu == SBOX_NP[meta["x"]]).all(), v)
            if v != "U":   # output shares alone must be uniform: each share bit is 1 half the time
                out = g.unrolled(stim)[:, g.output_idx]
                self.assertTrue((out.mean(0) == 0.5).all(), v)

    def test_share_domains_separate(self):
        """Outside the DOM cross terms (m01/m10 and their refresh XOR) no cell mixes domains."""
        for v in VARIANTS:
            d, ports, graph = self.load(v)
            nets = graph["nets"]
            types = graph["cell_types"]
            for c in graph["cells"]:
                t = types[c["type"]]
                out = c["pins"][t["output"]]
                ins = {nets[c["pins"][p]]["domain"] for p in t["inputs"] if p != "CLK"}
                if re.match(r"m(01|10)_\d$", out):
                    self.assertEqual(ins, {"s0", "s1"})
                elif re.match(r"p(01|10)_\d$", out):
                    self.assertEqual(ins, {"cross", "r"})
                else:
                    self.assertEqual(ins, {nets[out]["domain"]}, out)

    def test_dom_structure(self):
        """One fresh r bit per AND, used by exactly its two cross terms; barrier registers in D/DA."""
        for v in ("N", "D", "DA"):
            d, ports, graph = self.load(v)
            for i in range(5):
                fo = sorted(cell for cell, pin in graph["nets"]["r_%d_q" % i]["fanout"])
                self.assertEqual(fo, ["g_p01_%d" % i, "g_p10_%d" % i])
                for term in ("p00", "p01", "p11", "p10"):
                    reg = "%s_%d_q" % (term, i)
                    self.assertEqual(reg in graph["nets"], v != "N", reg)


if __name__ == "__main__":
    unittest.main()
