# SPDX-License-Identifier: Apache-2.0
"""Figures of the profiled key recovery, drawn from results/key_recovery/summary.json.

Runs in the cac-sca docker image (matplotlib):
  bash sim/docker_run.sh python3 analysis/plot_key_recovery.py
Writes results/key_recovery/
  fig_ge.png         guessing entropy (mean rank of the correct 2-bit key; 1.5 = random) against
                     the number of attack traces. Rows: the Gaussian template (primary), the
                     same template on per-key-bit POIs (post hoc), and the correlation
                     (secondary: blind to a key bit's main effect). Columns: first order
                     without and with added noise, and second order. Gray band: the null
                     distribution (permuted profiling labels, mean +- 2 SD, every dataset)
  fig_bits.png       first order, no added noise: P(top guess has the right key bit) for key
                     bits x1 and x2; N with the default and with the per-key-bit POIs, D and DA
  fig_injection.png  D and DA: final GE of the attack after adding alpha x N's first-order leak
                     to the real traces (positive control), with the null band and the leak size
                     that TVLA at the same campaign detects
Colors and style: the kill-test figures' palette (analysis/plots.py), one fixed color per
variant (U blue, N orange, D aqua, DA yellow); the null in gray.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import plots as P                 # noqa: E402  (style, palette, rcParams)
import matplotlib.pyplot as plt   # noqa: E402

RES = os.path.join(P.REPO, "results", "key_recovery")
KT = os.path.join(P.REPO, "results", "kill_test", "summary.json")
BAND = "#ecebe5"                  # null band: one step lighter than the grid color
# dataset -> (label, color, line style); fixed order U, N, D, DA (palette slots 1-4)
LINES = [
    ("U_tvla", "U (unmasked)", P.SERIES[0], "-"),
    ("U_cpa", "U, templates from U_tvla, attack on the K1 CPA traces", P.SERIES[0], (0, (4, 2))),
    ("N_pooled", "N (naive DOM)", P.SERIES[1], "-"),
    ("D_tvla", "D (DOM + barrier)", P.SERIES[2], "-"),
    ("DA_tvla", "DA (barrier after the affine layer)", P.SERIES[3], "-"),
]
PANELS = [("order1_noise0", "First order, no added noise"),
          ("order1_noise1", "First order, noise 1x"),
          ("order2_noise0", "Second order, no added noise")]
DISTS = [("tmpl", "Gaussian template\n(primary)"),
         ("tmpl_bits", "template, per-key-bit\nPOIs (post hoc)"),
         ("corr", "correlation (secondary;\nblind to main effects)")]


def res(summ, name, tag):
    return summ["datasets"].get(name, {}).get("results", {}).get(tag)


def null_band(ax, r, dist):
    """The null distribution's mean +- 2 SD per checkpoint, as a gray band."""
    nl = r.get("null", {}).get(dist)
    if not nl:
        return
    lo = [m - 2 * s for m, s in zip(nl["ge_mean"], nl["ge_sd"])]
    hi = [m + 2 * s for m, s in zip(nl["ge_mean"], nl["ge_sd"])]
    ax.fill_between(nl["n"], lo, hi, color=BAND, lw=0, zorder=1)


def panel(ax, summ, tag, dist):
    for name, _, _, _ in LINES:             # null bands first, underneath
        r = res(summ, name, tag)
        if r:
            null_band(ax, r, dist)
    for name, label, color, ls in LINES:
        r = res(summ, name, tag)
        if r and dist in r:
            ax.plot(r[dist]["n"], r[dist]["ge"], color=color, ls=ls, lw=1.6, zorder=3, label=label)
    ax.axhline(1.5, color=P.MUTED, lw=0.8, ls=(0, (4, 3)), zorder=2)
    ax.set_xscale("log")
    ax.set_ylim(-0.05, 2.3)
    ax.set_xlim(1, 2500)


def fig_ge(summ):
    fig, axs = plt.subplots(3, 3, figsize=(10.5, 8.4), sharex=True, sharey=True)
    for i, (dist, dname) in enumerate(DISTS):
        for j, (tag, title) in enumerate(PANELS):
            ax = axs[i, j]
            panel(ax, summ, tag, dist)
            if i == 0:
                ax.set_title(title, loc="left")
            if j == 0:
                ax.set_ylabel("%s\nguessing entropy (key rank)" % dname)
            if i == len(DISTS) - 1:
                ax.set_xlabel("attack traces per key")
    h, lab = axs[0, 0].get_legend_handles_labels()
    h += [plt.Rectangle((0, 0), 1, 1, color=BAND, lw=0), plt.Line2D([], [], color=P.MUTED, lw=0.8, ls=(0, (4, 3)))]
    lab += ["null: profiling labels permuted (mean +- 2 SD)", "random guessing (1.5)"]
    fig.legend(h, lab, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.05), fontsize=8.5)
    fig.suptitle("Profiled key recovery on the SPICE traces (2 key bits; 0 = key found, 1.5 = random)",
                 x=0.01, ha="left", y=1.08, fontweight="bold", fontsize=10.5, color=P.INK)
    fig.tight_layout()
    save(fig, "fig_ge.png")


