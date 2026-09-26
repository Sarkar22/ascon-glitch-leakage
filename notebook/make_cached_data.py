# SPDX-License-Identifier: Apache-2.0
"""Export the small data set the notebook plots in cached mode (notebook/data/, CSV).

The notebook runs in two modes (notebook/setup_env.py). In cached mode (no ngspice or PDK,
e.g. the organizers' CI) it plots only what this script writes. The raw SPICE trace matrices
(runs/kt/<campaign>/traces.npy, up to 64 MB each) are not exported. They are reduced to the
curves the notebook shows, plus small subsets. Everything is CSV except the JSON summaries
(the kill test's and those of later steps, see below), and MANIFEST.csv lists each file with
its size, sha256, source and meaning. Target: < 10 MB in total.

Inputs: results/ (committed) and the git-ignored campaign data in runs/kt/ (see
docs/KILL_TEST.md "Reproduce"). A campaign's traces are cut to the rows that
results/kill_test/summary.json analysed, so the exported curves always match the committed
results, also while a campaign is being extended. Re-run this script after
analysis/kill_test.py.

The live-demo reference (demo_reference_N_masksoff.csv) is the ngspice-42 run of exactly the
rows, chunking and settings that the notebook's live SPICE demo uses (setup_env.DEMO):
  python3 model/stimulus.py --dut build/N --mode masks_off --n 1000 --seed 201 \
      --out runs/kt/stim/N_masksoff.npy
  bash sim/docker_run.sh python3 sim/spice_campaign.py run --dut build/N \
      --stim runs/kt/stim/N_masksoff.npy --out runs/demo/N_masksoff --rows 60 --chunk 30 \
      --jobs 2 --save-outputs

Files written (per TVLA campaign <c> = U_tvla, N_masksoff, N_rvr, N_tvla, D_tvla, DA_tvla):
  tcurve_<c>.csv, maxt_vs_traces_<c>.csv, cpa_rank_vs_traces.csv, pernet_t_<V>_<src>.csv
      copies of results/kill_test/ (t per sample, max|t| vs traces, CPA ranks, per-net t)
  tvla_t_checkpoints_<c>.csv   first-order t per sample after 25 log-spaced trace counts
      (row key `traces`; the other column names are ns after the capturing clock edge)
  class_stats_<c>.csv          per sample: mean and std of the supply current per class
  traces_first50_<c>.csv       the first 50 analysed SPICE traces (uA) with label, x, mask,
      r, charge per window; column names after `charge_fC` are ns after the edge
  charge_models_<c>.csv        per row, first 2,000 analysed rows: charge per window in SPICE
      (fC) and the level-1 / level-2 cap-weighted toggle charge (fF, same rows)
  node_events_<V>.csv          SPICE VDD/2 crossings of every net (glitches included) of
      the first rows of the node re-runs (N: 200 rows, D: 100 rows)
  rows_M_tvla.csv              label, x, mask, r of the first 2,000 rows of the shared
      N/D/DA stimulus (seed 202)
  campaigns.csv, variants.csv, probing_nets.csv, kill_test_summary.json
  demo_reference_N_masksoff.csv   see above
  <dir>__<file>               CSV and JSON files of later steps, copied if they exist:
      results/{key_recovery,cost,layout,pex}/*.{csv,json} (--optional limits which, e.g.
      while a step is still writing its results)

    python3 notebook/make_cached_data.py [--out notebook/data] [--optional key_recovery cost]
                                                                   (host python3 + numpy)
"""
import argparse
import csv
import hashlib
import json
import os
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "analysis"))
sys.path.insert(0, HERE)

import kill_test as kt                    # noqa: E402  (also puts model/ and sim/ on the path)
import setup_env                          # noqa: E402
from tvla import WelchT                   # noqa: E402

RESULTS = os.path.join(REPO, "results", "kill_test")
N_CHECKPOINTS = 25
N_TRACES = 50
N_CHARGE_ROWS = 2000
NODE_ROWS = {"N": 200, "D": 100}
OPTIONAL_RESULTS = ("key_recovery", "cost", "layout", "pex")
DESCRIPTIONS = {}          # file -> (source, description), filled while writing


def note(name, source, text):
    DESCRIPTIONS[name] = (source, text)


