# SPDX-License-Identifier: Apache-2.0
"""Checks of the submission notebook and its helpers (stdlib unittest; numpy needed,
matplotlib optional: the figure tests are skipped without it).

  python3 -m unittest discover -s notebook -p 'test_*.py'
"""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_notebook                                  # noqa: E402
import nbanim                                         # noqa: E402
import nbdata                                         # noqa: E402
import nbexplorer                                     # noqa: E402

NB = os.path.join(HERE, "ascon_glitch_leakage.ipynb")


def load_nb():
    with open(NB) as f:
        return json.load(f)


def src(cell):
    return "".join(cell["source"])


class TestNotebook(unittest.TestCase):
    def test_text_matches_results(self):
        """The committed notebook's cells are what make_notebook.py builds from the current
        result files, so every quoted number matches summary.json."""
        built = make_notebook.build()
        have = load_nb()
        self.assertEqual([c["cell_type"] for c in have["cells"]], [c["cell_type"] for c in built["cells"]])
        for a, b in zip(have["cells"], built["cells"]):
            self.assertEqual(src(a), src(b))

    def test_no_unfilled_placeholders(self):
        for c in load_nb()["cells"]:
            self.assertNotIn("<<", src(c).replace("\\ll", ""))

    def test_colab_badge(self):
        """Organizer CI: a colab-badge line exists and every such line points to sscs-ose."""
        with open(NB) as f:
            lines = [ln for ln in f if "colab-badge" in ln]
        self.assertTrue(lines)
        for ln in lines:
            self.assertIn("sscs-ose", ln)
        self.assertIn("ISSCC27/submitted_notebooks/ascon_glitch_leakage/ascon_glitch_leakage.ipynb", lines[0])

    def test_every_code_cell_follows_markdown(self):
        cells = load_nb()["cells"]
        for k, c in enumerate(cells):
            if c["cell_type"] == "code" and k > 0:
                self.assertEqual(cells[k - 1]["cell_type"], "markdown", "code cell %d" % k)

    def test_code_cells_are_short_and_lint_friendly(self):
        for c in load_nb()["cells"]:
            if c["cell_type"] != "code":
                continue
            s = src(c)
            self.assertLessEqual(len(s.splitlines()), 40)
            for ln in s.splitlines():
                self.assertLessEqual(len(ln), 79, ln)
                self.assertFalse(ln.startswith(("!", "%")), "shell/magic lines fail flake8: " + ln)

    def test_license_and_spdx(self):
        first = src(load_nb()["cells"][0])
        self.assertIn("SPDX-License-Identifier: Apache-2.0", first)
        for name in os.listdir(HERE):
            if name.endswith(".py"):
                with open(os.path.join(HERE, name)) as f:
                    self.assertEqual(f.readline().strip(), "# SPDX-License-Identifier: Apache-2.0", name)

    def test_no_private_data(self):
        """No absolute home or media paths, e-mail addresses or host names in the notebook folder."""
        roots = "|".join(r"(?<![\w.])/%s/" % d for d in ("home", "media"))   # built, so this file passes
        pat = re.compile(r"(%s|[A-Za-z0-9._%%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,})" % roots)
        files = [os.path.join(HERE, n) for n in os.listdir(HERE) if n.endswith((".py", ".ipynb", ".md"))]
        files += [os.path.join(HERE, "media", n) for n in os.listdir(os.path.join(HERE, "media"))
                  if n.endswith(".json")]
        for p in files:
            with open(p, encoding="utf-8") as f:
                text = f.read()
            if p.endswith(".ipynb"):          # saved image data is base64, not text
                nb = json.loads(text)
                text = "\n".join(src(c) for c in nb["cells"])
                for c in nb["cells"]:
                    for o in c.get("outputs", []):
                        text += "".join(o.get("text", "")) + "".join(o.get("data", {}).get("text/plain", ""))
            m = pat.search(text)
            self.assertIsNone(m, "%s: %s" % (os.path.basename(p), m and m.group(0)))


