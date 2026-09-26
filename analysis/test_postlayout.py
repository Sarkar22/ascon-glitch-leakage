# SPDX-License-Identifier: Apache-2.0
"""Unit tests of the post-layout analysis (analysis/postlayout.py); host python3 + numpy, no
SPICE run needed. The last class checks the written results when they exist.

  python3 -m unittest discover -s analysis -p 'test_*.py'
"""
import csv
import json
import math
import os
import re
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cost_table as ct     # noqa: E402
import kill_test as kt      # noqa: E402
import postlayout as pl     # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, ".."))


def fake_campaign(rows=1200, lat=1, leak=0.0, seed=5):
    """A synthetic campaign dict in the shape load_run returns (fixed class = label 0)."""
    rng = np.random.default_rng(seed)
    ns = 400 * lat
    labels = rng.integers(0, 2, rows)
    tr = rng.normal(100.0, 10.0, (rows, ns))
    tr[:, 120] += leak * 10.0 * (labels == 0)
    man = {"latency": lat, "params": {"dt": 0.01, "pre": 0.2, "period": 4.0}}
    return dict(man=man, traces=tr, charge=tr.sum(1) * 0.01, meta={"label": labels}, lat=lat, skip=lat + 1,
                n_sim=rows, outputs=None)


class TestRegistration(unittest.TestCase):
    def test_counts_and_parts_match_the_registration(self):
        with open(os.path.join(REPO, "docs", "POSTLAYOUT.md")) as f:
            doc = " ".join(f.read().split())
        self.assertIn("N_pex 5,000 rows, DA_pex 10,000 rows", doc)
        self.assertEqual(pl.CAMPAIGNS["N_pex"][3], 5000)
        self.assertEqual(pl.CAMPAIGNS["DA_pex"][3], 10000)
        m = re.search(r"edge and evaluation (-?[\d.]+) to ([\d.]+) ns, clock fall ([\d.]+) to ([\d.]+) ns, "
                      r"input edges ([\d.]+) to ([\d.]+) ns", doc)
        self.assertIsNotNone(m)
        want = [float(v) for v in m.groups()]
        got = [v for _, a, b in pl.PARTS_POST for v in (a, b)]
        self.assertEqual(got, want)
        self.assertEqual(pl.THRESHOLD, 4.5)


class TestParts(unittest.TestCase):
    def test_part_of(self):
        self.assertEqual(pl.part_of(2.095, 4.0, 1), (1, "edge_and_evaluation"))
        self.assertEqual(pl.part_of(2.105, 4.0, 1), (1, "clock_fall"))
        self.assertEqual(pl.part_of(2.95, 4.0, 1), (1, "input_edges"))
        self.assertEqual(pl.part_of(4.5, 4.0, 2), (2, "edge_and_evaluation"))
        self.assertEqual(pl.part_of(3.85, 4.0, 1), (None, None))

    def test_region_max_post_layout(self):
        dt, pre, T = 0.01, 0.2, 4.0
        t = np.zeros(800)
        t[int((1.9 + pre) / dt)] = 6.0          # late evaluation: pre-layout "clock fall", now evaluation
        t[int((T + 2.5 + pre) / dt)] = -5.0     # second cycle, clock fall
        r = pl.post_regions(t, dt, pre, T, 2)
        self.assertEqual(r["cycle1_edge_and_evaluation"], 6.0)
        self.assertEqual(r["cycle2_clock_fall"], 5.0)
        self.assertEqual(r["cycle1_clock_fall"], 0.0)
        self.assertEqual(kt.region_max(t, dt, pre, T, 2)["cycle1_clock_fall"], 6.0)   # the pre-layout parts

    def test_peak_info_overlap_and_segments(self):
        dt, pre, T = 0.01, 0.2, 4.0
        t = np.zeros(400)
        t[int((2.05 + pre) / dt)] = 5.5
        t[int((0.9 + pre) / dt)] = 4.8
        t[int((3.0 + pre) / dt)] = 4.0          # below the threshold: not listed
        p = pl.peak_info(t, dt, pre, T, 1)
        self.assertTrue(p["peak"]["in_overlap_2.0_to_2.2"])
        self.assertEqual(p["peak"]["part"], "edge_and_evaluation")
        self.assertEqual([e["t"] for e in p["peaks_above_threshold_by_200ps_segment"]], [5.5, 4.8])
        self.assertEqual(p["samples_above_threshold"], 2)
        self.assertEqual(p["first_last_sample_above_threshold_ns"], [0.905, 2.055])


