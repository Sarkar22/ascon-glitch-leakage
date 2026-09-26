# SPDX-License-Identifier: Apache-2.0
"""Checks of the submission notebook and its helpers (stdlib unittest; numpy needed,
matplotlib optional: the figure tests are skipped without it).

  python3 -m unittest discover -s notebook -p 'test_*.py'
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_notebook                                  # noqa: E402
import nbanim                                         # noqa: E402
import nbdata                                         # noqa: E402
import nbexplorer                                     # noqa: E402
import setup_env                                      # noqa: E402

NB = os.path.join(HERE, "ascon_glitch_leakage.ipynb")
AI_USE = ("AI coding assistants were used in this project. All results come from open-source tools (ngspice, the "
          "sky130 PDK, OpenLane, Magic, KLayout, netgen, Python), and the author is responsible for all content.")


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

    def test_run_now_link_and_pinned_ref(self):
        """The second Colab link opens the author's repository at the pinned ref, is not a badge (the
        organizers' check requires every colab-badge line to point to sscs-ose), and the setup cell
        fetches the same repository and ref."""
        cells = load_nb()["cells"]
        ref, url = setup_env.DEFAULT_REPO_REF, setup_env.DEFAULT_REPO_URL
        run_now = "https://colab.research.google.com/github/%s/blob/%s/notebook/ascon_glitch_leakage.ipynb" % (
            url[len("https://github.com/"):], ref)
        self.assertIn(run_now, src(cells[0]))
        for ln in cells[0]["source"]:
            if "Sarkar22" in ln:
                self.assertNotIn("colab-badge", ln)
        setup = next(src(c) for c in cells if c["cell_type"] == "code")
        self.assertIn("REPO = '%s'" % url, setup)
        self.assertIn("os.environ.setdefault('ASCON_REPO_REF', '%s')" % ref, setup)

    def test_todo_markers(self):
        """Only the author's item is open: the e-mail."""
        text = "\n".join(src(c) for c in load_nb()["cells"])
        self.assertEqual(re.findall(r"TODO\([a-z]+\)[^|\n]*", text), ["TODO(user): e-mail "])
        self.assertNotIn("Acknowledgments", text)

    def test_ai_use_text(self):
        """The AI-use statement is the same sentence in the notebook, README.md and the PR body."""
        text = "\n".join(src(c) for c in load_nb()["cells"] if c["cell_type"] == "markdown")
        par = next(p for p in text.split("\n\n") if p.startswith("**AI-use disclosure.**"))
        self.assertEqual(" ".join(par.split()), "**AI-use disclosure.** " + AI_USE)
        for rel in ("README.md", os.path.join("docs", "PR_BODY.md")):
            p = os.path.join(os.path.dirname(HERE), rel)
            if not os.path.exists(p):
                continue
            with open(p) as f:
                flat = " ".join(f.read().split())
            self.assertIn(AI_USE, flat, rel)
            self.assertEqual(flat.count("AI coding assistants"), 1, rel)

    def test_repository_links(self):
        """Project files the notebook names are linked to the public repository at the pinned ref, and
        each linked path is in the repository (not in build/ or runs/, not git-ignored)."""
        text = "\n".join(src(c) for c in load_nb()["cells"] if c["cell_type"] == "markdown")
        base = "%s/(?:blob|tree)/%s/" % (re.escape(setup_env.DEFAULT_REPO_URL), re.escape(setup_env.DEFAULT_REPO_REF))
        links = re.findall(r"\]\(%s([^)#]+)\)" % base, text)
        for rel in ("docs/KILL_TEST.md", "docs/POSTLAYOUT.md", "layout/README.md", "notebook/colab_check.py",
                    "notebook/make_cached_data.py", "notebook/make_layout_media.py", "notebook/tests/colab_live.sh"):
            self.assertIn(rel, links)
        repo = os.path.dirname(HERE)
        if not os.path.exists(os.path.join(repo, "results")):
            self.skipTest("not inside the repository")
        for rel in set(links):
            self.assertTrue(os.path.exists(os.path.join(repo, rel)), rel)
            self.assertNotIn(rel.split("/")[0], ("build", "runs"), rel)
            if shutil.which("git") and os.path.exists(os.path.join(repo, ".git")):
                ignored = subprocess.run(["git", "-C", repo, "check-ignore", "-q", rel]).returncode == 0
                self.assertFalse(ignored, rel)
        for name in ("nbexplorer.py", "data/MANIFEST.csv", "LICENSE"):      # shipped: plain code spans
            self.assertNotIn("/" + name + ")", text)

    def test_gif_plays_on_colab_only(self):
        """Section 4.2 shows the GIF with IPython on Colab (the markdown image link may not load there);
        a headless run, like the one that saved the outputs, adds no output."""
        cell = next(src(c) for c in load_nb()["cells"] if c["cell_type"] == "code" and "save_gif" in src(c))
        self.assertIn("if 'google.colab' in sys.modules:", cell)
        self.assertIn("display(Image(filename=GIF))", cell)
        nb = load_nb()
        k = next(i for i, c in enumerate(nb["cells"]) if c["cell_type"] == "code" and "save_gif" in src(c))
        for o in nb["cells"][k].get("outputs", []):
            self.assertNotIn("image/gif", o.get("data", {}))

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


