# SPDX-License-Identifier: Apache-2.0
"""TVLA explorer: pick a variant, a number of traces and added noise, and see max|t| against
traces and the t curve, from the notebook's cached data set (data/, no SPICE traces needed).

Inputs per fixed-vs-random campaign (written by make_cached_data.py):
  data/tvla_t_checkpoints_<c>.csv   first-order Welch t per 10 ps sample at 25 trace counts
  data/class_stats_<c>.csv          per sample: mean and std of each class over all traces
and the campaign's class counts and noise unit from the kill-test summary.

Without added noise the t curves are the exact ones. Added white Gaussian noise of standard
deviation s (per 10 ps sample) is folded in statistically: each class variance grows by s^2,
and each class mean moves by the average of the noise over that class's traces, drawn as a
Gaussian random walk over the trace counts (the same distribution as noise added trace by
trace). The class-mean difference at each count is recovered as d = t * sqrt(v0/n0 + v1/n1),
with the class variances v and class fractions taken from the full campaign (exact at the
last count, close elsewhere). check_against_exact() compares with the kill test's
trace-by-trace noise runs.

  load(campaign)                       the cached statistics
  curve(st, noise_factor, seed)        max|t| per trace count and the t curves
  static_panel()                       a fixed set of views (for GitHub and for CI)
  interactive_panel()                  ipywidgets version (False when ipywidgets is missing)
"""
import numpy as np

import nbdata

CAMPAIGNS = {"U": "U_tvla", "N": "N_tvla", "D": "D_tvla", "DA": "DA_tvla"}


def load(campaign):
    keys, times, t = nbdata.read_matrix("tvla_t_checkpoints_%s" % campaign)
    cs = nbdata.read_csv("class_stats_%s" % campaign)
    c = nbdata.summary()["campaigns"][campaign]
    n = keys["traces"]
    p0 = c["class_counts"][0] / float(sum(c["class_counts"]))
    n0 = np.maximum(np.round(n * p0), 2)
    n1 = np.maximum(n - n0, 2)
    v0, v1 = cs["std_fixed_uA"] ** 2, cs["std_random_uA"] ** 2
    d = t * np.sqrt(v0 / n0[:, None] + v1 / n1[:, None])
    return {"campaign": campaign, "n": n, "n0": n0, "n1": n1, "d": d, "v0": v0, "v1": v1,
            "time_ns": times, "noise_unit_uA": c["spice"]["noise_unit_uA"]}


