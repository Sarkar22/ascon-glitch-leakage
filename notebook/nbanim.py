# SPDX-License-Identifier: Apache-2.0
"""One input change, animated: which nets switch when in N and in DA (level-2 model).

The events come from the timing-aware gate-level model (model/glitch.py: transport delays
from the sky130 tt Liberty, every transition counted) run on the generated netlists. They are
not SPICE waveforms; the pre-layout SPICE cells switch about 0.2 ns earlier (notebook
section 4.6). One stimulus row is shown: row ANIM_ROW of the fixed-vs-random stimulus used
by every SPICE campaign of N, D and DA (model/stimulus.py, mode tvla, seed 202).

Each net belongs to one pipeline stage, its register depth d (1 = driven from the input
registers, 2 = from the next register rank, ...). The evaluation of one row happens in
clock window row + d - 1 for stage d, so N (one stage) computes everything in cycle 1,
while DA computes its DOM products in cycle 1 and integrates them in cycle 2. Only the
row's own activity is shown; the other rows in the pipeline are left out.

  compute_events(variant)   live: needs the generated netlist build/<V>/graph.json
  load_events()             cached: media/glitch_events.json (written by build_cache())
  draw(ev, t_now)           one frame (t_now in ns after the first capturing edge)
  save_gif(ev, path)        the animation (matplotlib FuncAnimation + Pillow)
"""
import json
import os
import sys

import nbdata

ANIM_ROW = 185
STIM = dict(mode="tvla", n=20000, seed=202)       # = runs/kt/stim/M_tvla.npy
TIMING = dict(period_ps=4000.0, pre_ps=200.0, t_in_frac=0.75, bin_ps=10.0)
PERIOD_NS = 4.0
CACHE = os.path.join(nbdata.HERE, "media", "glitch_events.json")      # ships with the GIF

# the path of AND t1 = ~x1 & x2' (x2' = x2 ^ x1) through share 0 of the S-box output y1
PATHS = {
    "N": [("xs0_1_q", "x1 share 0 (a0), reg"),
          ("xs1_1_q", "x1 share 1, reg"),
          ("xs1_2_q", "x2 share 1, reg"),
          ("as1_2", "b1 = x2 ^ x1, share 1"),
          ("m01_1", "m01 = ~a0 & b1"),
          ("r_1_q", "r1 (fresh random), reg"),
          ("p01_1", "p01 = m01 ^ r1"),
          ("p00_1", "p00 = ~a0 & b0"),
          ("ts0_1", "t1 share 0 = p00 ^ p01"),
          ("bs0_0", "S-box XOR bs0_0"),
          ("ys0_1_d", "y1 share 0, output reg D"),
          ("ys0_1", "y1 share 0, output reg Q")],
    "DA": [("as0_1_q", "x1 share 0 (a0), reg"),
           ("as1_2_q", "b1 = x2 ^ x1, share 1, reg"),
           ("m01_1", "m01 = ~a0 & b1"),
           ("r_1_q", "r1 (fresh random), reg"),
           ("p01_1", "p01 = m01 ^ r1"),
           ("p00_1", "p00 = ~a0 & b0"),
           ("p01_1_q", "p01, barrier reg"),
           ("p00_1_q", "p00, barrier reg"),
           ("ts0_1", "t1 share 0 = p00 ^ p01"),
           ("bs0_0", "S-box XOR bs0_0"),
           ("ys0_1_d", "y1 share 0, output reg D")],
}
TITLES = {"N": "N, naive DOM (no barrier)",
          "DA": "DA, DOM barrier after the affine layer"}
DOMAIN_LABEL = {"s0": "share 0", "s1": "share 1", "cross": "both domains", "r": "fresh random"}


# ---------------------------------------------------------------- events (live or cached)

def _model_path():
    p = nbdata.path("model")
    if p not in sys.path:
        sys.path.insert(0, p)


def register_depth(g):
    """Register depth of every net: 0 for input ports, +1 through each flip-flop."""
    drv = {c["out"]: c["ins"] for c in g.comb}
    dq = {q: d for d, q, _ in g.dffs}
    memo = {}

    def depth(k):
        if k not in memo:
            if g.kind[k] == "port":
                memo[k] = 0
            elif k in dq:
                memo[k] = depth(dq[k]) + 1
            else:
                memo[k] = max(depth(i) for i in drv[k])
        return memo[k]
    return [depth(k) for k in range(g.n_nets)]


