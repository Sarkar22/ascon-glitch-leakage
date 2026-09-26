# SPDX-License-Identifier: Apache-2.0
"""Post-layout TVLA: the analysis registered in docs/POSTLAYOUT.md.

Campaigns (git-ignored, made by runs/pex/queue.sh; see layout/README.md):
  runs/pex/N_pex_tvla     build/N_pex,  rows 0-4,999 of runs/kt/stim/M_tvla.npy   (PL1)
  runs/pex/DA_pex_tvla    build/DA_pex, rows 0-9,999 of the same file              (PL2)
The trace counts are fixed by the registration: 5,000 and 10,000 rows, no early stop and no
extension. Pre-layout on the same rows: runs/kt/N_tvla and runs/kt/DA_tvla cut to the same
number of rows.

The test is the kill test's first-order TVLA, called through analysis/kill_test.py's own
functions (checkpoints, tvla_block -> model/tvla.py tvla_curve -> WelchT): fixed (x = 0x0B)
vs random, Welch t per 10 ps sample over the whole window, the first L+1 rows dropped,
threshold |t| > 4.5, max|t| against the kill test's trace checkpoints. spice_tvla() repeats
the SPICE part of kill_test.analyse_tvla() step for step (second order, 100 ps bins, charge
per window, added noise with the same noise unit and seeds). As a check that it is the same
code path, it is also run on the full pre-layout N_tvla and DA_tvla campaigns and must give
exactly their "spice" blocks in results/kill_test/summary.json (`reproduces_kill_test`).

Reported alongside (not pass/fail): 100 ps bins, charge per window, second order, added
noise, function check (registered outputs vs the S-box, and vs the pre-layout outputs of the
same rows), the pre-layout values on the same rows, max|t| by part of the cycle with the
registered post-layout boundaries (PL3), the smallest effect TVLA could detect for DA_pex as
a fraction of N_pex's measured effect (PL3; t = d sqrt(n) / 2, as in docs/KILL_TEST.md), the
charge per evaluation before and after layout, and two checks named in the registration and
in docs/reviews/stage3-layout-pex.md: KLU against the default solver (check 14), and the
current netlist text against the earlier one on the same rows (note N2); and the logic nets'
capacitance in three views, pre-layout estimate, Magic's flat extraction and OpenROAD's routed
wiring (note N1).

Outputs: results/pex/summary_postlayout.json, results/pex/tcurve_<V>_pex.csv,
results/pex/maxt_vs_traces_<V>_pex.csv. Figures: analysis/plot_postlayout.py.

  python3 analysis/postlayout.py          (host python3 + numpy; about a minute)
"""
import csv
import datetime
import json
import os
import sys

import numpy as np

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(REPO, "analysis"))

import kill_test as kt                     # noqa: E402  (also puts model/ and sim/ on the path)
import cost_table as ct                    # noqa: E402
from tvla import THRESHOLD, add_noise, tvla_curve    # noqa: E402

PEX = os.path.join(REPO, "runs", "pex")
OUT = os.path.join(REPO, "results", "pex")
STEM = "M_tvla"
NOISE = kt.NOISE

# The registration: campaign -> (variant, run directory, pre-layout campaign, fixed rows, criterion)
CAMPAIGNS = {
    "N_pex": ("N", os.path.join(PEX, "N_pex_tvla"), "N_tvla", 5000, "PL1"),
    "DA_pex": ("DA", os.path.join(PEX, "DA_pex_tvla"), "DA_tvla", 10000, "PL2"),
}
CRITERIA = {
    "PL1": ("N_pex: max|t| > 4.5 (the leak survives place and route), 5,000 rows", True),
    "PL2": ("DA_pex: max|t| < 4.5 (the fix survives place and route), 10,000 rows", False),
}
# Parts of each clock cycle after layout, ns after that cycle's capturing edge at the block's
# CLK pin (docs/POSTLAYOUT.md, from results/pex/node_timing_N.json); for latency 2 the same
# parts are used in each cycle. The evaluation tail and the clock fall overlap after layout:
# a peak between 2.0 and 2.2 ns is reported with that caveat.
PARTS_POST = (("edge_and_evaluation", -0.2, 2.1), ("clock_fall", 2.1, 2.9), ("input_edges", 2.9, 3.8))
OVERLAP_NS = (2.0, 2.2)
# KLU vs the default (Sparse) solver on the same netlist and rows (layout/README.md,
# docs/reviews/stage3-layout-pex.md check 14), and the current netlist text vs the earlier
# one (note N2): (reference run, compared run)
SOLVER_RUNS = {"N": ("bench_N_pex", "bench_N_pex_klu"), "DA": ("bench_DA_pex", "bench_DA_pex_klu")}
TEXT_RUNS = {"N": ("bench_N_pex_klu", "N_pex_tvla"), "DA": ("bench_DA_pex_klu", "DA_pex_tvla")}


