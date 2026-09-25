# SPDX-License-Identifier: Apache-2.0
"""Kill-test analysis (docs/KILL_TEST.md): TVLA and CPA on the SPICE campaigns and on the
level-1 (zero-delay) and level-2 (timing-aware) models driven by the same stimulus rows.

Inputs (git-ignored, made by the campaign commands listed in docs/KILL_TEST.md "Results"):
  runs/kt/stim/<stem>.npy, <stem>.meta.npz      stimulus (model/stimulus.py)
  runs/kt/<campaign>/traces.npy, outputs.npy    SPICE runs (sim/spice_campaign.py)
  runs/kt/<V>_nodes/events.npz                  net crossings (analysis/spice_nodes.py)
Outputs (small, committed): results/kill_test/summary.json and CSV files; the figures are
drawn from them by analysis/plots.py.

Conventions
  * Rows: the models start from the reset state, so the first L+1 rows (L = latency) of every
    campaign are dropped, for SPICE too, so that all levels see exactly the same rows.
  * Time: sample j of a row is the bin [j*dt, (j+1)*dt) from the window start; the capturing
    clock edge is at `pre` (0.2 ns), so "ns after the edge" = (j + 0.5)*dt - pre. For
    latency 2 the second cycle's edge is at T (4 ns) on the same axis.
  * TVLA: first-order Welch t per sample, pass/fail threshold 4.5; max|t| over samples.
    "first above" = first checkpoint with max|t| > 4.5; "stable from" = first checkpoint
    after which every checkpoint stays above 4.5.
  * Noise: white Gaussian noise (per 10 ps sample) of std f * (the largest per-sample std of
    the noiseless traces), f = 0.5, 1, 2, seeded; reported alongside, never used for pass/fail.
  * CPA (U, amendment A2): per-sample Pearson correlation, score = max over samples of
    |rho|; primary hypothesis = level-1 cap-weighted toggle count of the window simulated
    with each key guess and the known nonces; HW(S(x)) reported alongside.

  python3 analysis/kill_test.py            (host python3 + numpy; a few minutes)
"""
import csv
import datetime
import json
import os
import sys

import numpy as np

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(REPO, "model"))
sys.path.insert(0, os.path.join(REPO, "sim"))

from ascon_sbox import SBOX_NP                        # noqa: E402
from cpa import cpa_curve, hw_sbox_hypotheses         # noqa: E402
from glitch import TimingModel, glitch_traces         # noqa: E402
from netgraph import Graph                            # noqa: E402
from stimulus import encode                           # noqa: E402
from toggle import rows_from_cycles, toggle_traces    # noqa: E402
from tvla import THRESHOLD, WelchT, add_noise, tvla_curve   # noqa: E402
from spice_campaign import extend_stimulus            # noqa: E402

RUNS = os.path.join(REPO, "runs", "kt")
STIM = os.path.join(RUNS, "stim")
OUT = os.path.join(REPO, "results", "kill_test")
KEYS = ("unweighted", "weighted", "weighted_rise")
NOISE = (0.5, 1.0, 2.0)
JOBS = 4

# campaign: (variant, stimulus stem, role)
TVLA_RUNS = {
    "U_tvla": ("U", "U_tvla", "K1: unmasked, fixed vs random"),
    "N_masksoff": ("N", "N_masksoff", "C(b): N with masks forced to zero"),
    "N_rvr": ("N", "N_rvr", "C(a): N random vs random"),
    "N_tvla": ("N", "M_tvla", "K3: naive DOM, fixed vs random"),
    "D_tvla": ("D", "M_tvla", "K4: DOM with register barrier, fixed vs random"),
    "DA_tvla": ("DA", "M_tvla", "K5 (A1): D with the affine layer before the registers"),
}
CPA_RUNS = {"U_cpa_k%d" % k: ("U", "U_cpa_k%d" % k) for k in range(4)}
L1_100K = ("N", "D", "DA")


def rel(path):
    return os.path.relpath(path, REPO)


def dut(v):
    return os.path.join(REPO, "build", v)


def checkpoints(n, first=20):
    k = set(int(v) for v in np.round(np.logspace(np.log10(first), np.log10(max(n, first)), 41)))
    k |= set(range(500, n + 1, 500)) | {n}
    return sorted(c for c in k if 2 <= c <= n)


def curve_stats(r):
    n, m = r["n"], r["max_abs_t"]
    above = m > THRESHOLD
    first = int(n[np.argmax(above)]) if above.any() else None
    stable = None
    for i in range(len(n)):
        if above[i:].all():
            stable = int(n[i])
            break
    return first, stable


def load_manifest(run):
    with open(os.path.join(run, "manifest.json")) as f:
        return json.load(f)


def load_campaign(name, variant, stem):
    run = os.path.join(RUNS, name)
    if not os.path.exists(os.path.join(run, "traces.npy")):
        return None
    man = load_manifest(run)
    tr = np.load(os.path.join(run, "traces.npy")).astype(np.float64)
    stim = np.load(os.path.join(STIM, stem + ".npy"))
    meta = dict(np.load(os.path.join(STIM, stem + ".meta.npz")))
    lat = man["latency"]
    return dict(name=name, variant=variant, run=run, man=man, traces=tr, stim=stim, meta=meta,
                lat=lat, skip=lat + 1, n_sim=len(tr),
                outputs=np.load(os.path.join(run, "outputs.npy"))
                if os.path.exists(os.path.join(run, "outputs.npy")) else None)


def timing_params(man):
    p = man["params"]
    return dict(period_ps=1000.0 * p["period"], pre_ps=1000.0 * p["pre"], t_in_frac=p["t_in"],
                bin_ps=1000.0 * p["dt"])


