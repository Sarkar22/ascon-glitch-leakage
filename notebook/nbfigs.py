# SPDX-License-Identifier: Apache-2.0
"""Figures and tables of the notebook, drawn from the committed result files.

Needs numpy and matplotlib only (the organizers' CI has both). Every function reads
results/kill_test/*.csv, summary.json or results/probing/*.json through nbdata and
returns a matplotlib figure (the notebook shows it) or a markdown table string.

Colors: one fixed color per model level, the same as analysis/plots.py
(SPICE blue, level 2 orange, level 1 aqua); the threshold |t| = 4.5 is a dashed gray line.
"""
import numpy as np

import nbdata

COLORS = {
    "surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
    "grid": "#e1e0d9", "axis": "#c3c2b7",
    "series1": "#2a78d6", "series2": "#eb6834", "series3": "#1baf7a", "series4": "#eda100",
    "glitch": "#fbe3a6",
    "ramp": ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"],
}
LEVEL = {"spice": COLORS["series1"], "level2": COLORS["series2"], "level1": COLORS["series3"]}
TH = nbdata.THRESHOLD
TITLE = {"U": "U, unmasked", "N": "N, naive DOM", "D": "D, DOM + barrier (textbook)",
         "DA": "DA, DOM + barrier after the affine layer"}


def style():
    import matplotlib.pyplot as plt
    c = COLORS
    plt.rcParams.update({
        "figure.facecolor": c["surface"], "axes.facecolor": c["surface"],
        "savefig.facecolor": c["surface"], "font.family": "sans-serif", "font.size": 9,
        "text.color": c["ink"], "axes.labelcolor": c["ink2"], "axes.edgecolor": c["axis"],
        "axes.linewidth": 0.8, "xtick.color": c["muted"], "ytick.color": c["muted"],
        "axes.grid": True, "grid.color": c["grid"], "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
        "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlecolor": c["ink"],
        "lines.linewidth": 1.4, "figure.dpi": 100})


def _threshold(ax, both=False, label=True):
    for y in ((TH, -TH) if both else (TH,)):
        ax.axhline(y, color=COLORS["muted"], lw=0.8, ls=(0, (4, 3)), zorder=1)
    if label:
        ax.text(ax.get_xlim()[1], TH, " 4.5", va="center", ha="left", fontsize=7, color=COLORS["muted"],
                clip_on=False)


def tfmt(t):
    """A t value as the text quotes it: 1 decimal from 5 up, 2 decimals below."""
    return "%.1f" % t if t >= 5 else "%.2f" % t


def _tcurve(v):
    return nbdata.read_csv("tcurve_%s_tvla" % v)


# ---------------------------------------------------------------- workflow

