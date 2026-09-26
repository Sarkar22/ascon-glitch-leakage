# SPDX-License-Identifier: Apache-2.0
"""Unit tests of tools/make_submission.py (stdlib unittest; numpy only, no matplotlib: the
traced selection is exercised by CI, here the folder is built with --all-data)."""
import csv
import io
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import make_submission as ms  # noqa: E402


class TestSelection(unittest.TestCase):
    def test_is_bytecode(self):
        for p in ("__pycache__/nbdata.cpython-310.pyc", os.path.join("data", "__pycache__", "x"), "a.pyc", "b.pyo"):
            self.assertTrue(ms.is_bytecode(p), p)
        for p in ("nbdata.py", os.path.join("data", "MANIFEST.csv"), "pycache_notes.md"):
            self.assertFalse(ms.is_bytecode(p), p)

    def test_imported_names(self):
        src = "import os, a.b\nfrom c.d import e\nfrom . import f\ndef g():\n    import h\n"
        self.assertEqual(ms.imported_names(src), {"os", "a", "c", "h"})

    def test_helper_modules(self):
        mods = ms.helper_modules(ms.load_notebook())
        for m in ("setup_env", "nbdata", "nbfigs"):
            self.assertIn(m, mods)
        for m in mods:
            self.assertTrue(os.path.exists(os.path.join(ms.NB_DIR, m + ".py")))
        self.assertNotIn("make_notebook", mods)
        self.assertNotIn("test_notebook", mods)

    def test_markdown_files(self):
        found = ms.markdown_files(ms.load_notebook())
        self.assertIn(os.path.join("data", "MANIFEST.csv"), found)
        for f in found:
            self.assertTrue(os.path.isfile(os.path.join(ms.NB_DIR, f)), f)

    def test_trimmed_manifest(self):
        text = ms.trimmed_manifest([os.path.join("data", "MANIFEST.csv"),
                                    os.path.join("data", "tcurve_N_tvla.csv")])
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual([r["file"] for r in rows], ["tcurve_N_tvla.csv"])
        with self.assertRaises(SystemExit):
            ms.trimmed_manifest([os.path.join("data", "no_such_file.csv")])


class TestBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dest, cls.listing = ms.build(cls.tmp.name, all_data=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_path_and_files(self):
        self.assertTrue(self.dest.endswith(os.path.join(*ms.PR_PATH)))
        for f in (ms.NOTEBOOK, "LICENSE", "README.md", "setup_env.py", os.path.join("data", "MANIFEST.csv")):
            self.assertIn(f, self.listing)
        self.assertFalse([p for p in self.listing if "__pycache__" in p or p.endswith(".pyc")])
        self.assertNotIn("ci_smoke.ipynb", self.listing)
        n_data = len([f for f in os.listdir(os.path.join(ms.NB_DIR, "data"))])
        self.assertEqual(len([p for p in self.listing if p.startswith("data" + os.sep)]), n_data)

    def test_readme(self):
        with open(os.path.join(self.dest, "README.md")) as f:
            text = f.read()
        self.assertTrue(text.startswith("<!-- SPDX-License-Identifier: Apache-2.0 -->"))
        self.assertIn(ms.COLAB_URL, text)
        self.assertNotRegex(text, r"[{}]")                        # every placeholder filled
        self.assertNotRegex(text, r"/home/|/media/|/Users/")
        self.assertEqual(re.findall(r"TODO\(\w+\)[^|\n]*", text), ["TODO(user): e-mail "])
        ai = ("AI coding assistants were used in this project. All results come from open-source tools (ngspice, "
              "the sky130 PDK, OpenLane, Magic, KLayout, netgen, Python), and the author is responsible for all "
              "content.")
        flat = " ".join(text.split())
        self.assertIn("## AI use " + ai + " ## License", flat)      # the sentence alone, under its heading
        self.assertEqual(flat.count("AI coding assistants"), 1)
        self.assertIn("It finds no first-order key in D or DA", flat)
        self.assertIn("Magic extraction (capacitance only)", flat)

    def test_manifest_matches_files(self):
        with open(os.path.join(self.dest, "data", "MANIFEST.csv"), newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            self.assertEqual(ms.sha256(os.path.join(self.dest, "data", r["file"])), r["sha256"])


if __name__ == "__main__":
    unittest.main()