class TestCaches(unittest.TestCase):
    def test_explorer_matches_summary(self):
        """Without noise, the explorer reproduces each campaign's final max|t|."""
        s = nbdata.summary()["campaigns"]
        for c in nbexplorer.CAMPAIGNS.values():
            st = nbexplorer.load(c)
            self.assertEqual(int(st["n"][-1]), s[c]["rows_analysed"])
            got = float(nbexplorer.curve(st)["max_abs_t"][-1])
            self.assertAlmostEqual(got, s[c]["spice"]["final_max_abs_t"], delta=0.01, msg=c)

    def test_data_copy_is_current(self):
        """In the repository, data/ must hold the current kill-test summary (re-run
        make_cached_data.py after analysis/kill_test.py)."""
        repo = os.path.join(nbdata.root(), "results", "kill_test", "summary.json")
        copy = os.path.join(nbdata.DATA, "kill_test_summary.json")
        if not (os.path.exists(repo) and os.path.exists(copy)):
            self.skipTest("not inside the repository")
        with open(repo) as a, open(copy) as b:
            self.assertEqual(json.load(a), json.load(b))

    def test_probing_from_csv_matches_json(self):
        jdir = os.path.join(nbdata.root(), "results", "probing")
        if not os.path.isdir(jdir):
            self.skipTest("not inside the repository")
        got = nbdata.probing()
        for v in ("N", "D", "DA"):
            with open(os.path.join(jdir, v + ".json")) as f:
                want = json.load(f)
            self.assertEqual(got[v]["glitch_fail"], want["glitch_fail"])
            self.assertEqual(got[v]["n_nets"], want["n_nets"])

    def test_explorer_noise_is_plausible(self):
        exact, approx = nbexplorer.check_against_exact("N_tvla", 1.0)
        self.assertLess(abs(sum(approx) / len(approx) - exact), 1.5)

    def test_glitch_events(self):
        ev = nbanim.load_events()
        for v in ("N", "DA"):
            nets = ev["variants"][v]["nets"]
            for name, _ in nbanim.PATHS[v]:
                self.assertIn(name, nets)
            for net in nets.values():          # every waveform ends at the settled value
                if net["events"]:
                    self.assertEqual(net["events"][-1][1], net["v1"])
        n_n, g_n = nbanim.totals(ev["variants"]["N"])
        n_a, g_a = nbanim.totals(ev["variants"]["DA"])
        self.assertGreater(g_n, g_a)

    def test_headline_values(self):
        h = nbdata.fmt_headline()
        for k in ("N_t", "D_t", "DA_t", "N_n", "DA_n", "DA_detect_frac_words", "N_probe_fail", "kr_N_bits_sr",
                  "kr_DA_alpha", "kr_DA_alpha_words", "kr_alpha_range", "kr_null_sd_range_bits",
                  "cost_DA_area_vs_N_pct", "cost_DA_energy_vs_N_pct", "DDA_tdiff_near_peak", "pl_N_t", "pl_N_pre_t",
                  "pl_DA_t", "pl_DA_detect_frac", "pl_N_shift_ns", "lay_N_cap_rcx", "lay_core_DA_vs_N_pct",
                  "pl_energy_DA_vs_N_pct"):
            self.assertIn(k, h)

    def test_postlayout_verdicts_match_the_text(self):
        """Section 6 says N still leaks and DA shows none after layout; hold that to the data."""
        pl = nbdata.postlayout()
        cr = pl["criteria"]
        self.assertTrue(cr["PL1"]["pass"] and cr["PL1"]["max_abs_t"] > 4.5)
        self.assertTrue(cr["PL2"]["pass"] and cr["PL2"]["max_abs_t"] < 4.5)
        self.assertEqual((cr["PL1"]["rows_simulated"], cr["PL2"]["rows_simulated"]), (5000, 10000))
        self.assertTrue(pl["reproduces_kill_test"]["all_identical"])
        for v in ("N_pex", "DA_pex"):
            self.assertEqual(pl["campaigns"][v]["function_check"]["mismatches_vs_sbox"], 0)
        self.assertEqual(nbdata.fmt_headline()["lay_all_clean"], "True")
        text = "\n".join(src(c) for c in load_nb()["cells"] if c["cell_type"] == "markdown")
        self.assertIn("survives place and route under C-only extraction at tt", text)

    def test_layout_and_pex_copies_are_current(self):
        """In the repository, data/ must hold the current layout and post-layout results (re-run
        make_cached_data.py without --optional after analysis/postlayout.py)."""
        for step in ("layout", "pex"):
            src_dir = os.path.join(nbdata.root(), "results", step)
            if not os.path.isdir(src_dir) or not os.path.isdir(nbdata.DATA):
                self.skipTest("not inside the repository")
            for name in sorted(os.listdir(src_dir)):
                if not name.endswith((".csv", ".json")):
                    continue
                with open(os.path.join(src_dir, name), "rb") as a, \
                        open(os.path.join(nbdata.DATA, "%s__%s" % (step, name)), "rb") as b:
                    self.assertEqual(a.read(), b.read(), name)

    def test_layout_media_present(self):
        for v in ("N", "DA"):
            p = os.path.join(HERE, "media", "layout_%s.png" % v)
            self.assertTrue(os.path.exists(p), p)
            self.assertLess(os.path.getsize(p), 150e3)

    def test_d_and_da_share_their_peak(self):
        """Section 4.5 says D and DA end at the same max|t| at the same sample; hold it to the data."""
        h = nbdata.headline()
        self.assertTrue(h["DDA_same_peak"])
        self.assertEqual(h["D_peak_ns"], h["DA_peak_ns"])
        self.assertAlmostEqual(h["D_t"], h["DA_t"], delta=0.005)
        self.assertLess(h["DDA_tdiff_near_peak"], 0.05)

    def test_key_recovery_and_cost_copies_are_current(self):
        """In the repository, data/ must hold the current key-recovery summary and cost table
        (re-run make_cached_data.py after analysis/key_recovery.py and analysis/cost_table.py)."""
        for copy, parts in (("key_recovery__summary.json", ("results", "key_recovery", "summary.json")),
                            ("cost__cost.csv", ("results", "cost", "cost.csv"))):
            repo = os.path.join(nbdata.root(), *parts)
            data = os.path.join(nbdata.DATA, copy)
            if not (os.path.exists(repo) and os.path.exists(data)):
                self.skipTest("not inside the repository")
            with open(repo, "rb") as a, open(data, "rb") as b:
                self.assertEqual(a.read(), b.read(), copy)

    def test_primary_distinguisher_is_the_template(self):
        kr = nbdata.key_recovery()
        self.assertEqual(kr["primary_distinguisher"], "tmpl")
        for name in ("N_pooled", "D_tvla", "DA_tvla"):
            r = kr["datasets"][name]["results"]["order1_noise0"]
            self.assertGreaterEqual(r["null"]["tmpl"]["draws"], 10)      # a null distribution, not one draw