def write_csv(out, name, header, rows, source, text):
    with open(os.path.join(out, name), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    note(name, source, text)


def fmt(values, digits):
    return ["%.*f" % (digits, v) for v in values]


def time_axis(n_samples, dt, pre):
    """Sample centres in ns after the capturing clock edge."""
    return (np.arange(n_samples) + 0.5) * dt - pre


def log_checkpoints(n, first=20, count=N_CHECKPOINTS):
    k = np.unique(np.round(np.logspace(np.log10(first), np.log10(n), count)).astype(int))
    return sorted(set(int(v) for v in k if v <= n) | {n})


# --------------------------------------------------------------------- copies ---
def copy_results(out):
    for name in sorted(os.listdir(RESULTS)):
        if name.endswith(".csv"):
            shutil.copyfile(os.path.join(RESULTS, name), os.path.join(out, name))
            note(name, "results/kill_test/" + name, "copy of the committed kill-test result")
    shutil.copyfile(os.path.join(RESULTS, "summary.json"), os.path.join(out, "kill_test_summary.json"))
    note("kill_test_summary.json", "results/kill_test/summary.json",
         "every number of docs/KILL_TEST.md (written by analysis/kill_test.py)")


def copy_optional(out, dirs=OPTIONAL_RESULTS):
    found, missing = [], []
    for d in dirs:
        src = os.path.join(REPO, "results", d)
        files = sorted(f for f in os.listdir(src) if f.endswith((".csv", ".json"))) \
            if os.path.isdir(src) else []
        if not files:
            missing.append(d)
        for f in files:
            name = "%s__%s" % (d, f)
            shutil.copyfile(os.path.join(src, f), os.path.join(out, name))
            note(name, "results/%s/%s" % (d, f), "copy of a later step's result")
            found.append(name)
    return found, missing


def probing_table(out):
    rows = []
    for v in ("N", "D", "DA"):
        with open(os.path.join(REPO, "results", "probing", v + ".json")) as f:
            p = json.load(f)
        for n in p["nets"]:
            rows.append([v, n["net"], n["kind"], n.get("domain", ""), int(not n["value_ok"]),
                         int(not n["glitch_ok"]), " ".join("x%d" % b for b in n.get("both_shares_of") or [])])
    write_csv(out, "probing_nets.csv",
              ["variant", "net", "kind", "domain", "value_model_fail", "glitch_extended_fail",
               "both_shares_of"], rows, "results/probing/<V>.json",
              "exact first-order probing per net: 1 = the net's (glitch-extended) observation "
              "depends on the unshared input")


def variants_table(out, summary):
    rows = []
    for v, s in summary["setup"]["variants"].items():
        ports = os.path.join(REPO, "build", v, "ports.json")
        extra = {}
        if os.path.exists(ports):
            with open(ports) as f:
                extra = json.load(f)
        rows.append([v, s["n_cells"], s["n_dff"], s["latency"], extra.get("area_um2", ""),
                     extra.get("reg_to_reg_ps", ""), s["wire_cap_fF"], s["dut_sp_sha256"],
                     extra.get("description", "")])
    write_csv(out, "variants.csv",
              ["variant", "cells", "flip_flops", "latency_cycles", "cell_area_um2",
               "reg_to_reg_ps_liberty", "wire_cap_fF", "dut_sp_sha256", "description"], rows,
              "results/kill_test/summary.json (setup), build/<V>/ports.json",
              "the four netlist variants (pre-layout cell area; dut_sp_sha256 checks a rebuild)")


def campaigns_table(out, summary):
    rows = []
    for name, c in summary["campaigns"].items():
        man = kt.load_manifest(os.path.join(kt.RUNS, name))
        stem = os.path.basename(c["stimulus"])[:-4]
        meta = np.load(os.path.join(kt.STIM, stem + ".meta.npz"))
        sp = c["spice"]
        rows.append([name, c["variant"], c["role"], stem, str(meta["mode"]), int(meta["seed"]),
                     man["stimulus_rows_in_file"], c["rows_simulated"], c["dropped_first_rows"],
                     c["rows_analysed"], man["params"]["chunk"], man["stimulus_sha256"],
                     man["dut_sp_sha256"], man["ngspice"], c["functional_mismatches"],
                     sp["final_max_abs_t"], sp["first_above"] or "", sp["final_peak_ns_after_edge"],
                     c["spice_process_s"]])
    write_csv(out, "campaigns.csv",
              ["campaign", "variant", "role", "stimulus", "stimulus_mode", "stimulus_seed",
               "stimulus_rows_in_file", "rows_simulated", "dropped_first_rows", "traces",
               "spice_chunk", "stimulus_sha256", "dut_sp_sha256", "ngspice",
               "functional_mismatches", "spice_max_abs_t", "spice_first_above_4p5",
               "spice_peak_ns_after_edge", "spice_process_s"], rows,
              "results/kill_test/summary.json, runs/kt/<c>/manifest.json",
              "one row per SPICE campaign: stimulus, hashes, simulator and headline TVLA result")


# ---------------------------------------------------------------- from runs/ ---
def campaign_exports(out, name, variant, stem, summary):
    c = kt.load_campaign(name, variant, stem)
    if c is None:
        print("  %s: no traces in runs/kt, skipped" % name)
        return
    n_sim = summary["campaigns"][name]["rows_simulated"]
    if len(c["traces"]) < n_sim:
        raise RuntimeError("%s has %d rows, summary.json analysed %d" % (name, len(c["traces"]), n_sim))
    p = c["man"]["params"]
    dt, pre, skip = p["dt"], p["pre"], c["skip"]
    tr = c["traces"][skip:n_sim]
    n = len(tr)
    meta = c["meta"]
    lab = meta["label"][skip:n_sim]
    times = fmt(time_axis(tr.shape[1], dt, pre), 3)
    src = "runs/kt/%s/traces.npy (rows %d-%d)" % (name, skip, n_sim - 1)

    # t per sample at log-spaced trace counts
    acc, done, rows = WelchT(tr.shape[1]), 0, []
    for cp in log_checkpoints(n):
        acc.update(tr[done:cp], lab[done:cp])
        done = cp
        rows.append([cp] + fmt(acc.t(1), 2))
    write_csv(out, "tvla_t_checkpoints_%s.csv" % name, ["traces"] + times, rows, src,
              "first-order Welch t per 10 ps sample after `traces` traces (TVLA slider)")

    # class statistics
    f, r = tr[lab == 0], tr[lab == 1]
    rows = [[times[j], "%.4f" % f[:, j].mean(), "%.4f" % r[:, j].mean(),
             "%.4f" % f[:, j].std(ddof=1), "%.4f" % r[:, j].std(ddof=1)] for j in range(tr.shape[1])]
    write_csv(out, "class_stats_%s.csv" % name,
              ["ns_after_edge", "mean_fixed_uA", "mean_random_uA", "std_fixed_uA", "std_random_uA"],
              rows, src, "supply current per class over %d traces (%d fixed, %d random); label 0 = "
              "fixed" % (n, len(f), len(r)))

    # a few traces
    q = np.load(os.path.join(c["run"], "charge.npy"))[skip:n_sim]
    k = min(N_TRACES, n)
    rows = [[skip + i, int(lab[i]), int(meta["x"][skip + i]), int(meta["mask"][skip + i]),
             int(meta["r"][skip + i]), "%.4f" % q[i]] + fmt(tr[i], 2) for i in range(k)]
    write_csv(out, "traces_first%d_%s.csv" % (N_TRACES, name),
              ["row", "label", "x", "mask", "r", "charge_fC"] + times, rows, src,
              "the first %d analysed supply-current traces (uA per 10 ps bin)" % k)

    # per-row charge: SPICE vs the level-1 and level-2 models on the same rows
    m = min(N_CHARGE_ROWS, n)
    l1 = kt.model_rows(variant, c["stim"], skip + m, 1, c["man"])["weighted"].sum(1)
    l2 = kt.model_rows(variant, c["stim"], skip + m, 2, c["man"])["weighted"].sum(1)
    rows = [[skip + i, int(lab[i]), "%.4f" % q[i], "%.3f" % l1[i], "%.3f" % l2[i]] for i in range(m)]
    write_csv(out, "charge_models_%s.csv" % name,
              ["row", "label", "spice_charge_fC", "level1_weighted_fF", "level2_weighted_fF"], rows,
              src + ", model/toggle.py, model/glitch.py",
              "charge per window, SPICE vs the zero-delay (level 1) and timing-aware (level 2) "
              "models, first %d analysed rows" % m)


def node_events(out):
    for v, k in NODE_ROWS.items():
        path = os.path.join(kt.RUNS, "%s_nodes" % v, "events.npz")
        if not os.path.exists(path):
            print("  %s: no node events, skipped" % path)
            continue
        z = np.load(path)
        names = z["net_names"]
        keep = z["cycle"] < k
        order = np.lexsort((z["t_ns"][keep], z["cycle"][keep]))
        cyc, net = z["cycle"][keep][order], z["net"][keep][order]
        t, rise = z["t_ns"][keep][order], z["rise"][keep][order]
        rows = [[int(cyc[i]), names[net[i]], "%.4f" % t[i], int(rise[i])] for i in range(len(cyc))]
        write_csv(out, "node_events_%s.csv" % v, ["cycle", "net", "t_ns_from_window_start", "rise"],
                  rows, "runs/kt/%s_nodes/events.npz" % v,
                  "SPICE VDD/2 crossings of every net, cycles 0-%d of the node re-run on the "
                  "shared stimulus (rows_M_tvla.csv); window starts %.1f ns before the capturing "
                  "edge, period %.1f ns, latency %d" % (k - 1, float(z["pre"]), float(z["period"]),
                                                        int(z["latency"])))


def stim_rows(out, k=2000):
    meta = np.load(os.path.join(kt.STIM, "M_tvla.meta.npz"))
    rows = [[i, int(meta["label"][i]), int(meta["x"][i]), int(meta["mask"][i]), int(meta["r"][i])]
            for i in range(k)]
    write_csv(out, "rows_M_tvla.csv", ["row", "label", "x", "mask", "r"], rows,
              "runs/kt/stim/M_tvla.meta.npz (model/stimulus.py, tvla, seed 202)",
              "first %d rows of the stimulus shared by N_tvla, D_tvla and DA_tvla; label 0 = fixed "
              "x = 0x0B; mask = share 1, r = fresh bits" % k)


def demo_reference(out):
    d = setup_env.DEMO
    run = os.path.join(REPO, d["reference_run"])
    if not os.path.exists(os.path.join(run, "traces.npy")):
        print("  %s missing: make it with the command in this file's docstring" % d["reference_run"])
        return False
    man = kt.load_manifest(run)
    p = man["params"]
    if (man["rows"], p["chunk"]) != (d["rows"], d["chunk"]):
        raise RuntimeError("reference run does not match setup_env.DEMO")
    tr = np.load(os.path.join(run, "traces.npy"))
    q = np.load(os.path.join(run, "charge.npy"))
    y = np.load(os.path.join(run, "outputs.npy"))
    meta = np.load(os.path.join(kt.STIM, d["stimulus"] + ".meta.npz"))
    times = fmt(time_axis(tr.shape[1], p["dt"], p["pre"]), 3)
    with open(os.path.join(REPO, "build", d["variant"], "ports.json")) as f:
        ports = json.load(f)
    yv = np.zeros(len(y), dtype=int)          # unshared registered output (XOR of the shares)
    for k, port in enumerate(ports["outputs"]):
        yv ^= y[:, k].astype(int) << (4 - port["bit"])
    rows = []
    for i in range(len(tr)):
        rows.append([i, int(meta["label"][i]), int(meta["x"][i]), int(meta["mask"][i]),
                     int(meta["r"][i]), int(yv[i]), "%.6f" % q[i]] + fmt(tr[i], 4))
    write_csv(out, "demo_reference_%s.csv" % d["campaign"],
              ["row", "label", "x", "mask", "r", "y_registered", "charge_fC"] + times, rows,
              "%s (%s, pdk %s)" % (d["reference_run"], man["ngspice"], man["pdk"]["version"][:10]),
              "reference for the live SPICE demo: same rows (%d), chunking (%d) and settings; "
              "y_registered = the registered S-box output (shares XORed), 5-bit value, y0 = MSB"
              % (d["rows"], d["chunk"]))
    return True


def manifest(out):
    rows = []
    for name in sorted(os.listdir(out)):
        if name == "MANIFEST.csv":
            continue
        path = os.path.join(out, name)
        with open(path, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
        src, text = DESCRIPTIONS.get(name, ("", ""))
        rows.append([name, os.path.getsize(path), h, src, text])
    write_csv(out, "MANIFEST.csv", ["file", "bytes", "sha256", "source", "description"], rows, "", "")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(HERE, "data"))
    ap.add_argument("--jobs", type=int, default=2, help="processes for the level-2 model")
    ap.add_argument("--optional", nargs="*", default=list(OPTIONAL_RESULTS), choices=OPTIONAL_RESULTS,
                    help="later-step result folders to copy (default: all)")
    a = ap.parse_args()
    kt.JOBS = a.jobs
    if os.path.isdir(a.out):
        for f in os.listdir(a.out):          # start clean: no stale file survives a re-run
            if f.endswith((".csv", ".json")):
                os.remove(os.path.join(a.out, f))
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(RESULTS, "summary.json")) as f:
        summary = json.load(f)
    copy_results(a.out)
    probing_table(a.out)
    variants_table(a.out, summary)
    campaigns_table(a.out, summary)
    for name, (variant, stem, _) in kt.TVLA_RUNS.items():
        print("exporting %s" % name, flush=True)
        campaign_exports(a.out, name, variant, stem, summary)
    node_events(a.out)
    stim_rows(a.out)
    demo_reference(a.out)
    found, missing = copy_optional(a.out, a.optional)
    rows = manifest(a.out)
    total = sum(r[1] for r in rows)
    print("%d files, %.2f MB in %s" % (len(rows), total / 1e6, setup_env.short_path(a.out)))
    if found:
        print("later-step results copied: " + ", ".join(found))
    if missing:
        print("not there yet: results/{%s}/*.{csv,json}" % ",".join(missing))


if __name__ == "__main__":
    main()
