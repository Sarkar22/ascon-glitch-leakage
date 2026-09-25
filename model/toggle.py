# SPDX-License-Identifier: Apache-2.0
"""Level 1: zero-delay toggle model.

Per clock window, every net settles once (no glitches); the leakage of window k is the
Hamming distance between the settled net values at the end of window k and at the end
of window k-1, summed over nets:
  unweighted     number of nets that toggled
  weighted       sum of load_cap_fF of the toggled nets (fF; x VDD = charge moved)
  weighted_rise  same, rising (0->1) transitions only: the charge drawn from VPWR
Net set: every net in graph.json except CLK, i.e. the cell outputs and the input-port
nets (a port toggling stands in for the input stage of the flip-flop it feeds).
Windows and rows follow model/netgraph.py; rows_from_cycles() builds the per-row traces
of a latency-L design the way the SPICE runner does (row k = windows k .. k+L-1).
The first L+1 rows start from the reset state: drop them when comparing with SPICE.
"""
import numpy as np

from netgraph import Graph


def toggle_traces(graph, stim, per_net=False, include_ports=True):
    """dict of per-window arrays (n,): unweighted, weighted, weighted_rise [, per_net (n, n_nets)]."""
    g = graph if isinstance(graph, Graph) else Graph(graph)
    V = g.simulate(stim)
    old, new = V[:-1], V[1:]
    tog = old ^ new
    rise = tog & new
    keep = np.array([include_ports or k != "port" for k in g.kind])
    cap = np.where(keep, g.load_cap, 0.0)
    out = {"unweighted": (tog * keep).sum(1).astype(np.float64),
           "weighted": tog @ cap,
           "weighted_rise": rise @ cap}
    if per_net:
        out["per_net"] = tog
        out["net_names"] = g.net_names
    return out


def rows_from_cycles(per_window, latency):
    """Per-window traces (n, ...) -> per-row traces (n-L+1, L*...): row k = windows k..k+L-1."""
    x = np.asarray(per_window)
    if x.ndim == 1:
        x = x[:, None]
    n = len(x) - latency + 1
    return np.concatenate([x[j:j + n] for j in range(latency)], axis=1)


if __name__ == "__main__":
    import sys
    from stimulus import make_stimulus
    d = sys.argv[1] if len(sys.argv) > 1 else "build/N"
    stim, meta = make_stimulus(d, "random", 5, 0)
    t = toggle_traces(d, stim)
    for k in range(5):
        print("window %d: toggles %3d  weighted %.1f fF  rising %.1f fF"
              % (k, t["unweighted"][k], t["weighted"][k], t["weighted_rise"][k]))
