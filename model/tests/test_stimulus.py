# SPDX-License-Identifier: Apache-2.0
"""Stimulus modes: encoding, fixed/random classes, masks off, CPA context, determinism."""
import unittest

import numpy as np

import _common  # noqa: F401
from stimulus import make_stimulus

BITS = [{"name": "%s_%d" % (n, i), "role": role, "bit": i}
        for n, role in (("xs0", "share0"), ("xs1", "share1"), ("r", "rand")) for i in range(5)]
MASKED = {"variant": "N", "inputs": BITS}
PLAIN = {"variant": "U", "inputs": [{"name": "x_%d" % i, "role": "plain", "bit": i} for i in range(5)]}


def value(stim, cols):
    v = np.zeros(len(stim), dtype=np.uint8)
    for k, c in enumerate(cols):
        v |= stim[:, c] << (4 - k)
    return v


class TestStimulus(unittest.TestCase):
    def test_tvla_masked(self):
        s, m = make_stimulus(MASKED, "tvla", 4000, 1)
        self.assertEqual(s.shape, (4000, 15))
        self.assertEqual(s.dtype, np.uint8)
        self.assertTrue(set(np.unique(s)) <= {0, 1})
        x0, x1, r = value(s, range(5)), value(s, range(5, 10)), value(s, range(10, 15))
        self.assertTrue((x0 ^ x1 == m["x"]).all())
        self.assertTrue((x1 == m["mask"]).all() and (r == m["r"]).all())
        self.assertTrue((m["x"][m["label"] == 0] == 0x0B).all())
        self.assertGreater(len(np.unique(m["x"][m["label"] == 1])), 30)
        self.assertLess(abs(m["label"].mean() - 0.5), 0.03)
        # fresh uniform masks and r in both classes
        for c in (0, 1):
            self.assertEqual(len(np.unique(m["mask"][m["label"] == c])), 32)
            self.assertEqual(len(np.unique(m["r"][m["label"] == c])), 32)

    def test_masks_off(self):
        s, m = make_stimulus(MASKED, "masks_off", 1000, 2)
        self.assertTrue((s[:, 5:] == 0).all())                  # share 1 and r are zero
        self.assertTrue((value(s, range(5)) == m["x"]).all())  # share 0 carries x
        self.assertTrue((m["x"][m["label"] == 0] == 0x0B).all())

    def test_rvr(self):
        s, m = make_stimulus(MASKED, "rvr", 2000, 3)
        for c in (0, 1):
            self.assertGreater(len(np.unique(m["x"][m["label"] == c])), 30)

    def test_cpa(self):
        s, m = make_stimulus(PLAIN, "cpa", 500, 4, iv=1, key=2)
        x = value(s, range(5))
        self.assertTrue((x == m["x"]).all())
        self.assertTrue((x >> 4 == 1).all() and ((x >> 2) & 3 == 2).all())
        self.assertTrue((x & 3 == m["nonce"]).all())
        self.assertEqual(len(np.unique(m["nonce"])), 4)
        _, m2 = make_stimulus(PLAIN, "cpa", 10, 4)
        self.assertIn(m2["key"], range(4))                     # key drawn from the seed

    def test_plain_ignores_masks(self):
        s, m = make_stimulus(PLAIN, "tvla", 100, 5)
        self.assertTrue((value(s, range(5)) == m["x"]).all())
        self.assertTrue((m["mask"] == 0).all() and (m["r"] == 0).all())

    def test_deterministic(self):
        a, _ = make_stimulus(MASKED, "tvla", 100, 7)
        b, _ = make_stimulus(MASKED, "tvla", 100, 7)
        c, _ = make_stimulus(MASKED, "tvla", 100, 8)
        self.assertTrue(np.array_equal(a, b))
        self.assertFalse(np.array_equal(a, c))

    def test_exhaustive(self):
        s, m = make_stimulus(MASKED, "exhaustive")
        self.assertEqual(len({(a, b, c) for a, b, c in zip(m["x"], m["mask"], m["r"])}), 32768)


if __name__ == "__main__":
    unittest.main()