def curve(st, noise_factor=0.0, seed=0):
    """max|t| at each cached trace count and the t curves, with noise of
    noise_factor x the campaign's noise unit (the largest per-sample std without noise)."""
    s = noise_factor * st["noise_unit_uA"]
    n0, n1 = st["n0"], st["n1"]
    d = st["d"].copy()
    v0, v1 = st["v0"][None, :] + s * s, st["v1"][None, :] + s * s
    if s > 0:
        rng = np.random.default_rng(seed)
        m = d.shape[1]
        # sum of the noise over each class's traces, as a random walk over the checkpoints
        dn0 = np.diff(np.concatenate([[0.0], n0]))
        dn1 = np.diff(np.concatenate([[0.0], n1]))
        s0 = np.cumsum(rng.standard_normal((len(n0), m)) * (s * np.sqrt(dn0))[:, None], axis=0)
        s1 = np.cumsum(rng.standard_normal((len(n1), m)) * (s * np.sqrt(dn1))[:, None], axis=0)
        d = d + s0 / n0[:, None] - s1 / n1[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = d / np.sqrt(v0 / n0[:, None] + v1 / n1[:, None])
    t = np.nan_to_num(t)
    return {"n": st["n"], "max_abs_t": np.abs(t).max(1), "t": t}


def check_against_exact(campaign="N_tvla", factor=1.0):
    """Cached-statistics max|t| with noise vs the kill test's exact per-trace noise run,
    at the final trace count (different noise draws, so they agree only statistically)."""
    st = load(campaign)
    approx = [float(curve(st, factor, seed)["max_abs_t"][-1]) for seed in range(5)]
    exact = nbdata.summary()["campaigns"][campaign]["spice"]["noise"][str(factor)]["final_max_abs_t"]
    return exact, approx


def _plot(axs, variant, n_index, noise_factor, seed=0):
    import nbfigs
    C = nbfigs.COLORS
    st = load(CAMPAIGNS[variant])
    r = curve(st, noise_factor, seed)
    k = min(n_index, len(r["n"]) - 1)
    a, b = axs
    a.plot(r["n"], r["max_abs_t"], color=nbfigs.LEVEL["spice"], lw=1.6)
    a.plot([r["n"][k]], [r["max_abs_t"][k]], "o", ms=7, color=nbfigs.LEVEL["spice"], mec=C["surface"], mew=2)
    a.axhline(nbdata.THRESHOLD, color=C["muted"], lw=0.8, ls=(0, (4, 3)))
    a.set_xscale("log")
    a.set_ylim(0, max(15, float(r["max_abs_t"].max()) * 1.1))
    a.set_xlabel("traces")
    a.set_ylabel("max |t|")
    a.set_title("%s, noise %.2gx: max|t| %s at %s traces" % (
        variant, noise_factor, nbfigs.tfmt(r["max_abs_t"][k]), "{:,}".format(int(r["n"][k]))),
        loc="left", fontsize=9.5)
    b.plot(st["time_ns"], r["t"][k], color=nbfigs.LEVEL["spice"], lw=1.0)
    for y in (nbdata.THRESHOLD, -nbdata.THRESHOLD):
        b.axhline(y, color=C["muted"], lw=0.8, ls=(0, (4, 3)))
    b.set_xlabel("ns after the capturing clock edge")
    b.set_ylabel("Welch t")
    b.set_ylim(-15, 15)
    b.set_title("t against time at %s traces" % "{:,}".format(int(r["n"][k])), loc="left", fontsize=9.5)


def static_panel(views=(("N", 0.0), ("N", 1.0), ("DA", 0.0))):
    """A few fixed views, final trace count each (what the sliders show by default)."""
    import matplotlib.pyplot as plt
    import nbfigs
    nbfigs.style()
    fig, axs = plt.subplots(len(views), 2, figsize=(10, 2.7 * len(views)),
                            gridspec_kw={"width_ratios": [1, 1.6]})
    for row, (v, f) in zip(np.atleast_2d(axs), views):
        _plot(row, v, 10 ** 6, f)
    fig.tight_layout()
    return fig


def interactive_panel():
    """Sliders for variant, traces and noise; returns False when ipywidgets is missing."""
    try:
        import ipywidgets as w
        from IPython.display import display
    except ImportError:
        return False
    import matplotlib.pyplot as plt
    import nbfigs
    nbfigs.style()
    n_cp = len(load("N_tvla")["n"])
    variant = w.Dropdown(options=list(CAMPAIGNS), value="N", description="variant")
    n_idx = w.IntSlider(value=n_cp - 1, min=0, max=n_cp - 1, description="checkpoint",
                        continuous_update=False)
    noise = w.FloatSlider(value=0.0, min=0.0, max=3.0, step=0.25, description="noise (x)",
                          continuous_update=False)
    out = w.Output()

    def redraw(*_):
        with out:
            out.clear_output(wait=True)
            fig, axs = plt.subplots(1, 2, figsize=(10, 3.0), gridspec_kw={"width_ratios": [1, 1.6]})
            n_max = len(load(CAMPAIGNS[variant.value])["n"]) - 1
            n_idx.max = n_max
            _plot(axs, variant.value, min(n_idx.value, n_max), noise.value)
            fig.tight_layout()
            plt.show()

    for ctl in (variant, n_idx, noise):
        ctl.observe(redraw, names="value")
    display(w.VBox([w.HBox([variant, n_idx, noise]), out]))
    redraw()
    return True
