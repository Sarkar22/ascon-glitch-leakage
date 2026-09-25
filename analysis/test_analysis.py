# SPDX-License-Identifier: Apache-2.0
"""Unit tests of the kill-test analysis helpers (host python3 + numpy; no SPICE runs needed).

  python3 -m unittest discover -s analysis -p 'test_*.py'
"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import kill_test as kt      # noqa: E402
import spice_nodes as sn    # noqa: E402


class TestCrossings(unittest.TestCase):
    def test_glitch_pulse(self):
        t = np.arange(0, 1.0, 0.01)
        v = np.where((t > 0.2) & (t < 0.3), 1.8, 0.0)       # one pulse: rise then fall
        tc, d = sn.crossings(t, v, 0.9)
        self.assertEqual(d.tolist(), [1, 0])
        self.assertTrue(0.2 <= tc[0] <= 0.21 and 0.29 <= tc[1] <= 0.3)

    def test_no_crossing(self):
        tc, d = sn.crossings(np.arange(5.0), np.full(5, 1.8), 0.9)
        self.assertEqual(len(tc), 0)


class TestCurveStats(unittest.TestCase):
    def test_first_and_stable(self):
        r = {"n": np.array([10, 20, 30, 40, 50]), "max_abs_t": np.array([5.0, 3.0, 5.0, 6.0, 7.0])}
        self.assertEqual(kt.curve_stats(r), (10, 30))

    def test_never(self):
        r = {"n": np.array([10, 20]), "max_abs_t": np.array([1.0, 2.0])}
        self.assertEqual(kt.curve_stats(r), (None, None))


class TestRegions(unittest.TestCase):
    def test_latency2_regions(self):
        dt, pre, T = 0.01, 0.2, 4.0
        t = np.zeros(800)
        t[int((0.5 + pre) / dt)] = 7.0              # first cycle, evaluation
        t[int((T + 3.0 + pre) / dt)] = -9.0         # second cycle, input edges
        r = kt.region_max(t, dt, pre, T, 2)
        self.assertEqual(r["cycle1_edge_and_evaluation"], 7.0)
        self.assertEqual(r["cycle2_input_edges"], 9.0)
        self.assertEqual(r["cycle1_clock_fall"], 0.0)


class TestWaveformLag(unittest.TestCase):
    def test_recovers_shift(self):
        rng = np.random.default_rng(1)
        n, ns = 400, 400
        base = np.zeros((n, ns))
        amp = rng.normal(size=n)
        for k in range(n):
            base[k, 100:160] = amp[k] * np.hanning(60)     # data-dependent bump
        late = np.roll(base, 20, axis=1)                  # "level 2" 200 ps later
        lag, cc, c0 = kt.waveform_lag(base, late, 0.01)
        self.assertEqual(lag, 200)
        self.assertGreater(cc, 0.99)
        self.assertLess(c0, cc)


class TestPerNetTvla(unittest.TestCase):
    def test_planted_net_leak(self):
        rng = np.random.default_rng(2)
        n = 2000
        labels = rng.integers(0, 2, n)
        # net 1 switches in bin 3 only in class 0; net 0 switches at random in bin 5
        rows, nets, times = [], [], []
        for r in range(n):
            if labels[r] == 0 and rng.random() < 0.5:
                rows.append(r), nets.append(1), times.append(0.07)
            if rng.random() < 0.5:
                rows.append(r), nets.append(0), times.append(0.11)
        rows, nets, times = np.array(rows), np.array(nets), np.array(times)

        def row_events(a, b):
            m = (rows >= a) & (rows < b)
            return rows[m] - a, nets[m], times[m]
        t, act = kt.per_net_tvla(row_events, labels, n, 2, 10, 0.02)
        self.assertGreater(abs(t[1, 3]), 20)
        self.assertLess(abs(t[0, 5]), 4.5)
        self.assertAlmostEqual(act[0, 5], 0.5, delta=0.05)


class TestModelRowsAlignment(unittest.TestCase):
    def test_rows_match_spice_rows(self):
        """model_rows returns rows skip..n_sim-1 of the stimulus (same rows as a SPICE run)."""
        dut = os.path.join(kt.REPO, "build", "U")
        if not os.path.exists(os.path.join(dut, "graph.json")):
            self.skipTest("build/U missing (run gen/make_variants.py)")
        man = {"params": {"warmup": 4, "seed": 0, "period": 4.0, "pre": 0.2, "t_in": 0.75, "dt": 0.01}}
        rng = np.random.default_rng(3)
        stim = rng.integers(0, 2, (50, 5)).astype(np.uint8)
        a = kt.model_rows("U", stim, 50, 1, man)["weighted"]
        b = kt.model_rows("U", stim, 40, 1, man)["weighted"]
        self.assertEqual(len(a), 48)
        self.assertEqual(len(b), 38)
        np.testing.assert_array_equal(a[:38], b)       # same rows, independent of the run length


if __name__ == "__main__":
    unittest.main()
