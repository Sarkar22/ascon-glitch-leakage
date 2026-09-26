# SPDX-License-Identifier: Apache-2.0
"""Build the Code-a-Chip pull-request folder ISSCC27/submitted_notebooks/ascon_glitch_leakage/.

    python3 tools/make_submission.py [--out-root DIR] [--all-data] [--list]

The folder holds what the notebook needs when it runs, and nothing else:
  ascon_glitch_leakage.ipynb  the notebook as committed, with its saved outputs
  <helper>.py                 the modules of notebook/ that the notebook imports, directly or
                              through each other (found in the code cells' import statements)
  data/                       the cached data the notebook reads: every file that a cached-mode
                              run of the code cells opens (traced), plus the files of two paths a
                              cached run does not reach (the explorer's other variants and the
                              live SPICE demo's reference); MANIFEST.csv keeps only their rows
  media/                      the media files the code cells open or the markdown cells show
  LICENSE                     the repository's Apache-2.0 text
  README.md                   a short datasheet; its numbers come from data/ (nbdata.fmt_headline)
The folder is written to DIR/ISSCC27/submitted_notebooks/ascon_glitch_leakage (default DIR:
runs/submission, git-ignored), so the organizers' CI commands can be run from DIR as from the root
of their repository. A previous build there is replaced. The build never holds __pycache__ or *.pyc
files (it copies named files only and fails if one appears); the fork's copy must be taken from
this build, not from a folder in which the notebook has run (tools/check_submission.sh).

The traced run executes every code cell in cached mode and draws every figure, so it needs numpy
and matplotlib (for example: bash sim/docker_run.sh python3 tools/make_submission.py).
--all-data skips the trace and copies all of data/ and media/. --list prints the files only.
"""
import argparse
import ast
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NB_DIR = os.path.join(REPO, "notebook")
NOTEBOOK = "ascon_glitch_leakage.ipynb"
PR_PATH = ("ISSCC27", "submitted_notebooks", "ascon_glitch_leakage")
REPO_URL = "https://github.com/Sarkar22/ascon-glitch-leakage"
UPSTREAM = "sscs-ose/sscs-ose-code-a-chip.github.io"
COLAB_URL = ("https://colab.research.google.com/github/%s/blob/main/%s/%s"
             % (UPSTREAM, "/".join(PR_PATH), NOTEBOOK))
BADGE = ("[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](%s)"
         % COLAB_URL)
SHIPPED_DIRS = ("data", "media")


def load_notebook(path=None):
    with open(path or os.path.join(NB_DIR, NOTEBOOK)) as f:
        return json.load(f)


def cell_source(cell):
    src = cell["source"]
    return "".join(src) if isinstance(src, list) else src


def imported_names(source):
    """Top-level module names imported anywhere in a piece of Python source."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def helper_modules(nb):
    """The notebook/ modules the code cells import, followed through the modules' own imports."""
    todo = set()
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            todo |= imported_names(cell_source(cell))
    found = set()
    while todo:
        name = todo.pop()
        path = os.path.join(NB_DIR, name + ".py")
        if name in found or not os.path.exists(path):
            continue
        found.add(name)
        with open(path) as f:
            todo |= imported_names(f.read())
    return sorted(found)


def markdown_files(nb):
    """data/ and media/ files that the markdown cells name and that exist."""
    out = set()
    for cell in nb["cells"]:
        if cell["cell_type"] != "markdown":
            continue
        for m in re.findall(r"\b((?:%s)/[\w.-]+\.\w+)" % "|".join(SHIPPED_DIRS), cell_source(cell)):
            if os.path.isfile(os.path.join(NB_DIR, m)):
                out.add(m)
    return out