def model_rows(variant, stim, n_sim, level, man, per_net=False):
    """Level-1/2 per-row traces for stimulus rows skip..n_sim-1 (same rows as the SPICE run).

    The model is fed the rows that follow n_sim as the SPICE run saw them (the next rows of the
    file, or the runner's seeded random tail rows after the last row), because they drive the
    mid-window input edges; returns {weighting: (n_sim - skip, samples)}.
    """
    g = Graph(dut(variant))
    lat = g.latency
    p = man["params"]
    ext = extend_stimulus(stim, p, lat)[p["warmup"]:]
    ext = ext[:n_sim + lat]
    if level == 1:
        t = toggle_traces(g, ext)
    else:
        t = glitch_traces(os.path.join(dut(variant), "graph.json"), ext, jobs=JOBS,
                          **timing_params(man))
    skip = lat + 1
    out = {k: rows_from_cycles(t[k], lat)[skip:n_sim] for k in KEYS}
    return out


def functional_check(c):
    """Registered outputs of the SPICE run vs the S-box of the unshared input."""
    if c["outputs"] is None:
        return None
    with open(os.path.join(dut(c["variant"]), "ports.json")) as f:
        ports = json.load(f)
    y = np.zeros(len(c["outputs"]), dtype=np.uint8)
    for k, p in enumerate(ports["outputs"]):
        y ^= c["outputs"][:, k].astype(np.uint8) << (4 - p["bit"])
    x = c["meta"]["x"][:len(y)]
    return int((SBOX_NP[x] != y).sum())


def tvla_block(tr, labels, cps, dt=None, pre=None, keep_t=False):
    r = tvla_curve(tr, labels, cps)
    first, stable = curve_stats(r)
    k = int(r["argmax"][-1])
    res = {"n": r["n"].tolist(), "max_abs_t": np.round(r["max_abs_t"], 3).tolist(),
           "final_max_abs_t": round(float(r["max_abs_t"][-1]), 3), "final_argmax": k,
           "first_above": first, "stable_from": stable}
    if dt is not None:
        res["final_peak_ns_after_edge"] = round((k + 0.5) * dt - pre, 4)
    if keep_t:
        res["_t"] = r["t_final"]
    return res


# parts of each clock cycle, in ns after that cycle's capturing edge (T = 4 ns): the edge and
# the evaluation, the clock's falling edge (at T/2), the next row's input edges (at 0.75 T), and
# the quiet end of the evaluation part, where only late transitions and static current remain
REGIONS = (("edge_and_evaluation", -0.2, 1.8), ("clock_fall", 1.8, 2.8), ("input_edges", 2.8, 3.8),
           ("settled_1.3_to_1.8", 1.3, 1.8))    # the quiet end of the evaluation part (overlaps it)


def region_max(t, dt, pre, T, lat):
    tns = (np.arange(len(t)) + 0.5) * dt - pre
    out = {}
    for c in range(lat):
        for name, a, b in REGIONS:
            m = (tns >= a + c * T) & (tns < b + c * T)
            if m.any():
                key = name if lat == 1 else "cycle%d_%s" % (c + 1, name)
                out[key] = round(float(np.abs(t[m]).max()), 3)
    return out


def noise_sigma(tr):
    """Noise unit: the largest per-sample standard deviation of the noiseless traces (the size
    of the biggest data-dependent variation anywhere in the window)."""
    return float(tr.std(0).max())


def waveform_lag(sp, l2, dt, max_lag_ps=500, rows=3000, k=10):
    """Shift of level 2 against SPICE that best aligns the data-dependent parts of the two
    per-row waveforms, compared at k*dt (100 ps) resolution; returns (lag_ps, corr, corr_at_0).
    A positive lag means level-2 events come later than the SPICE current."""
    a = sp[:rows]
    b = l2[:rows]
    ns = a.shape[1]

    def binned(x):
        x = x[:, :ns - ns % k]
        x = x.reshape(len(x), -1, k).sum(2)
        return x - x.mean(0)
    A = binned(a)
    best, c0 = None, None
    for lag in range(-int(max_lag_ps / (1000 * dt)), int(max_lag_ps / (1000 * dt)) + 1):
        sh = np.zeros_like(b)
        if lag >= 0:
            sh[:, :ns - lag] = b[:, lag:]
        else:
            sh[:, -lag:] = b[:, :ns + lag]
        B = binned(sh)
        cc = float((A * B).sum() / np.sqrt((A * A).sum() * (B * B).sum()))
        if lag == 0:
            c0 = cc
        if best is None or cc > best[1]:
            best = (lag, cc)
    return int(round(best[0] * dt * 1000)), round(best[1], 4), round(c0, 4)


