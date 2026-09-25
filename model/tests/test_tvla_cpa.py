# SPDX-License-Identifier: Apache-2.0
"""TVLA and CPA on synthetic traces: planted leaks are found, pure noise is not."""
import unittest

import numpy as np

import _common  # noqa: F401
from tvla import WelchT, tvla_curve, log_checkpoints, THRESHOLD
from cpa import CPA, cpa_curve, hw_sbox_hypotheses, guess_correlation


class TestTvla(unittest.TestCase):
    N = 50000
    M = 100

    def setUp(self):
        rng = np.random.default_rng(2026)
        self.labels = rng.integers(0, 2, self.N)
        self.noise = rng.standard_normal((self.N, self.M))

    def test_pure_noise_below_threshold(self):
        r = tvla_curve(self.noise, self.labels, log_checkpoints(self.N))
        worst = r["max_abs_t"].max()
        print("\n  pure noise, %d traces x %d samples: max|t| = %.3f (final %.3f)"
              % (self.N, self.M, worst, r["max_abs_t"][-1]))
        self.assertLess(worst, THRESHOLD)
        r2 = tvla_curve(self.noise, self.labels, [self.N], order=2)
        print("  pure noise, second order: max|t| = %.3f" % r2["max_abs_t"][-1])
        self.assertLess(r2["max_abs_t"][-1], THRESHOLD)

    def test_planted_mean_leak(self):
        tr = self.noise.copy()
        tr[self.labels == 0, 37] += 0.1                    # 0.1 sigma mean difference
        r = tvla_curve(tr, self.labels, log_checkpoints(self.N))
        print("\n  planted 0.1-sigma leak: max|t| = %.2f at sample %d" % (r["max_abs_t"][-1], r["argmax"][-1]))
        self.assertEqual(r["argmax"][-1], 37)
        self.assertGreater(r["max_abs_t"][-1], THRESHOLD)
        others = np.delete(np.abs(r["t_final"]), 37)
        self.assertLess(others.max(), THRESHOLD)
        first = r["n"][np.argmax(r["max_abs_t"] > THRESHOLD)]
        print("  first detected at %d traces" % first)

    def test_second_order_leak(self):
        tr = self.noise.copy()
        tr[self.labels == 0, 12] *= 1.3                    # variance differs, means equal
        t1 = np.abs(tvla_curve(tr, self.labels, [self.N])["t_final"])
        t2 = np.abs(tvla_curve(tr, self.labels, [self.N], order=2)["t_final"])
        print("\n  planted variance leak: first order |t| = %.2f, second order |t| = %.2f" % (t1[12], t2[12]))
        self.assertLess(t1[12], THRESHOLD)
        self.assertGreater(t2[12], THRESHOLD)
        self.assertEqual(int(np.argmax(t2)), 12)

    def test_online_equals_batch(self):
        tr = 1e6 + 3.0 * self.noise[:20000, :10]            # large offset: no cancellation
        tr[:, 3] += 5 * self.labels[:20000]
        lab = self.labels[:20000]
        w = WelchT(10)
        for s in range(0, 20000, 777):
            w.update(tr[s:s + 777], lab[s:s + 777])
        a, b = tr[lab == 0], tr[lab == 1]
        t_ref = (a.mean(0) - b.mean(0)) / np.sqrt(a.var(0, ddof=1) / len(a) + b.var(0, ddof=1) / len(b))
        self.assertTrue(np.allclose(w.t(1), t_ref, rtol=1e-8, atol=1e-6))
        ca, cb = (a - a.mean(0)) ** 2, (b - b.mean(0)) ** 2
        t2_ref = (ca.mean(0) - cb.mean(0)) / np.sqrt(ca.var(0) / len(a) + cb.var(0) / len(b))
        self.assertTrue(np.allclose(w.t(2), t2_ref, rtol=1e-6, atol=1e-6))

    def test_zero_variance(self):
        w = WelchT(2)
        tr = np.array([[1.0, 1.0], [1.0, 2.0], [1.0, 1.0], [1.0, 2.0]])
        w.update(tr, np.array([0, 1, 0, 1]))
        t = w.t(1)
        self.assertEqual(t[0], 0.0)
        self.assertTrue(np.isinf(t[1]))


class TestCpa(unittest.TestCase):
    def test_recovers_key(self):
        rng = np.random.default_rng(5)
        n, key, iv = 3000, 2, 1
        nonce = rng.integers(0, 4, n)
        h = hw_sbox_hypotheses(iv, nonce)
        tr = rng.standard_normal((n, 20)) * 2.0
        tr[:, 5] += h[:, key]
        r = cpa_curve(tr, h, key, log_checkpoints(n, 50))
        print("\n  CPA synthetic (noise sigma 2): rank %d at %d traces, rank-1 from %d traces"
              % (r["rank"][-1], n, r["n"][np.argmax(np.minimum.accumulate(r["rank"][::-1])[::-1] == 1)]))
        self.assertEqual(r["rank"][-1], 1)

    def test_signed_scoring_separates_anticorrelated_guess(self):
        """iv=1: guesses 0 and 1 have rho = -0.93; the signed score keeps them apart."""
        rng = np.random.default_rng(7)
        nonce = rng.integers(0, 4, 400)
        h = hw_sbox_hypotheses(1, nonce)
        tr = h[:, 1:2] + 1.5 * rng.standard_normal((400, 1))
        rho = cpa_curve(tr, h, 1, [400])["rho_final"][:, 0]
        self.assertLess(rho[0], -0.2)                    # strongly anti-correlated wrong guess
        self.assertEqual(cpa_curve(tr, h, 1, [400], signed=True)["rank"][-1], 1)

    def test_online_equals_corrcoef(self):
        rng = np.random.default_rng(6)
        tr = 1e5 + rng.standard_normal((1000, 7))
        h = rng.integers(0, 6, (1000, 4)).astype(float)
        c = CPA(7, 4)
        for s in range(0, 1000, 333):
            c.update(tr[s:s + 333], h[s:s + 333])
        ref = np.corrcoef(np.hstack([h, tr]).T)[:4, 4:]
        self.assertTrue(np.allclose(c.corr(), ref, atol=1e-9))

    def test_guesses_distinguishable(self):
        for iv in (0, 1):
            c = np.abs(guess_correlation(iv) - np.eye(4))
            self.assertLess(c.max(), 0.95)


if __name__ == "__main__":
    unittest.main()
