# SPDX-License-Identifier: Apache-2.0
"""Unit tests of the cost table helpers (analysis/cost_table.py); no PDK or SPICE run needed.

  python3 -m unittest discover -s analysis -p 'test_*.py'
"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cost_table as ct     # noqa: E402


class TestCharge(unittest.TestCase):
    def test_latency2_window_counts_each_cycle_twice(self):
        q = np.array([2000.0, 2200.0, 1800.0])
        s1 = ct.charge_stats(q, 1, 1.8, 4.0)
        s2 = ct.charge_stats(q, 2, 1.8, 4.0)
        self.assertAlmostEqual(s1["q_eval_fC"], 2000.0)
        self.assertAlmostEqual(s2["q_eval_fC"], 1000.0)
        self.assertAlmostEqual(s2["e_eval_fJ"], 1800.0)            # fC x V = fJ
        self.assertAlmostEqual(s1["avg_power_uW_at_period"], 900.0)   # 3600 fJ / 4 ns
        self.assertEqual(s2["window_ns"], 8.0)
        self.assertAlmostEqual(s1["q_window_sem_fC"], 200.0 / np.sqrt(3))

    def test_random_neighbourhood(self):
        rnd = np.array([1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1], dtype=bool)
        # L = 1: rows r-2 .. r+1 must be random; the fixed row 4 excludes rows 3, 5, 6
        got = ct.random_neighbourhood(rnd, 1, 2)
        self.assertEqual(np.flatnonzero(got).tolist(), [2, 7, 8, 9, 10])
        # L = 2: rows r-3 .. r+2; row 4 excludes rows 2, 3, 5, 6, 7; skip 3
        got = ct.random_neighbourhood(rnd, 2, 3)
        self.assertEqual(np.flatnonzero(got).tolist(), [8, 9])


class TestVerdict(unittest.TestCase):
    def summary(self, t, first=None, stable=None):
        return {"campaigns": {"N_tvla": {"rows_analysed": 9998, "spice": {
            "final_max_abs_t": t, "first_above": first, "stable_from": stable}}}}

    def test_leak_and_no_leak(self):
        v = ct.verdict(self.summary(13.23, 1550, 1550), "N")
        self.assertTrue(v["leaks"])
        self.assertIn("above 4.5 from 1,550 on", v["text"])
        v = ct.verdict(self.summary(4.5 / 2), "N")
        self.assertFalse(v["leaks"])
        self.assertIn("no first-order leak detected", v["text"])
        self.assertIn("TVLA reaches |t| 4.5 on average for a leak of 2.00 x N's effect size",
                      v["text"])                                       # t 2.25 -> threshold is 2x
        self.assertNotIn("or more", v["text"])        # at that size detection is a coin toss, not a floor
        self.assertIsNone(ct.verdict({"campaigns": {}}, "N"))
        sm = self.summary(13.23)
        sm["campaigns"]["D_tvla"] = {"rows_analysed": 19997,
                                     "level2": {"unweighted": {"final_max_abs_t": 15.159},
                                                "weighted": {"final_max_abs_t": 15.159},
                                                "weighted_rise": {"final_max_abs_t": 16.734}},
                                     "spice": {"final_max_abs_t": 3.08, "first_above": None, "stable_from": None}}
        self.assertIn("level 2 predicts max|t| 15.2 (cap-weighted; 16.7 with the worst of three weightings) "
                      "on the same rows", ct.verdict(sm, "D")["text"])


class TestKeyRecoveryText(unittest.TestCase):
    def res(self, ge, sr, to90=None, p1=0.5, p2=0.5, n=765):
        return {"n": [1, 10, n], "final_ge": ge, "final_sr": sr, "traces_to_sr90": to90,
                "final_sr_x1": p1, "final_sr_x2": p2}

    def kr(self, name, tmpl, bits=None, corr=None, injection=None):
        r = {"tmpl": tmpl, "corr": corr or self.res(1.2, 0.3),
             "null": {d: {"final_ge_mean": 1.5, "final_ge_sd": 0.08, "final_ge_min": 1.35}
                      for d in ("tmpl", "tmpl_bits", "corr")}}
        if bits:
            r["tmpl_bits"] = bits
        ds = {"results": {"order1_noise0": r}}
        if injection:
            ds["injection"] = injection
        return {"datasets": {name: ds}}

    def test_recovered_and_primary_only(self):
        t = ct.key_recovery_text(self.kr("U_tvla", self.res(0.0, 1.0, 7), corr=self.res(0.0, 1.0, 2)), "U")
        self.assertEqual(t, "key recovered (template): SR >= 0.9 from 7 traces per key")   # not the correlation
        self.assertIsNone(ct.key_recovery_text(None, "N"))

    def test_n_reports_both_poi_rules(self):
        t = ct.key_recovery_text(self.kr("N_pooled", self.res(0.38, 0.62, None, 1.0, 0.63),
                                         bits=self.res(0.06, 0.94, 500, 1.0, 0.94)), "N")
        self.assertIn("default POIs (overall F): GE 0.38, SR 0.62 at 765 attack traces per key; "
                      "P(x1) 1.00, P(x2) 0.63", t)
        self.assertIn("Per-key-bit POIs (post hoc): key recovered (template): SR >= 0.9 from 500 traces", t)

    def test_no_recovery_names_the_detectable_effect(self):
        inj = {"smallest_detected_alpha": {"tmpl": 0.5, "corr": None},
               "alphas": {"1": {"tmpl": {"final_ge": 0.4}}, "0.5": {"tmpl": {"final_ge": 0.95}},
                          "0.35": {"tmpl": {"final_ge": 1.41}}, "0.25": {"tmpl": {"final_ge": 1.5}}}}
        t = ct.key_recovery_text(self.kr("DA_tvla", self.res(1.54, 0.23, n=533), injection=inj), "DA")
        self.assertIn("no key recovery at 533 attack traces per key (template): GE 1.54", t)
        self.assertIn("null 1.50 +- 0.08", t)
        self.assertIn("from 0.5 x N's strength (GE 0.95), not at 0.35 x (GE 1.41)", t)

    def test_partial_recovery(self):
        """GE below every null draw but SR < 0.9: 'partly recovered', not 'no key recovery'."""
        t = ct.key_recovery_text(self.kr("DA_tvla", self.res(0.27, 0.78, n=533)), "DA")
        self.assertTrue(t.startswith("key partly recovered at 533 attack traces per key (template): GE 0.27"), t)


if __name__ == "__main__":
    unittest.main()
