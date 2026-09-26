# SPDX-License-Identifier: Apache-2.0
"""Environment set-up for the notebook: live tools when they are there, cached data otherwise.

    import setup_env
    env = setup_env.setup()            # detect; on Colab also install; pick the mode
    print(env)                         # tool versions, paths, mode and why
    if env.live: ...                   # run the generator, the models and a short SPICE demo
    tc = setup_env.read_csv("tcurve_N_tvla.csv")   # precomputed results in data/

Modes
  live    the repository code, ngspice and the sky130A PDK at the pinned version are present.
          The notebook regenerates the netlists, runs the Python models and a short SPICE demo.
  cached  something is missing (for example in the organizers' CI, which installs only pytest,
          nbmake, pandas, graphviz and matplotlib). The notebook plots the precomputed results
          in data/ (written by make_cached_data.py) and calls no external tool.
  The environment variable ASCON_MODE=live|cached, or setup(mode=...), overrides the choice.
  Forcing live when a tool is missing raises an error that names it.

Installation (by default only on Google Colab; elsewhere with setup(install_tools=True),
ASCON_INSTALL=1 or `python3 setup_env.py --install`). Wall times measured in a clean Ubuntu 22.04
container with Python 3.12 (notebook/tests/colab_container.sh):
  apt-get update; apt-get install ngspice iverilog     24 s (ngspice-36, iverilog 11.0)
  pip install ciel==3.0.0                              8 s
  ciel enable --pdk-family sky130 -l sky130_fd_sc_hd -l sky130_fd_pr <PDK_HASH>
                                                       36 s, 457 MB under ~/.ciel
  git clone --depth 1 <REPO_URL>        only when the notebook runs without the repository
apt needs root (Colab runs as root); without it the apt step is skipped with a note.
ngspice-36 from apt gives the same supply-current traces as the ngspice-42 used for the
campaigns (same deck: largest difference 5e-5 uA, charge per window 2e-9 relative, same
registered outputs). Its transient analysis is as fast; it loads the sky130 models more
slowly and needs ~670 MB per process (ngspice-42: ~180 MB).

This file uses only the Python standard library at import time (numpy is imported by
read_csv), so it runs in any Python >= 3.8.
    python3 setup_env.py [--install] [--mode live|cached] [--check-data]
"""
import csv
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

# Pinned versions. PDK_HASH is the open_pdks commit the campaigns used (see the manifests).
PDK_HASH = "0fe599b2afb6708d281543108caf8310912f54af"
PDK_LIBRARIES = ("sky130_fd_sc_hd", "sky130_fd_pr")
CIEL_VERSION = "3.0.0"
APT_PACKAGES = ("ngspice", "iverilog")
REPO_URL = os.environ.get("ASCON_REPO_URL", "https://github.com/Sarkar22/ascon-glitch-leakage")
REPO_REF = os.environ.get("ASCON_REPO_REF", "main")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
# The live SPICE demo: naive masking (N) with the masks forced to zero, which leaks within
# ~40 traces. Its rows, chunking and settings match the shipped ngspice-42 reference
# (data/demo_reference_N_masksoff.csv, made by make_cached_data.py from reference_run).
DEMO = dict(campaign="N_masksoff", variant="N", stimulus="N_masksoff", mode="masks_off",
            n=1000, seed=201, rows=60, chunk=30, jobs=2, reference_run="runs/demo/N_masksoff")
# files that identify the repository root, and the PDK files the flow reads
REPO_MARKERS = ("gen/make_variants.py", "sim/spice_campaign.py", "model/stimulus.py")
PDK_FILES = ("libs.tech/ngspice/sky130.lib.spice",
             "libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice",
             "libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib",
             "libs.ref/sky130_fd_pr/spice")


def short_path(path):
    """A path for printing: relative to the working directory when it lies below it or one
    level up, else with ~ for the home directory.

    Keeps user names and local mount points out of saved notebook outputs."""
    if not path:
        return "-"
    path, cwd = os.path.abspath(path), os.getcwd()
    home = os.path.expanduser("~")

    def under(p, d):
        return p == d or p.startswith(d.rstrip(os.sep) + os.sep)
    rel = os.path.relpath(path, cwd)
    if cwd != os.sep and not rel.startswith(os.path.join("..", "..")) \
            and (under(cwd, home) or not under(path, home)):
        return rel
    if under(path, home):
        return "~" + path[len(home):]
    return path


def in_colab():
    """True inside Google Colab."""
    return "google.colab" in sys.modules or "COLAB_RELEASE_TAG" in os.environ


