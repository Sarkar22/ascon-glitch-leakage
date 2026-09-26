# SPDX-License-Identifier: Apache-2.0
"""Cost of the fix: area, delay, latency, randomness and energy of U, N, D and DA.

Inputs:
  build/<V>/ports.json, graph.json    netlist sizes, Liberty area and timing estimate
                                      (python3 gen/make_variants.py)
  $PDK Liberty (tt_025C_1v80)         cell areas (cross-check), dfxtp_1 setup time and CLK pin
                                      capacitance; skipped with a note if the PDK is absent
  runs/kt/<V>_tvla/charge.npy         SPICE charge per window (random-class rows)
  results/kill_test/summary.json      first-order TVLA verdict
  results/key_recovery/summary.json   profiled key recovery (optional)
Outputs: results/cost/cost.csv and results/cost/cost.md.

Definitions:
  * Area: sum of the Liberty cell areas (no placement utilisation, no clock tree).
  * Register-to-register delay: the generator's static estimate, i.e. the latest arrival at a
    flip-flop D pin over paths that start at a flip-flop (clock-to-Q plus logic, Liberty tt,
    pre-layout loads). The dfxtp_1 setup time is added for a minimum clock period, and the
    latency in time is latency x minimum period. DA also has a port-to-register path: its
    affine XORs sit in front of the input registers. In a round-based core that path merges
    into the previous round's linear layer.
  * Fresh random bits per evaluation: the DOM gadgets' r bits. The mask bits (share 1 of
    the input) are listed separately. The testbench re-shares every input, but in a masked
    core the state stays shared from round to round.
  * Charge and energy: the mean SPICE supply charge of the DUT (i(VPWR) only). A window
    starts 0.2 ns before the capturing edge and lasts L clock cycles (L = latency); it
    depends on the inputs of rows r-L-1 .. r+L. The TVLA campaigns interleave the fixed
    input 0x0B, and a random row next to a fixed row draws a different charge (U: 263 fC after
    two fixed rows against 291 fC after two random ones, docs/reviews/stage2-key-recovery.md,
    check 18). So the mean is taken over the random-class rows whose whole
    neighbourhood r-L-1 .. r+L is random-class too, which estimates the charge for all-random
    inputs without bias (the mean over all random-class rows is kept as a check). The
    circuit takes a new input every cycle, so in steady state the charge per evaluation is
    the charge per clock cycle, which is the window charge / L. For L = 2 each cycle holds
    the first stage of one evaluation and the second stage of the previous one; the 8 ns
    window counts every cycle twice. Energy = charge x 1.8 V. Not in the SPICE current: the
    gate charge of the CLK pins (ideal clock source) and of the input D pins (ideal
    sources). The CLK pin part is estimated from Liberty as n_dff x C_CLK x VDD^2 per cycle
    and listed separately.
  * Security: the kill test's first-order TVLA, and the profiled key recovery
    (analysis/key_recovery.py) with its primary distinguisher, the Gaussian template. For
    the variants without key recovery, the injection test gives the leak the attack would
    have found at the same data volume.

  python3 analysis/cost_table.py     (host python3 + numpy)
"""
import csv
import json
import math
import os
import sys

import numpy as np

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(REPO, "analysis"))
sys.path.insert(0, os.path.join(REPO, "gen"))

import kill_test as kt       # noqa: E402

OUT = os.path.join(REPO, "results", "cost")
VARIANTS = ("U", "N", "D", "DA")
CAMPAIGN = {"U": "U_tvla", "N": "N_tvla", "D": "D_tvla", "DA": "DA_tvla"}
EXTRA_CAMPAIGNS = {"N": "N_rvr"}                 # all-random rows: a cross-check of the charge
KEY_RECOVERY_DATASET = {"U": "U_tvla", "N": "N_pooled", "D": "D_tvla", "DA": "DA_tvla"}
VERDICT_NOTES = {         # level 2's max|t| on the same rows: %(l2)s cap-weighted, %(l2_worst)s worst weighting
    "D": "the SPICE node run confirms a net-level leak (docs/KILL_TEST.md, K6), and level 2 predicts max|t| "
         "%(l2)s (cap-weighted; %(l2_worst)s with the worst of three weightings) on the same rows; it does not "
         "show in the supply current at this count",
}
L2_WEIGHTINGS = ("unweighted", "weighted", "weighted_rise")
DFF = "dfxtp_1"
VDD = 1.8