class TestSetupCell(unittest.TestCase):
    """The setup cell's bootstrap on Colab, with git replaced by a stub that creates folders."""

    def boot(self, colab=True, upstream_has_folder=False):
        cell = next(src(c) for c in load_nb()["cells"] if c["cell_type"] == "code").splitlines()
        code = "\n".join(cell[:cell.index("sys.path.insert(0, os.getcwd())")])
        calls = []

        def fake_run(cmd, check=False, **kw):
            calls.append(cmd)
            if cmd[:2] == ["git", "clone"]:
                os.makedirs(cmd[-1])
                if cmd[-1] == "ascon-glitch-leakage":
                    os.makedirs(os.path.join(cmd[-1], "notebook"))
                    open(os.path.join(cmd[-1], "notebook", "nbdata.py"), "w").close()
            elif "sparse-checkout" in cmd and upstream_has_folder:
                os.makedirs(os.path.join("code-a-chip", cmd[-1]))
                open(os.path.join("code-a-chip", cmd[-1], "nbdata.py"), "w").close()
            return types.SimpleNamespace(returncode=0)
        mods = {"google.colab": types.ModuleType("google.colab")} if colab else {}
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as d, mock.patch("subprocess.run", fake_run), \
                mock.patch.dict(os.environ, {}), mock.patch.dict(sys.modules, mods):
            os.environ.pop("ASCON_REPO_REF", None)
            if not colab:
                sys.modules.pop("google.colab", None)
            os.chdir(d)
            try:
                exec(compile(code, "setup cell", "exec"), {})
                where = os.path.relpath(os.getcwd(), os.path.realpath(d))
            finally:
                os.chdir(cwd)
        return where, calls

    def test_before_the_merge_the_public_repository(self):
        where, calls = self.boot(upstream_has_folder=False)
        self.assertEqual(where, os.path.join("ascon-glitch-leakage", "notebook"))
        self.assertIn("sscs-ose", " ".join(calls[0]))
        self.assertEqual(calls[-1][-4:], ["--branch", setup_env.DEFAULT_REPO_REF, setup_env.DEFAULT_REPO_URL,
                                          "ascon-glitch-leakage"])

    def test_after_the_merge_the_sscs_ose_folder(self):
        where, calls = self.boot(upstream_has_folder=True)
        self.assertEqual(where, os.path.join("code-a-chip", "ISSCC27", "submitted_notebooks", "ascon_glitch_leakage"))
        self.assertEqual(len(calls), 2)                  # no clone of the author's repository

    def test_outside_colab_nothing_is_fetched(self):
        where, calls = self.boot(colab=False)
        self.assertEqual((where, calls), (".", []))


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
                  "pl_energy_DA_vs_N_pct", "pl_DA_detect_frac_full_N", "lay_N_clk_pins", "results_dated",
                  "ctl_all", "ctl_swap_pin", "rc_rows", "rc_last_ps", "rc_ckq_ps", "cost_DA_latency_vs_N_pct",
                  "cost_DA_latency_cycles", "cost_N_latency_cycles", "cost_U_ge", "cost_N_ge", "cost_DA_ge",
                  "ge_nand2_um2", "lay_fp_util"):
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

    def test_post_hoc_checks_match_the_text(self):
        """Section 6.3: every LVS and DRC negative control gives its expected result, the share swap
        keeps every count, and the RC bracket is what the text says (function intact, ideal rails,
        its C-only side reproduces the committed post-layout node timing)."""
        nc = nbdata.negative_controls()
        self.assertTrue(nc["all_as_expected"])
        for v in ("N", "DA"):
            cases = nc["lvs"][v]["cases"]
            self.assertEqual(sorted(cases), ["correct", "gate_type", "missing_ff", "share_swap"])
            for name, c in cases.items():
                self.assertEqual(c["verdict"], "match" if name == "correct" else "mismatch", (v, name))
                self.assertTrue(c["as_expected"], (v, name))
            for k in ("devices_layout_vs_netlist", "nets_layout_vs_netlist"):
                self.assertEqual(cases["share_swap"][k], cases["correct"][k])
            swap = cases["share_swap"]["change"]
            self.assertNotEqual(swap["from_domain"], swap["to_domain"])
        drc = nc["drc"]
        self.assertEqual((drc["clean"]["magic_markers"], drc["clean"]["klayout_markers"]), (0, 0))
        for tool in ("magic", "klayout"):
            t = drc["injected"][tool]
            self.assertTrue(t["exactly_the_injected"] and t["markers"] > 0 and t["markers_elsewhere"] == 0)
            self.assertEqual(sorted(t["markers_by_structure"]), ["met1_spacing", "via1_enclosure"])
        rc = nbdata.rc_check()
        fn = rc["function"]
        self.assertEqual((fn["c_only_mismatches_vs_sbox"], fn["rc_mismatches_vs_sbox"],
                          fn["rc_vs_c_only_output_bits_differing"]), (0, 0, 0))
        self.assertEqual(rc["netlists"]["rc"]["resistors"]["supply_nets_with_resistors"], [])
        self.assertTrue(rc["netlists"]["rc"]["devices_identical_to_c_only"])
        self.assertTrue(rc["c_only_vs_campaign"]["outputs_equal"])
        c_only = rc["net_timing"]["last_logic_crossing_ns"]["c_only"]
        committed = nbdata.node_timing()["post_layout"]["last_logic_crossing_ns"]
        self.assertAlmostEqual(c_only["median"], committed["median"], delta=0.005)
        self.assertAlmostEqual(c_only["max"], committed["max"], delta=0.005)
        text = "\n".join(src(c) for c in load_nb()["cells"] if c["cell_type"] == "markdown")
        self.assertIn("### 6.3 Post-hoc checks", text)
        self.assertIn("(a sanity check, not a TVLA)", text)
        self.assertNotIn("under 2 ps", text)

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
                  nbfigs.postlayout_cost_table(), nbfigs.controls_table()]
        if nbfigs.cost_table():
            tables.append(nbfigs.cost_table())
        for t in tables:
            html = nbfigs.md_to_html(t)
            self.assertEqual(html.count("<tr>") - 1, len(t.strip().splitlines()) - 2)


if __name__ == "__main__":
    unittest.main()