def rel(path):
    return os.path.relpath(path, REPO)


# ------------------------------------------------------------------ loading

def load_run(run, variant, rows=None, name=None):
    """A SPICE campaign as the dict kill_test.load_campaign returns, cut to `rows` rows."""
    man = kt.load_manifest(run)
    tr = np.load(os.path.join(run, "traces.npy")).astype(np.float64)
    q = np.load(os.path.join(run, "charge.npy"))
    op = os.path.join(run, "outputs.npy")
    outputs = np.load(op) if os.path.exists(op) else None
    if rows is not None:
        if len(tr) < rows:
            raise RuntimeError("%s has %d rows, %d needed" % (rel(run), len(tr), rows))
        tr, q = tr[:rows], q[:rows]
        outputs = outputs[:rows] if outputs is not None else None
    meta = dict(np.load(os.path.join(kt.STIM, STEM + ".meta.npz")))
    lat = man["latency"]
    return dict(name=name or os.path.basename(run), variant=variant, run=run, man=man, traces=tr,
                charge=q, outputs=outputs, meta=meta, lat=lat, skip=lat + 1, n_sim=len(tr))


# ------------------------------------------------------------------ the test

def region_max(t, dt, pre, T, lat, parts):
    """max|t| per part of each clock cycle (kill_test.region_max with other boundaries)."""
    tns = (np.arange(len(t)) + 0.5) * dt - pre
    out = {}
    for c in range(lat):
        for name, a, b in parts:
            m = (tns >= a + c * T) & (tns < b + c * T)
            if m.any():
                key = name if lat == 1 else "cycle%d_%s" % (c + 1, name)
                out[key] = round(float(np.abs(t[m]).max()), 3)
    return out


def post_regions(t, dt, pre, T, lat):
    return region_max(t, dt, pre, T, lat, PARTS_POST)


def spice_tvla(c, regions=kt.region_max):
    """The SPICE part of kill_test.analyse_tvla, step for step: first-order TVLA at the kill
    test's checkpoints (pass/fail), second order, 100 ps bins, charge per window, added noise
    (noise unit: the largest per-sample std of the noiseless traces; seeds 1000 + 10 f) and
    max|t| by part of the cycle (`regions`). Returns (spice block, final t, labels, traces)."""
    man, lat, skip = c["man"], c["lat"], c["skip"]
    p = man["params"]
    dt, pre, T = p["dt"], p["pre"], p["period"]
    tr = c["traces"][skip:]
    n = len(tr)
    labels = c["meta"]["label"][skip:skip + n]
    cps = kt.checkpoints(n)
    sp = kt.tvla_block(tr, labels, cps, dt, pre, keep_t=True)
    t_spice = sp.pop("_t")
    t2 = tvla_curve(tr, labels, [n], order=2)
    sp["second_order_final_max_abs_t"] = round(float(np.abs(t2["t_final"]).max()), 3)
    tr100 = tr.reshape(n, -1, 10).mean(2)
    r100 = tvla_curve(tr100, labels, [n])
    sp["final_max_abs_t_100ps_bins"] = round(float(r100["max_abs_t"][-1]), 3)
    q = c["charge"][skip:skip + n]
    rq = tvla_curve(q, labels, cps)
    sp["charge_per_window"] = {"final_abs_t": round(float(rq["max_abs_t"][-1]), 3),
                               "first_above": kt.curve_stats(rq)[0]}
    sig = kt.noise_sigma(tr)
    sp["noise_unit_uA"] = round(sig, 4)
    sp["noise"] = {}
    for f in NOISE:
        rn = tvla_curve(add_noise(tr, f * sig, seed=1000 + int(10 * f)), labels, cps)
        fa, st = kt.curve_stats(rn)
        sp["noise"][str(f)] = {"final_max_abs_t": round(float(rn["max_abs_t"][-1]), 3),
                               "first_above": fa, "stable_from": st,
                               "max_abs_t": np.round(rn["max_abs_t"], 3).tolist()}
    sp["max_abs_t_by_region"] = regions(t_spice, dt, pre, T, lat)
    return sp, t_spice, labels, tr


