# SPDX-License-Identifier: Apache-2.0
"""The bitsliced S-box against the published table and the author's model/RTL."""
import os
import unittest

import _common  # noqa: F401  (import paths)
import ascon_sbox as S


class TestSbox(unittest.TestCase):
    def test_published_table(self):
        self.assertEqual(S.SBOX, S.SBOX_PUBLISHED)

    def test_bijective(self):
        self.assertEqual(sorted(S.SBOX), list(range(32)))

    def test_packed_words_match(self):
        words = S.sbox_words(*S._column_state(), ones=(1 << 32) - 1)
        self.assertEqual(S._decode_columns(words), S.SBOX)

    def test_numpy_bits(self):
        import numpy as np
        x = np.arange(32, dtype=np.uint8)
        y = S.from_bits(list(S.sbox_words(*S.to_bits(x), ones=1)))
        self.assertTrue((y == S.SBOX_NP).all())

    @unittest.skipUnless(os.environ.get("ASCON_REF_DIR"), "set ASCON_REF_DIR to the zero-shadow-aead checkout")
    def test_reference_model_and_rtl(self):
        ref = os.environ["ASCON_REF_DIR"]
        self.assertEqual(S.table_from_reference_model(os.path.join(ref, "model", "ascon.py")), S.SBOX)
        self.assertEqual(S.table_from_rtl(os.path.join(ref, "rtl", "ascon_xof.sv")), S.SBOX)


if __name__ == "__main__":
    unittest.main()