def analyse_tvla(c):
    man, lat, skip = c["man"], c["lat"], c["skip"]
    p = man["params"]
    dt, pre, T = p["dt"], p["pre"], p["period"]
    tr = c["traces"][skip:]
    n = len(tr)
    labels = c["meta"]["label"][skip:skip + n]
    cps = checkpoints(n)
    res = {"variant": c["variant"], "run": rel(c["run"]), "rows_simulated": c["n_sim"],
           "rows_analysed": n, "dropped_first_rows": skip,
           "class_counts": np.bincount(labels, minlength=2).tolist(),
           "functional_mismatches": functional_check(c),
           "spice_process_s": round(sum(ch["wall_s"] for ch in man["chunks"]), 1),
           "spice_s_per_cycle_per_process": man["s_per_cycle_per_process"],
           "spice_throughput_cycles_per_s_last_step": man["throughput_cycles_per_s"],
           "spice_jobs": man["jobs"],
           "spice_params": {k: p[k] for k in ("period", "dt", "pre", "t_in", "tmax", "method")}}
    sp = tvla_block(tr, labels, cps, dt, pre, keep_t=True)
    t_spice = sp.pop("_t")
    t2 = tvla_curve(tr, labels, [n], order=2)
    sp["second_order_final_max_abs_t"] = round(float(np.abs(t2["t_final"]).max()), 3)
    # coarser views: 100 ps bins (sum of 10 bins) and the charge per window
    tr100 = tr.reshape(n, -1, 10).mean(2)
    r100 = tvla_curve(tr100, labels, [n])
    sp["final_max_abs_t_100ps_bins"] = round(float(r100["max_abs_t"][-1]), 3)
    q = np.load(os.path.join(c["run"], "charge.npy"))[skip:skip + n]
    rq = tvla_curve(q, labels, cps)
    sp["charge_per_window"] = {"final_abs_t": round(float(rq["max_abs_t"][-1]), 3),
                               "first_above": curve_stats(rq)[0]}
    # noise sweep
    sig = noise_sigma(tr)
    sp["noise_unit_uA"] = round(sig, 4)
    sp["noise"] = {}
    for f in NOISE:
        rn = tvla_curve(add_noise(tr, f * sig, seed=1000 + int(10 * f)), labels, cps)
        fa, st = curve_stats(rn)
        sp["noise"][str(f)] = {"final_max_abs_t": round(float(rn["max_abs_t"][-1]), 3),
                               "first_above": fa, "stable_from": st,
                               "max_abs_t": np.round(rn["max_abs_t"], 3).tolist()}
    sp["max_abs_t_by_region"] = region_max(t_spice, dt, pre, T, lat)
    res["spice"] = sp
    # mean traces
    mean_all = tr.mean(0)
    mdiff = tr[labels == 0].mean(0) - tr[labels == 1].mean(0)

    # models on the same rows
    stim = c["stim"]
    l1 = model_rows(c["variant"], stim, c["n_sim"], 1, man)
    l2 = model_rows(c["variant"], stim, c["n_sim"], 2, man)
    res["level1"], res["level2"] = {}, {}
    t_l2 = {}
    for k in KEYS:
        res["level1"][k] = tvla_block(l1[k], labels, cps)
        b = tvla_block(l2[k], labels, cps, dt, pre, keep_t=True)
        t_l2[k] = b.pop("_t")
        res["level2"][k] = b
    for k in KEYS:
        x = l2[k].reshape(n, -1, 10).sum(2)
        res["level2"][k]["final_max_abs_t_100ps_bins"] = round(float(tvla_curve(x, labels, [n])["max_abs_t"][-1]), 3)
    sig2 = noise_sigma(l2["weighted"])
    res["level2"]["noise"] = {}
    for f in NOISE:
        rn = tvla_curve(add_noise(l2["weighted"], f * sig2, seed=2000 + int(10 * f)), labels, cps)
        fa, st = curve_stats(rn)
        res["level2"]["noise"][str(f)] = {"final_max_abs_t": round(float(rn["max_abs_t"][-1]), 3),
                                          "first_above": fa}
    # level 2 vs SPICE on the same rows
    q2 = l2["weighted"].sum(1)
    q1 = l1["weighted"].sum(1)
    cmp = {"corr_charge_spice_vs_level2_weighted": round(float(np.corrcoef(q, q2)[0, 1]), 4),
           "corr_charge_spice_vs_level1_weighted": round(float(np.corrcoef(q, q1)[0, 1]), 4)}
    # data-dependent waveforms (minus the mean trace) at 100 ps resolution, best time shift
    lag, cc, c0 = waveform_lag(tr, l2["weighted"], dt)
    cmp.update(waveform_lag_ps=lag, waveform_corr_at_lag=cc, waveform_corr_at_0=c0)
    k2 = int(np.argmax(np.abs(t_l2["weighted"])))
    cmp["level2_peak_ns_after_edge"] = round((k2 + 0.5) * dt - pre, 4)
    cmp["spice_peak_ns_after_edge"] = sp["final_peak_ns_after_edge"]
    res["level2_vs_spice"] = cmp
    res["level2"]["weighted"]["max_abs_t_by_region"] = region_max(t_l2["weighted"], dt, pre, T, lat)

    # CSV files: t curves and max|t| vs traces
    ns = tr.shape[1]
    tns = (np.arange(ns) + 0.5) * dt - pre
    with open(os.path.join(OUT, "tcurve_%s.csv" % c["name"]), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ns_after_edge", "t_spice", "t_level2_unweighted", "t_level2_weighted",
                    "t_level2_weighted_rise", "mean_uA", "mean_fixed_minus_random_uA",
                    "mean_level2_weighted_fF"])
        m2 = l2["weighted"].mean(0)
        for j in range(ns):
            w.writerow(["%.3f" % tns[j], "%.4f" % t_spice[j], "%.4f" % t_l2["unweighted"][j],
                        "%.4f" % t_l2["weighted"][j], "%.4f" % t_l2["weighted_rise"][j],
                        "%.4f" % mean_all[j], "%.5f" % mdiff[j], "%.4f" % m2[j]])
    with open(os.path.join(OUT, "maxt_vs_traces_%s.csv" % c["name"]), "w", newline="") as f:
        w = csv.writer(f)
        cols = [("spice", sp)] + [("level1_" + k, res["level1"][k]) for k in KEYS] + \
               [("level2_" + k, res["level2"][k]) for k in KEYS]
        w.writerow(["traces"] + [h for h, _ in cols] +
                   ["spice_noise_%s" % f for f in NOISE])
        for i, nn in enumerate(sp["n"]):
            w.writerow([nn] + ["%.3f" % b["max_abs_t"][i] for _, b in cols] +
                       ["%.3f" % sp["noise"][str(f)]["max_abs_t"][i] for f in NOISE])
    return res, t_spice