# ------------------------------------------------------------------ helpers

def load_json(path):
    with open(path) as f:
        return json.load(f)


def netlist_facts(v):
    ports = load_json(os.path.join(kt.dut(v), "ports.json"))
    graph = load_json(os.path.join(kt.dut(v), "graph.json"))
    types = {}
    for c in graph["cells"]:
        t = c["type"].replace("sky130_fd_sc_hd__", "")
        types[t] = types.get(t, 0) + 1
    roles = [p["role"] for p in ports["inputs"]]
    d_nets = [c["pins"]["D"] for c in graph["cells"] if c["type"].endswith(DFF)]
    d_slews = [graph["nets"][n].get("slew_ps") for n in d_nets]
    return {"cells": ports["n_cells"], "dff": ports["n_dff"], "comb": ports["n_cells"] - ports["n_dff"],
            "cell_types": types, "area_um2": ports["area_um2"], "latency": ports["latency"],
            "reg_to_reg_ps": ports["reg_to_reg_ps"], "port_to_reg_ps": ports["port_to_reg_ps"],
            "fresh_random_bits": roles.count("rand"), "mask_bits": roles.count("share1"),
            "shares": 2 if "share1" in roles else 1,
            "worst_d_slew_ps": max(s if s is not None else graph["timing"].get("port_and_clk_slew_ps", 50.0)
                                   for s in d_slews),
            "clk_slew_ps": graph["timing"].get("port_and_clk_slew_ps", 50.0)}


def liberty_facts(cell_types):
    """Liberty area of every cell type used, dfxtp_1 CLK pin capacitance and setup tables.
    Returns None when the PDK is not installed."""
    try:
        import pdk
        lib = pdk.Liberty()
    except (FileNotFoundError, OSError, ImportError):
        return None
    area = {t: lib.cell(t)["area_um2"] for t in cell_types}
    clk_cap = lib.cell(DFF)["pins"]["CLK"]["cap_fF"]
    return {"area": area, "clk_cap_fF": clk_cap, "setup": setup_tables(lib, pdk)}


def setup_tables(lib, pdk):
    """setup_rising rise/fall constraint tables of dfxtp_1's D pin (index_1 = CLK
    transition, index_2 = D transition, ns)."""
    full = "%s__%s" % (pdk.LIB, DFF)
    start = lib.text.find('cell ("%s")' % full)
    depth, i = 0, lib.text.index("{", start)
    for k in range(i, len(lib.text)):
        depth += {"{": 1, "}": -1}.get(lib.text[k], 0)
        if depth == 0:
            break
    body, _ = pdk._parse(pdk._TOK.findall(lib.text[i + 1:k].replace("\\\n", " ")), 0)
    for s in body:
        if s[0] == "group" and s[1] == "pin" and s[2][0] == "D":
            for t in s[3]:
                if t[0] == "group" and t[1] == "timing":
                    attrs = {u[1]: u[2] for u in t[3] if u[0] == "attr"}
                    if attrs.get("timing_type") == "setup_rising":
                        return {u[1]: pdk._table(u) for u in t[3]
                                if u[0] == "group" and u[1] in ("rise_constraint", "fall_constraint")}
    raise KeyError("setup_rising of %s/D not found" % full)


def setup_ps(tables, clk_slew_ps, d_slew_ps):
    """Worst (rise/fall) dfxtp_1 setup time in ps at the given CLK and D transitions."""
    import pdk
    return max(1000.0 * pdk.interp2(tab, clk_slew_ps / 1000.0, d_slew_ps / 1000.0) for tab in tables.values())


def random_neighbourhood(random_row, latency, skip):
    """Rows whose window depends on random-class inputs only: the row itself and the rows
    r-L-1 .. r+L are all random-class (L = latency). Rows before `skip` and rows whose
    neighbourhood runs past either end are excluded."""
    rnd = np.asarray(random_row, dtype=bool)
    n = len(rnd)
    ok = rnd.copy()
    ok[:skip] = False
    for d in range(-latency - 1, latency + 1):
        if d == 0:
            continue
        other = np.zeros(n, dtype=bool)          # other[r] = rnd[r + d], False outside the run
        if d < 0:
            other[-d:] = rnd[:n + d]
        else:
            other[:n - d] = rnd[d:]
        ok &= other
    return ok