def workflow():
    """Block diagram: one generator, one netlist, four checks, one statistic."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    style()
    c = COLORS
    fig, ax = plt.subplots(figsize=(10, 3.9))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 40)
    ax.axis("off")

    def box(x, y, w, h, title, sub, edge):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2",
                                    fc=c["surface"], ec=edge, lw=1.3))
        ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center", fontsize=8.8,
                fontweight="bold", color=c["ink"])
        ax.text(x + w / 2, y + h * 0.3, sub, ha="center", va="center", fontsize=7.2, color=c["ink2"])

    def arrow(x0, y0, x1, y1):
        ax.annotate("", (x1, y1), (x0, y0), arrowprops=dict(arrowstyle="-|>", color=c["ink2"], lw=0.9))

    box(0.5, 15, 16, 10, "Generator", "gen/make_variants.py\nexplicit sky130_fd_sc_hd cells", c["axis"])
    box(20.5, 15, 17, 10, "One netlist per variant", "U, N, D, DA\ndut.v, dut.sp, graph.json", c["axis"])
    arrow(17.5, 20, 19.8, 20)
    rows = [("Exact probing check", "value and glitch-extended models,\nall 32,768 (x, mask, r)", c["muted"]),
            ("Level 1: zero-delay", "settled toggles per cycle", LEVEL["level1"]),
            ("Level 2: timing-aware", "Liberty delays, every glitch", LEVEL["level2"]),
            ("Level 3: ngspice-42", "sky130 tt transistors,\nDUT supply current", LEVEL["spice"])]
    ys = [31, 21.5, 12, 2.5]
    for (t, s, e), y in zip(rows, ys):
        box(42.5, y, 21, 7.5, t, s, e)
        arrow(38.2, 20, 41.8, y + 3.75)
    box(68.5, 12, 16, 16, "TVLA", "fixed x = 0x0B vs random\nWelch t per 10 ps\n|t| > 4.5 means leak", c["axis"])
    for y in ys[1:]:
        arrow(64.3, y + 3.75, 67.8, 20)
    box(88.5, 12, 11, 16, "Verdict", "per variant and\nper model level", c["axis"])
    arrow(85.2, 20, 87.8, 20)
    ax.annotate("", (94, 28.8), (64.3, 34.75), arrowprops=dict(arrowstyle="-|>", color=c["ink2"], lw=0.9,
                                                               connectionstyle="angle,angleA=0,angleB=90"))
    ax.text(53, 39.6, "every model sees the same cells, nets and stimulus rows", ha="center",
            fontsize=8, color=c["ink2"])
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------- headline

def headline():
    """|t| against time for N, D and DA: SPICE per 10 ps sample, and the zero-delay model's
    single value per row (it has no time axis)."""
    import matplotlib.pyplot as plt
    style()
    s = nbdata.summary()
    fig, axs = plt.subplots(3, 1, figsize=(9.5, 6.4), sharex=True, sharey=True)
    for ax, v in zip(axs, ("N", "D", "DA")):
        cam = s["campaigns"][v + "_tvla"]
        d = _tcurve(v)
        x = d["ns_after_edge"]
        ax.plot(x, np.abs(d["t_spice"]), color=LEVEL["spice"], lw=1.1, label="transistor-level SPICE")
        l1 = max(cam["level1"][k]["final_max_abs_t"] for k in nbdata.WEIGHTINGS)
        ax.plot([x[0], x[-1]], [l1, l1], color=LEVEL["level1"], lw=2,
                label="zero-delay model (one value per row; worst of 3 weightings)")
        ax.set_xlim(-0.2, 7.8)
        _threshold(ax)
        if v != "N":
            ax.axvline(3.8 + 0.2, color=COLORS["axis"], lw=0.8)
            ax.text(4.03, 14.2, "2nd clock edge", fontsize=7, color=COLORS["muted"], va="top")
        else:
            ax.axvspan(x[-1], 7.8, color=COLORS["grid"], alpha=0.35, lw=0)
            ax.text(5.8, 7.5, "N finishes in one 4 ns cycle", fontsize=7.5, color=COLORS["muted"],
                    ha="center")
        sp = cam["spice"]
        ax.set_title("%s:  SPICE max|t| %s at %s traces   |   zero-delay model %.2f"
                     % (TITLE[v], tfmt(sp["final_max_abs_t"]), "{:,}".format(cam["rows_analysed"]), l1),
                     loc="left", fontsize=9.5)
        ax.set_ylabel("|t|")
        ax.set_ylim(0, 15)
    axs[0].legend(loc="upper right", fontsize=8)
    axs[-1].set_xlabel("ns after the capturing clock edge")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------- max|t| vs traces

def maxt_vs_traces(variants=("N", "D", "DA")):
    """max|t| against the number of traces for the three model levels, with the curve a leak
    as strong as N's would follow (t = d_N * sqrt(n) / 2)."""
    import matplotlib.pyplot as plt
    style()
    h = nbdata.headline()
    fig, axs = plt.subplots(1, len(variants), figsize=(10, 3.3), sharey=True)
    for ax, v in zip(np.atleast_1d(axs), variants):
        d = nbdata.read_csv("maxt_vs_traces_%s_tvla" % v)
        n = d["traces"]
        ref = h["dN_sd"] * np.sqrt(n) / 2
        ax.plot(n, ref, color=COLORS["muted"], lw=1, ls=(0, (1, 2)), label="a leak as strong as N's")
        ax.plot(n, np.maximum(d["level1_weighted"], 1e-2), color=LEVEL["level1"], label="level 1, zero-delay")
        ax.plot(n, np.maximum(d["level2_weighted"], 1e-2), color=LEVEL["level2"], label="level 2, timing-aware")
        ax.plot(n, d["spice"], color=LEVEL["spice"], lw=2, label="SPICE")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_ylim(0.05, 60)
        ax.set_xlim(20, 25000)
        _threshold(ax, label=False)
        ax.set_title(TITLE[v], loc="left", fontsize=9.5)
        ax.set_xlabel("traces")
    np.atleast_1d(axs)[0].set_ylabel("max |t| over the window")
    np.atleast_1d(axs)[0].legend(loc="upper left", fontsize=7.5)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------- localization