def part_of(ns, T, lat, parts=PARTS_POST):
    """(cycle, part) of a time in ns after the first capturing edge, or (None, None)."""
    for c in range(lat):
        for name, a, b in parts:
            if a + c * T <= ns < b + c * T:
                return c + 1, name
    return None, None


def peak_info(t, dt, pre, T, lat, seg=20, top=6):
    """Where the t-peaks sit: the largest |t| overall and per 200 ps segment (segments whose
    largest |t| exceeds the threshold, largest first), each with its cycle part; and the first
    and last sample above the threshold."""
    tns = (np.arange(len(t)) + 0.5) * dt - pre

    def entry(k):
        cyc, part = part_of(tns[k], T, lat)
        e = {"ns_after_edge": round(float(tns[k]), 3), "t": round(float(t[k]), 3), "part": part}
        if lat > 1:
            e["cycle"] = cyc
        local = tns[k] - (cyc - 1) * T if cyc else None
        e["in_overlap_2.0_to_2.2"] = bool(local is not None and OVERLAP_NS[0] <= local <= OVERLAP_NS[1])
        return e
    a = np.abs(t)
    k = int(np.argmax(a))
    out = {"peak": entry(k)}
    m = len(a) - len(a) % seg
    blocks = a[:m].reshape(-1, seg)
    order = np.argsort(-blocks.max(1))
    out["peaks_above_threshold_by_200ps_segment"] = [
        entry(int(s * seg + np.argmax(blocks[s]))) for s in order[:top] if blocks[s].max() > THRESHOLD]
    above = np.flatnonzero(a > THRESHOLD)
    out["samples_above_threshold"] = int(len(above))
    out["first_last_sample_above_threshold_ns"] = (
        [round(float(tns[above[0]]), 3), round(float(tns[above[-1]]), 3)] if len(above) else None)
    return out


def effect_sd(t, n):
    """Standardized mean difference that gives Welch t with n traces: t = d sqrt(n) / 2."""
    return 2.0 * float(t) / np.sqrt(n)


def detectable_fraction(n_test, t_ref, n_ref, threshold=THRESHOLD):
    """The leak TVLA reaches `threshold` for on average at n_test traces, as a fraction of a
    reference effect measured as max|t| t_ref at n_ref traces (cost_table.tvla_detectable_fraction)."""
    return effect_sd(threshold, n_test) / effect_sd(t_ref, n_ref)


# ------------------------------------------------------------------ side results

def function_check(c, pre):
    """Registered outputs vs the S-box (kill_test.functional_check, on build/<V>_pex/ports.json)
    and vs the pre-layout campaign's outputs of the same rows."""
    d = {"outputs": c["outputs"], "variant": c["variant"] + "_pex", "meta": c["meta"]}
    out = {"rows": c["n_sim"], "mismatches_vs_sbox": kt.functional_check(d)}
    if c["outputs"] is not None and pre["outputs"] is not None:
        out["rows_differing_from_pre_layout_outputs"] = int(
            (c["outputs"][:c["n_sim"]] != pre["outputs"][:c["n_sim"]]).any(axis=1).sum())
    return out


def energy(c):
    """Mean charge per evaluation over the random-class rows whose whole neighbourhood is
    random-class too (the cost table's definition, analysis/cost_table.py)."""
    lat, n = c["lat"], c["n_sim"]
    random_row = c["meta"]["label"][:n] == 1
    clean = ct.random_neighbourhood(random_row, lat, lat + 1)
    p = c["man"]["params"]
    s = ct.charge_stats(c["charge"][clean], lat, p["vdd"], p["period"])
    return {k: round(v, 3) if isinstance(v, float) else v for k, v in s.items()}