def fig_bits(summ):
    fig, axs = plt.subplots(1, 3, figsize=(10.5, 3.3), sharey=True)
    specs = [(axs[0], "N: default POIs (overall F)", [("N_pooled", "N", P.SERIES[1], "tmpl")]),
             (axs[1], "N: per-key-bit POIs (post hoc)", [("N_pooled", "N", P.SERIES[1], "tmpl_bits")]),
             (axs[2], "D and DA: default POIs", [("D_tvla", "D", P.SERIES[2], "tmpl"),
                                                 ("DA_tvla", "DA", P.SERIES[3], "tmpl")])]
    for ax, title, series in specs:
        for name, label, color, dist in series:
            r = res(summ, name, "order1_noise0")
            if not r or dist not in r:
                continue
            ax.plot(r[dist]["n"], r[dist]["sr_x1"], color=color, lw=1.6, label="%s, key bit x1" % label)
            ax.plot(r[dist]["n"], r[dist]["sr_x2"], color=color, lw=1.6, ls=(0, (4, 2)),
                    label="%s, key bit x2" % label)
        ax.axhline(0.5, color=P.MUTED, lw=0.8, ls=(0, (4, 3)))
        ax.set_xscale("log")
        ax.set_ylim(0.3, 1.02)
        ax.set_title(title, loc="left", fontsize=9.5)
        ax.set_xlabel("attack traces per key")
        ax.legend(loc="upper left", fontsize=7.5)
    axs[0].set_ylabel("P(top guess has the right bit)\n(random: 0.5)")
    fig.suptitle("Which key bit leaks at first order (Gaussian template, no added noise)", x=0.01, ha="left",
                 fontweight="bold", fontsize=10.5, color=P.INK)
    fig.tight_layout()
    save(fig, "fig_bits.png")


def tvla_alpha(kts, campaign):
    """Leak size (fraction of N's) at which TVLA reaches 4.5 on average: t = d sqrt(n) / 2."""
    c = kts["campaigns"]
    d_n = 2 * c["N_tvla"]["spice"]["final_max_abs_t"] / math.sqrt(c["N_tvla"]["rows_analysed"])
    return (2 * P.TH / math.sqrt(c[campaign]["rows_analysed"])) / d_n, c[campaign]["rows_analysed"]


def fig_injection(summ, kts):
    names = [(n, lab, col) for n, lab, col, _ in LINES if n in ("D_tvla", "DA_tvla")
             and "injection" in summ["datasets"].get(n, {})]
    if not names:
        return
    fig, axs = plt.subplots(1, len(names), figsize=(4.4 * len(names), 3.4), sharey=True, squeeze=False)
    for ax, (name, label, color) in zip(axs[0], names):
        e = summ["datasets"][name]
        r0 = e["results"]["order1_noise0"]
        inj = e["injection"]
        for dist, ls, dl in (("tmpl", "-", "Gaussian template (primary)"),
                             ("corr", (0, (4, 2)), "correlation (secondary)")):
            nl = r0["null"][dist]
            if dist == "tmpl":
                ax.axhspan(nl["final_ge_mean"] - 2 * nl["final_ge_sd"], nl["final_ge_mean"] + 2 * nl["final_ge_sd"],
                           color=BAND, lw=0, zorder=1)
            al = [0.0] + sorted(float(a) for a in inj["alphas"])
            ge = [r0[dist]["final_ge"]] + [inj["alphas"]["%g" % a][dist]["final_ge"] for a in al[1:]]
            ax.plot(al, ge, color=color, ls=ls, lw=1.6, marker="o", ms=4, zorder=3, label=dl)
        a_t, n_t = tvla_alpha(kts, name)
        ax.axvline(a_t, color=P.INK2, lw=0.9, ls=(0, (1, 2)), zorder=2)
        ax.text(a_t + 0.02, 2.12, "TVLA at %s traces\nreaches 4.5 from here" % format(n_t, ","), fontsize=7,
                color=P.INK2, va="top")
        ax.axhline(1.5, color=P.MUTED, lw=0.8, ls=(0, (4, 3)), zorder=2)
        ax.set_xlim(-0.03, 1.05)
        ax.set_ylim(-0.05, 2.2)
        ax.set_title("%s: %d attack traces per key" % (label, r0["tmpl"]["n"][-1]), loc="left", fontsize=9.5)
        ax.set_xlabel("injected leak, x N's first-order effect (0 = the real traces)")
    axs[0, 0].set_ylabel("guessing entropy at the last checkpoint")
    h, lab = axs[0, 0].get_legend_handles_labels()
    h.append(plt.Rectangle((0, 0), 1, 1, color=BAND, lw=0))
    lab.append("null of the template (mean +- 2 SD)")
    axs[0, -1].legend(h, lab, loc="lower left", fontsize=7.5)
    fig.suptitle("What the attack would have found: N's leak added to the real D and DA traces", x=0.01,
                 ha="left", fontweight="bold", fontsize=10.5, color=P.INK)
    fig.tight_layout()
    save(fig, "fig_injection.png")


def save(fig, name):
    out = os.path.join(RES, name)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote", os.path.relpath(out, P.REPO))


def main():
    with open(os.path.join(RES, "summary.json")) as f:
        summ = json.load(f)
    with open(KT) as f:
        kts = json.load(f)
    fig_ge(summ)
    fig_bits(summ)
    fig_injection(summ, kts)


if __name__ == "__main__":
    main()