def _log(verbose, msg):
    if verbose:
        print(msg, flush=True)


def run(cmd, cwd=None, check=True, verbose=True, env=None):
    """Run a command (list or shell string), print its wall time; returns (seconds, output)."""
    t0 = time.time()
    p = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    dt = time.time() - t0
    text = cmd if isinstance(cmd, str) else " ".join(cmd)
    _log(verbose, "  [%6.1f s] %s" % (dt, text))
    if check and p.returncode != 0:
        raise RuntimeError("command failed (rc %d): %s\n%s" % (p.returncode, text, p.stdout[-3000:]))
    return dt, p.stdout


# ------------------------------------------------------------------ detection ---
def find_repo(start=None):
    """Root of the repository (the directory holding gen/, model/, sim/), or None.

    Looked for in $ASCON_REPO, then upwards from `start` (default: this file's directory),
    then upwards from the working directory, then in ./ascon-glitch-leakage."""
    cands = []
    if os.environ.get("ASCON_REPO"):
        cands.append(os.environ["ASCON_REPO"])
    for base in (start or HERE, os.getcwd()):
        d = os.path.abspath(base)
        while True:
            cands.append(d)
            up = os.path.dirname(d)
            if up == d:
                break
            d = up
    cands.append(os.path.join(os.getcwd(), "ascon-glitch-leakage"))
    for d in cands:
        if all(os.path.exists(os.path.join(d, m)) for m in REPO_MARKERS):
            return d
    return None


def pdk_candidates():
    """Places a sky130A PDK is looked for: $PDK, $PDK_ROOT/sky130A, ~/.ciel/sky130A."""
    out = []
    if os.environ.get("PDK") and os.path.isdir(os.environ["PDK"]):
        out.append(os.environ["PDK"])
    if os.environ.get("PDK_ROOT"):
        out.append(os.path.join(os.environ["PDK_ROOT"], "sky130A"))
    out.append(os.path.expanduser("~/.ciel/sky130A"))
    return out


def pdk_version(path):
    """open_pdks commit of a PDK directory (from its resolved path or its SOURCES file)."""
    m = re.search(r"[0-9a-f]{40}", os.path.realpath(path))
    if m:
        return m.group(0)
    src = os.path.join(path, "SOURCES")
    if os.path.exists(src):
        with open(src) as f:
            m = re.search(r"open_pdks\s+([0-9a-f]{40})", f.read())
        if m:
            return m.group(1)
    return None


def find_pdk():
    """(path, version, problem): the first complete sky130A PDK, or (None, None, reason)."""
    reason = "no sky130A PDK found (looked in %s)" % ", ".join(
        short_path(c) for c in pdk_candidates())
    for c in pdk_candidates():
        if not os.path.isdir(c):
            continue
        missing = [f for f in PDK_FILES if not os.path.exists(os.path.join(c, f))]
        if missing:
            reason = "PDK at %s lacks %s" % (short_path(c), ", ".join(missing))
            continue
        return os.path.realpath(c), pdk_version(c), None
    return None, None, reason


def tool_version(name):
    """Version string of ngspice or iverilog on PATH, or None."""
    exe = shutil.which(name)
    if exe is None:
        return None
    try:
        if name == "ngspice":
            out = subprocess.run([exe, "-v"], capture_output=True, text=True, timeout=60).stdout
            m = re.search(r"ngspice-(\S+)", out)
            return m.group(1) if m else "unknown"
        if name == "iverilog":
            out = subprocess.run([exe, "-V"], capture_output=True, text=True, timeout=60).stdout
            m = re.search(r"version\s+(\S+)", out)
            return m.group(1) if m else "unknown"
    except (OSError, subprocess.SubprocessError):
        return None
    return "present"


def _module_version(name):
    try:
        mod = __import__(name)
    except ImportError:
        return None
    return getattr(mod, "__version__", "present")


# ---------------------------------------------------------------- installation ---
def _is_root():
    return hasattr(os, "geteuid") and os.geteuid() == 0


