# SPDX-License-Identifier: Apache-2.0
"""Figures of the kill test, drawn from results/kill_test/*.csv and summary.json.

Runs in the cac-sca docker image (matplotlib):
  bash sim/docker_run.sh python3 analysis/plots.py
Writes results/kill_test/fig/*.png:
  tvla_<campaign>.png     mean current, mean difference (fixed - random) and t vs time (SPICE, level 2)
  maxt_vs_traces.png      max|t| vs number of traces, SPICE / level 2 / level 1, per campaign
  noise.png               max|t| vs traces in SPICE with added Gaussian noise
  cpa_U.png               rank of the correct key vs traces, 4 keys, both hypotheses
  localization_<V>.png    SPICE t around the peak and per-net |t| of the nets' transitions
Colors: one fixed color per model level (SPICE blue, level 2 orange, level 1 aqua).
"""
import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
RES = os.path.join(REPO, "results", "kill_test")
FIG = os.path.join(RES, "fig")

SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
LEVEL = {"spice": "#2a78d6", "level2": "#eb6834", "level1": "#1baf7a"}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
RAMP = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]       # ordinal blue (light -> dark)
TH = 4.5
TITLES = {"U_tvla": "U (unmasked)", "N_masksoff": "N, masks off (control b)",
          "N_rvr": "N, random vs random (control a)", "N_tvla": "N (naive DOM)",
          "D_tvla": "D (DOM + register barrier)", "DA_tvla": "DA (D, affine layer before registers)"}

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "sans-serif", "font.size": 9, "text.color": INK, "axes.labelcolor": INK2,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "legend.frameon": False, "axes.titlesize": 10,
    "axes.titleweight": "bold", "axes.titlecolor": INK, "lines.linewidth": 1.4})


def read_csv(path):
    with open(path) as f:
        rows = list(csv.reader(f))
    head, body = rows[0], rows[1:]
    return {h: np.array([float(r[i]) if r[i] not in ("", "None") else np.nan for r in body])
            for i, h in enumerate(head)}


def threshold(ax, both=True):
    for y in ((TH, -TH) if both else (TH,)):
        ax.axhline(y, color=MUTED, lw=0.8, ls=(0, (4, 3)), zorder=1)