class TestTest(unittest.TestCase):
    def test_spice_tvla_is_the_kill_test_path(self):
        c = fake_campaign(leak=0.6)
        sp, t, labels, tr = pl.spice_tvla(c, pl.post_regions)
        self.assertEqual(len(tr), c["n_sim"] - 2)                         # first L+1 rows dropped
        ref = kt.tvla_block(c["traces"][2:], c["meta"]["label"][2:], kt.checkpoints(len(tr)), 0.01, 0.2)
        for k in ("n", "max_abs_t", "final_max_abs_t", "final_argmax", "first_above", "stable_from",
                  "final_peak_ns_after_edge"):
            self.assertEqual(sp[k], ref[k], k)
        self.assertGreater(sp["final_max_abs_t"], 4.5)
        self.assertAlmostEqual(sp["final_peak_ns_after_edge"], 1.005)
        self.assertEqual(sorted(sp["noise"]), ["0.5", "1.0", "2.0"])
        self.assertAlmostEqual(sp["noise_unit_uA"], round(float(tr.std(0).max()), 4))
        self.assertIn("final_max_abs_t_100ps_bins", sp)
        self.assertIn("edge_and_evaluation", sp["max_abs_t_by_region"])

    def test_detectable_fraction(self):
        f = pl.detectable_fraction(9997, 8.192, 4998)
        self.assertAlmostEqual(f, 4.5 / 8.192 * math.sqrt(4998 / 9997))
        s = {"campaigns": {"N_tvla": {"spice": {"final_max_abs_t": 13.23}, "rows_analysed": 9998},
                           "DA_tvla": {"rows_analysed": 19997}}}
        self.assertAlmostEqual(pl.detectable_fraction(19997, 13.23, 9998), ct.tvla_detectable_fraction(s, "DA"))

    def test_curve_shift(self):
        x = np.arange(400) * 0.01
        a = np.exp(-((x - 1.0) / 0.1) ** 2)
        b = np.exp(-((x - 1.7) / 0.1) ** 2)
        r = pl.curve_shift(a, b, 0.01)
        self.assertAlmostEqual(r["best_shift_ns"], 0.7)
        self.assertGreater(r["corr_at_best_shift"], 0.99)


class TestSpef(unittest.TestCase):
    def test_spef_caps(self):
        import tempfile
        text = "\n".join(['*SPEF "ieee 1481-1999"', "*C_UNIT 1 PF", "", "*NAME_MAP", "*1 CLK", "*7 m01_1", "",
                          "*PORTS", "*1 I *C 0 0", "", "*D_NET *7 0.0021", "*CONN", "*I *3:A I", "*CAP",
                          "1 *7:1 0.001", "*END", "", "*D_NET *1 0.0005", "*END"])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.spef")
            with open(p, "w") as f:
                f.write(text)
            caps = pl.spef_caps(p)
        self.assertAlmostEqual(caps["m01_1"], 2.1)
        self.assertAlmostEqual(caps["CLK"], 0.5)


class TestWrittenResults(unittest.TestCase):
    """The committed results agree with themselves (skipped before analysis/postlayout.py ran)."""

    @classmethod
    def setUpClass(cls):
        p = os.path.join(REPO, "results", "pex", "summary_postlayout.json")
        if not os.path.exists(p):
            raise unittest.SkipTest("results/pex/summary_postlayout.json not written yet")
        with open(p) as f:
            cls.s = json.load(f)

    def read(self, name):
        with open(os.path.join(REPO, "results", "pex", name)) as f:
            rows = list(csv.reader(f))
        return {h: [float(r[i]) for r in rows[1:]] for i, h in enumerate(rows[0])}

    def test_criteria_follow_the_numbers(self):
        cr = self.s["criteria"]
        self.assertEqual(cr["PL1"]["pass"], cr["PL1"]["max_abs_t"] > 4.5)
        self.assertEqual(cr["PL2"]["pass"], cr["PL2"]["max_abs_t"] < 4.5)
        for k, rows in (("PL1", 5000), ("PL2", 10000)):
            self.assertEqual(cr[k]["rows_simulated"], rows)
            self.assertTrue(cr[k]["complete"])
        n, da = cr["PL1"], cr["PL2"]
        self.assertAlmostEqual(cr["PL3"]["DA_pex_detectable_fraction_of_N_pex"],
                               4.5 / n["max_abs_t"] * math.sqrt(n["traces"] / da["traces"]), places=3)

    def test_csvs_match_summary(self):
        for name in ("N_pex", "DA_pex"):
            c = self.s["campaigns"][name]
            m = self.read("maxt_vs_traces_%s.csv" % name)
            self.assertEqual(int(m["traces"][-1]), c["rows_analysed"])
            self.assertAlmostEqual(m["post_layout"][-1], c["spice"]["final_max_abs_t"], places=3)
            self.assertAlmostEqual(m["pre_layout_same_rows"][-1],
                                   c["pre_layout_same_rows"]["final_max_abs_t"], places=3)
            t = self.read("tcurve_%s.csv" % name)
            self.assertAlmostEqual(max(abs(v) for v in t["t_post_layout"]), c["spice"]["final_max_abs_t"], places=3)
            self.assertEqual(c["function_check"]["mismatches_vs_sbox"], 0)

    def test_capacitance_views(self):
        for v in ("N", "DA"):
            e = self.s["capacitance_views"][v]
            self.assertAlmostEqual(e["magic_over_estimate"], e["magic_flat_fF"] / e["prelayout_estimate_fF"], places=2)
            self.assertGreater(e["magic_flat_fF"], e["openrcx_routed_wiring_fF"])

    def test_same_code_path_as_the_kill_test(self):
        self.assertTrue(self.s["reproduces_kill_test"]["all_identical"])


if __name__ == "__main__":
    unittest.main()
