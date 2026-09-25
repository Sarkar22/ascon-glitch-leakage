# SPDX-License-Identifier: Apache-2.0
"""Exact probing checks: expected verdicts per variant."""
import unittest

import _common
from _common import variant_dir


@unittest.skipUnless(_common.pdk_available(), "sky130A PDK not found (set PDK)")
class TestProbing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from probing import check
        cls.res = {v: {r["net"]: r for r in check(variant_dir(v))} for v in _common.VARIANTS}

    def fails(self, v, key):
        return {n for n, r in self.res[v].items() if not r[key]}

    def test_unmasked_fails_value_model(self):
        """Sanity: the check does detect dependence on x."""
        self.assertIn("x_0_q", self.fails("U", "value_ok"))
        self.assertIn("y_0_d", self.fails("U", "value_ok"))

    def test_value_model_passes_masked(self):
        for v in ("N", "D", "DA"):
            self.assertEqual(self.fails(v, "value_ok"), set(), v)

    def test_naive_fails_glitch_model_at_integration(self):
        bad = self.fails("N", "glitch_ok")
        for i in range(5):
            self.assertIn("ts0_%d" % i, bad)
            self.assertIn("ts1_%d" % i, bad)
        self.assertEqual(len(bad), 39)

    def test_barrier_leaves_only_dependent_and_inputs(self):
        """D: only the cross-domain terms of the ANDs whose inputs share a variable (t1, t3, t4)."""
        want = {"%s_%d" % (t, i) for t in ("m01", "p01", "m10", "p10") for i in (1, 3, 4)}
        self.assertEqual(self.fails("D", "glitch_ok"), want)

    def test_affine_first_passes_both(self):
        self.assertEqual(self.fails("DA", "glitch_ok"), set())


if __name__ == "__main__":
    unittest.main()