def curve_shift(t_pre, t_post, dt, max_ns=1.0):
    """Shift of the post-layout t-curve against the pre-layout one that best aligns them
    (Pearson correlation of the signed curves; positive = post-layout later)."""
    best, c0 = None, None
    n = len(t_pre)
    for lag in range(-int(round(max_ns / dt)), int(round(max_ns / dt)) + 1):
        if lag >= 0:
            a, b = t_pre[:n - lag], t_post[lag:]
        else:
            a, b = t_pre[-lag:], t_post[:n + lag]
        cc = float(np.corrcoef(a, b)[0, 1])
        if lag == 0:
            c0 = cc
        if best is None or cc > best[1]:
            best = (lag, cc)
    return {"corr_no_shift": round(c0, 4), "best_shift_ns": round(best[0] * dt, 3),
            "corr_at_best_shift": round(best[1], 4)}


def compare_runs(ref, other, skip, rows=None):
    """Per-bin and per-window differences of two SPICE runs of the same stimulus rows."""
    a = np.load(os.path.join(PEX, ref, "traces.npy")).astype(np.float64)
    b = np.load(os.path.join(PEX, other, "traces.npy")).astype(np.float64)
    qa = np.load(os.path.join(PEX, ref, "charge.npy"))
    qb = np.load(os.path.join(PEX, other, "charge.npy"))
    m = min(len(a), len(b)) if rows is None else rows
    a, b, qa, qb = a[skip:m], b[skip:m], qa[skip:m], qb[skip:m]
    da, db = a - a.mean(0), b - b.mean(0)
    ma, mb = kt.load_manifest(os.path.join(PEX, ref)), kt.load_manifest(os.path.join(PEX, other))
    return {"reference": "runs/pex/" + ref, "compared": "runs/pex/" + other, "rows": [skip, m - 1],
            "reference_dut_sp_sha256": ma["dut_sp_sha256"][:8], "compared_dut_sp_sha256": mb["dut_sp_sha256"][:8],
            "reference_solver": ma["params"]["options"] or "sparse",
            "compared_solver": mb["params"]["options"] or "sparse",
            "reference_chunk_rows": ma["params"]["chunk"], "compared_chunk_rows": mb["params"]["chunk"],
            "max_abs_diff_per_bin_uA": round(float(np.abs(a - b).max()), 3),
            "rms_diff_per_bin_uA": round(float(np.sqrt(((a - b) ** 2).mean())), 4),
            "peak_current_uA": round(float(np.abs(a).max()), 1),
            "max_rel_charge_diff": float("%.3g" % np.abs(qb / qa - 1).max()),
            "corr_data_dependent": round(float((da * db).sum() / np.sqrt((da * da).sum() * (db * db).sum())), 7)}


def spef_caps(path):
    """Total capacitance (fF) of every net in an OpenRCX SPEF file (*D_NET lines, PIN_CAP NONE,
    coupling included), by net name."""
    with open(path) as f:
        lines = f.read().split("\n")
    names, caps, scale = {}, {}, 1000.0
    in_map = False
    for ln in lines:
        w = ln.split()
        if not w:
            continue
        if w[0] == "*C_UNIT":
            scale = float(w[1]) * {"PF": 1000.0, "FF": 1.0}[w[2].upper()]
        elif w[0] == "*NAME_MAP":
            in_map = True
        elif in_map and len(w) == 2 and w[0].startswith("*") and w[0][1:].isdigit():
            names[w[0]] = w[1]
        elif w[0] == "*D_NET":
            in_map = False
            caps[names.get(w[1], w[1])] = float(w[2]) * scale
        elif w[0].startswith("*") and not w[0][1:].isdigit():
            in_map = False
    return caps


def capacitance_views(variants=("N", "DA", "U")):
    """The logic nets' capacitance in three views (docs/reviews/stage3-layout-pex.md, N1): the
    pre-layout estimate, Magic's flat extraction (cell pin geometry and coupling to cell-internal
    nodes included; results/pex/netcap_<V>.csv) and OpenROAD's extraction of the routed wiring
    alone (the final SPEF of the OpenLane run, git-ignored)."""
    out = {}
    for v in variants:
        with open(os.path.join(OUT, "netcap_%s.csv" % v)) as f:
            rows = list(csv.DictReader(f))
        spef = os.path.join(PEX, "ol", v, "runs", "pex", "results", "final", "spef", "dut_%s.spef" % v)
        e = {"nets": len(rows), "prelayout_estimate_fF": round(sum(float(r["prelayout_fF"]) for r in rows), 1),
             "magic_flat_fF": round(sum(float(r["extracted_total_fF"]) for r in rows), 1)}
        if os.path.exists(spef):
            caps = spef_caps(spef)
            per = [(float(r["extracted_total_fF"]), caps[r["net"]]) for r in rows]
            e["openrcx_routed_wiring_fF"] = round(sum(b for _, b in per), 1)
            ratio = [a / b for a, b in per if b > 0]
            e["magic_over_openrcx_per_net"] = {"min": round(min(ratio), 2), "median": round(float(np.median(ratio)), 2),
                                               "max": round(max(ratio), 2)}
            e["openrcx_source"] = rel(spef)
        e["magic_over_estimate"] = round(e["magic_flat_fF"] / e["prelayout_estimate_fF"], 2)
        out[v] = e
    return out


