# SPDX-License-Identifier: Apache-2.0
"""Data access for the notebook: find the data files and read the results.

Needs only the Python standard library and numpy, so it also runs on a bare host.

Where the data come from, in this order:
  1. data/ next to this file: the notebook's own data set (CSV and a few JSON summaries, listed
     in data/MANIFEST.csv; written by make_cached_data.py from results/ and the SPICE runs).
     This is what the submission folder ships and what CI reads.
  2. results/ of the repository (results/kill_test/, results/probing/), when data/ lacks a file.

  root()                 the repository root (holds build/, model/) or, without it, this folder
  summary()              the kill-test summary (summary.json)
  read_csv(name)         a result CSV as {column: numpy array}
  read_matrix(name)      a wide CSV (keys, times in ns, values)
  probing()              the exact probing results for N, D, DA
  headline(s)            the numbers quoted in the notebook's text
  fmt_headline(s)        the same numbers as strings, for the notebook builder
  key_recovery()         the profiled key recovery (results/key_recovery/summary.json)
  cost()                 the cost table (results/cost/cost.csv), one dict per variant
  layout()               the layouts and their sign-off (results/layout/summary.json)
  postlayout()           the post-layout TVLA (results/pex/summary_postlayout.json)
  node_timing()          pre- vs post-layout node timing of N (results/pex/node_timing_N.json)
  placement(v)           the placed cells of a layout (results/layout/placement_<V>.csv)
  read_step_csv(step, n) a CSV of a later step (data/<step>__<n>.csv or results/<step>/<n>.csv)

The numbers the notebook quotes from the result files come from headline(), so the prose and
those files cannot drift apart (make_notebook.py fills the text; test_notebook.py checks it).
A few numbers from the reviews in docs/reviews/ are quoted as fixed text.
"""
import csv
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
MARKER = os.path.join("results", "kill_test", "summary.json")
THRESHOLD = 4.5
WEIGHTINGS = ("unweighted", "weighted", "weighted_rise")
VARIANT_NAMES = {
    "U": "unmasked",
    "N": "naive DOM (no register barrier)",
    "D": "DOM with register barrier (textbook placement)",
    "DA": "DOM with the barrier after Ascon's affine layer",
}


def root():
    """Repository root: $ASCON_GLITCH_ROOT, else the first parent of this file or of the working
    directory that holds results/kill_test/summary.json, else this file's folder."""
    env = os.environ.get("ASCON_GLITCH_ROOT")
    if env and os.path.exists(os.path.join(env, MARKER)):
        return os.path.abspath(env)
    for start in (HERE, os.getcwd()):
        d = start
        while True:
            if os.path.exists(os.path.join(d, MARKER)):
                return d
            up = os.path.dirname(d)
            if up == d:
                break
            d = up
    return HERE


def path(*parts):
    return os.path.join(root(), *parts)


def find(data_name, results_parts):
    """data/<data_name> if it exists, else <root>/<results_parts...>."""
    p = os.path.join(DATA, data_name)
    if os.path.exists(p):
        return p
    p = path(*results_parts)
    if os.path.exists(p):
        return p
    raise FileNotFoundError("%s: neither data/%s nor %s" % (data_name, data_name, os.path.join(*results_parts)))


def source():
    """'data' when the notebook reads its own data set, else 'results'."""
    return "data" if os.path.exists(os.path.join(DATA, "kill_test_summary.json")) else "results"


def summary():
    with open(find("kill_test_summary.json", ("results", "kill_test", "summary.json"))) as f:
        return json.load(f)


