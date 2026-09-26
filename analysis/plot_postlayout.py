# SPDX-License-Identifier: Apache-2.0
"""Figures of the post-layout TVLA (docs/POSTLAYOUT.md), drawn from results/pex/*.csv and
summary_postlayout.json (written by analysis/postlayout.py).

Runs in the cac-sca docker image (matplotlib):
  bash sim/docker_run.sh python3 analysis/plot_postlayout.py
Writes results/pex/fig/:
  tvla_pre_vs_post.png            Welch t against time, N and DA, post-layout vs pre-layout on the same rows
  maxt_vs_traces_pre_vs_post.png  max|t| against the number of traces, same pairs
Colors: post-layout in the SPICE blue of analysis/plots.py, the pre-layout reference in gray.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import plots                      # noqa: E402  (colours, rcParams, read_csv, threshold)

REPO = os.path.normpath(os.path.join(HERE, ".."))
RES = os.path.join(REPO, "results", "pex")
FIG = os.path.join(RES, "fig")
POST, PRE = plots.LEVEL["spice"], plots.MUTED
NAMES = {"N_pex": "N, naive DOM", "DA_pex": "DA, DOM + barrier after the affine layer"}


def save(fig, name):
    os.makedirs(FIG, exist_ok=True)
    fig.savefig(os.path.join(FIG, name), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote", os.path.relpath(os.path.join(FIG, name), REPO))


def part_lines(ax, parts, lat, T=4.0):
    """Light vertical lines at the registered post-layout cycle-part boundaries."""
    for c in range(lat):
        for name, (a, b) in parts.items():
            if name != "edge_and_evaluation":
                ax.axvline(a + c * T, color=plots.GRID, lw=1.0, zorder=0)


def tvla_pre_vs_post(s):
    fig, axs = plt.subplots(2, 1, figsize=(8.6, 5.6), gridspec_kw={"height_ratios": [1, 1]})
    parts = s["criteria"]["PL3"]["parts_ns_after_each_edge"]
    for ax, name in zip(axs, ("N_pex", "DA_pex")):
        c = s["campaigns"][name]
        d = plots.read_csv(os.path.join(RES, "tcurve_%s.csv" % name))
        x = d["ns_after_edge"]
        lat = 2 if name == "DA_pex" else 1
        part_lines(ax, parts, lat)
        ax.plot(x, d["t_pre_layout_same_rows"], color=PRE, lw=0.9,
                label="pre-layout, same rows (max|t| %.2f)" % c["pre_layout_same_rows"]["final_max_abs_t"])
        ax.plot(x, d["t_post_layout"], color=POST, lw=1.4,
                label="post-layout, C-only extraction (max|t| %.2f)" % c["spice"]["final_max_abs_t"])
        plots.threshold(ax)
        ax.set_xlim(x[0], x[-1] + 0.005)
        ax.set_ylabel("Welch t (signed)")
        ax.set_title("%s: %s traces, sky130 tt" % (NAMES[name], "{:,}".format(c["rows_analysed"])), loc="left")
        ax.legend(loc="lower right", fontsize=7.5)
    axs[-1].set_xlabel("ns after the capturing clock edge at the block's CLK pin (DA: second edge at 4 ns)")
    fig.tight_layout()
    save(fig, "tvla_pre_vs_post.png")


def maxt_pre_vs_post(s):
    fig, axs = plt.subplots(1, 2, figsize=(8.6, 3.2), sharey=True)
    n_ref = s["campaigns"]["N_pex"]
    d_n = 2.0 * n_ref["spice"]["final_max_abs_t"] / np.sqrt(n_ref["rows_analysed"])
    for ax, name in zip(axs, ("N_pex", "DA_pex")):
        d = plots.read_csv(os.path.join(RES, "maxt_vs_traces_%s.csv" % name))
        n = d["traces"]
        ax.plot(n, d_n * np.sqrt(n) / 2, color=plots.MUTED, lw=1, ls=(0, (1, 2)),
                label="a leak as strong as post-layout N's")
        ax.plot(n, d["pre_layout_same_rows"], color=PRE, lw=1.0, label="pre-layout, same rows")
        ax.plot(n, d["post_layout"], color=POST, lw=1.8, label="post-layout")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_ylim(0.1, 30)
        ax.set_xlim(20, 12000)
        plots.threshold(ax, both=False)
        ax.set_title(NAMES[name], loc="left")
        ax.set_xlabel("traces")
    axs[0].set_ylabel("max |t| over the window")
    axs[0].legend(loc="upper left", fontsize=7.5)
    fig.tight_layout()
    save(fig, "maxt_vs_traces_pre_vs_post.png")


def main():
    with open(os.path.join(RES, "summary_postlayout.json")) as f:
        s = json.load(f)
    tvla_pre_vs_post(s)
    maxt_pre_vs_post(s)


if __name__ == "__main__":
    main()