def localization(v="N", top=14):
    """SPICE supply-current t (top) and the per-net |t| of each net's own transition count
    from the SPICE node-voltage re-run (bottom); * marks nets flagged by glitch-extended
    probing."""
    import matplotlib.pyplot as plt
    style()
    s = nbdata.summary()
    loc = s["localization"][v]
    d = nbdata.read_csv("pernet_t_%s_spice_nodes" % v)
    x = d.pop("ns_after_edge")
    names = list(d)
    t = np.array([d[k] for k in names])
    order = list(np.argsort(-np.abs(t).max(1))[:top])
    flagged = set(loc["glitch_extended_flagged_nets"])
    tc = _tcurve(v)
    xmax = 2.0 if v == "N" else 6.0
    fig, ax = plt.subplots(2, 1, figsize=(9.5, 5.6), sharex=True, gridspec_kw={"height_ratios": [1, 2.1]})
    ax[0].plot(tc["ns_after_edge"], tc["t_spice"], color=LEVEL["spice"], lw=1.1)
    ax[0].set_xlim(-0.2, xmax)
    _threshold(ax[0], both=True, label=False)
    ax[0].set_ylabel("Welch t")
    ax[0].set_title("%s: supply current, %s traces" % (TITLE[v], "{:,}".format(s["campaigns"][v + "_tvla"]
                                                                                ["rows_analysed"])),
                    loc="left", fontsize=9.5)
    img = np.abs(t[order])
    dx = x[1] - x[0]
    im = ax[1].imshow(img, aspect="auto", cmap="Blues", vmin=0, vmax=max(9, img.max()),
                      extent=(x[0] - dx / 2, x[-1] + dx / 2, len(order) - 0.5, -0.5), interpolation="nearest")
    ax[1].set_yticks(range(len(order)))
    ax[1].set_yticklabels(["%s%s" % (names[i], " *" if names[i] in flagged else "") for i in order], fontsize=7.5)
    ax[1].grid(False)
    ax[1].set_title("each net's own transitions (SPICE node voltages, %s traces); * = flagged by probing"
                    % "{:,}".format(loc["spice_nodes"]["rows"]), loc="left", fontsize=9)
    ax[1].set_xlabel("ns after the capturing clock edge")
    cb = fig.colorbar(im, ax=list(ax), pad=0.01, fraction=0.03)
    cb.set_label("|t| of the net's transition count", color=COLORS["ink2"])
    return fig


# ---------------------------------------------------------------- model trust

