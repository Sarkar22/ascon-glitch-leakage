# SPDX-License-Identifier: Apache-2.0
"""Unit tests of the profiled key recovery (analysis/key_recovery.py) on synthetic traces.

  python3 -m unittest discover -s analysis -p 'test_*.py'
"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import key_recovery as kr   # noqa: E402


def synthetic(n_rows, n_samples=40, leak=1.0, seed=0):
    """Rows with uniform x and trace = leak * template[x] + N(0, 1)."""
    rng = np.random.default_rng(seed)
    tmpl = rng.normal(size=(32, n_samples))
    x = rng.integers(0, 32, n_rows)
    tr = leak * tmpl[x] + rng.normal(size=(n_rows, n_samples))
    return tr, x


class TestInputs(unittest.TestCase):
    def test_guesses_partition_the_inputs(self):
        nonce = np.arange(4)
        for iv in (0, 1):
            sets = [set(kr.guess_inputs(iv, g, nonce).tolist()) for g in range(4)]
            self.assertEqual(sum(len(s) for s in sets), 16)
            self.assertEqual(set().union(*sets), set(range(iv * 16, iv * 16 + 16)))
            for g, s in enumerate(sets):
                self.assertTrue(all(kr.scenario_of(v) == (iv << 2) | g for v in s))


class TestSplit(unittest.TestCase):
    def test_disjoint_guarded_and_seeded(self):
        rows = np.arange(3, 5000)
        p, a = kr.block_split(rows, seed=7, block=50, guard=3)
        self.assertFalse((p & a).any())
        self.assertFalse(((rows % 50 >= 47) & (p | a)).any())      # guard rows unused
        pr, ar = rows[p], rows[a]
        # every profiling row is more than `guard` rows away from every attack row
        d = np.abs(pr[:, None] - ar[None, :]).min()
        self.assertGreater(d, 3)
        p2, a2 = kr.block_split(rows, seed=7, block=50, guard=3)
        self.assertTrue((p == p2).all() and (a == a2).all())
        p3, _ = kr.block_split(rows, seed=8, block=50, guard=3)
        self.assertFalse((p == p3).all())
        self.assertTrue(0.3 < p.mean() < 0.65)


class TestProfile(unittest.TestCase):
    def test_matches_direct_computation(self):
        tr, x = synthetic(600, 5, leak=0.5)
        p = kr.profile(tr, x)
        means = np.array([tr[x == c].mean(0) for c in range(32)])
        within = sum(((tr[x == c] - means[c]) ** 2).sum(0) for c in range(32)) / (600 - 32)
        n = np.bincount(x, minlength=32)
        between = (n[:, None] * (means - tr.mean(0)) ** 2).sum(0) / 31
        np.testing.assert_allclose(p["means"], means)
        np.testing.assert_allclose(p["var"], within)
        np.testing.assert_allclose(p["F"], between / within)

    def test_missing_class_rejected(self):
        with self.assertRaises(ValueError):
            kr.profile(np.zeros((10, 3)), np.arange(10))

    def test_pois_spacing(self):
        score = np.array([0, 9, 8, 7, 0, 0, 6, 0, 0, 5.0])
        self.assertEqual(kr.select_pois(score, 3, spacing=3).tolist(), [1, 6, 9])
        self.assertEqual(kr.select_pois(score, 2, spacing=1).tolist(), [1, 2])
        self.assertEqual(kr.select_pois(score, 1, spacing=3, chosen=[1]).tolist(), [6])


class TestPerBitPois(unittest.TestCase):
    def test_interaction_leak_found(self):
        """Sample 3 carries a large main effect of x1 (bit 3); sample 20 carries x2 only through
        x2 XOR x3, i.e. no main effect of x2. F picks sample 3; the x2 contrast finds 20."""
        rng = np.random.default_rng(11)
        n = 6400
        x = rng.integers(0, 32, n)
        tr = rng.normal(size=(n, 30))
        tr[:, 3] += 2.0 * ((x >> 3) & 1)
        tr[:, 20] += 0.6 * (((x >> 2) ^ (x >> 1)) & 1)
        p = kr.profile(tr, x)
        self.assertEqual(int(np.argmax(p["F"])), 3)
        c2 = kr.key_bit_chi2(p, kr.KEY_BITS["x2"])
        self.assertEqual(int(np.argmax(c2)), 20)
        self.assertLess(abs(float(np.median(c2)) - 15.3), 4.0)     # chi2(16) median without effect
        main_x2 = tr[(x >> 2) & 1 == 1, 20].mean() - tr[(x >> 2) & 1 == 0, 20].mean()
        self.assertLess(abs(main_x2), 0.1)                        # no main effect of x2
        # x1's contrast peaks at sample 3 too, so it adds no POI: [top F, top x2 contrast]
        self.assertEqual(kr.per_bit_pois(p).tolist(), [3, 20])

    def test_chi2_matches_direct(self):
        tr, x = synthetic(900, 4, leak=0.4, seed=4)
        p = kr.profile(tr, x)
        want = np.zeros(4)
        for c in range(32):
            if not (c >> 2) & 1:
                d = p["means"][c | 4] - p["means"][c]
                want += d * d / (p["var"] * (1 / p["counts"][c | 4] + 1 / p["counts"][c]))
        np.testing.assert_allclose(kr.key_bit_chi2(p, 2), want)


class TestNullAndInjection(unittest.TestCase):
    def fake(self, final_ges):
        return [{d: {"ge": [1.5, g], "final_sr": 0.25, "n": [1, 10]} for d in kr.DISTS} for g in final_ges]

    def test_null_summary_p_value(self):
        draws = self.fake([1.2, 1.4, 1.5, 1.6])
        real = {d: {"final_ge": 1.3} for d in kr.DISTS}
        nl = kr.null_summary(draws, real)
        self.assertEqual(nl["tmpl"]["draws"], 4)
        self.assertAlmostEqual(nl["tmpl"]["p_vs_null"], 2 / 5)          # (1 + one draw <= 1.3) / 5
        self.assertAlmostEqual(nl["tmpl"]["final_ge_mean"], 1.425)
        self.assertEqual(nl["tmpl"]["final_ge_min"], 1.2)
        real = {d: {"final_ge": 0.1} for d in kr.DISTS}
        self.assertAlmostEqual(kr.null_summary(draws, real)["corr"]["p_vs_null"], 1 / 5)

    def test_inject_adds_scaled_pattern(self):
        tr, x = synthetic(2000, 6, leak=0.0, seed=8)
        pattern = np.linspace(-1, 1, 32)
        out = kr.inject(tr, x, 4, pattern, 0.5)
        sd = np.sqrt(kr.profile(tr, x)["var"][4])
        np.testing.assert_allclose(out[:, 4] - tr[:, 4], 0.5 * pattern[x] * sd)
        np.testing.assert_array_equal(np.delete(out, 4, 1), np.delete(tr, 4, 1))
        src = {"traces": tr.copy(), "x": x}
        src["traces"][:, 2] += 3.0 * pattern[x]
        s, pat = kr.injection_pattern(src)
        self.assertEqual(s, 2)
        self.assertAlmostEqual(float(pat.mean()), 0.0, places=12)
        self.assertGreater(np.corrcoef(pat, pattern)[0, 1], 0.99)


class TestKeyRank(unittest.TestCase):
    def test_ranks_and_ties(self):
        r, s = kr.key_rank(np.array([0.1, 0.5, 0.2, 0.3]), 1)
        self.assertEqual((float(r), float(s)), (0.0, 1.0))
        r, s = kr.key_rank(np.array([0.1, 0.5, 0.2, 0.3]), 0)
        self.assertEqual((float(r), float(s)), (3.0, 0.0))
        r, s = kr.key_rank(np.zeros(4), 2)                 # all tied: random guessing
        self.assertEqual((float(r), float(s)), (1.5, 0.25))
        r, s = kr.key_rank(np.array([[1.0, 2.0], [1.0, 0.0], [0.0, 0.0], [0.0, 0.0]]), 0)
        self.assertEqual(r.tolist(), [0.5, 0.0])
        self.assertEqual(s.tolist(), [0.5, 1.0])

    def test_top_bit_success(self):
        # key 2 = x1 1, x2 0; top guess 3 = x1 1, x2 1: bit x1 right, bit x2 wrong
        b1, b2 = kr.top_bit_success(np.array([0.1, 0.2, 0.3, 0.9]), 2)
        self.assertEqual((float(b1), float(b2)), (1.0, 0.0))
        b1, b2 = kr.top_bit_success(np.zeros(4), 2)       # all tied
        self.assertEqual((float(b1), float(b2)), (0.5, 0.5))
        b1, b2 = kr.top_bit_success(np.array([0.9, 0.2, 0.9, 0.0]), 0)   # tie of 0 and 2
        self.assertEqual((float(b1), float(b2)), (0.5, 1.0))


class TestAttack(unittest.TestCase):
    def attack_all(self, leak, seed=1, n_prof=3200, n_att=1600, trials=20):
        tr, x = synthetic(n_prof + n_att, leak=leak, seed=seed)
        p = kr.profile(tr[:n_prof], x[:n_prof])
        tm = kr.Templates(tr[:n_prof], x[:n_prof], k_corr=10, k_tmpl=5, spacing=1, prof=p)
        tb = kr.Templates(tr[:n_prof], x[:n_prof], prof=p, pois=kr.per_bit_pois(p))
        rng = np.random.default_rng(seed)
        ranks = {d: [] for d in kr.DISTS}
        for iv, key in kr.SCENARIOS:
            sel = np.flatnonzero(kr.scenario_of(x[n_prof:]) == (iv << 2) | key) + n_prof
            r = kr.attack(tm, tr[sel], x[sel], iv, key, [1, 2, 10, 40], trials, rng, extra={"tmpl_bits": tb})
            for d in ranks:
                ranks[d].append(r[d][0].mean(0))
        return {d: np.mean(v, axis=0) for d, v in ranks.items()}

    def test_recovers_key_when_it_leaks(self):
        ge = self.attack_all(leak=1.0)
        for d in kr.DISTS:
            self.assertLess(ge[d][-1], 0.05, d)
        self.assertEqual(ge["corr"][0], 1.5)               # one trace: correlation undefined, tie

    def test_random_without_leak(self):
        ge = [self.attack_all(leak=0.0, seed=s) for s in range(4)]
        for d in kr.DISTS:
            m = np.mean([g[d][-1] for g in ge])
            self.assertTrue(1.1 < m < 1.9, (d, m))

    def test_rows_must_match_scenario(self):
        tr, x = synthetic(800)
        tm = kr.Templates(tr, x, k_corr=5, k_tmpl=3, spacing=1)
        with self.assertRaises(ValueError):
            kr.attack(tm, tr[:10], x[:10], 0, 0, [5], 2, np.random.default_rng(0))


class TestModelSelection(unittest.TestCase):
    def test_heldout_info_and_choice(self):
        rng = np.random.default_rng(5)
        n = 3000
        x = rng.integers(0, 32, n)
        tr = rng.normal(size=(n, 30))
        tr[:, 7] += 0.8 * rng.normal(size=32)[x]          # a one-dimensional leak
        k, scores = kr.choose_k_tmpl(tr, x, np.arange(n), np.zeros(n, dtype=int), "t")
        self.assertIn(k, (1, 2))
        self.assertGreater(scores[k], 0.05)
        self.assertGreater(scores[1], scores[8])           # extra POIs only add estimation noise
        tm = kr.Templates(tr[:1500], x[:1500], k_tmpl=1)
        self.assertEqual(tm.poi_tmpl.tolist(), [7])
        self.assertGreater(kr.heldout_info(tm, tr[1500:], x[1500:]), 0.05)
        flat = rng.normal(size=(n, 30))
        tm0 = kr.Templates(flat[:1500], x[:1500], k_tmpl=2)
        self.assertLess(kr.heldout_info(tm0, flat[1500:], x[1500:]), 0.02)


class TestSplitExperiment(unittest.TestCase):
    def dataset(self, leak):
        tr, x = synthetic(4000, leak=leak, seed=3)
        return {"name": "syn", "traces": tr, "x": x, "row": np.arange(4000),
                "src": np.zeros(4000, dtype=int)}

    def test_leak_control_and_noise(self):
        ds = self.dataset(0.6)
        res, info = kr.run_split_dataset(ds, 1, 0.0, None, splits=2, trials=10, noise_unit=1.0)
        self.assertLess(res["tmpl"]["final_ge"], 0.1)
        self.assertLess(info["rows_profiling_mean"] + info["rows_attack_mean"], 4000 * 0.95)
        ctl, _ = kr.run_split_dataset(ds, 1, 0.0, 0, splits=3, trials=10, noise_unit=1.0)
        for d in kr.DISTS:
            self.assertTrue(0.9 < ctl[d]["final_ge"] < 2.1, (d, ctl[d]["final_ge"]))
        noisy, _ = kr.run_split_dataset(ds, 1, 5.0, None, splits=2, trials=10, noise_unit=1.0)
        self.assertGreater(noisy["tmpl"]["ge"][3], res["tmpl"]["ge"][3])   # noise makes it harder

    def test_second_order_transform(self):
        tr = np.array([[1.0, 2.0], [3.0, 6.0], [5.0, 0.0]])
        prof = np.array([True, True, False])
        np.testing.assert_allclose(kr.transform(tr, prof, 2), [[1, 4], [1, 4], [9, 16]])
        self.assertIs(kr.transform(tr, prof, 1), tr)


if __name__ == "__main__":
    unittest.main()