def install(verbose=True, pdk=True, apt=True):
    """Install ngspice and iverilog (apt, needs root), ciel (pip) and the pinned PDK (ciel).

    Steps whose result is already present are skipped, so calling this again is cheap.
    Returns {step: seconds or a note}."""
    times = {}
    missing = [p for p in APT_PACKAGES if shutil.which(p) is None]
    if apt and missing:
        if _is_root():
            env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
            _log(verbose, "installing %s with apt-get" % " ".join(missing))
            t1, _ = run("apt-get -qq update", verbose=verbose, env=env)
            t2, _ = run("apt-get -qq install -y --no-install-recommends " + " ".join(missing),
                        verbose=verbose, env=env)
            times["apt"] = round(t1 + t2, 1)
        else:
            times["apt"] = "skipped: not root (install %s yourself)" % " ".join(missing)
            _log(verbose, times["apt"])
    path, version, _ = find_pdk()
    if pdk and (path is None or version != PDK_HASH):
        ciel = _ciel_command()
        if ciel is None:
            _log(verbose, "installing ciel %s with pip" % CIEL_VERSION)
            times["pip_ciel"] = round(run([sys.executable, "-m", "pip", "install", "-q",
                                           "ciel==" + CIEL_VERSION], verbose=verbose)[0], 1)
            ciel = _ciel_command()
        if ciel is None:
            raise RuntimeError("ciel was installed but cannot be run")
        root = os.environ.get("PDK_ROOT", os.path.expanduser("~/.ciel"))
        cmd = ciel + ["enable", "--pdk-root", root, "--pdk-family", "sky130"]
        for lib in PDK_LIBRARIES:
            cmd += ["-l", lib]
        _log(verbose, "fetching sky130 %s with ciel into %s" % (PDK_HASH[:8], short_path(root)))
        times["ciel_enable"] = round(run(cmd + [PDK_HASH], verbose=verbose)[0], 1)
    return times


def _ciel_command():
    exe = shutil.which("ciel") or os.path.join(os.path.dirname(sys.executable), "ciel")
    if os.path.exists(exe):
        return [exe]
    return None


def clone_repo(dest=None, verbose=True):
    """Shallow clone of the repository (for Colab, where only the notebook is opened)."""
    dest = dest or os.path.join(os.getcwd(), "ascon-glitch-leakage")
    if not os.path.exists(dest):
        run(["git", "clone", "-q", "--depth", "1", "--branch", REPO_REF, REPO_URL, dest],
            verbose=verbose)
    return dest