class TestFigures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import matplotlib
            matplotlib.use("Agg")
        except ImportError:
            raise unittest.SkipTest("matplotlib not installed")

    def test_figures_draw(self):
        import matplotlib.pyplot as plt
        import nbfigs
        for f in (nbfigs.workflow, nbfigs.headline, nbfigs.maxt_vs_traces, lambda: nbfigs.localization("N"),
                  lambda: nbfigs.localization("D"), nbfigs.model_vs_spice, nbfigs.noise,
                  nbexplorer.static_panel, lambda: nbanim.draw(nbanim.load_events(), 0.8),
                  nbfigs.key_recovery, nbfigs.key_recovery_injection, nbfigs.cost_figure, nbfigs.layout_figure,
                  nbfigs.postlayout_tcurves, nbfigs.postlayout_maxt):
            fig = f()
            self.assertTrue(fig.axes)
            plt.close(fig)

    def test_tables(self):
        import nbfigs
        tables = [nbfigs.probing_table(), nbfigs.variants_table(), nbfigs.model_table(), nbfigs.criteria_table(),
                  nbfigs.key_recovery_table(), nbfigs.layout_table(), nbfigs.postlayout_table(),
                  nbfigs.postlayout_cost_table()]
        if nbfigs.cost_table():
            tables.append(nbfigs.cost_table())
        for t in tables:
            html = nbfigs.md_to_html(t)
            self.assertEqual(html.count("<tr>") - 1, len(t.strip().splitlines()) - 2)


if __name__ == "__main__":
    unittest.main()
