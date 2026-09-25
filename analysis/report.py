# SPDX-License-Identifier: Apache-2.0
"""Markdown tables of the kill-test results, generated from results/kill_test/summary.json.

  python3 analysis/report.py > /tmp/tables.md

Every number in the tables is read from summary.json (written by analysis/kill_test.py), so
the tables in docs/KILL_TEST.md can be regenerated and checked against the data.
"""
import json
import os

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SUMMARY = os.path.join(REPO, "results", "kill_test", "summary.json")
SRC = "`results/kill_test/summary.json`"


def f(x, nd=1):
    return "n/a" if x is None else ("%.*f" % (nd, x))


def pf(x):
    return {True: "**pass**", False: "**FAIL**", None: "not run"}[x]


def criteria_table(s):
    k = s["criteria"]
    c = s["campaigns"]
    rows = []
    k1 = k["K1"]
    cpa = k1.get("cpa_primary_final_rank_per_key", {})
    rows.append(("K1", "U in SPICE: max\\|t\\| > 4.5, and CPA ranks the correct key first",
                 "TVLA max\\|t\\| %s (first > 4.5 at %s traces); CPA rank of the correct key, primary "
                 "hypothesis, keys 0-3: %s (HW(S(x)): %s)" % (
                     f(k1.get("tvla_max_abs_t")), k1.get("tvla_first_above"),
                     ", ".join(str(cpa[x]) for x in sorted(cpa)) or "n/a",
                     ", ".join(str(v) for _, v in sorted(k1.get("cpa_hw_final_rank_per_key", {}).items())) or "n/a"),
                 "TVLA %s; CPA 4 x %s" % (k1.get("tvla_traces"), (k1.get("cpa_traces_per_key") or ["n/a"])[0]),
                 "TVLA %s, CPA %s -> %s" % (pf(k1.get("tvla_pass")), pf(k1.get("cpa_pass")), pf(k1.get("pass")))))
    k2 = k["K2"]["values"]
    parts = []
    for key in ("N_tvla_at_spice_count", "D_tvla_at_spice_count", "N_at_100k", "D_at_100k", "DA_at_100k"):
        if key in k2:
            parts.append("%s (%d): %s" % (key.replace("_tvla_at_spice_count", " @ SPICE count").replace("_at_100k", " @ 100k"),
                                          k2[key]["traces"], f(max(k2[key]["max_abs_t"].values()), 2)))
    rows.append(("K2", "N and D, zero-delay model: max\\|t\\| < 4.5",
                 "max over the 3 weightings: " + "; ".join(parts), "as listed", pf(k["K2"].get("pass"))))
    for kid, text in (("K3", "N in SPICE: max\\|t\\| > 4.5"),
                      ("K4", "D in SPICE: max\\|t\\| < 4.5 (informational)"),
                      ("K5", "DA in SPICE: max\\|t\\| < 4.5 at 20,000 (A1)")):
        e = k[kid]
        if "max_abs_t" not in e:
            rows.append((kid, text, "not run", "-", "not run"))
            continue
        val = "max\\|t\\| %s at %.3f ns after the edge; first > 4.5 at %s, stable from %s" % (
            f(e["max_abs_t"]), e["peak_ns_after_edge"], e["first_above"] or "never", e["stable_from"] or "-")
        verdict = pf(e["pass"])
        if kid == "K4":
            verdict = "leaks (finding)" if not e["pass"] else "no leak"
        if kid == "K5" and not e.get("complete"):
            verdict += " (incomplete: %d of 20,000)" % e["traces"]
        rows.append((kid, text, val, str(e["traces"]), verdict))
    k6 = k.get("K6", {})
    parts, verdicts = [], []
    for v in ("N", "D", "DA"):
        e = k6.get(v)
        if not e:
            continue
        sn = e.get("spice_nodes", {})
        parts.append("%s: peak %.3f ns; flagged nets switch %s ns (5th-95th pct., SPICE nodes, %s traces); "
                     "nets whose transitions leak: %s (all flagged: %s); 10 most class-dependent nets within "
                     "+-100 ps of the peak all flagged: %s" % (
                         v, e["spice_peak_ns_after_edge"], sn.get("flagged_switching_p5_p95_ns"), sn.get("rows"),
                         ", ".join(sn.get("nets_above_threshold_anywhere", [])) or "none",
                         sn.get("all_above_anywhere_flagged"), sn.get("top10_near_peak_all_flagged")))
        if "match" in e:
            verdicts.append("%s %s" % (v, {True: "match", False: "no match",
                                           None: "n/a (no leak peak in SPICE)"}[e["match"]]))
    rows.append(("K6", "SPICE t-peaks on or after the switching of the flagged nets (informational)",
                 "; ".join(parts) or "not run", "node re-runs", ", ".join(verdicts) or "not run"))
    cc = k["C"]
    rows.append(("C", "(a) N random vs random < 4.5; (b) N masks off leaks",
                 "(a) max\\|t\\| %s; (b) max\\|t\\| %s, first > 4.5 at %s traces" % (
                     f(cc.get("a_max_abs_t")), f(cc.get("b_max_abs_t")), cc.get("b_first_above")),
                 "(a) %s, (b) %s" % (cc.get("a_traces"), cc.get("b_traces")),
                 "(a) %s, (b) %s" % (pf(cc.get("a_pass")), pf(cc.get("b_pass")))))
    out = ["| Id | Criterion | Measured | Traces | Result |", "|---|---|---|---|---|"]
    out += ["| %s |" % " | ".join(r) for r in rows]
    return "\n".join(out)