def model_vs_spice(v="N"):
    """Signed t against time, SPICE vs level 2 (cap-weighted), on the same rows."""
    import matplotlib.pyplot as plt
    style()
    d = _tcurve(v)
    fig, ax = plt.subplots(figsize=(9.5, 3.0))
    ax.plot(d["ns_after_edge"], d["t_level2_weighted"], color=LEVEL["level2"], lw=0.9,
            label="level 2, timing-aware model (10 ps bins)")
    ax.plot(d["ns_after_edge"], d["t_spice"], color=LEVEL["spice"], lw=1.4, label="SPICE")
    ax.set_xlim(-0.2, 2.2 if v == "N" else 6.0)
    _threshold(ax, both=True, label=False)
    ax.set_ylabel("Welch t (signed)")
    ax.set_xlabel("ns after the capturing clock edge")
    ax.set_title("%s: same rows, same statistic, different waveforms" % TITLE[v], loc="left", fontsize=9.5)
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    return fig


def model_table():
    """Markdown table: what each model level says, per campaign."""
    s = nbdata.summary()
    rows = ["| Campaign | Traces | SPICE max\\|t\\| | level 2 max\\|t\\| (cap-weighted) | level 1 max\\|t\\| "
            "(cap-weighted) | charge per trace, corr. SPICE vs level 1 / level 2 | level-2 lag (ps) |",
            "|---|---|---|---|---|---|---|"]
    for name in ("U_tvla", "N_masksoff", "N_rvr", "N_tvla", "D_tvla", "DA_tvla"):
        c = s["campaigns"][name]
        lv = c["level2_vs_spice"]
        rows.append("| %s | %s | %.1f | %.1f | %.2f | %.2f / %.2f | %+d |" % (
            name, "{:,}".format(c["rows_analysed"]), c["spice"]["final_max_abs_t"],
            c["level2"]["weighted"]["final_max_abs_t"], c["level1"]["weighted"]["final_max_abs_t"],
            lv["corr_charge_spice_vs_level1_weighted"], lv["corr_charge_spice_vs_level2_weighted"],
            lv["waveform_lag_ps"]))
    return "\n".join(rows)


# ---------------------------------------------------------------- noise

def noise(variants=("N", "DA")):
    """SPICE max|t| against traces with white Gaussian noise added (0.5x, 1x, 2x the largest
    per-sample standard deviation of the noiseless traces)."""
    import matplotlib.pyplot as plt
    style()
    s = nbdata.summary()
    fig, axs = plt.subplots(1, len(variants), figsize=(9.5, 3.1), sharey=True)
    for ax, v in zip(np.atleast_1d(axs), variants):
        d = nbdata.read_csv("maxt_vs_traces_%s_tvla" % v)
        unit = s["campaigns"][v + "_tvla"]["spice"]["noise_unit_uA"]
        ax.plot(d["traces"], d["spice"], color=COLORS["ramp"][3], lw=1.6, label="no noise")
        for k, f in enumerate(("0.5", "1.0", "2.0")):
            ax.plot(d["traces"], d["spice_noise_%s" % f], color=COLORS["ramp"][2 - k], lw=1.4,
                    label="noise %sx" % f.rstrip("0").rstrip("."))
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_ylim(0.5, 30)
        _threshold(ax, label=False)
        ax.set_title("%s   (1x = %.0f uA)" % (TITLE[v], unit), loc="left", fontsize=9.5)
        ax.set_xlabel("traces")
    np.atleast_1d(axs)[0].set_ylabel("max |t| (SPICE)")
    np.atleast_1d(axs)[-1].legend(loc="upper left", fontsize=7.5)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------- tables

def probing_table():
    """Markdown table of the exact probing checks (results/probing/*.json)."""
    pr = nbdata.probing()
    rows = ["| Variant | nets | value model: insecure nets | glitch-extended model: insecure nets | "
            "variables whose two shares meet in a failing cone |", "|---|---|---|---|---|"]
    for v in ("N", "D", "DA"):
        p = pr[v]
        both = sorted({b for r in p["nets"] if not r["glitch_ok"] for b in r["both_shares_of"]})
        rows.append("| %s | %d | %d | %d | %s |" % (v, p["n_nets"], len(p["value_fail"]), len(p["glitch_fail"]),
                                                   ", ".join("x%d" % b for b in both) or "none"))
    return "\n".join(rows)


