# SPDX-License-Identifier: Apache-2.0
"""Ascon 5-bit S-box, bitsliced exactly as written in docs/KILL_TEST.md.

Bit order: x = x0<<4 | x1<<3 | x2<<2 | x3<<1 | x4 (x0 is the MSB).

    x0 ^= x4;  x4 ^= x3;  x2 ^= x1;
    t_i = ~x_i & x_{i+1}          (i = 0..4, indices mod 5)
    x_i ^= t_{i+1}                (i = 0..4)
    x1 ^= x0;  x0 ^= x4;  x3 ^= x2;  x2 = ~x2;

`sbox_words` works on Python ints (single bits or bit-packed words) and on numpy
arrays of 0/1, so the same code builds the 32-entry table and evaluates columns.

Cross-checks (run `python3 model/ascon_sbox.py`):
  * the published Ascon S-box table (Dobraunig et al., Ascon v1.2, Table 2);
  * the author's Ascon model (model/ascon.py of the zero-shadow-aead repository,
    which passes the official KATs): its permutation is run for one round with a zero
    round constant and the linear layer disabled, on a state whose 32 columns are the
    32 possible S-box inputs;
  * the S-box statements of the RTL (rtl/ascon_xof.sv, function ascon_round), which
    are extracted from the source text and executed on the same column-packed state.
The reference repository is located with the environment variable ASCON_REF_DIR;
without it those two checks are skipped (and say so).
"""
import importlib.util
import os
import re
import sys

import numpy as np


def sbox_words(x0, x1, x2, x3, x4, ones=1):
    """Bitsliced S-box on five words; `ones` is the all-ones word used for NOT."""
    x0 ^= x4
    x4 ^= x3
    x2 ^= x1
    x = [x0, x1, x2, x3, x4]
    t = [(x[i] ^ ones) & x[(i + 1) % 5] for i in range(5)]
    x = [x[i] ^ t[(i + 1) % 5] for i in range(5)]
    x0, x1, x2, x3, x4 = x
    x1 ^= x0
    x0 ^= x4
    x3 ^= x2
    x2 ^= ones
    return x0, x1, x2, x3, x4


def to_bits(x):
    """5-bit value (int or numpy array) -> list [x0, ..., x4], x0 = MSB."""
    return [(x >> (4 - i)) & 1 for i in range(5)]


def from_bits(bits):
    """[x0, ..., x4] (ints or arrays) -> 5-bit value, x0 = MSB."""
    v = 0
    for i, b in enumerate(bits):
        v = v | (b << (4 - i))
    return v


def sbox(x):
    """S-box of one 5-bit int."""
    return from_bits(sbox_words(*to_bits(x)))


SBOX = tuple(sbox(x) for x in range(32))
SBOX_NP = np.array(SBOX, dtype=np.uint8)

# Published table (Ascon v1.2 submission, Table 2), used as an independent check.
SBOX_PUBLISHED = (0x04, 0x0B, 0x1F, 0x14, 0x1A, 0x15, 0x09, 0x02,
                  0x1B, 0x05, 0x08, 0x12, 0x1D, 0x03, 0x06, 0x1C,
                  0x1E, 0x13, 0x07, 0x0E, 0x00, 0x0D, 0x11, 0x18,
                  0x10, 0x0C, 0x01, 0x19, 0x16, 0x0A, 0x0F, 0x17)


def hw(v):
    """Hamming weight of 5-bit values (int or numpy array)."""
    return sum((v >> i) & 1 for i in range(5))


# ------------------------------------------------------------ cross-checks ---
def _column_state(nbits=32):
    """Five words whose column j (bit j of every word) is the S-box input j."""
    words = [0] * 5
    for j in range(nbits):
        for i, b in enumerate(to_bits(j)):
            words[i] |= b << j
    return words


def _decode_columns(words, nbits=32):
    return tuple(from_bits([(w >> j) & 1 for w in words]) for j in range(nbits))


def table_from_reference_model(path):
    """S-box table derived from the permutation in the author's Python model."""
    spec = importlib.util.spec_from_file_location("ascon_ref_model", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ror = lambda x, n: 0          # pL becomes x_i ^= 0 ^ 0: the identity
    out = mod.permutation(_column_state(), rc=[0])   # pC with constant 0: no-op
    return _decode_columns(out)


def table_from_rtl(path):
    """S-box table from the pS statements of function ascon_round in the RTL."""
    with open(path) as f:
        src = f.read()
    body = re.search(r"function\s+automatic\s+logic\s*\[319:0\]\s*ascon_round(.*?)endfunction",
                     src, re.S)
    if body is None:
        raise ValueError("ascon_round not found in " + path)
    text = re.sub(r"//[^\n]*", "", body.group(1))
    stmt_re = re.compile(r"^\s*([xt][0-4])\s*=\s*([xt0-4\s\^&~()]+)$")
    env = dict(zip(["x0", "x1", "x2", "x3", "x4"], _column_state()))
    n_used = 0
    for stmt in text.split(";"):
        m = stmt_re.match(stmt.strip())
        if m:                          # skips slicing, the pC and the pL statements
            env[m.group(1)] = eval(m.group(2), {}, env)
            n_used += 1
    if n_used != 12:
        raise ValueError("expected 12 S-box statements in the RTL, found %d" % n_used)
    mask = (1 << 32) - 1
    return _decode_columns([env["t%d" % i] & mask for i in range(5)])


def crosscheck(ref_dir=None, verbose=True):
    """Return a dict of check name -> bool (None when the source is unavailable)."""
    ref_dir = ref_dir or os.environ.get("ASCON_REF_DIR")
    res = {"bitsliced == published table": SBOX == SBOX_PUBLISHED,
           "bitsliced on packed columns == per-value":
               _decode_columns(sbox_words(*_column_state(), ones=(1 << 32) - 1)) == SBOX}
    model = os.path.join(ref_dir, "model", "ascon.py") if ref_dir else None
    rtl = os.path.join(ref_dir, "rtl", "ascon_xof.sv") if ref_dir else None
    res["bitsliced == author's Python model"] = (
        table_from_reference_model(model) == SBOX if model and os.path.exists(model) else None)
    res["bitsliced == author's RTL formulas"] = (
        table_from_rtl(rtl) == SBOX if rtl and os.path.exists(rtl) else None)
    if verbose:
        for k, v in res.items():
            print("%-45s %s" % (k, {True: "PASS", False: "FAIL", None: "SKIPPED (set ASCON_REF_DIR)"}[v]))
    return res


if __name__ == "__main__":
    print("SBOX = [" + ", ".join("0x%02x" % v for v in SBOX) + "]")
    r = crosscheck()
    sys.exit(0 if all(v is not False for v in r.values()) else 1)