def wall_clock(c):
    ch = [x["wall_s"] for x in c["man"]["chunks"]]
    return {"wall_s": round(c["man"]["wall_s_this_invocation"], 1), "jobs": c["man"]["jobs"],
            "threads": c["man"]["threads"], "chunks": len(ch), "chunk_rows": c["man"]["params"]["chunk"],
            "chunk_wall_s_median": round(float(np.median(ch)), 1), "chunk_wall_s_max": round(float(max(ch)), 1)}


# ------------------------------------------------------------------ files

def write_csvs(name, dt, pre, post_t, pre_t, post_tr, pre_tr, labels, post_sp, pre_sp):
    os.makedirs(OUT, exist_ok=True)
    tns = (np.arange(len(post_t)) + 0.5) * dt - pre
    mp, mq = post_tr.mean(0), pre_tr.mean(0)
    dp = post_tr[labels == 0].mean(0) - post_tr[labels == 1].mean(0)
    dq = pre_tr[labels == 0].mean(0) - pre_tr[labels == 1].mean(0)
    with open(os.path.join(OUT, "tcurve_%s.csv" % name), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["ns_after_edge", "t_post_layout", "t_pre_layout_same_rows", "mean_post_uA", "mean_pre_uA",
                    "mean_fixed_minus_random_post_uA", "mean_fixed_minus_random_pre_uA"])
        for j in range(len(tns)):
            w.writerow(["%.3f" % tns[j], "%.4f" % post_t[j], "%.4f" % pre_t[j], "%.3f" % mp[j], "%.3f" % mq[j],
                        "%.4f" % dp[j], "%.4f" % dq[j]])
    with open(os.path.join(OUT, "maxt_vs_traces_%s.csv" % name), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["traces", "post_layout", "pre_layout_same_rows"] +
                   ["post_layout_noise_%s" % x for x in NOISE])
        for i, nn in enumerate(post_sp["n"]):
            w.writerow([nn, "%.3f" % post_sp["max_abs_t"][i], "%.3f" % pre_sp["max_abs_t"][i]] +
                       ["%.3f" % post_sp["noise"][str(x)]["max_abs_t"][i] for x in NOISE])


# ------------------------------------------------------------------ main

def reproduce_kill_test():
    """spice_tvla on the full pre-layout campaigns must equal their summary.json blocks."""
    with open(os.path.join(REPO, "results", "kill_test", "summary.json")) as f:
        ks = json.load(f)["campaigns"]
    out = {}
    for name in ("N_tvla", "DA_tvla"):
        want = ks[name]
        c = load_run(os.path.join(kt.RUNS, name), kt.TVLA_RUNS[name][0], rows=want["rows_simulated"], name=name)
        sp = spice_tvla(c)[0]
        same = json.loads(json.dumps(sp)) == want["spice"]
        out[name] = {"traces": want["rows_analysed"], "identical_spice_block": bool(same)}
    out["all_identical"] = all(v["identical_spice_block"] for v in out.values())
    return out