def variants_table():
    """Markdown table of the four variants (cell counts from summary.json)."""
    s = nbdata.summary()["setup"]["variants"]
    rnd = {"U": 0, "N": 5, "D": 5, "DA": 5}
    rows = ["| Id | Structure | cells (flip-flops) | latency | fresh random bits per S-box |",
            "|---|---|---|---|---|"]
    for v in ("U", "N", "D", "DA"):
        rows.append("| %s | %s | %d (%d) | %d | %d |" % (v, nbdata.VARIANT_NAMES[v], s[v]["n_cells"],
                                                         s[v]["n_dff"], s[v]["latency"], rnd[v]))
    return "\n".join(rows)


def criteria_table():
    """Markdown table of the pre-registered criteria and their outcome (summary.json)."""
    s = nbdata.summary()
    cr = s["criteria"]
    k2 = cr["K2"]["values"]

    def worst(d):
        return max(d["max_abs_t"][k] for k in nbdata.WEIGHTINGS)

    def ok(b):
        return "pass" if b else "**fail**"
    k6 = cr["K6"]
    rows = ["| Id | Criterion | Measured | Result |", "|---|---|---|---|",
            "| K1 | U in SPICE: max\\|t\\| > 4.5, and CPA ranks the correct key first (<= 2,000 traces) | "
            "TVLA %.1f; CPA rank of the correct key for keys 0/1/2/3: %s | TVLA pass, CPA fail: K1 %s |"
            % (cr["K1"]["tvla_max_abs_t"], " / ".join(str(cr["K1"]["cpa_primary_final_rank_per_key"][k])
                                                     for k in "0123"), ok(cr["K1"]["pass"])),
            "| K2 | N and D in the zero-delay model: max\\|t\\| < 4.5 | worst weighting: N %.2f, D %.2f at the "
            "SPICE counts; N %.2f, D %.2f at 100,000 | %s |"
            % (worst(k2["N_tvla_at_spice_count"]), worst(k2["D_tvla_at_spice_count"]), worst(k2["N_at_100k"]),
               worst(k2["D_at_100k"]), ok(cr["K2"]["pass"])),
            "| K3 | N in SPICE: max\\|t\\| > 4.5 (<= 20,000 traces) | %s at %s traces, above 4.5 from %s | %s |"
            % (tfmt(cr["K3"]["max_abs_t"]), "{:,}".format(cr["K3"]["traces"]), "{:,}".format(cr["K3"]["first_above"]),
               ok(cr["K3"]["pass"])),
            "| K4 | D in SPICE: max\\|t\\| < 4.5 (informational) | %s at %s traces | below 4.5 |"
            % (tfmt(cr["K4"]["max_abs_t"]), "{:,}".format(cr["K4"]["traces"])),
            "| K5 | DA in SPICE: max\\|t\\| < 4.5 at 20,000 (amendment A1) | %s at %s traces | %s |"
            % (tfmt(cr["K5"]["max_abs_t"]), "{:,}".format(cr["K5"]["traces"]), ok(cr["K5"]["pass"])),
            "| K6 | SPICE t-peaks on or after the switching of the flagged nets (informational) | N: peak %.3f ns, "
            "flagged nets switch %.2f-%.2f ns | N match; D no peak to place |"
            % (k6["N"]["spice_peak_ns_after_edge"], *k6["N"]["spice_nodes"]["flagged_switching_p5_p95_ns"]),
            "| C | (a) N random vs random < 4.5; (b) N with masks off leaks | (a) %.2f; (b) %.1f | %s |"
            % (cr["C"]["a_max_abs_t"], cr["C"]["b_max_abs_t"], ok(cr["C"]["pass"])),
            "| GO | K1, K2 and K3 | K1 fails on its CPA part | **%s** by the letter of the rule |"
            % ("GO" if cr["GO"] else "NO-GO")]
    return "\n".join(rows)


