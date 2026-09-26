# SPDX-License-Identifier: Apache-2.0
"""Unit tests of setup_env.py, the cached data set (data/) and ci_smoke.ipynb (stdlib unittest).

    python3 -m unittest discover -s notebook -p 'test_*.py'

No tool is installed or run: the tests use cached mode, and the live-mode check only runs
where ngspice is missing (it must then refuse). Host python3 + numpy is enough.
"""
import csv
import json
import os
import re
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import setup_env  # noqa: E402

# local absolute paths or an e-mail address (written so that this file does not match itself)
PRIVATE = re.compile(r"/(?:home|media|Users)/|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}")


class TestDetection(unittest.TestCase):
    def test_find_repo(self):
        repo = setup_env.find_repo()
        self.assertIsNotNone(repo)
        self.assertEqual(os.path.realpath(repo), os.path.realpath(os.path.dirname(HERE)))

    def test_short_path_hides_home(self):
        home = os.path.expanduser("~")
        with mock.patch("os.getcwd", return_value="/"):
            p = setup_env.short_path(os.path.join(home, ".ciel", "sky130A"))
        self.assertTrue(p.startswith("~"), p)
        self.assertEqual(setup_env.short_path(None), "-")

    def test_pdk_version_from_path(self):
        h = setup_env.PDK_HASH
        self.assertEqual(setup_env.pdk_version("/x/versions/%s/sky130A" % h), h)

    def test_cached_mode_installs_nothing(self):
        with mock.patch.object(setup_env, "install") as inst, \
                mock.patch.object(setup_env, "clone_repo") as clone:
            env = setup_env.setup(mode="cached", verbose=False)
        inst.assert_not_called()
        clone.assert_not_called()
        self.assertEqual(env.mode, "cached")
        self.assertFalse(env.live)
        self.assertIn("mode", str(env))

    def test_auto_mode_without_ngspice_is_cached(self):
        with mock.patch.object(setup_env, "tool_version", return_value=None), \
                mock.patch.dict(os.environ, {"ASCON_MODE": ""}), \
                mock.patch.object(setup_env, "in_colab", return_value=False):
            env = setup_env.setup(verbose=False)
            self.assertEqual(env.mode, "cached")
            self.assertIn("ngspice not installed", env.reasons)
            with self.assertRaises(RuntimeError):
                setup_env.setup(mode="live", verbose=False)

    def test_bad_mode(self):
        with self.assertRaises(ValueError):
            setup_env.setup(mode="fast", verbose=False)


class TestCachedData(unittest.TestCase):
    def test_manifest_matches(self):
        self.assertEqual(setup_env.check_data(verbose=False), [])

    def test_every_file_listed_and_small(self):
        with open(setup_env.data_path("MANIFEST.csv"), newline="") as f:
            listed = {r["file"]: int(r["bytes"]) for r in csv.DictReader(f)}
        present = set(os.listdir(setup_env.DATA_DIR)) - {"MANIFEST.csv"}
        self.assertEqual(present, set(listed))
        self.assertLess(sum(listed.values()), 10e6)

    def test_no_private_strings(self):
        for name in os.listdir(setup_env.DATA_DIR):
            with open(os.path.join(setup_env.DATA_DIR, name), errors="replace") as f:
                text = f.read()
            self.assertIsNone(PRIVATE.search(text), name)

    def test_read_helpers(self):
        c = setup_env.read_csv("campaigns.csv")
        self.assertIn("N_tvla", list(c["campaign"]))
        n = list(c["campaign"]).index("N_tvla")
        self.assertGreater(c["spice_max_abs_t"][n], 4.5)
        keys, times, t = setup_env.read_matrix("tvla_t_checkpoints_N_tvla.csv")
        self.assertEqual(t.shape, (len(keys["traces"]), len(times)))
        tc = setup_env.read_csv("tcurve_N_tvla.csv")
        self.assertLess(abs(abs(t[-1]).max() - abs(tc["t_spice"]).max()), 0.01)

    def test_demo_reference_matches_demo(self):
        d = setup_env.DEMO
        keys, times, ref = setup_env.read_matrix("demo_reference_%s.csv" % d["campaign"], key_cols=7)
        self.assertEqual(ref.shape[0], d["rows"])
        self.assertEqual(len(times), 400)
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "model"))
        from ascon_sbox import SBOX_NP
        self.assertTrue((SBOX_NP[keys["x"].astype(int)] == keys["y_registered"]).all())


class TestSmokeNotebook(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(HERE, "ci_smoke.ipynb")) as f:
            self.nb = json.load(f)

    def test_badge_points_to_sscs_ose(self):
        lines = [ln for c in self.nb["cells"] for ln in c["source"] if "colab-badge" in ln]
        self.assertTrue(lines)
        self.assertTrue(all("sscs-ose" in ln for ln in lines))

    def test_code_cells_fit_flake8_defaults(self):
        for c in self.nb["cells"]:
            if c["cell_type"] == "code":
                for ln in "".join(c["source"]).splitlines():
                    self.assertLessEqual(len(ln), 79, ln)
                    self.assertFalse(ln.lstrip().startswith(("%", "!")), ln)
                self.assertEqual(c["outputs"], [])

    def test_license_and_ids(self):
        self.assertIn("SPDX-License-Identifier: Apache-2.0", "".join(self.nb["cells"][0]["source"]))
        ids = [c.get("id") for c in self.nb["cells"]]
        self.assertTrue(all(ids) and len(set(ids)) == len(ids))


if __name__ == "__main__":
    unittest.main()