# ------------------------------------------------------------------------- the trace ---
def _trace_main(nb_dir, report):
    """(In a subprocess.) Run the code cells in cached mode; record the files opened under the
    repository and the helper modules loaded; write both to `report` (JSON)."""
    repo = os.path.dirname(nb_dir)
    opened = set()

    def hook(event, args):
        if event == "open" and args and isinstance(args[0], (str, bytes)):
            p = os.path.realpath(os.fsdecode(args[0]))
            if p.startswith(repo + os.sep):
                opened.add(os.path.relpath(p, nb_dir))

    os.chdir(nb_dir)
    sys.path.insert(0, nb_dir)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    nb = load_notebook(os.path.join(nb_dir, NOTEBOOK))
    sys.addaudithook(hook)
    ns = {"__name__": "__main__"}
    for i, cell in enumerate(nb["cells"]):
        if cell["cell_type"] != "code":
            continue
        try:
            code = compile(cell_source(cell), "<cell %d>" % i, "exec")
        except SyntaxError as e:
            raise SystemExit("cell %d is not plain Python (IPython syntax?): %s" % (i, e))
        exec(code, ns)
        plt.close("all")
    # paths a cached run does not reach: the explorer's variant menu (ipywidgets) and the live
    # SPICE demo's reference; read them the way those paths do
    if "nbexplorer" in sys.modules:
        for campaign in sys.modules["nbexplorer"].CAMPAIGNS.values():
            sys.modules["nbexplorer"].load(campaign)
    if "setup_env" in sys.modules:
        se = sys.modules["setup_env"]
        se.read_matrix("demo_reference_%s.csv" % se.DEMO["campaign"], key_cols=7)
    modules = sorted(name for name, mod in list(sys.modules.items())
                     if os.path.dirname(os.path.realpath(getattr(mod, "__file__", None) or "/"))
                     == os.path.realpath(nb_dir))
    with open(report, "w") as f:
        json.dump({"opened": sorted(opened), "modules": modules}, f, indent=1)