# ---------------------------------------------------------------- key recovery (section 5)

VARIANT_COLOR = {"U": COLORS["series1"], "N": COLORS["series2"], "D": COLORS["series3"],
                 "DA": COLORS["series4"]}
BAND = "#ecebe5"          # null band: one step lighter than the grid color
KR_LINES = [("U_tvla", "U", "tmpl", "-", "U (unmasked)"),
            ("N_pooled", "N", "tmpl", "-", "N, default POIs"),
            ("N_pooled", "N", "tmpl_bits", (0, (4, 2)), "N, per-key-bit POIs (post hoc)"),
            ("D_tvla", "D", "tmpl", "-", "D"),
            ("DA_tvla", "DA", "tmpl", "-", "DA")]
KR_PANELS = [("order1_noise0", "First order, no added noise"), ("order1_noise1", "First order, noise 1x"),
             ("order2_noise0", "Second order, no added noise")]


def _kr_result(kr, name, tag):
    return kr["datasets"].get(name, {}).get("results", {}).get(tag)


def key_recovery():
    """Guessing entropy of the Gaussian template (the primary distinguisher) against the
    number of attack traces per key; gray: the null (permuted profiling labels, mean +- 2 SD)."""
    import matplotlib.pyplot as plt
    style()
    kr = nbdata.key_recovery()
    fig, axs = plt.subplots(1, 3, figsize=(10, 3.5), sharey=True)
    for ax, (tag, title) in zip(axs, KR_PANELS):
        for name, v, dist, ls, label in KR_LINES:
            r = _kr_result(kr, name, tag)
            if r and dist == "tmpl":
                nl = r["null"][dist]
                ax.fill_between(nl["n"], [m - 2 * sd for m, sd in zip(nl["ge_mean"], nl["ge_sd"])],
                                [m + 2 * sd for m, sd in zip(nl["ge_mean"], nl["ge_sd"])], color=BAND, lw=0, zorder=1)
        for name, v, dist, ls, label in KR_LINES:
            r = _kr_result(kr, name, tag)
            if r:
                ax.plot(r[dist]["n"], r[dist]["ge"], color=VARIANT_COLOR[v], ls=ls, lw=1.6, zorder=3, label=label)
        ax.axhline(1.5, color=COLORS["muted"], lw=0.8, ls=(0, (4, 3)), zorder=2)
        ax.set_xscale("log")
        ax.set_xlim(1, 1200)
        ax.set_ylim(-0.05, 2.2)
        ax.set_title(title, loc="left", fontsize=9.5)
        ax.set_xlabel("attack traces per key")
    axs[0].set_ylabel("guessing entropy\n(0 = key found, 1.5 = random)")
    h, lab = axs[0].get_legend_handles_labels()
    h.append(plt.Rectangle((0, 0), 1, 1, color=BAND, lw=0))
    lab.append("null: labels permuted (mean +- 2 SD)")
    fig.legend(h, lab, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.13), fontsize=8)
    fig.tight_layout()
    return fig