def save(fig, name):
    os.makedirs(FIG, exist_ok=True)
    fig.savefig(os.path.join(FIG, name), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote", os.path.relpath(os.path.join(FIG, name), REPO))


def tvla_time(name, summ):
    d = read_csv(os.path.join(RES, "tcurve_%s.csv" % name))
    c = summ["campaigns"][name]
    x = d["ns_after_edge"]
    fig, ax = plt.subplots(3, 1, figsize=(7.2, 6.2), sharex=True,
                           gridspec_kw={"height_ratios": [1, 1, 1.6]})
    ax[0].plot(x, d["mean_uA"], color=LEVEL["spice"], lw=1.0)
    ax[0].set_ylabel("mean current (uA)")
    ax[0].set_title("%s: %d traces" % (TITLES.get(name, name), c["rows_analysed"]), loc="left")
    ax[1].plot(x, d["mean_fixed_minus_random_uA"], color=LEVEL["spice"], lw=1.0)
    ax[1].set_ylabel("fixed - random (uA)")
    ax[2].plot(x, d["t_level2_weighted"], color=LEVEL["level2"], lw=1.0,
               label="level 2, timing-aware model (max|t| %.1f)" % c["level2"]["weighted"]["final_max_abs_t"])
    ax[2].plot(x, d["t_spice"], color=LEVEL["spice"], lw=1.2,
               label="SPICE (max|t| %.1f)" % c["spice"]["final_max_abs_t"])
    threshold(ax[2])
    ax[2].set_ylabel("Welch t")
    ax[2].set_xlabel("ns after the capturing clock edge")
    ax[2].legend(loc="upper right", fontsize=8)
    save(fig, "tvla_%s.png" % name)


def maxt_vs_traces(summ):
    names = [n for n in TITLES if n in summ["campaigns"]]
    cols = 3
    rows = (len(names) + cols - 1) // cols
    fig, axs = plt.subplots(rows, cols, figsize=(10, 3.1 * rows), squeeze=False)
    for ax, name in zip(axs.flat, names):
        d = read_csv(os.path.join(RES, "maxt_vs_traces_%s.csv" % name))
        n = d["traces"]
        ax.plot(n, np.maximum(d["level1_weighted"], 1e-2), color=LEVEL["level1"], label="level 1, zero-delay")
        ax.plot(n, np.maximum(d["level2_weighted"], 1e-2), color=LEVEL["level2"], label="level 2, timing-aware")
        ax.plot(n, d["spice"], color=LEVEL["spice"], lw=2, label="SPICE")
        threshold(ax, both=False)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_ylim(0.1, max(100, float(np.nanmax(d["spice"])) * 1.5))
        ax.set_title(TITLES[name], loc="left")
        ax.set_xlabel("traces")
        ax.set_ylabel("max |t|")
    for ax in list(axs.flat)[len(names):]:
        ax.set_visible(False)
    axs.flat[0].legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    save(fig, "maxt_vs_traces.png")


def noise(summ):
    names = [n for n in ("U_tvla", "N_tvla", "D_tvla", "DA_tvla") if n in summ["campaigns"]]
    fig, axs = plt.subplots(1, len(names), figsize=(3.3 * len(names), 3.0), squeeze=False)
    for ax, name in zip(axs[0], names):
        d = read_csv(os.path.join(RES, "maxt_vs_traces_%s.csv" % name))
        sig = summ["campaigns"][name]["spice"]["noise_unit_uA"]
        ax.plot(d["traces"], d["spice"], color=RAMP[3], lw=1.6, label="no noise")
        for k, f in enumerate(("0.5", "1.0", "2.0")):
            ax.plot(d["traces"], d["spice_noise_%s" % f], color=RAMP[2 - k], lw=1.6,
                    label="noise %sx" % f.rstrip("0").rstrip("."))
        ax.text(0.98, 0.04, "1x = %.0f uA (largest per-sample std)" % sig, transform=ax.transAxes,
                ha="right", color=INK2, fontsize=7)
        threshold(ax, both=False)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_ylim(0.1, None)
        ax.set_title(TITLES[name], loc="left")
        ax.set_xlabel("traces")
        ax.set_ylabel("max |t| (SPICE)")
    h, lab = axs[0][0].get_legend_handles_labels()
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    fig.legend(h, lab, loc="lower center", ncol=4, fontsize=8)
    save(fig, "noise.png")


def cpa(summ):
    path = os.path.join(RES, "cpa_rank_vs_traces.csv")
    if not os.path.exists(path):
        return
    with open(path) as f:
        rows = list(csv.DictReader(f))
    hyps = [("level1_model", "primary: level-1 toggle model"), ("hw_sbox", "pre-registered: HW(S(x))")]
    fig, axs = plt.subplots(1, 2, figsize=(9, 3.0), sharey=True)
    for ax, (h, title) in zip(axs, hyps):
        for key in range(4):
            r = [q for q in rows if q["hypothesis"] == h and int(q["key"]) == key]
            if not r:
                continue
            off = (key - 1.5) * 0.07          # small offset so that equal ranks stay visible
            ax.step([int(q["traces"]) for q in r], [int(q["rank"]) + off for q in r], where="post",
                    color=SERIES[key], lw=1.6, label="key %d" % key)
        ax.set_xscale("log")
        ax.set_yticks([1, 2, 3, 4])
        ax.set_ylim(4.3, 0.7)
        ax.set_title(title, loc="left")
        ax.set_xlabel("traces")
    axs[0].set_ylabel("rank of the correct key (lines offset)")
    axs[1].legend(loc="lower right", fontsize=8, ncol=2)
    fig.tight_layout()
    save(fig, "cpa_U.png")


def localization(v, summ):
    loc = summ.get("localization", {}).get(v)
    path = os.path.join(RES, "pernet_t_%s_spice_nodes.csv" % v)
    if loc is None or not os.path.exists(path):
        return
    d = read_csv(path)
    x = d.pop("ns_after_edge")
    names = list(d)
    t = np.array([d[k] for k in names])
    best = np.abs(t).max(1)
    order = [i for i in np.argsort(-best)[:16]]
    flagged = set(loc["glitch_extended_flagged_nets"])
    tc = read_csv(os.path.join(RES, "tcurve_%s_tvla.csv" % v))
    peak = loc["spice_peak_ns_after_edge"]
    xmax = 2.2 if v == "N" else x.max()
    fig, ax = plt.subplots(2, 1, figsize=(7.2, 6.0), sharex=True, gridspec_kw={"height_ratios": [1, 2]})
    ax[0].plot(tc["ns_after_edge"], tc["t_spice"], color=LEVEL["spice"], lw=1.2, label="SPICE supply current")
    threshold(ax[0])
    significant = abs(loc["spice_peak_t"]) > TH
    if significant:
        ax[0].axvline(peak, color=INK2, lw=0.8)
    ax[0].set_ylabel("Welch t")
    ax[0].set_title("%s: supply-current t (%d traces) and per-net transition t (SPICE node voltages, %d traces)"
                    % (v, summ["campaigns"][v + "_tvla"]["rows_analysed"], loc["spice_nodes"]["rows"]),
                    loc="left", fontsize=9)
    img = np.abs(t[order])
    dx = x[1] - x[0]
    im = ax[1].imshow(img, aspect="auto", cmap="Blues", vmin=0, vmax=max(10, img.max()),
                      extent=(x[0] - dx / 2, x[-1] + dx / 2, len(order) - 0.5, -0.5), interpolation="nearest")
    ax[1].set_yticks(range(len(order)))
    ax[1].set_yticklabels(["%s%s" % (names[i], " *" if names[i] in flagged else "") for i in order], fontsize=7)
    ax[1].grid(False)
    if significant:
        ax[1].axvline(peak, color=INK2, lw=0.8)
    ax[1].set_xlabel("ns after the capturing clock edge   (* = flagged by glitch-extended probing)")
    ax[1].set_xlim(-0.2, xmax)
    cb = fig.colorbar(im, ax=list(ax), pad=0.01, fraction=0.03)   # both panels keep the same width
    cb.set_label("|t| of the net's transition count", color=INK2)
    save(fig, "localization_%s.png" % v)


def main():
    with open(os.path.join(RES, "summary.json")) as f:
        summ = json.load(f)
    for name in summ["campaigns"]:
        tvla_time(name, summ)
    maxt_vs_traces(summ)
    noise(summ)
    cpa(summ)
    for v in ("N", "D", "DA"):
        localization(v, summ)


if __name__ == "__main__":
    main()