def window_charge(name):
    """Charge per window (fC) and per clock cycle over the random-class rows of a campaign
    whose neighbourhood is random-class too (random_neighbourhood), and, as a check, over
    all random-class rows."""
    run = os.path.join(kt.RUNS, name)
    man = kt.load_manifest(run)
    q = np.load(os.path.join(run, "charge.npy"))
    stem = kt.TVLA_RUNS[name][1]
    meta = np.load(os.path.join(kt.STIM, stem + ".meta.npz"))
    lat = man["latency"]
    n = len(q)
    random_row = (meta["label"][:n] == 1) if str(meta["mode"]) == "tvla" else np.ones(n, dtype=bool)
    rows = np.arange(n)
    keep = random_row & (rows >= lat + 1)
    clean = random_neighbourhood(random_row, lat, lat + 1)
    out = charge_stats(q[clean], lat, man["params"]["vdd"], man["params"]["period"])
    out["q_window_all_random_class_rows_fC"] = float(q[keep].mean())
    out["rows_all_random_class"] = int(keep.sum())
    return out


def charge_stats(q_window, latency, vdd, period_ns):
    """Mean charge per window and per evaluation (= per cycle in steady state), energy."""
    q_window = np.asarray(q_window, dtype=np.float64)
    q_eval = q_window.mean() / latency
    return {"rows": int(len(q_window)), "window_ns": latency * period_ns,
            "q_window_fC": float(q_window.mean()), "q_window_std_fC": float(q_window.std(ddof=1)),
            "q_window_sem_fC": float(q_window.std(ddof=1) / math.sqrt(len(q_window))),
            "q_eval_fC": float(q_eval), "e_eval_fJ": float(q_eval * vdd),
            "avg_power_uW_at_period": float(q_eval * vdd / period_ns)}   # fJ/ns = uW


def tvla_detectable_fraction(summary, v):
    """The leak TVLA would reach 4.5 for on average at the variant's trace count, as a
    fraction of N's effect size (t = d sqrt(n) / 2, docs/KILL_TEST.md)."""
    c = summary["campaigns"]
    n_ref = c["N_tvla"]
    d_n = 2.0 * n_ref["spice"]["final_max_abs_t"] / math.sqrt(n_ref["rows_analysed"])
    n = c[CAMPAIGN[v]]["rows_analysed"]
    return (2.0 * kt.THRESHOLD / math.sqrt(n)) / d_n


def verdict(summary, v):
    c = summary["campaigns"].get(CAMPAIGN[v])
    if c is None:
        return None
    sp = c["spice"]
    n = c["rows_analysed"]
    t = sp["final_max_abs_t"]
    if t > kt.THRESHOLD:
        text = "leaks: max|t| %.1f at %s traces (above 4.5 from %s on)" % (
            t, format(n, ","), format(sp["stable_from"] or sp["first_above"], ","))
    else:
        text = "no first-order leak detected: max|t| %.2f < 4.5 at %s traces; at this count TVLA reaches " \
               "|t| 4.5 on average for a leak of %.2f x N's effect size" % (
                   t, format(n, ","), tvla_detectable_fraction(summary, v))
    if v in VERDICT_NOTES:
        l2 = c["level2"]
        worst = max(l2[k]["final_max_abs_t"] for k in L2_WEIGHTINGS if k in l2)
        text += "; " + VERDICT_NOTES[v] % {"l2": "%.1f" % l2["weighted"]["final_max_abs_t"],
                                           "l2_worst": "%.1f" % worst}
    return {"max_abs_t": t, "traces": n, "leaks": bool(t > kt.THRESHOLD), "text": text}


def bits_text(r):
    return "P(x1) %.2f, P(x2) %.2f" % (r["final_sr_x1"], r["final_sr_x2"])


def recovered_text(r, name="template"):
    """'key recovered (template): SR >= 0.9 from 7 traces per key' or None."""
    t = r["traces_to_sr90"]
    if t is None:
        return None
    return "key recovered (%s): SR >= 0.9 from %d trace%s per key" % (name, t, "" if t == 1 else "s")


def not_recovered_text(r, name="template"):
    """The result when SR stays below 0.9: 'partly recovered' if GE lies below every null
    draw, else 'no key recovery'."""
    what = "key partly recovered" if r["final_ge"] < r["null_min"] else "no key recovery"
    return "%s at %d attack traces per key (%s): GE %.2f, SR %.2f (random 1.5, 0.25; null %.2f +- %.2f)" % (
        what, r["n"][-1], name, r["final_ge"], r["final_sr"], r["null_mean"], r["null_sd"])