def key_recovery_injection():
    """D and DA: final guessing entropy after adding alpha x N's first-order leak to the real
    traces (0 = the real traces), for the template and the correlation, with the template's
    null band and the leak size at which TVLA reaches 4.5 on average."""
    import matplotlib.pyplot as plt
    style()
    kr = nbdata.key_recovery()
    h = nbdata.headline()
    fig, axs = plt.subplots(1, 2, figsize=(9.5, 3.3), sharey=True)
    for ax, (v, name) in zip(axs, (("D", "D_tvla"), ("DA", "DA_tvla"))):
        e = kr["datasets"][name]
        r0 = e["results"]["order1_noise0"]
        inj = e["injection"]
        nl = r0["null"]["tmpl"]
        ax.axhspan(nl["final_ge_mean"] - 2 * nl["final_ge_sd"], nl["final_ge_mean"] + 2 * nl["final_ge_sd"],
                   color=BAND, lw=0, zorder=1)
        al = [0.0] + sorted(float(a) for a in inj["alphas"])
        for dist, ls, label in (("tmpl", "-", "Gaussian template (primary)"),
                                ("corr", (0, (4, 2)), "correlation (secondary)")):
            ge = [r0[dist]["final_ge"]] + [inj["alphas"]["%g" % a][dist]["final_ge"] for a in al[1:]]
            ax.plot(al, ge, color=VARIANT_COLOR[v], ls=ls, lw=1.6, marker="o", ms=4, zorder=3, label=label)
        a_t = h[v + "_detect_frac_of_N"]
        ax.axvline(a_t, color=COLORS["ink2"], lw=0.9, ls=(0, (1, 2)), zorder=2)
        ax.text(a_t + 0.02, 2.1, "TVLA at %s traces\nreaches 4.5 from here" % "{:,}".format(h[v + "_n"]),
                fontsize=7, color=COLORS["ink2"], va="top")
        ax.axhline(1.5, color=COLORS["muted"], lw=0.8, ls=(0, (4, 3)), zorder=2)
        ax.set_xlim(-0.03, 1.05)
        ax.set_ylim(-0.05, 2.2)
        ax.set_title("%s: %s attack traces per key" % (v, "{:,}".format(r0["tmpl"]["n"][-1])),
                     loc="left", fontsize=9.5)
        ax.set_xlabel("injected leak, x N's first-order effect")
    axs[0].set_ylabel("guessing entropy, last checkpoint")
    hd, lab = axs[1].get_legend_handles_labels()
    hd.append(plt.Rectangle((0, 0), 1, 1, color=BAND, lw=0))
    lab.append("template null (mean +- 2 SD)")
    axs[1].legend(hd, lab, loc="lower left", fontsize=7.5)
    fig.tight_layout()
    return fig


def key_recovery_table():
    """Markdown table: the attack's result per variant and order (no added noise)."""
    kr = nbdata.key_recovery()

    def cell(r, d):
        return "%.2f (%.2f)" % (r[d]["final_ge"], r[d]["final_sr"])
    rows = ["| Variant, order | attack traces per key | template, default POIs: GE (SR) | template, per-key-bit "
            "POIs (post hoc): GE (SR) | null GE, mean +- SD | p vs null (default POIs) | correlation GE "
            "(secondary) |", "|---|---|---|---|---|---|---|"]
    for name, label, tag in (("U_tvla", "U, 1st", "order1_noise0"),
                             ("U_cpa", "U on the K1 CPA traces, 1st", "order1_noise0"),
                             ("N_pooled", "N, 1st", "order1_noise0"), ("D_tvla", "D, 1st", "order1_noise0"),
                             ("DA_tvla", "DA, 1st", "order1_noise0"), ("N_pooled", "N, 2nd", "order2_noise0"),
                             ("D_tvla", "D, 2nd", "order2_noise0"), ("DA_tvla", "DA, 2nd", "order2_noise0")):
        r = _kr_result(kr, name, tag)
        if not r:
            continue
        nl = r["null"]["tmpl"]
        rows.append("| %s | %s | %s | %s | %.2f +- %.2f (%d draws) | %.3f | %.2f |" % (
            label, "{:,}".format(r["tmpl"]["n"][-1]), cell(r, "tmpl"), cell(r, "tmpl_bits"), nl["final_ge_mean"],
            nl["final_ge_sd"], nl["draws"], r["tmpl"]["p_vs_null"], r["corr"]["final_ge"]))
    return "\n".join(rows)


# ---------------------------------------------------------------- cost (section 7)