# ----------------------------------------------------------------- the switch ---
class Env:
    """What setup() found. mode is "live" or "cached"; reasons says why."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    @property
    def live(self):
        return self.mode == "live"

    def __str__(self):
        short = short_path
        rows = [("mode", self.mode + ("" if self.live else "  (" + "; ".join(self.reasons) + ")")),
                ("platform", "Google Colab" if self.colab else sys.platform),
                ("python", sys.version.split()[0]),
                ("numpy", self.numpy or "-"), ("matplotlib", self.matplotlib or "-"),
                ("ngspice", self.ngspice or "-"), ("iverilog", self.iverilog or "-"),
                ("PDK", short(self.pdk) + ("  (open_pdks %s)" % self.pdk_version[:10]
                                             if self.pdk_version else "")),
                ("repository", short(self.repo)), ("cached data", short(self.data_dir))]
        if self.install_times:
            rows.append(("installed", ", ".join("%s %s" % (k, v if isinstance(v, str)
                                                            else "%.1f s" % v)
                                                 for k, v in self.install_times.items())))
        return "\n".join("%-12s %s" % r for r in rows)


def setup(mode=None, install_tools=None, clone=None, verbose=True):
    """Detect the tools, install them if asked (default: on Colab), and choose the mode.

    mode           None (auto), "live" or "cached"; default from $ASCON_MODE
    install_tools  None (auto: only on Colab, or when $ASCON_INSTALL=1), True or False
    clone          None (auto: when installing and no repository is found), True or False
    On success in live mode, PDK is exported to the environment and the repository's
    model/, sim/ and analysis/ directories are put on sys.path."""
    mode = mode or os.environ.get("ASCON_MODE") or None
    if mode not in (None, "live", "cached"):
        raise ValueError("mode must be 'live' or 'cached'")
    colab = in_colab()
    if install_tools is None:
        install_tools = os.environ.get("ASCON_INSTALL") == "1" or (colab and mode != "cached")
    times = {}
    if install_tools and mode != "cached":
        times = install(verbose=verbose)
    repo = find_repo()
    if repo is None and (clone or (clone is None and install_tools and mode != "cached")):
        repo = clone_repo(verbose=verbose)
    pdk, pdk_ver, pdk_problem = find_pdk()
    ng = tool_version("ngspice")
    reasons = []
    if repo is None:
        reasons.append("repository code not found")
    if ng is None:
        reasons.append("ngspice not installed")
    if pdk is None:
        reasons.append(pdk_problem)
    elif pdk_ver != PDK_HASH:
        reasons.append("PDK version %s is not the pinned %s" % (pdk_ver, PDK_HASH[:10]))
    if mode == "live" and reasons:
        raise RuntimeError("live mode needs: " + "; ".join(reasons))
    chosen = mode or ("cached" if reasons else "live")
    if chosen == "cached" and mode == "cached":
        reasons = reasons or ["requested"]
    if chosen == "live":
        os.environ["PDK"] = pdk
        os.environ["ASCON_REPO"] = repo           # later calls (spice_demo) find it again
        for sub in ("model", "sim", "analysis"):
            p = os.path.join(repo, sub)
            if p not in sys.path:
                sys.path.insert(0, p)
    env = Env(mode=chosen, reasons=reasons, colab=colab, repo=repo, pdk=pdk,
              pdk_version=pdk_ver, ngspice=ng, iverilog=tool_version("iverilog"),
              numpy=_module_version("numpy"), matplotlib=_module_version("matplotlib"),
              data_dir=DATA_DIR, install_times=times)
    _log(verbose, str(env))
    return env


# ----------------------------------------------------------------- cached data ---
def data_path(name):
    """Path of a file in the cached data set (data/ next to this file)."""
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError("%s is not in the cached data (run make_cached_data.py)" % name)
    return path


def read_csv(name):
    """A cached CSV as {column: numpy array} (float columns where every value parses)."""
    import numpy as np
    with open(data_path(name), newline="") as f:
        rows = list(csv.reader(f))
    head, body = rows[0], rows[1:]
    out = {}
    for j, col in enumerate(head):
        vals = [r[j] for r in body]
        try:
            out[col] = np.array([float(v) if v != "" else np.nan for v in vals])
        except ValueError:
            out[col] = np.array(vals)
    return out


def read_matrix(name, key_cols=1):
    """A cached wide CSV as (keys, times, values).

    The first key_cols columns are per-row keys (returned as {column: array}); the other
    column names are sample times in ns after the capturing clock edge (returned as a float
    array) and their values form the 2-D array (rows, samples)."""
    import numpy as np
    with open(data_path(name), newline="") as f:
        rows = list(csv.reader(f))
    head, body = rows[0], rows[1:]
    keys = {head[j]: np.array([float(r[j]) for r in body]) for j in range(key_cols)}
    times = np.array([float(h) for h in head[key_cols:]])
    values = np.array([[float(v) for v in r[key_cols:]] for r in body])
    return keys, times, values


def check_data(verbose=True):
    """Verify every file listed in data/MANIFEST.csv against its size and sha256."""
    bad = []
    with open(data_path("MANIFEST.csv"), newline="") as f:
        for r in csv.DictReader(f):
            path = os.path.join(DATA_DIR, r["file"])
            if not os.path.exists(path):
                bad.append(r["file"] + " missing")
                continue
            with open(path, "rb") as g:
                h = hashlib.sha256(g.read()).hexdigest()
            if h != r["sha256"]:
                bad.append(r["file"] + " sha256 mismatch")
    _log(verbose, "cached data: %s" % ("all files match MANIFEST.csv" if not bad
                                        else "; ".join(bad)))
    return bad


# ------------------------------------------------------------- live SPICE demo ---
def spice_demo(jobs=None, verbose=True):
    """Run the live SPICE demo (DEMO) and compare it with the shipped ngspice-42 reference.

    Simulates the first DEMO["rows"] rows of naive masking (N) with the masks forced to zero
    in `jobs` parallel ngspice processes (python3 sim/spice_campaign.py, as in the campaigns),
    checks the registered outputs against the S-box, compares current and charge with
    data/demo_reference_N_masksoff.csv and runs TVLA on the rows. Needs live mode; takes
    ~2-6 min on 2 CPUs. Returns a dict with the arrays (times, traces, reference, label) and
    the comparison; prints a short report."""
    import json
    import numpy as np
    repo = find_repo()
    if repo is None or tool_version("ngspice") is None or find_pdk()[0] is None:
        raise RuntimeError("the SPICE demo needs live mode (see setup())")
    os.environ.setdefault("PDK", find_pdk()[0])
    for sub in ("model", "sim"):
        if os.path.join(repo, sub) not in sys.path:
            sys.path.insert(0, os.path.join(repo, sub))
    from ascon_sbox import SBOX_NP
    from stimulus import make_stimulus
    from tvla import tvla_curve
    d, jobs = DEMO, jobs or DEMO["jobs"]
    dut = os.path.join(repo, "build", d["variant"])
    if not os.path.exists(os.path.join(dut, "dut.sp")):
        run([sys.executable, "gen/make_variants.py"], cwd=repo, verbose=verbose)
    work = os.path.join(repo, "runs", "colab")
    os.makedirs(work, exist_ok=True)
    stim, meta = make_stimulus(dut, d["mode"], d["n"], d["seed"])
    stim_path = os.path.join(work, d["stimulus"] + ".npy")
    np.save(stim_path, stim)
    out = os.path.join(work, "spice_" + d["campaign"])
    _log(verbose, "SPICE demo: %d rows of %s (%s), %d ngspice processes"
         % (d["rows"], d["variant"], d["mode"], jobs))
    secs, _ = run([sys.executable, "sim/spice_campaign.py", "run", "--dut", dut, "--stim",
                   stim_path, "--out", out, "--rows", str(d["rows"]), "--chunk", str(d["chunk"]),
                   "--jobs", str(jobs), "--save-outputs"], cwd=repo, verbose=verbose)
    tr = np.load(os.path.join(out, "traces.npy")).astype(float)
    q = np.load(os.path.join(out, "charge.npy"))
    bits = np.load(os.path.join(out, "outputs.npy"))
    with open(os.path.join(out, "manifest.json")) as f:
        man = json.load(f)
    with open(os.path.join(dut, "ports.json")) as f:
        ports = json.load(f)
    y = np.zeros(len(bits), dtype=int)           # registered output, shares XORed
    for k, port in enumerate(ports["outputs"]):
        y ^= bits[:, k].astype(int) << (4 - port["bit"])
    keys, times, ref = read_matrix("demo_reference_%s.csv" % d["campaign"], key_cols=7)
    skip = man["latency"] + 1                    # rows that start from reset, as in the analysis
    label = meta["label"][:d["rows"]].astype(int)
    res = {"seconds": round(secs, 1), "ngspice": man["ngspice"], "jobs": jobs, "rows": d["rows"],
           "s_per_cycle_per_process": man["s_per_cycle_per_process"],
           "peak_rss_MB": man["peak_rss_MB_max"],
           "max_abs_diff_uA": float(np.abs(tr - ref).max()),
           "max_charge_rel_diff": float((np.abs(q - keys["charge_fC"]) / keys["charge_fC"]).max()),
           "outputs_equal_sbox": bool((y == SBOX_NP[meta["x"][:d["rows"]]]).all()),
           "outputs_equal_reference": bool((y == keys["y_registered"]).all()),
           "tvla_traces": d["rows"] - skip,
           "tvla_max_abs_t_live": float(tvla_curve(tr[skip:], label[skip:],
                                                   [d["rows"] - skip])["max_abs_t"][-1]),
           "tvla_max_abs_t_reference": float(tvla_curve(ref[skip:], label[skip:],
                                                        [d["rows"] - skip])["max_abs_t"][-1]),
           "times": times, "traces": tr, "reference": ref, "label": label, "skip": skip}
    res["ok"] = (res["max_abs_diff_uA"] <= 0.01 and res["max_charge_rel_diff"] <= 1e-6
                 and res["outputs_equal_sbox"] and res["outputs_equal_reference"])
    _log(verbose, "  %s: %.1f s (%.2f s per cycle per process, peak %d MB per process)"
         % (res["ngspice"], secs, res["s_per_cycle_per_process"], res["peak_rss_MB"]))
    _log(verbose, "  registered outputs = S-box(x) in all %d rows: %s"
         % (d["rows"], "yes" if res["outputs_equal_sbox"] else "NO"))
    _log(verbose, "  vs the shipped ngspice-42 reference: largest current difference %.1e uA, "
         "charge %.1e relative" % (res["max_abs_diff_uA"], res["max_charge_rel_diff"]))
    _log(verbose, "  TVLA fixed vs random on %d traces: max|t| %.2f (reference %.2f; > 4.5 = leak)"
         % (res["tvla_traces"], res["tvla_max_abs_t_live"], res["tvla_max_abs_t_reference"]))
    return res


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--install", action="store_true", help="install the tools (apt, pip, ciel)")
    ap.add_argument("--mode", choices=("live", "cached"), default=None)
    ap.add_argument("--check-data", action="store_true", help="verify data/ against MANIFEST.csv")
    a = ap.parse_args(argv)
    setup(mode=a.mode, install_tools=True if a.install else None)
    if a.check_data:
        return 1 if check_data() else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