def partial(r):
    return r["final_ge"] < r["null_min"] and r["traces_to_sr90"] is None


def injection_text(inj):
    """What the primary attack detects at the same data volume (injection test)."""
    al = inj["smallest_detected_alpha"]["tmpl"]
    ge = {float(a): r["tmpl"]["final_ge"] for a, r in inj["alphas"].items()}
    if al is None:
        return "an injected leak shaped like N's is not detected even at N's full strength (GE %.2f)" % ge[max(ge)]
    below = sorted((a for a in ge if a < al), reverse=True)
    text = "at this data volume the attack detects an injected leak shaped like N's from %g x N's strength " \
           "(GE %.2f)" % (al, ge[al])
    if below:
        text += ", not at %g x (GE %.2f)" % (below[0], ge[below[0]])
    return text


def result(ds, tag, dist):
    """A key-recovery result with its null mean and SD attached (or None)."""
    r = ds and ds["results"].get(tag)
    if not r or dist not in r:
        return None
    out = dict(r[dist])
    nl = r.get("null", {}).get(dist, {})
    out["null_mean"], out["null_sd"] = nl.get("final_ge_mean", float("nan")), nl.get("final_ge_sd", float("nan"))
    out["null_min"] = nl.get("final_ge_min", float("-inf"))
    return out


def key_recovery_text(kr, v, order=1):
    """Result of the profiled attack with the primary distinguisher (Gaussian template), no
    added noise. N adds the post hoc per-key-bit template; D and DA add the injection test."""
    if kr is None:
        return None
    ds = kr["datasets"].get(KEY_RECOVERY_DATASET[v])
    tag = "order%d_noise0" % order
    t = result(ds, tag, "tmpl")
    if not t:
        return None
    if v == "N" and order == 1:
        b = result(ds, tag, "tmpl_bits")
        text = "default POIs (overall F): %s; %s" % (
            recovered_text(t) or "GE %.2f, SR %.2f at %d attack traces per key" % (t["final_ge"], t["final_sr"],
                                                                                   t["n"][-1]), bits_text(t))
        if b:
            text += ". Per-key-bit POIs (post hoc): %s; %s" % (
                recovered_text(b) or "GE %.2f, SR %.2f at %d" % (b["final_ge"], b["final_sr"], b["n"][-1]),
                bits_text(b))
        return text
    text = recovered_text(t) or not_recovered_text(t)
    if v == "N" and order == 2:
        text += " (not independent evidence: the centred square carries N's first-order shift)"
    if order == 1 and ds.get("injection") and not recovered_text(t) and not partial(t):
        text += "; " + injection_text(ds["injection"])
    return text


# ------------------------------------------------------------------ table

COLUMNS = [
    ("variant", "Variant"), ("shares", "Shares"), ("cells", "Cells"), ("dff", "Flip-flops"),
    ("comb", "Logic cells"), ("area_um2", "Area (um2)"), ("area_vs_N", "Area vs N"),
    ("reg_to_reg_ps", "Reg-to-reg (ps)"), ("setup_ps", "Setup (ps)"), ("min_period_ps", "Min period (ps)"),
    ("port_to_reg_ps", "Port-to-reg (ps)"), ("latency_cycles", "Latency (cycles)"),
    ("latency_ns", "Latency (ns)"), ("latency_vs_N", "Latency vs N"),
    ("fresh_random_bits", "Fresh random bits"), ("mask_bits", "Mask bits"),
    ("window_ns", "SPICE window (ns)"), ("charge_rows", "Rows averaged"), ("q_window_fC", "Charge per window (fC)"),
    ("q_window_sem_fC", "Charge per window, std. error (fC)"),
    ("q_eval_fC", "Charge per evaluation (fC)"), ("e_eval_fJ", "Energy per evaluation (fJ)"),
    ("energy_vs_N", "Energy vs N (SPICE only)"), ("clk_pin_fJ", "CLK pins, not in SPICE (fJ/cycle)"),
    ("e_total_fJ", "Energy incl. CLK pins (fJ)"), ("total_vs_N", "Total vs N (incl. CLK pins)"),
    ("q_window_all_random_class_rows_fC", "Check: charge per window over all random-class rows (fC)"),
    ("tvla_max_abs_t", "TVLA max|t|"), ("tvla_traces", "TVLA traces"),
    ("first_order_verdict", "First-order verdict"), ("key_recovery_order1", "Profiled key recovery, 1st order"),
    ("key_recovery_order2", "Profiled key recovery, 2nd order"),
]