def cost_table():
    """Markdown table of the cost of each variant, from the cost step's CSV (data/cost__cost.csv
    or results/cost/cost.csv); None while that step has not written it."""
    try:
        c = nbdata.cost()
    except FileNotFoundError:
        return None
    rows = list(c.values())
    cols = [("variant", "Variant", None), ("cells", "cells", None), ("dff", "flip-flops", None),
            ("area_um2", "cell area (um^2)", 1), ("area_vs_N", "area vs N", 2),
            ("latency_cycles", "latency (cycles)", None), ("min_period_ps", "min. clock period (ps)", 0),
            ("latency_ns", "latency (ns)", 2), ("latency_vs_N", "latency vs N", 2),
            ("fresh_random_bits", "fresh random bits", None),
            ("e_eval_fJ", "energy per evaluation, SPICE (fJ)", 0), ("e_total_fJ", "incl. CLK pins (fJ)", 0),
            ("total_vs_N", "energy vs N", 2)]
    cols = [col for col in cols if col[0] in rows[0]]

    def cell(v, digits):
        return v if digits is None or v == "" else "%.*f" % (digits, float(v))
    out = ["| " + " | ".join(h for _, h, _ in cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(cell(r[k], d) for k, _, d in cols) + " |")
    return "\n".join(out)


def cost_figure():
    """Area, energy per evaluation (SPICE plus the CLK pins) and latency in time of the four
    variants, as small multiples on their own axes (pre-layout)."""
    import matplotlib.pyplot as plt
    style()
    c = nbdata.cost()
    order = [v for v in ("U", "N", "D", "DA") if v in c]
    fig, axs = plt.subplots(1, 3, figsize=(10, 2.6), sharey=True)
    for ax, (key, title, unit) in zip(axs, (("area_um2", "Cell area", "um^2"),
                                            ("e_total_fJ", "Energy per evaluation, incl. CLK pins", "fJ"),
                                            ("latency_ns", "Latency in time", "ns"))):
        vals = [float(c[v][key]) for v in order]
        y = np.arange(len(order))
        ax.barh(y, vals, height=0.62, color=[VARIANT_COLOR[v] for v in order], zorder=3)
        for yi, val in zip(y, vals):
            ax.text(val, yi, "  %s" % (("%.0f" % val) if val >= 10 else ("%.2f" % val)), va="center",
                    fontsize=8, color=COLORS["ink2"])
        ax.set_xlim(0, max(vals) * 1.28)
        ax.set_title("%s (%s)" % (title, unit), loc="left", fontsize=9.5)
        ax.grid(axis="y", visible=False)
    axs[0].set_yticks(np.arange(len(order)))
    axs[0].set_yticklabels(order)
    axs[0].invert_yaxis()
    fig.tight_layout()
    return fig


def show(fig=None):
    """Show the current figure(s) inline and return nothing (no duplicate output)."""
    import matplotlib.pyplot as plt
    plt.show()


def md_to_html(text):
    """A markdown pipe table (as written by the functions above) as a small HTML table."""
    import html
    import re
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip().startswith("|")]

    def cells(ln):
        parts = re.split(r"(?<!\\)\|", ln.strip()[1:-1])
        out = []
        for c in parts:
            c = html.escape(c.strip().replace("\\|", "|"))
            c = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", c)
            out.append(c)
        return out
    head = cells(lines[0])
    body = [cells(ln) for ln in lines[2:]]
    h = "".join("<th style='text-align:left'>%s</th>" % c for c in head)
    b = "".join("<tr>%s</tr>" % "".join("<td style='text-align:left'>%s</td>" % c for c in r) for r in body)
    return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (h, b)


def show_md(text):
    """Display a markdown table as HTML (renders on GitHub too), with the markdown as the
    plain-text fallback; prints it outside Jupyter."""
    try:
        from IPython.display import display
    except ImportError:
        print(text)
        return
    display({"text/html": md_to_html(text), "text/plain": text}, raw=True)