def criteria(camps):
    out = {}
    for name, (v, run, pre, rows, cid) in CAMPAIGNS.items():
        text, want_leak = CRITERIA[cid]
        c = camps[name]
        sp = c["spice"]
        t = sp["final_max_abs_t"]
        out[cid] = {"criterion": text, "campaign": name, "registered_rows": rows,
                    "rows_simulated": c["rows_simulated"], "traces": c["rows_analysed"],
                    "max_abs_t": t, "max_abs_t_over_all_checkpoints": round(max(sp["max_abs_t"]), 3),
                    "first_above": sp["first_above"], "stable_from": sp["stable_from"],
                    "peak_ns_after_edge": sp["final_peak_ns_after_edge"],
                    "pre_layout_same_rows_max_abs_t": c["pre_layout_same_rows"]["final_max_abs_t"],
                    "pass": bool(t > THRESHOLD) if want_leak else bool(t < THRESHOLD),
                    "complete": c["rows_simulated"] == rows}
    n, da = camps["N_pex"], camps["DA_pex"]
    frac = detectable_fraction(da["rows_analysed"], n["spice"]["final_max_abs_t"], n["rows_analysed"])
    out["PL3"] = {
        "criterion": "Informational: where the t-peaks sit, by part of the cycle, and the smallest effect TVLA "
                     "could detect for DA_pex expressed as a fraction of N_pex's measured effect",
        "parts_ns_after_each_edge": {p: [a, b] for p, a, b in PARTS_POST},
        "N_pex": {"peaks": n["peaks"], "max_abs_t_by_part": n["spice"]["max_abs_t_by_region"]},
        "DA_pex": {"peaks": da["peaks"], "max_abs_t_by_part": da["spice"]["max_abs_t_by_region"]},
        "N_pex_effect_sd": round(effect_sd(n["spice"]["final_max_abs_t"], n["rows_analysed"]), 4),
        "DA_pex_detectable_sd": round(effect_sd(THRESHOLD, da["rows_analysed"]), 4),
        "DA_pex_detectable_fraction_of_N_pex": round(frac, 3),
        "method": "TVLA reaches |t| 4.5 on average for a standardized effect d = 2 * 4.5 / sqrt(n_DA_pex); N_pex's "
                  "measured effect is d_N = 2 * max|t| / sqrt(n_N_pex) (t = d sqrt(n) / 2, docs/KILL_TEST.md; "
                  "analysis/cost_table.py tvla_detectable_fraction)"}
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    summary = {"generated": datetime.date.today().isoformat(), "registration": "docs/POSTLAYOUT.md",
               "threshold": THRESHOLD, "noise_factors": list(NOISE), "campaigns": {}}
    camps = summary["campaigns"]
    for name, (v, run, pre_name, rows, cid) in CAMPAIGNS.items():
        c = load_run(run, v, name=name)
        if c["n_sim"] != rows or c["man"]["rows"] != rows:
            raise RuntimeError("%s: %d rows, the registration fixes %d" % (name, c["n_sim"], rows))
        pre = load_run(os.path.join(kt.RUNS, pre_name), v, rows=rows, name=pre_name)
        if c["man"]["stimulus_sha256"] != pre["man"]["stimulus_sha256"]:
            raise RuntimeError("%s and %s used different stimulus files" % (name, pre_name))
        p = c["man"]["params"]
        dt, pre_ns, T, lat = p["dt"], p["pre"], p["period"], c["lat"]
        sp, t_post, labels, tr_post = spice_tvla(c, post_regions)
        sq, t_pre, labels_pre, tr_pre = spice_tvla(pre, kt.region_max)
        assert np.array_equal(labels, labels_pre)
        sq["max_abs_t_by_post_layout_parts"] = post_regions(t_pre, dt, pre_ns, T, lat)
        res = {"variant": v, "criterion": cid, "run": rel(run), "dut": c["man"]["dut"],
               "dut_sp_sha256": c["man"]["dut_sp_sha256"], "stimulus": rel(os.path.join(kt.STIM, STEM + ".npy")),
               "stimulus_sha256": c["man"]["stimulus_sha256"], "rows_simulated": c["n_sim"],
               "rows_analysed": len(tr_post), "dropped_first_rows": c["skip"],
               "class_counts": np.bincount(labels, minlength=2).tolist(),
               "spice_params": {k: p[k] for k in ("period", "dt", "pre", "t_in", "tmax", "method", "options",
                                                  "corner", "temp", "vdd", "chunk")},
               "ngspice": c["man"]["ngspice"], "pdk": c["man"]["pdk"]["version"],
               "function_check": function_check(c, pre),
               "spice": sp,
               "peaks": peak_info(t_post, dt, pre_ns, T, lat)}
        pk = peak_info(t_pre, dt, pre_ns, T, lat)
        res["pre_layout_same_rows"] = dict(
            run=rel(pre["run"]), rows=[0, rows - 1], solver=pre["man"]["params"]["options"] or "sparse",
            dut_sp_sha256=pre["man"]["dut_sp_sha256"], **sq, peak_ns_after_edge=pk["peak"]["ns_after_edge"],
            first_last_sample_above_threshold_ns=pk["first_last_sample_above_threshold_ns"],
            samples_above_threshold=pk["samples_above_threshold"])
        res["pre_vs_post"] = {
            "max_abs_t": [sq["final_max_abs_t"], sp["final_max_abs_t"]],
            "peak_ns_after_edge": [sq["final_peak_ns_after_edge"], sp["final_peak_ns_after_edge"]],
            "t_curve": curve_shift(t_pre, t_post, dt),
            "charge_per_window_mean_fC": [round(float(pre["charge"][c["skip"]:].mean()), 2),
                                          round(float(c["charge"][c["skip"]:].mean()), 2)],
            "charge_ratio_post_over_pre": round(float(c["charge"][c["skip"]:].mean() /
                                                      pre["charge"][c["skip"]:].mean()), 4),
            "corr_charge_per_row": round(float(np.corrcoef(c["charge"][c["skip"]:],
                                                           pre["charge"][c["skip"]:])[0, 1]), 4),
            "noise_unit_uA": [sq["noise_unit_uA"], sp["noise_unit_uA"]]}
        res["energy_per_evaluation"] = {"pre_layout_same_rows": energy(pre), "post_layout": energy(c),
                                        "note": "post-layout includes the clock tree and the flip-flops' CLK "
                                                "pins, which draw from the DUT supply after layout; pre-layout "
                                                "has an ideal clock (no CLK-pin charge in the trace)"}
        res["spice_wall_clock"] = wall_clock(c)
        camps[name] = res
        write_csvs(name, dt, pre_ns, t_post, t_pre, tr_post, tr_pre, labels, sp, sq)
        print("%-7s %5d traces  post max|t| %6.2f (first > 4.5 %s, stable %s, peak %.3f ns, %s)  "
              "pre same rows %6.2f (peak %.3f ns)  func %s" % (
                  name, len(tr_post), sp["final_max_abs_t"], sp["first_above"], sp["stable_from"],
                  sp["final_peak_ns_after_edge"], res["peaks"]["peak"]["part"], sq["final_max_abs_t"],
                  sq["final_peak_ns_after_edge"], res["function_check"]), flush=True)
    e = {v: camps[v + "_pex"]["energy_per_evaluation"] for v in ("N", "DA")}
    summary["energy_DA_vs_N"] = {
        "pre_layout_same_rows": round(e["DA"]["pre_layout_same_rows"]["e_eval_fJ"] /
                                      e["N"]["pre_layout_same_rows"]["e_eval_fJ"], 3),
        "post_layout": round(e["DA"]["post_layout"]["e_eval_fJ"] / e["N"]["post_layout"]["e_eval_fJ"], 3)}
    summary["solver_check_klu_vs_sparse"] = {
        v: compare_runs(a, b, skip=0) for v, (a, b) in SOLVER_RUNS.items()
        if os.path.exists(os.path.join(PEX, a, "traces.npy")) and os.path.exists(os.path.join(PEX, b, "traces.npy"))}
    summary["netlist_text_check"] = {
        v: compare_runs(a, b, skip=0, rows=120) for v, (a, b) in TEXT_RUNS.items()
        if os.path.exists(os.path.join(PEX, a, "traces.npy"))}
    summary["capacitance_views"] = capacitance_views()
    summary["reproduces_kill_test"] = reproduce_kill_test()
    summary["criteria"] = criteria(camps)
    with open(os.path.join(OUT, "summary_postlayout.json"), "w") as f:
        json.dump(summary, f, indent=1)
        f.write("\n")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("N_pex", "DA_pex")}
                      for k, v in summary["criteria"].items()}, indent=1))
    print("reproduces kill test:", summary["reproduces_kill_test"])
    print("solver check:", json.dumps(summary["solver_check_klu_vs_sparse"]))
    print("netlist text check:", json.dumps(summary["netlist_text_check"]))
    print("energy DA/N:", summary["energy_DA_vs_N"])
    print("capacitance views:", json.dumps(summary["capacitance_views"]))


if __name__ == "__main__":
    main()