def compute_events(variant, row=ANIM_ROW):
    """Level-2 events of one stimulus row for every net (live; needs build/<V>/)."""
    _model_path()
    from glitch import TimingModel
    from netgraph import Graph
    from stimulus import make_stimulus
    dut = nbdata.path("build", variant)
    g = Graph(dut)
    stim, meta = make_stimulus(dut, STIM["mode"], STIM["n"], STIM["seed"])
    m = TimingModel(g, **TIMING)
    dep = register_depth(g)
    V = g.simulate(stim[:row + max(dep) + 2]).tolist()
    windows = {}
    nets = {}
    for i, name in enumerate(g.net_names):
        d = dep[i]
        if d == 0:
            continue
        w = row + d - 1                    # the clock window in which this stage works on row
        if w not in windows:
            windows[w] = m.window_events(V[w], V[w + 1])
        wave = windows[w][i] or []
        shift = (d - 1) * PERIOD_NS
        nets[name] = {"domain": g.domain[i], "depth": d, "kind": g.kind[i],
                      "v0": V[w][i], "v1": V[w + 1][i],
                      "events": [[round(t / 1000.0 + shift, 4), v] for t, v in wave]}
    return {"variant": variant, "row": row, "x": int(meta["x"][row]),
            "label": int(meta["label"][row]), "nets": nets}


def build_cache(variants=("N", "DA"), row=ANIM_ROW):
    ev = {"source": "level-2 model (model/glitch.py), sky130_fd_sc_hd tt Liberty delays, "
                    "stimulus mode %(mode)s seed %(seed)d" % STIM,
          "row": row, "variants": {v: compute_events(v, row) for v in variants}}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w") as f:
        json.dump(ev, f, indent=0)
        f.write("\n")
    return CACHE


def load_events():
    with open(CACHE) as f:
        return json.load(f)


def events(mode="cached", row=ANIM_ROW):
    """Live mode with generated netlists: recompute; otherwise read the cached events."""
    if mode == "live" and os.path.exists(nbdata.path("build", "N", "graph.json")):
        return {"row": row, "variants": {v: compute_events(v, row) for v in ("N", "DA")}}
    return load_events()


def counts(net, t_now=None):
    """(transitions, glitch transitions) of a net up to t_now. A glitch transition is any
    transition beyond the one settled toggle (a net that ends where it started and moved
    in between glitched with all its transitions)."""
    ev = [e for e in net["events"] if t_now is None or e[0] <= t_now]
    toggle = 1 if (net["v0"] != net["v1"]) else 0
    n_all = len(net["events"])
    extra = max(0, n_all - toggle)
    if t_now is None or len(ev) == n_all:
        return len(ev), extra
    return len(ev), min(extra, len(ev))


def totals(ev_v, t_now=None, kinds=("comb",)):
    """Transitions and glitch transitions over all combinational nets of one variant."""
    n = g = 0
    for net in ev_v["nets"].values():
        if net["kind"] in kinds:
            a, b = counts(net, t_now)
            n += a
            g += b
    return n, g


# ---------------------------------------------------------------- drawing

def _colors():
    import nbfigs
    c = nbfigs.COLORS
    return {"s0": c["series1"], "s1": c["series2"], "cross": c["series3"], "r": c["muted"]}


# the two panels' time windows, in ns after the first capturing edge
WINDOWS = ((-0.2, 1.8), (PERIOD_NS - 0.2, PERIOD_NS + 1.8))


def caption(t_now):
    """One line that says what happens at this moment of the animation."""
    if t_now < 0.3:
        return "Clock edge: the input registers start to switch (clock-to-Q)."
    if t_now < 0.62:
        return ("N: b1 = x2 ^ x1 is computed after the registers, so it arrives late and glitches; "
                "DA: b1 comes straight from a register.")
    if t_now < 0.9:
        return ("N: m01 = ~a0 & b1 glitches while it sees both shares of x1. "
                "DA: p01 glitches too (r1 and m01 skew), but its cone holds no variable twice.")
    if t_now < 1.8:
        return ("N: the glitch runs on through three XOR levels to the output register. "
                "DA: glitches end at the barrier flip-flops' D pins.")
    if t_now < PERIOD_NS:
        return "Waiting for the next clock edge."
    if t_now < PERIOD_NS + 0.3:
        return "Second edge: N's result is captured; DA's barrier registers release the products."
    return ("DA, cycle 2: integration starts from registered, refreshed products; the glitches "
            "left here (y1 D pin) see no variable twice.")