def _rows(p):
    with open(p, newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def read_csv(name, strings=False):
    """A result CSV as {column: float array} (empty cells and 'None' become nan); with
    strings=True as {column: list of str}."""
    import numpy as np
    head, body = _rows(find(name + ".csv", ("results", "kill_test", name + ".csv")))
    if strings:
        return {h: [r[i] for r in body] for i, h in enumerate(head)}
    return {h: np.array([float(r[i]) if r[i] not in ("", "None") else np.nan for r in body])
            for i, h in enumerate(head)}


def read_matrix(name, key_cols=1):
    """A wide data/ CSV as (keys {column: array}, times in ns, values (rows, samples))."""
    import numpy as np
    head, body = _rows(os.path.join(DATA, name + ".csv"))
    keys = {head[j]: np.array([float(r[j]) for r in body]) for j in range(key_cols)}
    times = np.array([float(h) for h in head[key_cols:]])
    values = np.array([[float(v) for v in r[key_cols:]] for r in body])
    return keys, times, values


def probing(variants=("N", "D", "DA")):
    """Per variant: n_nets, value_fail, glitch_fail (net names) and nets [{net, glitch_ok,
    both_shares_of (x bit numbers)}], from data/probing_nets.csv or results/probing/<V>.json."""
    p = os.path.join(DATA, "probing_nets.csv")
    if not os.path.exists(p):
        out = {}
        for v in variants:
            with open(path("results", "probing", v + ".json")) as f:
                out[v] = json.load(f)
        return out
    head, body = _rows(p)
    col = {h: i for i, h in enumerate(head)}
    out = {v: {"variant": v, "n_nets": 0, "value_fail": [], "glitch_fail": [], "nets": []} for v in variants}
    for r in body:
        v = r[col["variant"]]
        if v not in out:
            continue
        o = out[v]
        net = r[col["net"]]
        o["n_nets"] += 1
        if r[col["value_model_fail"]] == "1":
            o["value_fail"].append(net)
        gl_fail = r[col["glitch_extended_fail"]] == "1"
        if gl_fail:
            o["glitch_fail"].append(net)
        both = [int(b[1:]) for b in r[col["both_shares_of"]].split()]
        o["nets"].append({"net": net, "glitch_ok": not gl_fail, "both_shares_of": both})
    return out


def key_recovery():
    """The key-recovery summary: data/key_recovery__summary.json, else results/key_recovery/."""
    with open(find("key_recovery__summary.json", ("results", "key_recovery", "summary.json"))) as f:
        return json.load(f)


def cost():
    """The cost table as {variant: {column: str}} (data/cost__cost.csv, else results/cost/)."""
    with open(find("cost__cost.csv", ("results", "cost", "cost.csv")), newline="") as f:
        return {r["variant"]: r for r in csv.DictReader(f)}


def _step_json(step, name):
    with open(find("%s__%s" % (step, name), ("results", step, name))) as f:
        return json.load(f)


def layout():
    """Layout and sign-off of N, DA and U: data/layout__summary.json, else results/layout/."""
    return _step_json("layout", "summary.json")


def postlayout():
    """The post-layout TVLA (docs/POSTLAYOUT.md): data/pex__summary_postlayout.json, else results/pex/."""
    return _step_json("pex", "summary_postlayout.json")


def node_timing():
    """N's node timing before and after layout: data/pex__node_timing_N.json, else results/pex/."""
    return _step_json("pex", "node_timing_N.json")


def placement(v):
    """The placed cells of variant v (data/layout__placement_<V>.csv, else results/layout/), as a
    list of dicts: instance, cell, x_um, y_um, w_um, h_um (float), kind (logic / clock / physical),
    domain (s0, s1, r, cross, x), output_net, flagged (bool)."""
    head, body = _rows(find("layout__placement_%s.csv" % v, ("results", "layout", "placement_%s.csv" % v)))
    out = []
    for r in body:
        d = dict(zip(head, r))
        for k in ("x_um", "y_um", "w_um", "h_um"):
            d[k] = float(d[k])
        d["flagged"] = d["flagged"] == "1"
        out.append(d)
    return out


def read_step_csv(step, name):
    """A CSV of a later step (e.g. step 'pex', name 'tcurve_N_pex') as {column: float array}."""
    import numpy as np
    head, body = _rows(find("%s__%s.csv" % (step, name), ("results", step, name + ".csv")))
    return {h: np.array([float(r[i]) if r[i] not in ("", "None") else np.nan for r in body])
            for i, h in enumerate(head)}


def effect_size_sd(t, n):
    """Standardized mean difference (in per-sample standard deviations) that gives Welch t
    with n traces split about evenly between the two classes: t = d * sqrt(n) / 2."""
    return 2.0 * t / math.sqrt(n)


def headline(s=None):
    """The numbers the notebook quotes, as plain Python values."""
    s = s or summary()
    c = s["campaigns"]
    cr = s["criteria"]
    h = {}
    for name, key in (("U_tvla", "U"), ("N_masksoff", "Nmo"), ("N_rvr", "Nrvr"),
                      ("N_tvla", "N"), ("D_tvla", "D"), ("DA_tvla", "DA")):
        sp = c[name]["spice"]
        h[key + "_t"] = sp["final_max_abs_t"]
        h[key + "_n"] = c[name]["rows_analysed"]
        h[key + "_first"] = sp["first_above"]
        h[key + "_stable"] = sp["stable_from"]
        h[key + "_tmax_cp"] = max(sp["max_abs_t"])
        h[key + "_peak_ns"] = sp["final_peak_ns_after_edge"]
        h[key + "_t2"] = sp["second_order_final_max_abs_t"]
        h[key + "_t100"] = sp["final_max_abs_t_100ps_bins"]
        h[key + "_tq"] = sp["charge_per_window"]["final_abs_t"]
        h[key + "_noise_unit"] = sp["noise_unit_uA"]
        for f in ("0.5", "1.0", "2.0"):
            nz = sp["noise"][f]
            h["%s_t_noise%s" % (key, f)] = nz["final_max_abs_t"]
            h["%s_stable_noise%s" % (key, f)] = nz["stable_from"]
            h["%s_noise%s_first" % (key, f)] = nz["first_above"]
            h["%s_noise%s_tmax_cp" % (key, f)] = max(nz["max_abs_t"])
        h[key + "_l1"] = max(c[name]["level1"][k]["final_max_abs_t"] for k in WEIGHTINGS)
        h[key + "_l1cap"] = c[name]["level1"]["weighted"]["final_max_abs_t"]
        h[key + "_l2"] = max(c[name]["level2"][k]["final_max_abs_t"] for k in WEIGHTINGS)
        h[key + "_l2cap"] = c[name]["level2"]["weighted"]["final_max_abs_t"]
        h[key + "_l2cap100"] = c[name]["level2"]["weighted"]["final_max_abs_t_100ps_bins"]
        lv = c[name]["level2_vs_spice"]
        h[key + "_corr_l1"] = lv["corr_charge_spice_vs_level1_weighted"]
        h[key + "_corr_l2"] = lv["corr_charge_spice_vs_level2_weighted"]
        h[key + "_lag_ps"] = lv["waveform_lag_ps"]
        h[key + "_mismatch"] = c[name]["functional_mismatches"]
    for v in ("N", "D", "DA"):
        l1 = s["level1_100k"][v]
        h[v + "_l1_100k"] = max(l1[k]["final_max_abs_t"] for k in WEIGHTINGS)
        h[v + "_l1_100k_cp"] = max(l1[k]["max_abs_t_over_all_checkpoints"] for k in WEIGHTINGS)
    h["l1_100k_n"] = s["level1_100k"]["N"]["rows_analysed"]
    # detectable effect: the smallest standardized difference that reaches 4.5 on average
    h["dN_sd"] = effect_size_sd(h["N_t"], h["N_n"])
    for v in ("D", "DA"):
        h[v + "_detect_sd"] = effect_size_sd(THRESHOLD, h[v + "_n"])
        h[v + "_detect_frac_of_N"] = h[v + "_detect_sd"] / h["dN_sd"]
    h.update(d_da_peak())
    h["K1_cpa_ranks"] = [cr["K1"]["cpa_primary_final_rank_per_key"][k] for k in ("0", "1", "2", "3")]
    h["K1_pass"] = cr["K1"]["pass"]
    h["GO"] = s["criteria"]["GO"]
    loc = s["localization"]
    h["N_flagged_leaky_nets"] = loc["N"]["spice_nodes"]["nets_above_threshold_anywhere"]
    h["N_nodes_rows"] = loc["N"]["spice_nodes"]["rows"]
    h["D_leaky_nets"] = loc["D"]["spice_nodes"]["nets_above_threshold_anywhere"]
    h["D_nodes_rows"] = loc["D"]["spice_nodes"]["rows"]
    h["N_l2_nets"] = len(loc["N"]["level2_nets"]["nets_above_threshold_anywhere"])
    h["N_l2_nets_rows"] = loc["N"]["level2_nets"]["rows"]
    pr = probing()
    for v in ("N", "D", "DA"):
        h[v + "_probe_fail"] = len(pr[v]["glitch_fail"])
        h[v + "_probe_value_fail"] = len(pr[v]["value_fail"])
        h[v + "_nets"] = pr[v]["n_nets"]
    for v in ("U", "N", "D", "DA"):
        sv = s["setup"]["variants"][v]
        h[v + "_cells"] = sv["n_cells"]
        h[v + "_dff"] = sv["n_dff"]
        h[v + "_latency"] = sv["latency"]
    h["spice_wall_s"] = s["spice_wall_clock_s"]["total_s"]
    h["ngspice"] = s["setup"]["ngspice"]
    h["pdk_commit"] = s["setup"]["pdk"]["version"]
    h["generated"] = s["generated"]
    return h


def d_da_peak(half_width=3):
    """D and DA peak at the same sample with the same max|t|: are their t-curves one observation?
    DDA_same_peak: both SPICE t-curves (tcurve_*.csv) have their largest |t| at the same sample;
    DDA_tdiff_near_peak: the largest |t_D - t_DA| within half_width samples of D's peak."""
    import numpy as np
    d, a = read_csv("tcurve_D_tvla"), read_csv("tcurve_DA_tvla")
    td, ta = d["t_spice"], a["t_spice"]
    i, j = int(np.argmax(np.abs(td))), int(np.argmax(np.abs(ta)))
    lo, hi = max(i - half_width, 0), min(i + half_width + 1, len(td), len(ta))
    return {"DDA_same_peak": bool(i == j and d["ns_after_edge"][i] == a["ns_after_edge"][j]),
            "DDA_tdiff_near_peak": float(np.max(np.abs(td[lo:hi] - ta[lo:hi])))}


def _n(x):
    """Trace count with a thousands separator."""
    return "{:,}".format(int(x)) if x is not None else "never"


def fmt_headline(s=None):
    """headline() as strings: t values with 1 decimal (2 for values below 5), counts with
    separators. Keys ending in _n/_first/_stable are counts."""
    h = headline(s)
    out = {}
    for k, v in h.items():
        if isinstance(v, bool) or isinstance(v, (list, dict)) or isinstance(v, str):
            out[k] = v if isinstance(v, str) else json.dumps(v)
        elif k.endswith(("_n", "_first", "_stable", "_rows", "_cells", "_dff", "_nets")) \
                or "_stable_noise" in k or k == "l1_100k_n":
            out[k] = _n(v)
        elif k.endswith("_ps") or k.endswith("_latency") or k.endswith("_fail") or k.endswith("_mismatch"):
            out[k] = str(int(v))
        elif k.endswith("_sd") or k.endswith("_peak_ns"):
            out[k] = "%.3f" % v
        elif k.endswith("_frac_of_N") or k.startswith(("N_corr", "U_corr")) or "_corr_" in k:
            out[k] = "%.2f" % v
        elif isinstance(v, float) and v < 5:
            out[k] = "%.2f" % v
        elif isinstance(v, (int, float)):
            out[k] = "%.1f" % v
    out["spice_wall_h"] = "%.1f" % (h["spice_wall_s"] / 3600.0)
    out["DDA_tdiff_near_peak"] = "%.3f" % h["DDA_tdiff_near_peak"]
    out["D_detect_frac_words"] = fraction_words(h["D_detect_frac_of_N"])
    out["DA_detect_frac_words"] = fraction_words(h["DA_detect_frac_of_N"])
    out["N_leaky_list"] = ", ".join(h["N_flagged_leaky_nets"])
    out["D_leaky_list"] = ", ".join(h["D_leaky_nets"])
    out["N_leaky_count"] = str(len(h["N_flagged_leaky_nets"]))
    out["D_leaky_count"] = str(len(h["D_leaky_nets"]))
    out["K1_cpa_ranks"] = " / ".join(str(r) for r in h["K1_cpa_ranks"])
    out.update(key_recovery_values(s=s))
    out.update(cost_values())
    out.update(postlayout_values())
    return out


def _ge(v):
    return "%.2f" % v


def _count(v):
    return _n(v) if v is not None else "never"


def key_recovery_values(kr=None, s=None):
    """The key-recovery numbers the text quotes, as strings (prefix kr_)."""
    kr = kr or key_recovery()
    s = s or summary()
    sp = s["setup"]["spice_params"]
    ds = kr["datasets"]
    out = {"kr_perms": str(kr["method"]["null_draws"]["no_noise"]), "kr_splits": str(kr["method"]["splits"]),
           "kr_trials": str(kr["method"]["trials_per_unit"])}
    n1 = ds["N_pooled"]["results"]["order1_noise0"]
    t, b, c = n1["tmpl"], n1["tmpl_bits"], n1["corr"]
    out.update(kr_N_n=_n(t["n"][-1]), kr_N_ge=_ge(t["final_ge"]), kr_N_sr=_ge(t["final_sr"]),
               kr_N_px1=_ge(t["final_sr_x1"]), kr_N_px2=_ge(t["final_sr_x2"]),
               kr_N_x1_from=_count(t["traces_to_sr90_x1"]), kr_N_p=_ge(t["p_vs_null"]),
               kr_N_bits_ge=_ge(b["final_ge"]), kr_N_bits_sr=_ge(b["final_sr"]),
               kr_N_bits_px1=_ge(b["final_sr_x1"]), kr_N_bits_px2=_ge(b["final_sr_x2"]),
               kr_N_bits_from=_count(b["traces_to_sr90"]), kr_N_bits_p="%.3f" % b["p_vs_null"],
               kr_N_null=_ge(n1["null"]["tmpl"]["final_ge_mean"]), kr_N_null_sd=_ge(n1["null"]["tmpl"]["final_ge_sd"]),
               kr_N_bits_null=_ge(n1["null"]["tmpl_bits"]["final_ge_mean"]),
               kr_N_bits_null_sd=_ge(n1["null"]["tmpl_bits"]["final_ge_sd"]),
               kr_N_corr_ge=_ge(c["final_ge"]))
    # where the per-key-bit POIs sit (ns after the edge), over the splits
    pois = [q for split in n1["split_info"]["poi_bits_per_split"] for q in split]
    ns = sorted({round((q + 0.5) * sp["dt"] - sp["pre"], 3) for q in pois})
    late = [v for v in ns if v > 1.1]
    out["kr_N_x2_poi_ns"] = ("%.3f-%.3f" % (min(late), max(late))) if late else "-"
    nt = ds["N_tvla"]["results"]["order1_noise0"]
    out.update(kr_Ntvla_n=_n(nt["tmpl"]["n"][-1]), kr_Ntvla_bits_ge=_ge(nt["tmpl_bits"]["final_ge"]),
               kr_Ntvla_ge=_ge(nt["tmpl"]["final_ge"]))
    for f in ("0.5", "1"):
        r = ds["N_pooled"]["results"]["order1_noise%s" % f]
        out["kr_N_noise%s_ge" % f] = _ge(r["tmpl"]["final_ge"])
        out["kr_N_noise%s_bits_ge" % f] = _ge(r["tmpl_bits"]["final_ge"])
    for v, name in (("D", "D_tvla"), ("DA", "DA_tvla")):
        e = ds[name]
        r = e["results"]["order1_noise0"]
        nl = r["null"]["tmpl"]
        inj = e["injection"]
        al = inj["smallest_detected_alpha"]["tmpl"]
        ge = {float(a): x["tmpl"]["final_ge"] for a, x in inj["alphas"].items()}
        below = sorted((a for a in ge if al is None or a < al), reverse=True)
        out.update({"kr_%s_n" % v: _n(r["tmpl"]["n"][-1]), "kr_%s_ge" % v: _ge(r["tmpl"]["final_ge"]),
                    "kr_%s_sr" % v: _ge(r["tmpl"]["final_sr"]), "kr_%s_null" % v: _ge(nl["final_ge_mean"]),
                    "kr_%s_null_sd" % v: _ge(nl["final_ge_sd"]), "kr_%s_p" % v: _ge(r["tmpl"]["p_vs_null"]),
                    "kr_%s_bits_ge" % v: _ge(r["tmpl_bits"]["final_ge"]),
                    "kr_%s_alpha" % v: ("%g" % al) if al is not None else "none of the tried strengths",
                    "kr_%s_alpha_ge" % v: _ge(ge[al]) if al is not None else "-",
                    "kr_%s_below" % v: ("%g" % below[0]) if below else "-",
                    "kr_%s_below_ge" % v: _ge(ge[below[0]]) if below else "-",
                    "kr_%s_corr_full_ge" % v: _ge(inj["alphas"]["1"]["corr"]["final_ge"]),
                    "kr_%s_corr_alpha" % v: ("%g" % inj["smallest_detected_alpha"]["corr"])
                    if inj["smallest_detected_alpha"]["corr"] is not None else "none"})
        o2 = e["results"]["order2_noise0"]["tmpl"]
        out.update({"kr_%s_o2_ge" % v: _ge(o2["final_ge"]), "kr_%s_o2_sr" % v: _ge(o2["final_sr"]),
                    "kr_%s_o2_p" % v: "%.3f" % o2["p_vs_null"]})
    o2 = ds["N_pooled"]["results"]["order2_noise0"]["tmpl"]
    out.update(kr_N_o2_ge=_ge(o2["final_ge"]), kr_N_o2_sr=_ge(o2["final_sr"]))
    u = ds["U_tvla"]["results"]["order1_noise0"]["tmpl"]
    out["kr_U_from"] = _count(u["traces_to_sr90"])
    out["kr_U_n"] = _n(u["n"][-1])
    uc = ds["U_cpa"]
    out["kr_Ucpa_from"] = _count(uc["results"]["order1_noise0"]["tmpl"]["traces_to_sr90"])
    out["kr_Ucpa_n"] = _n(min(uc["attack_rows_per_key"]))
    for f in ("0.5", "1"):
        r = uc["results"]["order1_noise%s" % f]
        for d in ("tmpl", "corr"):
            out["kr_Ucpa_noise%s_%s_ge" % (f, d)] = _ge(r[d]["final_ge"])
            out["kr_Ucpa_noise%s_%s_sr" % (f, d)] = _ge(r[d]["final_sr"])
    dfc = uc["charge_deficit_pct_per_key"]
    out["kr_Ucpa_deficit"] = "%.0f-%.0f" % (min(dfc), max(dfc))
    # the null's spread, without added noise: the TVLA data sets (U, N, D, DA) for the default and
    # the per-key-bit template, and U on the CPA traces (four keys only) on its own
    tvla_sets = [name for name in ds if name != "U_cpa"]
    for d, key in (("tmpl", "kr_null_sd_range"), ("tmpl_bits", "kr_null_sd_range_bits")):
        sds = [r["null"][d]["final_ge_sd"] for name in tvla_sets
               for tag, r in ds[name]["results"].items() if tag.endswith("noise0") and d in r["null"]]
        out[key] = "%.2f-%.2f" % (min(sds), max(sds))
    out["kr_Ucpa_null_sd"] = _ge(uc["results"]["order1_noise0"]["null"]["tmpl"]["final_ge_sd"])
    # the injected-leak bound of D and DA together, as a range of N's strength (e.g. 0.35-0.5)
    als = sorted(ds[name]["injection"]["smallest_detected_alpha"]["tmpl"] for name in ("D_tvla", "DA_tvla")
                 if ds[name]["injection"]["smallest_detected_alpha"]["tmpl"] is not None)
    out["kr_alpha_range"] = ("%g-%g" % (als[0], als[-1]) if als[0] != als[-1] else "%g" % als[0]) if als else "-"
    for v, name in (("D", "D_tvla"), ("DA", "DA_tvla")):
        al = ds[name]["injection"]["smallest_detected_alpha"]["tmpl"]
        out["kr_%s_alpha_words" % v] = fraction_words(al) if al is not None else "-"
    return out


def cost_values(c=None):
    """The cost numbers the text quotes, as strings (prefix cost_)."""
    c = c or cost()
    digits = {"area_um2": 0, "min_period_ps": 0, "port_to_reg_ps": 0, "e_eval_fJ": 0, "e_total_fJ": 0,
              "latency_ns": 2}                  # everything else as written in the CSV
    out = {}
    for v, r in c.items():
        for k in ("cells", "dff", "area_um2", "area_vs_N", "latency_cycles", "min_period_ps", "latency_ns",
                  "latency_vs_N", "fresh_random_bits", "e_eval_fJ", "energy_vs_N", "e_total_fJ", "total_vs_N",
                  "port_to_reg_ps", "q_window_all_random_class_rows_fC", "q_window_fC"):
            if r.get(k) not in (None, ""):
                out["cost_%s_%s" % (v, k)] = ("%.*f" % (digits[k], float(r[k]))) if k in digits else r[k]
    for v in ("D", "DA"):
        for k in ("area_vs_N", "energy_vs_N", "total_vs_N", "latency_vs_N"):
            out["cost_%s_%s_pct" % (v, k)] = "%d" % round(100 * (float(c[v][k]) - 1))
    out["cost_dff_extra"] = str(int(c["DA"]["dff"]) - int(c["N"]["dff"]))
    u = c["U"]
    out["cost_U_bias_pct"] = "%.1f" % (100 * (1 - float(u["q_window_all_random_class_rows_fC"]) / float(u["q_window_fC"])))
    return out


def postlayout_values(pl=None, lay=None, nt=None):
    """The layout and post-layout numbers the text quotes, as strings (prefixes lay_ and pl_)."""
    pl = pl or postlayout()
    lay = lay or layout()
    nt = nt or node_timing()
    c, cr = pl["campaigns"], pl["criteria"]
    out = {}
    for v in ("N", "DA"):
        e = c[v + "_pex"]
        sp, pre = e["spice"], e["pre_layout_same_rows"]
        pk = e["peaks"]
        out.update({
            "pl_%s_rows" % v: _n(e["rows_simulated"]), "pl_%s_n" % v: _n(e["rows_analysed"]),
            "pl_%s_t" % v: "%.2f" % sp["final_max_abs_t"], "pl_%s_pre_t" % v: "%.2f" % pre["final_max_abs_t"],
            "pl_%s_first" % v: _count(sp["first_above"]), "pl_%s_pre_first" % v: _count(pre["first_above"]),
            "pl_%s_stable" % v: _count(sp["stable_from"]),
            "pl_%s_tmax_cp" % v: "%.2f" % max(sp["max_abs_t"]),
            "pl_%s_peak_ns" % v: "%.3f" % sp["final_peak_ns_after_edge"],
            "pl_%s_pre_peak_ns" % v: "%.3f" % pre["final_peak_ns_after_edge"],
            "pl_%s_t100" % v: "%.2f" % sp["final_max_abs_t_100ps_bins"],
            "pl_%s_pre_t100" % v: "%.2f" % pre["final_max_abs_t_100ps_bins"],
            "pl_%s_tq" % v: "%.2f" % sp["charge_per_window"]["final_abs_t"],
            "pl_%s_pre_tq" % v: "%.2f" % pre["charge_per_window"]["final_abs_t"],
            "pl_%s_t2" % v: "%.1f" % sp["second_order_final_max_abs_t"],
            "pl_%s_pre_t2" % v: "%.1f" % pre["second_order_final_max_abs_t"],
            "pl_%s_mismatch" % v: str(e["function_check"]["mismatches_vs_sbox"]),
            "pl_%s_out_diff" % v: str(e["function_check"]["rows_differing_from_pre_layout_outputs"]),
            "pl_%s_charge_ratio" % v: "%.2f" % e["pre_vs_post"]["charge_ratio_post_over_pre"],
            "pl_%s_shift_ns" % v: "%.2f" % e["pre_vs_post"]["t_curve"]["best_shift_ns"],
            "pl_%s_shift_corr" % v: "%.2f" % e["pre_vs_post"]["t_curve"]["corr_at_best_shift"],
            "pl_%s_noshift_corr" % v: "%.2f" % e["pre_vs_post"]["t_curve"]["corr_no_shift"],
            "pl_%s_above" % v: str(pk["samples_above_threshold"]),
            "pl_%s_e_fJ" % v: _n(round(e["energy_per_evaluation"]["post_layout"]["e_eval_fJ"])),
            "pl_%s_pre_e_fJ" % v: _n(round(e["energy_per_evaluation"]["pre_layout_same_rows"]["e_eval_fJ"])),
            "pl_%s_part" % v: (pk["peak"]["part"] or "-").replace("_", " "),
        })
        span = pk["first_last_sample_above_threshold_ns"]
        out["pl_%s_span" % v] = ("%.3f-%.3f" % tuple(span)) if span else "-"
        for f in ("0.5", "1.0", "2.0"):
            out["pl_%s_t_noise%s" % (v, f)] = "%.2f" % sp["noise"][f]["final_max_abs_t"]
            out["pl_%s_stable_noise%s" % (v, f)] = _count(sp["noise"][f]["stable_from"])
    reg = c["N_pex"]["spice"]["max_abs_t_by_region"]
    out["pl_N_rest"] = "%.2f" % max(reg["clock_fall"], reg["input_edges"])
    out["pl_N_clockfall"] = "%.2f" % reg["clock_fall"]
    out["pl_N_inputedges"] = "%.2f" % reg["input_edges"]
    out["pl_DA_peak_cycle"] = str(c["DA_pex"]["peaks"]["peak"].get("cycle", 1))
    out["pl_DA_detect_frac"] = "%.2f" % cr["PL3"]["DA_pex_detectable_fraction_of_N_pex"]
    out["pl_DA_detect_sd"] = "%.3f" % cr["PL3"]["DA_pex_detectable_sd"]
    out["pl_N_effect_sd"] = "%.3f" % cr["PL3"]["N_pex_effect_sd"]
    out["pl_PL1"] = "pass" if cr["PL1"]["pass"] else "fail"
    out["pl_PL2"] = "pass" if cr["PL2"]["pass"] else "fail"
    en = pl["energy_DA_vs_N"]
    out["pl_energy_DA_vs_N_pct"] = "%d" % round(100 * (en["post_layout"] - 1))
    out["pl_pre_energy_DA_vs_N_pct"] = "%d" % round(100 * (en["pre_layout_same_rows"] - 1))
    sv = pl["solver_check_klu_vs_sparse"]
    mant, ex = ("%.1e" % max(x["max_rel_charge_diff"] for x in sv.values())).split("e")
    out["pl_klu_rel"] = "%se%d" % (mant, int(ex))
    out["pl_klu_corr"] = "%.7f" % min(x["corr_data_dependent"] for x in sv.values())
    out["pl_wall_h"] = "%.1f" % (sum(c[k]["spice_wall_clock"]["wall_s"] for k in c) / 3600.0)
    for v in ("N", "DA", "U"):
        L = lay[v]
        cv = pl["capacitance_views"][v]
        out.update({"lay_%s_die" % v: "%.1f x %.1f" % tuple(L["die_um"]),
                    "lay_%s_core" % v: _n(round(L["core_area_um2"])),
                    "lay_%s_die_area" % v: _n(round(L["die_area_um2"])),
                    "lay_%s_util" % v: "%.1f" % L["placement_utilisation_pct"],
                    "lay_%s_cts" % v: str(sum(L["clock_tree"]["buffers"].values())),
                    "lay_%s_cells" % v: str(L["cells_final_by_category"]["logic"]),
                    "lay_%s_cap_est" % v: "%.0f" % cv["prelayout_estimate_fF"],
                    "lay_%s_cap_rcx" % v: "%.0f" % cv["openrcx_routed_wiring_fF"],
                    "lay_%s_cap_magic" % v: "%.0f" % cv["magic_flat_fF"],
                    "lay_%s_cap_ratio" % v: "%.1f" % cv["magic_over_estimate"],
                    "lay_%s_xtors" % v: _n(L["pex"]["n_devices"])})
        cp = L["pex"]["coupling_between_named_nets_by_domain"].get("s0-s1")
        if cp:
            out["lay_%s_s0s1_fF" % v] = "%.1f" % cp["fF"]
    out["lay_core_DA_vs_N_pct"] = "%d" % round(100 * (lay["DA"]["core_area_um2"] / lay["N"]["core_area_um2"] - 1))
    out["lay_die_DA_vs_N_pct"] = "%d" % round(100 * (lay["DA"]["die_area_um2"] / lay["N"]["die_area_um2"] - 1))
    out["lay_all_clean"] = str(all(lay[v]["drc_router"] == lay[v]["drc_magic"] == lay[v]["drc_klayout"] == 0
                                   and lay[v]["lvs"].startswith("Circuits match")
                                   and lay[v]["antenna_pin_violations"] == lay[v]["antenna_net_violations"] == 0
                                   and lay[v]["final_vs_generator"]["logic_unchanged"] for v in ("N", "DA", "U")))
    for k, tag in (("clk_to_q_ns", "ckq"), ("last_logic_crossing_ns", "last")):
        out["pl_%s_pre" % tag] = "%.2f" % nt["pre_layout"][k]["median"]
        out["pl_%s_post" % tag] = "%.2f" % nt["post_layout"][k]["median"]
        out["pl_%s_post_max" % tag] = "%.2f" % nt["post_layout"][k]["max"]
    return out


def fraction_words(f):
    """0.5 -> 'half', 0.25 -> 'a quarter', else 'about 0.xx'."""
    for val, word in ((1 / 2, "half"), (1 / 3, "a third"), (1 / 4, "a quarter"), (1 / 5, "a fifth")):
        if abs(f - val) < 0.03:
            return word
    return "%.2f" % f


if __name__ == "__main__":
    for k, v in sorted(fmt_headline().items()):
        print("%-24s %s" % (k, v))
