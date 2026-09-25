# SPDX-License-Identifier: Apache-2.0
"""Level-1 (toggle) and level-2 (glitch) models, plus zero-delay TVLA sanity on the variants."""
import json
import os
import tempfile
import unittest

import numpy as np

import _common
from _common import variant_dir


def tiny_graph(path, delay_a=100.0, delay_b=150.0, xor_delay=50.0):
    """Two registers a, b (different clk->Q) into one XOR: x = a ^ b."""
    cap = lambda d: {"driver": d, "domain": "x", "fanout": [], "wire_cap_fF": 1.0, "load_cap_fF": 2.0}
    g = {"variant": "T", "module": "dut_T", "latency": 1, "clock": "CLK",
         "inputs": [{"name": "ia", "role": "plain", "bit": 0}, {"name": "ib", "role": "plain", "bit": 1}],
         "outputs": [],
         "cell_types": {"xor": {"inputs": ["A", "B"], "output": "X", "function": "A ^ B", "sequential": False},
                        "dff": {"inputs": ["CLK", "D"], "output": "Q", "function": "D", "sequential": True}},
         "cells": [{"name": "ff_a", "type": "dff", "pins": {"CLK": "CLK", "D": "ia", "Q": "a"},
                    "delay_ps": {"CLK": {"rise": delay_a, "fall": delay_a}}},
                   {"name": "ff_b", "type": "dff", "pins": {"CLK": "CLK", "D": "ib", "Q": "b"},
                    "delay_ps": {"CLK": {"rise": delay_b, "fall": delay_b}}},
                   {"name": "g_x", "type": "xor", "pins": {"A": "a", "B": "b", "X": "x"},
                    "delay_ps": {"A": {"rise": xor_delay, "fall": xor_delay},
                                 "B": {"rise": xor_delay, "fall": xor_delay}}}],
         "nets": {"ia": cap(None), "ib": cap(None), "a": cap("ff_a"), "b": cap("ff_b"), "x": cap("g_x")},
         "dffs": ["ff_a", "ff_b"]}
    with open(path, "w") as f:
        json.dump(g, f)
    return path


class TestEventEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = tiny_graph(os.path.join(self.tmp, "graph.json"))

    def test_glitch_on_skewed_inputs(self):
        from glitch import TimingModel
        stim = np.array([[0, 0], [1, 1], [0, 0], [1, 0]], dtype=np.uint8)
        r = TimingModel(self.path, bin_ps=10, pre_ps=0, period_ps=1000).traces(stim, per_net=True,
                                                                                include_ports=False)
        x = r["net_names"].index("x")
        # window 1: a, b both rise (100 / 150 ps) -> x pulses 0->1 at 150, 1->0 at 200
        self.assertEqual(r["per_net"][1, x], 2)
        self.assertEqual(r["unweighted"][1, 10], 1)   # a at 100 ps
        self.assertEqual(r["unweighted"][1, 15], 2)   # b at 150, x at 150
        self.assertEqual(r["unweighted"][1, 20], 1)   # x back at 200
        # window 3: only a rises -> one clean transition of x
        self.assertEqual(r["per_net"][3, x], 1)

    def test_min_pulse_filter(self):
        from glitch import TimingModel
        stim = np.array([[0, 0], [1, 1]], dtype=np.uint8)
        r = TimingModel(self.path, min_pulse_ps=60).traces(stim, per_net=True)
        self.assertEqual(r["per_net"][1, r["net_names"].index("x")], 0)

    def test_transport_cancellation(self):
        """An input event that re-evaluates the output earlier cancels later pending events."""
        from glitch import TimingModel
        path = tiny_graph(os.path.join(self.tmp, "g2.json"), delay_a=100, delay_b=100)
        m = TimingModel(path)
        g = m.graph
        # make the XOR's B arc much faster than its A arc: A at 100 -> x due 400; B at 100 -> due 110
        out_i, ins, tt, rise, fall = m.comb[0]
        m.comb[0] = (out_i, ins, tt, (300.0, 10.0), (300.0, 10.0))
        v0 = [0] * g.n_nets
        v1 = list(v0)
        v1[g.idx["a"]] = v1[g.idx["b"]] = 1
        waves = m.window_events(v0, v1)
        self.assertIsNone(waves[g.idx["x"]])        # 1 due at 400 was cancelled by 0 due at 110