def draw(ev, t_now, fig=None):
    """Draw the state at t_now (ns after the first edge). Returns the figure."""
    import matplotlib.pyplot as plt
    import nbfigs
    nbfigs.style()
    col = _colors()
    C = nbfigs.COLORS
    if fig is None:
        fig = plt.figure(figsize=(10.0, 7.4))
    fig.clf()
    variants = [v for v in ("N", "DA") if v in ev["variants"]]
    heights = [len(PATHS[v]) + 1.5 for v in variants]
    gs = fig.add_gridspec(len(variants), 2, height_ratios=heights, width_ratios=[1, 1],
                          left=0.22, right=0.985, top=0.875, bottom=0.1, hspace=0.35, wspace=0.05)
    for r, v in enumerate(variants):
        nets = ev["variants"][v]["nets"]
        rows = PATHS[v]
        n_rows = len(rows)
        for c, (a, b) in enumerate(WINDOWS):
            ax = fig.add_subplot(gs[r, c])
            ax.set_xlim(a, b)
            ax.set_ylim(n_rows - 0.4, -1.2)
            ax.grid(False)
            ax.spines["left"].set_visible(False)
            ax.set_yticks([])
            ticks = [a + 0.2 + k * 0.4 for k in range(5)]
            ax.set_xticks(ticks)
            ax.set_xticklabels(["%.1f" % (x - c * PERIOD_NS) for x in ticks])
            if r == len(variants) - 1:
                ax.set_xlabel("ns after clock edge %d" % (c + 1))
            ax.axvline(a + 0.2, color=C["axis"], lw=0.8)            # the capturing edge
            active = a <= t_now <= b
            for k, (name, label) in enumerate(rows):
                net = nets[name]
                y = k
                if c == 0:
                    ax.text(a - 0.03 * (b - a), y, label, ha="right", va="center", fontsize=7.5,
                            color=C["ink"], clip_on=False)
                    ax.plot([a - 0.018 * (b - a)], [y], marker="s", ms=5, color=col[net["domain"]],
                            clip_on=False)
                _wave(ax, net, y, a, b, min(t_now, b), col[net["domain"]], C)
            if v == "DA":
                yb = 5.5                                              # between p00_1 and p01_1_q
                ax.axhline(yb, color=C["ink2"], lw=1.6)
                if c == 1:
                    ax.text(b - 0.03, yb - 0.08, "DOM register barrier", ha="right", va="bottom",
                            fontsize=7.5, color=C["ink2"],
                            bbox=dict(boxstyle="square,pad=0.1", fc=C["surface"], ec="none"))
            if active:
                ax.axvline(t_now, color=C["ink"], lw=0.9, alpha=0.7)
            if c == 0:
                ax.set_title(TITLES[v], loc="left", fontsize=9.5)
            else:
                n, g = totals(ev["variants"][v], t_now)
                ax.set_title("all nets so far: %d transitions, %d of them glitch transitions" % (n, g),
                             loc="right", fontsize=8.5, color=C["ink2"], fontweight="normal")
    ex = ev["variants"][variants[0]]
    fig.text(0.02, 0.965, "One input change, level-2 event model (sky130 tt Liberty delays): "
             "stimulus row %d, %s class, x = 0x%02X" %
             (ex["row"], "fixed" if ex["label"] == 0 else "random", ex["x"]),
             fontsize=10, fontweight="bold", color=C["ink"])
    handles = [plt.Line2D([], [], color=col[d], lw=2, label=DOMAIN_LABEL[d]) for d in ("s0", "s1", "cross", "r")]
    handles.append(plt.matplotlib.patches.Patch(color=C["glitch"], label="glitch pulse"))
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.215, 0.955), ncol=5, fontsize=8)
    fig.text(0.02, 0.025, caption(t_now), fontsize=9, color=C["ink"])
    return fig


def _wave(ax, net, y, a, b, t_end, color, C):
    """Digital waveform of one net from a to t_end, glitch pulses shaded."""
    h = 0.32
    ev = net["events"]
    toggled = net["v0"] != net["v1"]
    # shade the span of extra transitions (the part of the waveform that is a glitch)
    if len(ev) > (1 if toggled else 0):
        t0 = ev[0][0]
        t1 = ev[-2][0] if toggled else ev[-1][0]
        if t1 > t0 and t0 <= t_end:
            ax.fill_between([max(t0, a), min(t1, t_end)], y - 0.45, y + 0.45, color=C["glitch"],
                            lw=0, zorder=0)
    if t_end < a:
        return
    v_a = net["v0"]                          # the value when this panel's window opens
    for t, v in ev:
        if t <= a:
            v_a = v
    xs, ys = [a], [v_a]
    for t, v in ev:
        if t <= a:
            continue
        if t > t_end:
            break
        xs += [t, t]
        ys += [ys[-1], v]
    xs.append(t_end)
    ys.append(ys[-1])
    ax.plot(xs, [y + h - 2 * h * v for v in ys], color=color, lw=1.4, solid_joinstyle="miter")


def frame_times(step=0.04, hold=8):
    ts = []
    for a, b in WINDOWS:
        n = int(round((b - a) / step))
        ts += [a + k * step for k in range(n + 1)]
    return ts + [ts[-1]] * hold


def save_gif(ev, out, dpi=80, step=0.04, fps=12):
    """Write the animation as an animated GIF (Pillow; no ffmpeg needed)."""
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter
    fig = plt.figure(figsize=(10.0, 7.4))
    ts = frame_times(step)
    anim = FuncAnimation(fig, lambda k: draw(ev, ts[k], fig), frames=len(ts), blit=False)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    anim.save(out, writer=PillowWriter(fps=fps), dpi=dpi)
    plt.close(fig)
    return out


if __name__ == "__main__":
    # python3 notebook/nbanim.py   (needs the generated netlists in build/; host numpy is enough)
    print("wrote", os.path.relpath(build_cache(), os.getcwd()))
