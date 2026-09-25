# SPDX-License-Identifier: Apache-2.0
"""Shared test setup: import paths and one fresh build of all variants per test run.

The variants are generated into a temporary directory (not build/), so the tests check
the generator as it is now. Tests that need the PDK are skipped when it is not found.
"""
import atexit
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "model"), os.path.join(ROOT, "gen")):
    if p not in sys.path:
        sys.path.insert(0, p)

VARIANTS = ("U", "N", "D", "DA")
_BUILD = None


def pdk_available():
    try:
        import pdk
        pdk.pdk_root()
        return True
    except (FileNotFoundError, ImportError):
        return False


def build_dir():
    """Directory holding <V>/{dut.v,dut.sp,ports.json,graph.json}, generated once."""
    global _BUILD
    if _BUILD is None:
        import make_variants
        _BUILD = tempfile.mkdtemp(prefix="sbox_variants_")
        atexit.register(shutil.rmtree, _BUILD, True)
        make_variants.main(list(VARIANTS), _BUILD, verbose=False)
    return _BUILD


def variant_dir(v):
    return os.path.join(build_dir(), v)