@unittest.skipUnless(_common.pdk_available(), "sky130A PDK not found (set PDK)")
class TestVariantModels(unittest.TestCase):
    def test_toggle_definition(self):
        from netgraph import Graph
        from stimulus import make_stimulus
        from toggle import toggle_traces, rows_from_cycles
        g = Graph(variant_dir("N"))
        stim, _ = make_stimulus(variant_dir("N"), "random", 200, 3)
        t = toggle_traces(g, stim, per_net=True)
        V = g.simulate(stim)
        tog = V[1:] ^ V[:-1]
        self.assertTrue((t["per_net"] == tog).all())
        self.assertTrue(np.allclose(t["unweighted"], tog.sum(1)))
        self.assertTrue(np.allclose(t["weighted"], tog @ g.load_cap))
        self.assertTrue(np.allclose(t["weighted_rise"], (tog & V[1:]) @ g.load_cap))
        rows = rows_from_cycles(t["weighted"], 2)
        self.assertEqual(rows.shape, (199, 2))
        self.assertTrue(np.allclose(rows[:, 1], t["weighted"][1:]))

    def test_glitch_model_consistent_with_zero_delay(self):
        from glitch import glitch_traces
        from stimulus import make_stimulus
        from toggle import toggle_traces
        for v in _common.VARIANTS:
            stim, _ = make_stimulus(variant_dir(v), "random", 300, 4)
            z = toggle_traces(variant_dir(v), stim, per_net=True)["per_net"]
            r = glitch_traces(variant_dir(v), stim, per_net=True)
            p = r["per_net"]
            self.assertTrue(((p % 2) == z).all(), v)       # parity of transitions = settled toggle
            self.assertTrue((p >= z).all(), v)
            self.assertEqual(r["late_events"], 0)
            self.assertTrue(np.allclose(r["unweighted"].sum(1), p.sum(1)))
        # the naive design glitches more than the unmasked one, relative to its settled toggles
        stim, _ = make_stimulus(variant_dir("N"), "random", 300, 4)
        pn = glitch_traces(variant_dir("N"), stim, per_net=True)["per_net"]
        zn = toggle_traces(variant_dir("N"), stim, per_net=True)["per_net"]
        self.assertGreater(pn.sum(), 1.5 * zn.sum())

    def test_glitch_parallel_equals_serial(self):
        from glitch import glitch_traces
        from stimulus import make_stimulus
        stim, _ = make_stimulus(variant_dir("D"), "random", 400, 5)
        a = glitch_traces(variant_dir("D"), stim)
        b = glitch_traces(variant_dir("D"), stim, jobs=2, chunk=150)
        self.assertTrue(np.array_equal(a["weighted"], b["weighted"]))

    def test_zero_delay_tvla_sanity(self):
        """U and N with masks off leak in the zero-delay model; masked N, D, DA do not."""
        from stimulus import make_stimulus
        from toggle import toggle_traces, rows_from_cycles
        from tvla import tvla_curve, THRESHOLD
        cases = [("U", "tvla", 3000, True), ("N", "masks_off", 3000, True),
                 ("N", "tvla", 20000, False), ("D", "tvla", 20000, False), ("DA", "tvla", 20000, False),
                 ("N", "rvr", 20000, False)]
        for v, mode, n, leaks in cases:
            stim, meta = make_stimulus(variant_dir(v), mode, n, 11)
            t = toggle_traces(variant_dir(v), stim)
            lat = 2 if v in ("D", "DA") else 1
            skip = lat + 1                                   # windows that start from reset
            for key in ("unweighted", "weighted"):
                rows = rows_from_cycles(t[key], lat)[skip:]
                labels = meta["label"][skip:skip + len(rows)]
                m = tvla_curve(rows, labels, [len(rows)])["max_abs_t"][-1]
                self.assertEqual(m > THRESHOLD, leaks, "%s %s %s max|t| = %.2f" % (v, mode, key, m))


if __name__ == "__main__":
    unittest.main()