def campaign_table(s):
    out = ["| Campaign | Traces | SPICE max\\|t\\| | first > 4.5 | peak (ns after edge) | level 2 max\\|t\\| "
           "(unw / cap / rise) | level 1 max\\|t\\| (unw / cap / rise) | function check |",
           "|---|---|---|---|---|---|---|---|"]
    for name, c in s["campaigns"].items():
        sp = c["spice"]
        l1 = " / ".join(f(c["level1"][k]["final_max_abs_t"], 2) for k in ("unweighted", "weighted", "weighted_rise"))
        l2 = " / ".join(f(c["level2"][k]["final_max_abs_t"], 1) for k in ("unweighted", "weighted", "weighted_rise"))
        out.append("| %s | %d | %s | %s | %.3f | %s | %s | %s mismatches |" % (
            name, c["rows_analysed"], f(sp["final_max_abs_t"]), sp["first_above"] or "-",
            sp["final_peak_ns_after_edge"], l2, l1, c["functional_mismatches"]))
    return "\n".join(out)


def region_table(s):
    out = ["| Campaign | SPICE max\\|t\\| by part of the cycle | level 2 (cap-weighted) |", "|---|---|---|"]
    for name, c in s["campaigns"].items():
        a = c["spice"]["max_abs_t_by_region"]
        b = c["level2"]["weighted"]["max_abs_t_by_region"]
        out.append("| %s | %s | %s |" % (name, ", ".join("%s %s" % (k, f(v)) for k, v in a.items()),
                                         ", ".join("%s %s" % (k, f(v)) for k, v in b.items())))
    return "\n".join(out)


def noise_table(s):
    out = ["| Campaign | noise unit (uA) | no noise | 0.5x | 1x | 2x |", "|---|---|---|---|---|---|"]
    for name, c in s["campaigns"].items():
        sp = c["spice"]
        cells = ["%s (%s)" % (f(sp["final_max_abs_t"]), sp["stable_from"] or "-")]
        for k in ("0.5", "1.0", "2.0"):
            n = sp["noise"][k]
            cells.append("%s (%s)" % (f(n["final_max_abs_t"]), n["stable_from"] or "-"))
        out.append("| %s | %.1f | %s |" % (name, sp["noise_unit_uA"], " | ".join(cells)))
    return "\n".join(out)