def level1_100k(man):
    res = {}
    stim = np.load(os.path.join(STIM, "M_tvla100k.npy"))
    meta = np.load(os.path.join(STIM, "M_tvla100k.meta.npz"))
    for v in L1_100K:
        rows = model_rows(v, stim, len(stim), 1, man)
        n = len(rows["weighted"])
        skip = Graph(dut(v)).latency + 1
        labels = meta["label"][skip:skip + n]
        cps = checkpoints(n)
        res[v] = {"rows_analysed": n, "stimulus": rel(os.path.join(STIM, "M_tvla100k.npy"))}
        for k in KEYS:
            b = tvla_block(rows[k], labels, cps)
            res[v][k] = {kk: b[kk] for kk in ("final_max_abs_t", "first_above")}
            res[v][k]["max_abs_t_over_all_checkpoints"] = round(max(b["max_abs_t"]), 3)
    return res


def model_hypotheses(c, nonce_all):
    """(rows, 4) level-1 cap-weighted toggle counts with each key guess and the known nonces."""
    with open(os.path.join(dut("U"), "ports.json")) as f:
        ports = json.load(f)
    iv = int(c["meta"]["iv"])
    h = []
    for g in range(4):
        x = (iv << 4) | (g << 2) | nonce_all.astype(np.int64)
        stim = encode(ports, x, np.zeros_like(x), np.zeros_like(x))
        h.append(model_rows("U", stim, c["n_sim"], 1, c["man"])["weighted"][:, 0])
    return np.stack(h, axis=1)


def literal_table_hypotheses(iv, nonce):
    """A2 read literally: one value per (key guess, nonce), the level-1 cap-weighted toggle
    count of the window of that nonce averaged over the previous and the next nonce."""
    g = Graph(dut("U"))
    with open(os.path.join(dut("U"), "ports.json")) as f:
        ports = json.load(f)
    tab = np.zeros((4, 4))
    for guess in range(4):
        for nc in range(4):
            v = []
            for pv in range(4):
                for nx in range(4):
                    x = np.array([(iv << 4) | (guess << 2) | q for q in (pv, pv, nc, nx)])
                    z = np.zeros(4, dtype=int)
                    v.append(toggle_traces(g, encode(ports, x, z, z))["weighted"][2])
            tab[guess, nc] = np.mean(v)
    return tab[:, np.asarray(nonce, dtype=np.int64)].T


def analyse_cpa(c):
    skip = c["skip"]
    tr = c["traces"][skip:]
    n = len(tr)
    meta = c["meta"]
    key, iv = int(meta["key"]), int(meta["iv"])
    nonce = meta["nonce"][skip:skip + n]
    cps = checkpoints(n)
    hyp = {"level1_model": model_hypotheses(c, meta["nonce"])[:n],
           "hw_sbox": hw_sbox_hypotheses(iv, nonce)}
    res = {"key": key, "iv": iv, "run": rel(c["run"]), "rows_analysed": n,
           "functional_mismatches": functional_check(c)}
    # how similar the four guesses' hypotheses are (off-diagonal Pearson correlations)
    for hname, h in hyp.items():
        cc = np.corrcoef(np.asarray(h, dtype=float).T)
        off = cc[~np.eye(4, dtype=bool)]
        res["guess_hypothesis_corr_" + hname] = [round(float(off.min()), 4), round(float(off.max()), 4)]
    # A2 read literally (a (guess, nonce) table): the four guesses' tables turn out to be affine
    # images of each other, so every guess gets the same correlation (no key information)
    lit = cpa_curve(tr, literal_table_hypotheses(iv, nonce), key, [n])
    sc = lit["scores"][-1]
    res["literal_guess_nonce_table"] = {"scores": np.round(sc, 6).tolist(),
                                        "degenerate_all_guesses_equal": bool(np.ptp(sc) < 1e-9)}
    # the same CPA on the level-1 and level-2 model traces of the same rows (how far the
    # cheap models predict the SPICE outcome)
    for lvl in (1, 2):
        m = model_rows("U", c["stim"], c["n_sim"], lvl, c["man"])["weighted"]
        res["on_level%d_traces" % lvl] = {
            h: int(cpa_curve(m, hh, key, [len(m)])["rank"][-1]) for h, hh in hyp.items()}
    sig = noise_sigma(tr)
    for hname, h in hyp.items():
        for signed in (False, True):
            r = cpa_curve(tr, h, key, cps, signed)
            ranks = r["rank"]
            stable = next((int(r["n"][i]) for i in range(len(ranks)) if (ranks[i:] == 1).all()), None)
            tag = hname + ("_signed" if signed else "")
            res[tag] = {"n": r["n"].tolist(), "rank": ranks.tolist(), "final_rank": int(ranks[-1]),
                        "rank1_stable_from": stable,
                        "final_scores": np.round(r["scores"][-1], 4).tolist()}
        res[hname]["noise"] = {}
        for f in NOISE:
            r = cpa_curve(add_noise(tr, f * sig, seed=3000 + int(10 * f)), h, key, cps)
            ranks = r["rank"]
            stable = next((int(r["n"][i]) for i in range(len(ranks)) if (ranks[i:] == 1).all()), None)
            res[hname]["noise"][str(f)] = {"final_rank": int(ranks[-1]), "rank1_stable_from": stable,
                                           "rank": ranks.tolist()}
    return res


# ---------------------------------------------------------------- localization (N, D, DA)