def build_rows():
    kts = load_json(os.path.join(kt.OUT, "summary.json"))
    krp = os.path.join(REPO, "results", "key_recovery", "summary.json")
    krs = load_json(krp) if os.path.exists(krp) else None
    facts = {v: netlist_facts(v) for v in VARIANTS}
    types = sorted({t for f in facts.values() for t in f["cell_types"]})
    lib = liberty_facts(types)
    rows, checks = [], {}
    for v in VARIANTS:
        f = facts[v]
        r = {"variant": v, "shares": f["shares"], "cells": f["cells"], "dff": f["dff"], "comb": f["comb"],
             "area_um2": f["area_um2"], "reg_to_reg_ps": f["reg_to_reg_ps"],
             "port_to_reg_ps": f["port_to_reg_ps"], "latency_cycles": f["latency"],
             "fresh_random_bits": f["fresh_random_bits"], "mask_bits": f["mask_bits"]}
        if lib:
            area = sum(lib["area"][t] * n for t, n in f["cell_types"].items())
            checks["area_liberty_vs_ports_%s" % v] = round(area - f["area_um2"], 3)
            r["setup_ps"] = round(setup_ps(lib["setup"], f["clk_slew_ps"], f["worst_d_slew_ps"]), 1)
            r["min_period_ps"] = round(f["reg_to_reg_ps"] + r["setup_ps"], 1)
            r["latency_ns"] = round(f["latency"] * r["min_period_ps"] / 1000.0, 3)
        name = CAMPAIGN[v]
        if os.path.exists(os.path.join(kt.RUNS, name, "charge.npy")):
            q = window_charge(name)
            r.update(window_ns=q["window_ns"], charge_rows=q["rows"], q_window_fC=round(q["q_window_fC"], 1),
                     q_window_sem_fC=round(q["q_window_sem_fC"], 1), q_eval_fC=round(q["q_eval_fC"], 1),
                     e_eval_fJ=round(q["e_eval_fJ"], 1),
                     q_window_all_random_class_rows_fC=round(q["q_window_all_random_class_rows_fC"], 1))
            checks["charge_rows_%s" % name] = q["rows"]
            checks["charge_rows_all_random_class_%s" % name] = q["rows_all_random_class"]
            checks["charge_window_std_fC_%s" % name] = round(q["q_window_std_fC"], 1)
            if v in EXTRA_CAMPAIGNS and os.path.exists(os.path.join(kt.RUNS, EXTRA_CAMPAIGNS[v], "charge.npy")):
                qx = window_charge(EXTRA_CAMPAIGNS[v])
                checks["charge_per_evaluation_fC_%s" % EXTRA_CAMPAIGNS[v]] = round(qx["q_eval_fC"], 1)
        if lib:
            r["clk_pin_fJ"] = round(f["dff"] * lib["clk_cap_fF"] * VDD * VDD, 1)
            if "e_eval_fJ" in r:
                r["e_total_fJ"] = round(r["e_eval_fJ"] + r["clk_pin_fJ"], 1)
        vd = verdict(kts, v)
        if vd:
            r.update(tvla_max_abs_t=vd["max_abs_t"], tvla_traces=vd["traces"], first_order_verdict=vd["text"])
        r["key_recovery_order1"] = key_recovery_text(krs, v, 1)
        r["key_recovery_order2"] = key_recovery_text(krs, v, 2) if f["shares"] == 2 else None
        rows.append(r)
    base = {r["variant"]: r for r in rows}
    for r in rows:
        r["area_vs_N"] = round(r["area_um2"] / base["N"]["area_um2"], 2)
        for k, out in (("e_eval_fJ", "energy_vs_N"), ("e_total_fJ", "total_vs_N"), ("latency_ns", "latency_vs_N")):
            if k in r and k in base["N"]:
                r[out] = round(r[k] / base["N"][k], 2)
    corr_note = None
    if krs:
        corr_note = correlation_note(krs)
    meta = {"liberty": "sky130_fd_sc_hd__tt_025C_1v80" if lib else None,
            "dfxtp_1_clk_pin_cap_fF": lib["clk_cap_fF"] if lib else None, "checks": checks,
            "correlation_note": corr_note}
    return rows, meta