def model_table(s):
    out = ["| Campaign | corr. charge per trace, SPICE vs level 2 | vs level 1 | waveform corr. SPICE vs level 2, "
           "100 ps (no shift) | level-2 shift (ps) | corr. at that shift | t-peak SPICE / level 2 (ns) |",
           "|---|---|---|---|---|---|---|"]
    for name, c in s["campaigns"].items():
        m = c["level2_vs_spice"]
        out.append("| %s | %.3f | %.3f | %.3f | %+d | %.3f | %.3f / %.3f |" % (
            name, m["corr_charge_spice_vs_level2_weighted"], m["corr_charge_spice_vs_level1_weighted"],
            m["waveform_corr_at_0"], m["waveform_lag_ps"], m["waveform_corr_at_lag"],
            m["spice_peak_ns_after_edge"], m["level2_peak_ns_after_edge"]))
    return "\n".join(out)


def cpa_table(s):
    out = ["| Key | Traces | primary (level-1 model): rank, rank 1 from | HW(S(x)): rank | primary, signed | "
           "HW, signed | primary on level-1 / level-2 traces | HW on level-1 / level-2 traces | primary with noise 0.5x / 1x / 2x |",
           "|---|---|---|---|---|---|---|---|---|"]
    for name, r in sorted(s["cpa"].items()):
        p = r["level1_model"]
        out.append("| %d | %d | %d, %s | %d | %d | %d | %d / %d | %d / %d | %s |" % (
            r["key"], r["rows_analysed"], p["final_rank"], p["rank1_stable_from"] or "-", r["hw_sbox"]["final_rank"],
            r["level1_model_signed"]["final_rank"], r["hw_sbox_signed"]["final_rank"],
            r["on_level1_traces"]["level1_model"], r["on_level2_traces"]["level1_model"],
            r["on_level1_traces"]["hw_sbox"], r["on_level2_traces"]["hw_sbox"],
            " / ".join(str(p["noise"][k]["final_rank"]) for k in ("0.5", "1.0", "2.0"))))
    return "\n".join(out)


def localization_table(s):
    out = []
    for v, loc in s.get("localization", {}).items():
        out.append("**%s**: SPICE t-peak %s at %.3f ns after the edge." % (
            v, f(loc["spice_peak_t"]), loc["spice_peak_ns_after_edge"]))
        for src, label in (("spice_nodes", "SPICE node voltages"), ("level2_nets", "level 2")):
            if src not in loc:
                continue
            r = loc[src]
            top = ", ".join("%s %s%s" % (e["net"], f(e["abs_t"]), "*" if e["flagged"] else "")
                            for e in r["nets_by_abs_t_near_spice_peak"][:8])
            anyw = ", ".join("%s %s%s @%.2f" % (e["net"], f(e["abs_t"]), "*" if e["flagged"] else "", e["ns_after_edge"])
                             for e in r["nets_by_abs_t_anywhere"][:8])
            out.append("- %s (%d traces; window +-100 ps around %.3f ns): flagged nets switch between %s ns "
                       "(5th-95th percentile); most class-dependent nets near the peak: %s; anywhere in the "
                       "window (net \\|t\\| @ns): %s" % (
                           label, r["rows"], r["time_examined_ns_after_edge"],
                           r.get("flagged_nets_switching_p5_p95_ns_after_edge"), top, anyw))
    return "\n".join(out)


def main():
    with open(SUMMARY) as fh:
        s = json.load(fh)
    for title, fn in (("Criteria", criteria_table), ("Campaigns", campaign_table), ("Regions", region_table),
                      ("Noise", noise_table), ("Models vs SPICE", model_table), ("CPA", cpa_table),
                      ("Localization", localization_table)):
        try:
            body = fn(s)
        except KeyError as e:
            body = "(missing: %s)" % e
        print("### %s\n\n%s\n" % (title, body))


if __name__ == "__main__":
    main()