def trace():
    """Files and helper modules a cached-mode run of the notebook uses (see _trace_main)."""
    env = dict(os.environ, ASCON_MODE="cached", MPLBACKEND="Agg", PYTHONDONTWRITEBYTECODE="1")
    for k in ("ASCON_INSTALL", "ASCON_GLITCH_ROOT"):
        env.pop(k, None)
    with tempfile.TemporaryDirectory() as tmp:
        report = os.path.join(tmp, "trace.json")
        p = subprocess.run([sys.executable, os.path.abspath(__file__), "_trace", NB_DIR, report],
                           env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if p.returncode != 0:
            tail = p.stdout[-3000:]
            hint = ("\nThe trace needs numpy and matplotlib: run this in the cac-sca image "
                    "(bash sim/docker_run.sh python3 tools/make_submission.py) or use --all-data."
                    if "No module named" in tail else "")
            raise SystemExit("the traced notebook run failed:\n%s%s" % (tail, hint))
        with open(report) as f:
            return json.load(f)


# ----------------------------------------------------------------------- the files ---
def select(all_data=False):
    """(helper modules, data and media files) of the submission, as paths relative to notebook/."""
    nb = load_notebook()
    modules = helper_modules(nb)
    if all_data:
        files = {os.path.join(d, f) for d in SHIPPED_DIRS
                 for f in os.listdir(os.path.join(NB_DIR, d))
                 if os.path.isfile(os.path.join(NB_DIR, d, f)) and not is_bytecode(f)}
    else:
        t = trace()
        extra = sorted(set(t["modules"]) - set(modules))
        if extra:
            raise SystemExit("the notebook loads modules the import scan did not find: %s" % extra)
        files, outside = set(), []
        for p in t["opened"]:
            if is_bytecode(p) or p == NOTEBOOK:
                continue
            if p.endswith(".py") and os.path.dirname(p) == "" and p[:-3] in modules:
                continue
            if p.split(os.sep)[0] in SHIPPED_DIRS and os.path.dirname(p) in SHIPPED_DIRS:
                files.add(p)
            else:
                outside.append(p)
        if outside:
            raise SystemExit("the notebook reads files the submission folder would not hold:\n  "
                             + "\n  ".join(outside))
    files |= markdown_files(nb)
    files.add(os.path.join("data", "MANIFEST.csv"))
    return modules, sorted(files)


def is_bytecode(path):
    """True for Python bytecode or its cache folder, which the folder must never ship."""
    return "__pycache__" in path.split(os.sep) or path.endswith((".pyc", ".pyo"))


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def trimmed_manifest(files):
    """data/MANIFEST.csv with the rows of the shipped data files only; checks their hashes."""
    shipped = {os.path.basename(f) for f in files if f.startswith("data" + os.sep)}
    shipped.discard("MANIFEST.csv")
    with open(os.path.join(NB_DIR, "data", "MANIFEST.csv"), newline="") as f:
        reader = csv.DictReader(f)
        head, rows = reader.fieldnames, [r for r in reader if r["file"] in shipped]
    missing = shipped - {r["file"] for r in rows}
    if missing:
        raise SystemExit("not in data/MANIFEST.csv: %s (run notebook/make_cached_data.py)"
                         % sorted(missing))
    stale = [r["file"] for r in rows if sha256(os.path.join(NB_DIR, "data", r["file"])) != r["sha256"]]
    if stale:
        raise SystemExit("data/ does not match MANIFEST.csv: %s" % stale)
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=head, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


# -------------------------------------------------------------------------- README ---
def docstring_line(module):
    with open(os.path.join(NB_DIR, module + ".py")) as f:
        doc = ast.get_docstring(ast.parse(f.read())) or ""
    return doc.strip().split("\n\n")[0].replace("\n", " ").replace("|", "\\|")


def notebook_paragraph(nb, start):
    """The markdown paragraph of the notebook that starts with `start`."""
    for cell in nb["cells"]:
        if cell["cell_type"] == "markdown":
            for par in cell_source(cell).split("\n\n"):
                if par.strip().startswith(start):
                    return par.strip()
    raise SystemExit("no paragraph starting with %r in the notebook" % start)


def readme(modules, files):
    """The README.md of the submission folder, with the numbers from data/."""
    sys.path.insert(0, NB_DIR)
    import nbdata
    import setup_env
    h = nbdata.fmt_headline()
    nb = load_notebook()
    # the project repository and the ref the notebook's setup cell fetches before the merge
    repo = getattr(setup_env, "DEFAULT_REPO_URL", REPO_URL)
    ref = getattr(setup_env, "DEFAULT_REPO_REF", "main")
    tree = "%s/tree/%s/" % (repo, ref)
    blob = "%s/blob/%s/" % (repo, ref)
    ai = notebook_paragraph(nb, "**AI-use disclosure.**")[len("**AI-use disclosure.**"):].strip()
    n_data = sum(f.startswith("data" + os.sep) for f in files)
    media = [os.path.basename(f) for f in files if f.startswith("media" + os.sep)]
    what = ["| `%s` | the notebook, with its saved outputs |" % NOTEBOOK]
    what += ["| `%s.py` | %s |" % (m, docstring_line(m)) for m in modules]
    what += ["| `data/` | the %d data files the notebook reads (CSV, JSON), each listed with its size, "
             "SHA-256, source and meaning in `data/MANIFEST.csv` |" % n_data,
             "| `media/` | the animation and images the notebook shows: %s |"
             % ", ".join("`%s`" % m for m in media),
             "| `LICENSE` | Apache License 2.0 |"]
    run_now = blob.replace("https://github.com/", "https://colab.research.google.com/github/") \
        + "notebook/" + NOTEBOOK
    v = dict(h)
    v.update(badge=BADGE, repo=repo, nb=NOTEBOOK, what="\n".join(what), ai=ai, tree=tree,
             blob=blob, run_now=run_now, pdk_hash=setup_env.PDK_HASH, ciel=setup_env.CIEL_VERSION,
             demo_rows=setup_env.DEMO["rows"], ci=repo + "/actions/workflows/ci.yml")
    return README.format(**v)


README = """<!-- SPDX-License-Identifier: Apache-2.0 -->
# Safe on paper, leaky in SPICE: glitch leakage of a masked Ascon S-box on SKY130

{badge}

IEEE SSCS Code-a-Chip, ISSCC 2027. Notebook: [`{nb}`]({nb}). Project repository (full flow):
<{repo}>.

| Name | Affiliation | Role | IEEE member | SSCS member | Contact |
|---|---|---|---|---|---|
| Emon Sarkar | University of Waterloo, Electrical and Computer Engineering | author | yes | no | esarkar@uwaterloo.ca |

## Claim

A first-order masked Ascon S-box that a zero-delay leakage model calls secure leaks at first order in
transistor-level ngspice simulation on the open sky130 PDK. The leak comes from the timing of the unregistered
cross-domain logic (glitches and data-dependent arrival times), and an exact glitch-extended probing check, which
runs in seconds, names the nets that carry it. With DOM's register barrier moved behind Ascon's input affine layer
(DA), no first-order leak shows up within {DA_n} simulated traces. After place and route and extraction of the
parasitic capacitances, N still leaks and DA still shows none (at half the traces). No chip was fabricated: these
are results of transistor-level simulation with the foundry's device models at one corner (tt, 27 °C, 1.8 V).

## Headline

One S-box column (5 bits), 4 ns clock, first-order fixed-vs-random TVLA; a leak is max|t| above 4.5.

| Design | Zero-delay model | Glitch-extended probing | SPICE, pre-layout | SPICE, post-layout |
|---|---|---|---|---|
| N: masked, no register barrier | {N_l1} (secure) | {N_probe_fail} of {N_nets} nets insecure | **{N_t}** at {N_n} traces: leaks | **{pl_N_t}** at {pl_N_n} traces: leaks |
| D: DOM, barrier in the textbook place | {D_l1} (secure) | {D_probe_fail} of {D_nets} nets insecure | {D_t} at {D_n} traces | not laid out |
| DA: DOM, barrier after the affine layer | {DA_l1} (secure) | {DA_probe_fail} of {DA_nets} nets insecure | {DA_t} at {DA_n} traces | {pl_DA_t} at {pl_DA_n} traces |

- A profiled template attack on the same traces recovers N's key at first order (success rate {kr_N_bits_sr} at
  {kr_N_n} traces per key, with points of interest chosen per key bit after the default attack missed one bit;
  {kr_N_sr} with the default ones). It finds no first-order key in D or DA; a second-order template partly recovers
  both (success rate {kr_D_o2_sr} on D, {kr_DA_o2_sr} on DA), as expected for two-share masking.
- D is not shown to be secure: its net-level leak is confirmed in SPICE on {D_leaky_count} nets and the timing-aware
  model predicts max|t| {D_l2cap} (cap-weighted), but the leak does not reach the supply current at {D_n} traces.
- D and DA end at the same max|t| ({DA_t}) at the same sample ({DA_peak_ns} ns, in the first cycle's clock-fall
  region), probably from circuitry the two variants share: one observation, not two.
- Layouts (OpenLane v1, every generator cell kept) are DRC, LVS and antenna clean in Magic, KLayout and netgen, and
  the same checks fail on injected faults: LVS on a netlist with one share input swapped (every count unchanged), a
  changed gate type or a missing flip-flop, DRC on two injected defects. The post-layout netlists come from Magic
  extraction (capacitance only); a post-hoc RC bracket on {rc_rows} rows of N delays its evaluation by about
  {rc_last_ps} ps and changes little else.
- Cost of the fix, DA against N: {cost_DA_area_vs_N_pct} % more cell area, {cost_DA_energy_vs_N_pct} % more energy
  per evaluation before layout ({pl_energy_DA_vs_N_pct} % after layout, where the clock tree is included),
  {cost_DA_latency_cycles} cycles of latency instead of {cost_N_latency_cycles}, the same
  {cost_DA_fresh_random_bits} fresh random bits.

## How to run

| Mode | What runs | Needs |
|---|---|---|
| Cached (default) | Every figure, table and the explorer, drawn from `data/` | Python 3.10 or later with numpy and matplotlib; under a minute |
| Live | Also installs ngspice, Icarus Verilog and the sky130 PDK, fetches the project repository and simulates {demo_rows} clock cycles of N in ngspice, compared with the shipped ngspice-42 reference | Colab (badge above) or Linux; a few minutes |

GitHub shows the notebook with its saved outputs. The Colab badge opens this folder's notebook on the
`sscs-ose` repository once the organizers have merged it; before that, [open the same notebook in Colab from
the project repository]({run_now}). The notebook, its helpers and its data are also in the project repository
at [`notebook/`]({tree}notebook); to run it locally:
`git clone {repo} && cd ascon-glitch-leakage/notebook && jupyter lab {nb}`.
The project's [continuous integration]({ci}) runs the organizers' lint and `pytest --nbmake` checks on this
folder, and on a fresh Ubuntu machine installs ngspice-42 and the pinned PDK and checks the live path against
the shipped results.

Pinned versions: sky130A from open_pdks `{pdk_hash}` (installed with ciel {ciel}); ngspice-42 for every campaign;
OpenLane v1 at commit `ff5509f`.

## What is where

| File | Contents |
|---|---|
{what}

The rest of the flow is in the [project repository]({repo}): the netlist generator ([`gen/`]({tree}gen)), the
leakage models, probing check, TVLA and CPA ([`model/`]({tree}model)), the parallel ngspice runner
([`sim/`]({tree}sim)), the analysis and key recovery ([`analysis/`]({tree}analysis)), the OpenLane flow and
extraction ([`layout/`]({tree}layout)), and the registrations with fixed criteria and their results
([`docs/KILL_TEST.md`]({blob}docs/KILL_TEST.md), [`docs/POSTLAYOUT.md`]({blob}docs/POSTLAYOUT.md)) and the
reviews ([`docs/reviews/`]({tree}docs/reviews)).

## AI use

{ai}

## License

Apache License 2.0; see [`LICENSE`](LICENSE).
"""


# --------------------------------------------------------------------------- build ---
def build(out_root, all_data=False):
    """Write the folder; returns (folder, [relative file paths])."""
    modules, files = select(all_data)
    dest = os.path.join(os.path.abspath(out_root), *PR_PATH)
    if os.path.exists(dest):
        if os.listdir(dest) and not os.path.exists(os.path.join(dest, NOTEBOOK)):
            raise SystemExit("%s exists and is not a previous build; not replacing it" % dest)
        shutil.rmtree(dest)
    os.makedirs(dest)
    manifest = trimmed_manifest(files)
    text = readme(modules, files)
    shutil.copyfile(os.path.join(NB_DIR, NOTEBOOK), os.path.join(dest, NOTEBOOK))
    for m in modules:
        shutil.copyfile(os.path.join(NB_DIR, m + ".py"), os.path.join(dest, m + ".py"))
    for f in files:
        os.makedirs(os.path.join(dest, os.path.dirname(f)), exist_ok=True)
        if f == os.path.join("data", "MANIFEST.csv"):
            with open(os.path.join(dest, f), "w", newline="") as g:
                g.write(manifest)
        else:
            shutil.copyfile(os.path.join(NB_DIR, f), os.path.join(dest, f))
    shutil.copyfile(os.path.join(REPO, "LICENSE"), os.path.join(dest, "LICENSE"))
    with open(os.path.join(dest, "README.md"), "w") as g:
        g.write(text)
    listing = sorted(os.path.relpath(os.path.join(d, f), dest)
                     for d, _, fs in os.walk(dest) for f in fs)
    bytecode = [p for p in listing if is_bytecode(p)]
    if bytecode:                            # the PR must never carry __pycache__ or *.pyc
        raise SystemExit("the folder holds Python bytecode: %s" % bytecode)
    return dest, listing


def check_license():
    with open(os.path.join(REPO, "LICENSE")) as f:
        head = f.read(400)
    if "Apache License" not in head or "Version 2.0" not in head:
        raise SystemExit("LICENSE is not the Apache License 2.0 text")


def main(argv=None):
    sys.dont_write_bytecode = True          # no __pycache__ in notebook/
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["_trace"]:
        _trace_main(*argv[1:3])
        return 0
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out-root", default=os.path.join(REPO, "runs", "submission"),
                    help="the folder is written to OUT_ROOT/%s" % "/".join(PR_PATH))
    ap.add_argument("--all-data", action="store_true",
                    help="copy all of data/ and media/ instead of tracing a notebook run")
    ap.add_argument("--list", action="store_true", help="print the selected files, write nothing")
    a = ap.parse_args(argv)
    check_license()
    if a.list:
        modules, files = select(a.all_data)
        for p in [NOTEBOOK] + [m + ".py" for m in modules] + files + ["LICENSE", "README.md"]:
            print(p)
        return 0
    dest, listing = build(a.out_root, a.all_data)
    size = sum(os.path.getsize(os.path.join(dest, p)) for p in listing)
    for p in listing:
        print("  %9d  %s" % (os.path.getsize(os.path.join(dest, p)), p))
    per_dir = {}
    for p in listing:
        top = p.split(os.sep)[0] if os.sep in p else "."
        per_dir[top] = per_dir.get(top, 0) + 1
    print("%s: %d files (%s), %.2f MB" % (dest, len(listing), ", ".join(
        "%s %d" % kv for kv in sorted(per_dir.items())), size / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