def correlation_note(krs):
    """The secondary distinguisher's results on the injection test, in words."""
    parts = []
    for v in ("D", "DA"):
        ds = krs["datasets"].get(KEY_RECOVERY_DATASET[v], {})
        inj = ds.get("injection")
        if inj:
            al = inj["smallest_detected_alpha"]["corr"]
            full = inj["alphas"]["1"]["corr"]["final_ge"]
            parts.append("%s: %s" % (v, "detects an injected N-shaped leak from %g x N's strength" % al if al
                                     else "misses an injected N-shaped leak even at N's full strength (GE %.2f)" % full))
    return "; ".join(parts) if parts else None


def fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return ("%.2f" % v) if abs(v) < 10 else ("%.1f" % v)
    if isinstance(v, int) and v >= 1000:
        return format(v, ",")
    return str(v)


def write(rows, meta):
    os.makedirs(OUT, exist_ok=True)
    keys = [k for k, _ in COLUMNS]
    with open(os.path.join(OUT, "cost.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(keys)
        for r in rows:
            w.writerow(["" if r.get(k) is None else r.get(k) for k in keys])
    head = dict(COLUMNS)
    hw = ["variant", "shares", "cells", "dff", "comb", "area_um2", "area_vs_N", "reg_to_reg_ps", "setup_ps",
          "min_period_ps", "port_to_reg_ps", "latency_cycles", "latency_ns", "latency_vs_N",
          "fresh_random_bits", "mask_bits"]
    en = ["variant", "window_ns", "charge_rows", "q_window_fC", "q_window_sem_fC", "q_eval_fC", "e_eval_fJ",
          "energy_vs_N", "clk_pin_fJ", "e_total_fJ", "total_vs_N"]

    def table(keys):
        out = ["| " + " | ".join(head[k].replace("|", "\\|") for k in keys) + " |", "|" + "---|" * len(keys)]
        return out + ["| " + " | ".join(fmt(r.get(k)) for k in keys) + " |" for r in rows]
    ck = meta["checks"]
    lines = ["<!-- SPDX-License-Identifier: Apache-2.0 -->",
             "# Cost of the fix: U, N, D and DA",
             "",
             "Generated by `analysis/cost_table.py` from the netlists (`build/<V>/ports.json`, `graph.json`), the "
             "Liberty file (%s), the SPICE campaigns' `charge.npy`, `results/kill_test/summary.json` and "
             "`results/key_recovery/summary.json`. Pre-layout estimates; SPICE at sky130 tt, 1.8 V, 27 C, "
             "clock period 4 ns. All columns are also in `cost.csv`." % (meta["liberty"] or "absent"),
             "", "**Hardware**", ""] + table(hw) + ["", "**Energy** (SPICE supply charge of the DUT, all-random "
                                                        "neighbourhoods; the last three columns add the Liberty "
                                                        "estimate of the CLK-pin charge; see below)", ""] + table(en)
    lines += ["", "**Security** (first order: the kill test's TVLA. Key recovery: `analysis/key_recovery.py`, no "
              "added noise, with the primary distinguisher, the Gaussian template; GE = mean rank of the correct "
              "2-bit key, 1.5 = random; the null is the same pipeline on permuted profiling labels):", ""]
    lines += ["| Variant | First-order TVLA | Profiled key recovery, 1st order | 2nd order |", "|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s |" % (r["variant"], fmt(r.get("first_order_verdict")).replace("|", "\\|"),
                                                fmt(r.get("key_recovery_order1")), fmt(r.get("key_recovery_order2"))))
    lines += ["", "**What the columns cover.**",
              "- Area: sum of the Liberty cell areas, without placement utilisation or a clock tree.",
              "- Reg-to-reg: the generator's static estimate (clock-to-Q plus logic to the latest flip-flop D pin, "
              "Liberty tt, pre-layout loads). Setup: dfxtp_1 `setup_rising` at the generator's clock slew and the "
              "slowest D-pin slew. Min period = reg-to-reg + setup. Latency (ns) = latency x min period: the "
              "barrier doubles the cycles but shortens the cycle, so in time D's latency is %s and DA's %s longer "
              "than N's, not twice as long." % (pct(rows, "D", "latency_vs_N"), pct(rows, "DA", "latency_vs_N")),
              "- Port-to-reg: logic between the input ports and the input registers. Only DA has any: its affine "
              "XORs sit in front of the registers (%s ps). In a round-based core they merge into the previous "
              "round's linear layer." % fmt(next(r["port_to_reg_ps"] for r in rows if r["variant"] == "DA")),
              "- Fresh random bits: the DOM gadgets' r bits per S-box evaluation. Mask bits: share 1 of the input. "
              "The testbench re-shares every input, but a masked core keeps its state shared between rounds, so "
              "these bits are needed only once, at the start.",
              "- Charge: the mean SPICE supply charge of the DUT (i(VPWR)). The window starts 0.2 ns before the "
              "capturing edge, lasts L cycles and depends on the inputs of rows r-L-1 .. r+L. The TVLA campaigns "
              "interleave the fixed input 0x0B, and a random row next to a fixed row draws a different charge, so "
              "the mean is taken over the random-class rows whose whole neighbourhood is random-class ('Rows "
              "averaged'); this estimates the all-random charge without that bias. Over all random-class rows "
              "the means are %s fC: %s %% lower for U, and within %s %% for the masked variants." % (
                  ", ".join("%s %s" % (r["variant"], fmt(r.get("q_window_all_random_class_rows_fC"))) for r in rows),
                  "%.1f" % bias_pct(rows[0]), "%.1f" % max(abs(bias_pct(r)) for r in rows[1:])),
              "- A new input enters every cycle, so the charge per evaluation is the charge per clock cycle, i.e. "
              "the window charge / L. For latency 2 the 8 ns window covers two cycles, and each cycle holds the "
              "first stage of one evaluation and the second stage of the previous one. Energy = charge x 1.8 V. "
              "This assumes a pipelined use: a round-based core that does not interleave two independent states "
              "needs 2 cycles per round with a latency-2 S-box and pays about one extra cycle of clock and "
              "register overhead per evaluation, which these figures leave out.",
              "- Not in the SPICE current: the gate charge of the CLK pins (ideal clock) and of the input D pins "
              "(ideal sources). The CLK pin column estimates the first as n_dff x C_CLK (%s fF, Liberty) x VDD^2 "
              "per cycle; a clock tree would add its own buffers." % fmt(meta["dfxtp_1_clk_pin_cap_fF"]),
              "- Key recovery: the Gaussian template is the primary distinguisher (fixed after the stage-2 review; "
              "it sees a key bit's main effect). N's per-key-bit POIs were added post hoc, after the review found "
              "that key bit x2 leaks through interactions that the default POIs (overall F) miss. The correlation "
              "distinguisher is secondary and enters no verdict: centring over the attack traces removes the "
              "level shift between keys" + (" (injection test: %s)." % meta["correlation_note"]
                                            if meta.get("correlation_note") else "."),
              "",
              "Checks: the Liberty area equals the generator's for every variant (difference %s um2). "
              "Rows averaged for the charge: %s (all random-class rows: %s). Charge per evaluation of N on the "
              "all-random campaign N_rvr: %s fC." % (
                  ", ".join("%g" % ck.get("area_liberty_vs_ports_" + v, float("nan")) for v in VARIANTS),
                  ", ".join("%s %s" % (CAMPAIGN[v], format(ck.get("charge_rows_" + CAMPAIGN[v], 0), ","))
                            for v in VARIANTS),
                  ", ".join(format(ck.get("charge_rows_all_random_class_" + CAMPAIGN[v], 0), ",") for v in VARIANTS),
                  ck.get("charge_per_evaluation_fC_N_rvr"))]
    with open(os.path.join(OUT, "cost.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", kt.rel(os.path.join(OUT, "cost.csv")), "and cost.md")


def bias_pct(r):
    """How much lower (in %) the mean over all random-class rows is than the all-random estimate."""
    return round(100.0 * (1.0 - r["q_window_all_random_class_rows_fC"] / r["q_window_fC"]), 1)


def pct(rows, v, key):
    """'28 %' for a ratio of 1.28 in column key of variant v."""
    r = next(r for r in rows if r["variant"] == v)
    return "-" if r.get(key) is None else "%d %%" % round(100 * (r[key] - 1))


def main():
    rows, meta = build_rows()
    for r in rows:
        print({k: r.get(k) for k, _ in COLUMNS if k not in ("first_order_verdict",)})
    print(meta)
    write(rows, meta)


if __name__ == "__main__":
    main()