def per_net_tvla(row_events, labels, n_rows, n_nets, n_bins, bin_ns):
    """Welch t (n_nets, n_bins) of the per-row, per-net transition counts in bins of bin_ns.

    row_events(a, b) -> (row, net, t_ns) arrays for rows a..b-1 (row relative to a)."""
    acc = WelchT(n_nets * n_bins)
    act = np.zeros(n_nets * n_bins)
    chunk = max(50, int(4e6 // (n_nets * n_bins)))
    for a in range(0, n_rows, chunk):
        b = min(a + chunk, n_rows)
        r, net, t = row_events(a, b)
        kb = np.clip((t / bin_ns).astype(np.int64), 0, n_bins - 1)
        x = np.zeros((b - a, n_nets * n_bins))
        np.add.at(x, (r, net * n_bins + kb), 1.0)
        acc.update(x, labels[a:b])
        act += x.sum(0)
    t = np.nan_to_num(acc.t(1), posinf=999.0, neginf=-999.0).reshape(n_nets, n_bins)
    return t, (act / n_rows).reshape(n_nets, n_bins)


def spice_node_events(variant):
    path = os.path.join(RUNS, variant + "_nodes", "events.npz")
    if not os.path.exists(path):
        return None
    e = np.load(path)
    return {k: e[k] for k in e.files}


def localize(variant, t_spice, spice_run, lag_ps=0, bin_ns=0.02):
    """Which nets switch, and which nets' switching depends on the class, at the SPICE t-peak."""
    man = load_manifest(os.path.join(RUNS, spice_run))
    p = man["params"]
    T, pre, dt = p["period"], p["pre"], p["dt"]
    lat = man["latency"]
    skip = lat + 1
    with open(os.path.join(REPO, "results", "probing", variant + ".json")) as f:
        flagged = set(json.load(f)["glitch_fail"])
    k = int(np.argmax(np.abs(t_spice)))
    t_peak = (k + 0.5) * dt              # ns from the window start
    res = {"_pre": pre, "spice_peak_ns_after_edge": round(t_peak - pre, 4),
           "spice_peak_t": round(float(t_spice[k]), 3), "glitch_extended_flagged_nets": sorted(flagged)}
    # secondary peaks: best |t| per 200 ps segment, top 5 segments above threshold
    seg = np.abs(t_spice).reshape(-1, 20)
    order = np.argsort(-seg.max(1))[:5]
    res["spice_peaks_by_200ps_segment"] = [
        {"ns_after_edge": round((s * 20 + int(np.argmax(seg[s])) + 0.5) * dt - pre, 3),
         "abs_t": round(float(seg[s].max()), 2)} for s in order if seg[s].max() > THRESHOLD]
    n_bins = int(round(lat * T / bin_ns))
    stim = np.load(os.path.join(STIM, "M_tvla.npy"))
    meta = np.load(os.path.join(STIM, "M_tvla.meta.npz"))

    def summarize(t, act, names, t_at, n_rows):
        kb = min(int(t_at / bin_ns), n_bins - 1)
        lo, hi = max(0, kb - 5), min(n_bins, kb + 6)        # +-100 ps around the peak
        near = np.abs(t[:, lo:hi]).max(1)
        top = np.argsort(-near)[:12]
        best_any = np.abs(t).max(1)
        top_any = np.argsort(-best_any)[:12]
        out = {"rows": n_rows, "bin_ns": bin_ns, "time_examined_ns_after_edge": round(t_at - pre, 3),
               "nets_by_abs_t_near_spice_peak": [
                   {"net": str(names[i]), "abs_t": round(float(near[i]), 2),
                    "flagged": str(names[i]) in flagged,
                    "mean_transitions_near_peak": round(float(act[i, lo:hi].sum()), 4)}
                   for i in top],
               "nets_by_abs_t_anywhere": [
                   {"net": str(names[i]), "abs_t": round(float(best_any[i]), 2),
                    "ns_after_edge": round((int(np.argmax(np.abs(t[i]))) + 0.5) * bin_ns - pre, 3),
                    "flagged": str(names[i]) in flagged} for i in top_any]}
        sig = [str(names[i]) for i in range(len(names)) if near[i] > THRESHOLD]
        out["nets_above_threshold_near_peak"] = sig
        out["all_of_them_flagged"] = bool(sig) and all(s in flagged for s in sig)
        anyw = [str(names[i]) for i in range(len(names)) if best_any[i] > THRESHOLD]
        out["nets_above_threshold_anywhere"] = anyw
        out["all_above_anywhere_flagged"] = all(s in flagged for s in anyw)
        out["top10_near_peak_all_flagged"] = all(str(names[i]) in flagged for i in top[:10])
        # switching-time window of the flagged nets: 5th..95th percentile of their transitions
        fl = [i for i in range(len(names)) if str(names[i]) in flagged]
        prof = act[fl].sum(0)
        if prof.sum() > 0:
            cdf = np.cumsum(prof) / prof.sum()
            p5 = (np.searchsorted(cdf, 0.05) + 0.5) * bin_ns - pre
            p95 = (np.searchsorted(cdf, 0.95) + 0.5) * bin_ns - pre
            out["flagged_nets_switching_p5_p95_ns_after_edge"] = [round(p5, 3), round(p95, 3)]
        out["_act"] = act
        out["_t"] = t
        out["_names"] = [str(x) for x in names]
        return out

    # SPICE node voltages (short re-run)
    ev = spice_node_events(variant)
    if ev is not None:
        names = ev["net_names"]
        n_rows = int(ev["n_rows"])
        rows_ev = []
        for off in range(lat):                     # cycle c belongs to row c - off at +off*T
            rows_ev.append((ev["cycle"] - off, ev["net"].astype(np.int64), ev["t_ns"] + off * T))
        rr = np.concatenate([x[0] for x in rows_ev])
        nn = np.concatenate([x[1] for x in rows_ev])
        tt = np.concatenate([x[2] for x in rows_ev])
        ok = (rr >= skip) & (rr < n_rows)
        rr, nn, tt = rr[ok], nn[ok], tt[ok]
        order = np.argsort(rr, kind="stable")
        rr, nn, tt = rr[order], nn[order], tt[order]
        n_an = n_rows - skip
        labels = meta["label"][skip:n_rows]

        def row_events(a, b):
            lo, hi = np.searchsorted(rr, skip + a), np.searchsorted(rr, skip + b)
            return rr[lo:hi] - skip - a, nn[lo:hi], tt[lo:hi]
        t, act = per_net_tvla(row_events, labels, n_an, len(names), n_bins, bin_ns)
        res["spice_nodes"] = summarize(t, act, names, t_peak, n_an)
        # determinism: the re-run's supply current vs the campaign on the same rows
        tr_n = np.load(os.path.join(RUNS, variant + "_nodes", "traces.npy"))
        tr_c = np.load(os.path.join(RUNS, spice_run, "traces.npy"))[:len(tr_n)]
        res["spice_nodes"]["rerun_vs_campaign_trace_corr"] = round(float(
            np.corrcoef(tr_n[skip:].ravel(), tr_c[skip:].ravel())[0, 1]), 6)
        res["spice_nodes"]["rerun_vs_campaign_max_abs_diff_uA"] = round(float(
            np.abs(tr_n[skip:] - tr_c[skip:]).max()), 3)

    # level 2 on the same stimulus (all 20,000 rows)
    g = Graph(dut(variant))
    tm = TimingModel(g, **timing_params(man))
    n_all = len(stim)
    V = g.simulate(stim[:n_all])
    names = np.array(g.net_names)
    net_ok = np.array([kd != "port" for kd in g.kind])
    idx_map = -np.ones(g.n_nets, dtype=np.int64)
    idx_map[net_ok] = np.arange(net_ok.sum())
    names_l2 = names[net_ok]
    pre_ns = tm.p["pre_ps"] / 1000.0
    rows_V = V.tolist()
    n_rows = n_all - lat                       # rows whose windows are all inside V
    n_an = n_rows - skip
    labels = meta["label"][skip:n_rows]

    def row_events(a, b):
        rr, nn, tt = [], [], []
        for j in range(a, b):
            row = skip + j
            for off in range(lat):
                w = row + off
                waves = tm.window_events(rows_V[w], rows_V[w + 1])
                for i, wv in enumerate(waves):
                    if wv and idx_map[i] >= 0:
                        for tp, _ in wv:
                            rr.append(j - a)
                            nn.append(idx_map[i])
                            tt.append(tp / 1000.0 + pre_ns + off * T)
        return np.array(rr, dtype=np.int64), np.array(nn, dtype=np.int64), np.array(tt)
    t, act = per_net_tvla(row_events, labels, n_an, len(names_l2), n_bins, bin_ns)
    # level-2 delays differ from SPICE: look at the SPICE peak shifted by the lag that best
    # aligns the two data-dependent waveforms (level2_vs_spice.waveform_lag_ps)
    res["level2_nets"] = summarize(t, act, names_l2, t_peak + lag_ps / 1000.0, n_an)
    res["level2_nets"]["lag_applied_ps"] = lag_ps
    return res


def write_pernet_csv(v, src, r, pre):
    """Per-net Welch t of the transition counts, one column per net, one row per time bin."""
    t, names, bw = r["_t"], r["_names"], r["bin_ns"]
    with open(os.path.join(OUT, "pernet_t_%s_%s.csv" % (v, src)), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ns_after_edge"] + names)
        for j in range(t.shape[1]):
            w.writerow(["%.3f" % ((j + 0.5) * bw - pre)] + ["%.2f" % x for x in t[:, j]])


def setup_block(summary):
    """Netlist sizes and simulator versions, from the SPICE runs' manifests."""
    out = {"variants": {}}
    for name in list(summary["campaigns"]) + list(summary["cpa"]):
        man = load_manifest(os.path.join(RUNS, name))
        v = man["variant"]
        out["variants"][v] = {"n_cells": man["n_cells"], "n_dff": man["n_dff"], "latency": man["latency"],
                              "wire_cap_fF": man["wire_cap_fF"], "dut_sp_sha256": man["dut_sp_sha256"]}
        out["ngspice"] = man["ngspice"]
        out["pdk"] = man["pdk"]
        out["spice_params"] = man["params"]
    return out


def spice_wall_clock():
    """Wall-clock seconds of each SPICE job, from the job queue log (runs/kt/queue.log); a job
    without an END line (the first one ran under an earlier queue runner) is taken from its
    manifest."""
    path = os.path.join(RUNS, "queue.log")
    if not os.path.exists(path):
        return {}
    start, out = {}, {}
    with open(path) as f:
        for line in f:
            w = line.split()
            if len(w) < 3 or w[1] not in ("START", "END"):
                continue
            t = datetime.datetime.strptime(w[0], "%Y-%m-%d_%H:%M:%S")
            if w[1] == "START":
                start[w[2]] = t
            elif w[2] in start:
                out[w[2]] = int((t - start[w[2]]).total_seconds())
    for job in start:
        if job not in out:
            man = os.path.join(RUNS, job, "manifest.json")
            if os.path.exists(man):
                out[job] = int(load_manifest(os.path.join(RUNS, job))["wall_s_this_invocation"])
    out["total_s"] = sum(v for k, v in out.items())
    return out


def strip_private(d):
    if isinstance(d, dict):
        return {k: strip_private(v) for k, v in d.items() if not k.startswith("_")}
    if isinstance(d, list):
        return [strip_private(v) for v in d]
    return d


def criteria(s):
    c = s["campaigns"]
    crit = {}

    def spice_max(name):
        return c[name]["spice"]["final_max_abs_t"] if name in c else None

    # K1
    k1 = {"criterion": "U in SPICE: max|t| > 4.5, and CPA ranks the correct key first (<= 2,000)"}
    if "U_tvla" in c:
        k1["tvla_max_abs_t"] = spice_max("U_tvla")
        k1["tvla_traces"] = c["U_tvla"]["rows_analysed"]
        k1["tvla_first_above"] = c["U_tvla"]["spice"]["first_above"]
        k1["tvla_pass"] = k1["tvla_max_abs_t"] > THRESHOLD
    cp = s.get("cpa", {})
    if len(cp) == 4:
        k1["cpa_primary_final_rank_per_key"] = {str(v["key"]): v["level1_model"]["final_rank"] for v in cp.values()}
        k1["cpa_primary_rank1_stable_from"] = {str(v["key"]): v["level1_model"]["rank1_stable_from"] for v in cp.values()}
        k1["cpa_hw_final_rank_per_key"] = {str(v["key"]): v["hw_sbox"]["final_rank"] for v in cp.values()}
        k1["cpa_traces_per_key"] = [v["rows_analysed"] for v in cp.values()]
        k1["cpa_pass"] = all(r == 1 for r in k1["cpa_primary_final_rank_per_key"].values())
    if "tvla_pass" in k1 and "cpa_pass" in k1:
        k1["pass"] = k1["tvla_pass"] and k1["cpa_pass"]
    crit["K1"] = k1
    # K2
    k2 = {"criterion": "N and D in the zero-delay model: max|t| < 4.5 at the SPICE trace count and at 100,000"}
    vals = {}
    for name in ("N_tvla", "D_tvla", "DA_tvla"):
        if name in c:
            vals[name + "_at_spice_count"] = {
                "traces": c[name]["rows_analysed"],
                "max_abs_t": {k: c[name]["level1"][k]["final_max_abs_t"] for k in KEYS}}
    for v, r in s.get("level1_100k", {}).items():
        vals["%s_at_100k" % v] = {"traces": r["rows_analysed"],
                                  "max_abs_t": {k: r[k]["final_max_abs_t"] for k in KEYS},
                                  "max_over_checkpoints": {k: r[k]["max_abs_t_over_all_checkpoints"] for k in KEYS}}
    k2["values"] = vals
    need = [k for k in vals if k.startswith(("N_", "D_"))]
    if need:
        k2["pass"] = all(max(vals[k]["max_abs_t"].values()) < THRESHOLD for k in need)
    crit["K2"] = k2
    # K3, K4, K5
    for kid, name, want_leak, text in (
            ("K3", "N_tvla", True, "N in SPICE: max|t| > 4.5 at first order (<= 20,000)"),
            ("K4", "D_tvla", False, "D in SPICE: max|t| < 4.5 (informational)"),
            ("K5", "DA_tvla", False, "DA in SPICE: max|t| < 4.5 at 20,000 (amendment A1)")):
        e = {"criterion": text}
        if name in c:
            sp = c[name]["spice"]
            e.update(max_abs_t=sp["final_max_abs_t"], traces=c[name]["rows_analysed"],
                     first_above=sp["first_above"], stable_from=sp["stable_from"],
                     peak_ns_after_edge=sp["final_peak_ns_after_edge"])
            e["pass"] = (sp["final_max_abs_t"] > THRESHOLD) if want_leak else (sp["final_max_abs_t"] < THRESHOLD)
            if kid == "K5":
                e["complete"] = c[name]["rows_analysed"] >= 20000 - 3
        crit[kid] = e
    # K6 (informational): SPICE t-peak on or after the switching of the flagged nets, and the
    # nets whose transitions depend on the class near the peak are flagged nets
    k6 = {"criterion": "SPICE t-peaks of N and D occur on or after the switching of the nets flagged by "
                       "glitch-extended probing (informational, amendment A1)"}
    for v, loc in s.get("localization", {}).items():
        e = {"spice_peak_ns_after_edge": loc["spice_peak_ns_after_edge"], "spice_peak_t": loc["spice_peak_t"]}
        for src in ("spice_nodes", "level2_nets"):
            if src in loc:
                r = loc[src]
                w = r.get("flagged_nets_switching_p5_p95_ns_after_edge")
                e[src] = {"rows": r["rows"], "flagged_switching_p5_p95_ns": w,
                          "nets_above_threshold_near_peak": r["nets_above_threshold_near_peak"],
                          "nets_above_threshold_anywhere": r["nets_above_threshold_anywhere"],
                          "all_above_anywhere_flagged": r["all_above_anywhere_flagged"],
                          "top10_near_peak_all_flagged": r["top10_near_peak_all_flagged"]}
        r = loc.get("spice_nodes")
        e["significant_spice_peak"] = bool(abs(loc["spice_peak_t"]) > THRESHOLD)
        if not e["significant_spice_peak"]:
            e["match"] = None
            e["note"] = ("no first-order leak in the supply current (max|t| below 4.5), so there is no "
                         "t-peak to place; the per-net results above still show which nets' own "
                         "transitions depend on the class")
        elif r and r.get("flagged_nets_switching_p5_p95_ns_after_edge"):
            p5 = r["flagged_nets_switching_p5_p95_ns_after_edge"][0]
            e["peak_on_or_after_flagged_switching"] = bool(loc["spice_peak_ns_after_edge"] >= p5)
            # match: the peak comes on or after the flagged nets start switching, every net whose
            # own transitions leak (|t| > 4.5 anywhere) is flagged, and so are the ten most
            # class-dependent nets within +-100 ps of the peak
            e["match"] = bool(e["peak_on_or_after_flagged_switching"] and r["all_above_anywhere_flagged"]
                              and r["top10_near_peak_all_flagged"])
        k6[v] = e
    crit["K6"] = k6
    # C
    cc = {"criterion": "(a) N random-vs-random < 4.5 at 10,000; (b) N masks-off leaks strongly at 1,000"}
    if "N_rvr" in c:
        cc["a_max_abs_t"] = spice_max("N_rvr")
        cc["a_traces"] = c["N_rvr"]["rows_analysed"]
        cc["a_pass"] = cc["a_max_abs_t"] < THRESHOLD
    if "N_masksoff" in c:
        cc["b_max_abs_t"] = spice_max("N_masksoff")
        cc["b_traces"] = c["N_masksoff"]["rows_analysed"]
        cc["b_first_above"] = c["N_masksoff"]["spice"]["first_above"]
        cc["b_pass"] = cc["b_max_abs_t"] > THRESHOLD
    if "a_pass" in cc and "b_pass" in cc:
        cc["pass"] = cc["a_pass"] and cc["b_pass"]
    crit["C"] = cc
    crit["GO"] = all(crit[k].get("pass") is True for k in ("K1", "K2", "K3")) and \
        crit["C"].get("pass") is True
    return crit


def main():
    os.makedirs(OUT, exist_ok=True)
    only = set(sys.argv[1:])
    summary = {"generated": datetime.date.today().isoformat(), "threshold": THRESHOLD,
               "noise_factors": list(NOISE), "campaigns": {}, "cpa": {}}
    t_spice = {}
    for name, (v, stem, role) in TVLA_RUNS.items():
        if only and name not in only:
            continue
        c = load_campaign(name, v, stem)
        if c is None:
            print("%-11s not run" % name)
            continue
        res, t = analyse_tvla(c)
        res["role"] = role
        res["stimulus"] = rel(os.path.join(STIM, stem + ".npy"))
        summary["campaigns"][name] = res
        t_spice[name] = t
        sp = res["spice"]
        print("%-11s %5d rows  SPICE max|t| %7.2f (first > 4.5 at %s, stable %s, peak %.3f ns)  "
              "L1 %s  L2 %s  func mism %s" % (
                  name, res["rows_analysed"], sp["final_max_abs_t"], sp["first_above"], sp["stable_from"],
                  sp["final_peak_ns_after_edge"],
                  [res["level1"][k]["final_max_abs_t"] for k in KEYS],
                  [res["level2"][k]["final_max_abs_t"] for k in KEYS], res["functional_mismatches"]),
              flush=True)
    for name, (v, stem) in CPA_RUNS.items():
        if only and name not in only:
            continue
        c = load_campaign(name, v, stem)
        if c is None:
            print("%-11s not run" % name)
            continue
        res = analyse_cpa(c)
        summary["cpa"][name] = res
        print("%-11s key %d: level-1-model rank %d (rank 1 from %s), HW rank %d, func mism %s; "
              "on model traces L1 %s L2 %s" % (
                  name, res["key"], res["level1_model"]["final_rank"], res["level1_model"]["rank1_stable_from"],
                  res["hw_sbox"]["final_rank"], res["functional_mismatches"], res["on_level1_traces"],
                  res["on_level2_traces"]), flush=True)
    if summary["cpa"]:
        with open(os.path.join(OUT, "cpa_rank_vs_traces.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["campaign", "key", "hypothesis", "traces", "rank"])
            for name, r in summary["cpa"].items():
                for h in ("level1_model", "hw_sbox", "level1_model_signed", "hw_sbox_signed"):
                    for nn, rk in zip(r[h]["n"], r[h]["rank"]):
                        w.writerow([name, r["key"], h, nn, rk])
    if not only or "l1_100k" in only:
        man0 = load_manifest(os.path.join(RUNS, next(iter(summary["campaigns"]))))
        summary["level1_100k"] = level1_100k(man0)
        print("level 1, 100k:", {v: [r[k]["final_max_abs_t"] for k in KEYS]
                                 for v, r in summary["level1_100k"].items()}, flush=True)
    summary["localization"] = {}
    for v, name in (("N", "N_tvla"), ("D", "D_tvla"), ("DA", "DA_tvla")):
        if name in t_spice and (not only or "loc" in only or name in only):
            lag = summary["campaigns"][name]["level2_vs_spice"]["waveform_lag_ps"]
            loc = localize(v, t_spice[name], name, lag)
            for src in ("spice_nodes", "level2_nets"):
                if src in loc:
                    np.savez_compressed(os.path.join(RUNS, "pernet_%s_%s.npz" % (v, src)),
                                        t=loc[src]["_t"], act=loc[src]["_act"])
                    write_pernet_csv(v, src, loc[src], loc["_pre"])
            summary["localization"][v] = strip_private(loc)
            print("localization %s: SPICE peak %.3f ns; nets near peak (SPICE nodes): %s; (level 2): %s" % (
                v, loc["spice_peak_ns_after_edge"],
                loc.get("spice_nodes", {}).get("nets_above_threshold_near_peak"),
                loc["level2_nets"]["nets_above_threshold_near_peak"]), flush=True)
    summary["spice_wall_clock_s"] = spice_wall_clock()
    summary["setup"] = setup_block(summary)
    summary["criteria"] = criteria(summary)
    name = "summary.json" if not only else "summary_partial.json"
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(strip_private(summary), f, indent=1)
    print(json.dumps(summary["criteria"], indent=1))


if __name__ == "__main__":
    main()
