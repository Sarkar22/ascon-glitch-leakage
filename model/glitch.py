# SPDX-License-Identifier: Apache-2.0
"""Level 2: timing-aware gate-level model (transport delays, every transition counted).

For each clock window the settled values at its start and end come from the zero-delay
evaluation (netgraph.Graph.simulate). Inside the window:
  * every flip-flop output changes to its new value at its clock-to-Q delay (rise or
    fall, from the tt Liberty at the net's estimated load; stored in graph.json);
  * the input ports change to the next row at t_in_frac * period (SPICE runner: 0.75 T);
  * each combinational cell reacts to every input event after the delay of that input
    pin's arc for the new output edge (Liberty cell_rise / cell_fall at the driver's
    slew and the net load, averaged over the arc's timing groups). Transport delay: an
    event scheduled at time T cancels the cell's pending output events at >= T, so pulses
    of any width survive (min_pulse_ps > 0 drops output pulses narrower than that, a rough
    inertial filter). Simultaneous input events are applied one at a time, in pin order.
Every transition on every net (glitches included) is binned in time. Times are relative
to the capturing clock edge; a window spans [-pre_ps, period_ps - pre_ps) like the SPICE
runner's (defaults: period 5 ns, pre 0.2 ns, 10 ps bins; params_from_manifest() takes them
from a SPICE run's manifest.json so both use the same grid). Per window it returns
  unweighted     transitions per bin
  weighted       sum of load_cap_fF of the transitioning nets per bin (fF)
  weighted_rise  same for rising transitions only (charge drawn from VPWR)
and optionally per_net transition counts (n, n_nets). Rows of a latency-2 design:
toggle.rows_from_cycles(). Clock-tree and flip-flop-internal activity is not modelled.
"""
import json
import multiprocessing

import numpy as np

from netgraph import Graph

DEFAULTS = dict(period_ps=5000.0, pre_ps=200.0, t_in_frac=0.75, bin_ps=10.0, min_pulse_ps=0.0)


def params_from_manifest(path):
    """Timing parameters of a SPICE run (sim/spice_campaign.py manifest.json, times in ns)."""
    with open(path) as f:
        p = json.load(f)["params"]
    return dict(period_ps=1000.0 * p["period"], pre_ps=1000.0 * p["pre"], t_in_frac=p["t_in"],
                bin_ps=1000.0 * p["dt"])


class TimingModel:
    def __init__(self, graph, **params):
        self.graph = graph if isinstance(graph, Graph) else Graph(graph)
        self.p = dict(DEFAULTS, **params)
        g = self.graph
        self.n_bins = int(round(self.p["period_ps"] / self.p["bin_ps"]))
        self.dffs = []
        for d, q, c in g.dffs:
            dl = c["delay_ps"]["CLK"]
            self.dffs.append((q, dl["rise"], dl["fall"]))
        self.comb = []
        for c in g.comb:
            dl = c["cell"]["delay_ps"]
            self.comb.append((c["out"], tuple(c["ins"]), tuple(c["tt"]),
                              tuple(dl[p]["rise"] for p in c["pins"]),
                              tuple(dl[p]["fall"] for p in c["pins"])))
        self.ports = list(g.input_idx)

    def window_events(self, v0, v1):
        """Transitions of one window: list per net (None or [(t_ps, value), ...])."""
        waves = [None] * self.graph.n_nets
        for q, dr, df in self.dffs:
            if v0[q] != v1[q]:
                waves[q] = [(dr if v1[q] else df, v1[q])]
        t_in = self.p["t_in_frac"] * self.p["period_ps"]
        for i in self.ports:
            if v0[i] != v1[i]:
                waves[i] = [(t_in, v1[i])]
        min_pulse = self.p["min_pulse_ps"]
        for out_i, ins, tt, rise, fall in self.comb:
            ev = []
            for k, i in enumerate(ins):
                w = waves[i]
                if w:
                    ev.extend((t, k, v) for t, v in w)
            if not ev:
                continue
            ev.sort()
            code = 0
            for k, i in enumerate(ins):
                code |= v0[i] << k
            last0 = v0[out_i]
            out = []
            for t, k, v in ev:
                code = (code & ~(1 << k)) | (v << k)
                nv = tt[code]
                T = t + (rise[k] if nv else fall[k])
                while out and out[-1][0] >= T:
                    out.pop()
                if nv != (out[-1][1] if out else last0):
                    out.append((T, nv))
            if min_pulse > 0 and len(out) > 1:
                kept = []
                for T, nv in out:
                    if kept and T - kept[-1][0] < min_pulse:
                        kept.pop()                  # drop the pulse (both edges)
                    else:
                        kept.append((T, nv))
                out = kept
            if out:
                waves[out_i] = out
        return waves

    def traces(self, stim, per_net=False, include_ports=True, check=True):
        V = self.graph.simulate(stim)
        return self._traces_from_states(V, per_net, include_ports, check)

    def _traces_from_states(self, V, per_net, include_ports, check):
        g = self.graph
        n = len(V) - 1
        nb, pre, bw = self.n_bins, self.p["pre_ps"], self.p["bin_ps"]
        cap = g.load_cap
        keep = [include_ports or k != "port" for k in g.kind]
        unw = np.zeros((n, nb))
        wt = np.zeros((n, nb))
        wr = np.zeros((n, nb))
        pn = np.zeros((n, g.n_nets), dtype=np.int16) if per_net else None
        late = 0
        rows = V.tolist()
        for k in range(n):
            v0, v1 = rows[k], rows[k + 1]
            waves = self.window_events(v0, v1)
            for i, w in enumerate(waves):
                if not w:
                    continue
                if check and w[-1][1] != v1[i]:
                    raise AssertionError("net %s does not settle to its zero-delay value" % g.net_names[i])
                if per_net:
                    pn[k, i] = len(w)
                if not keep[i]:
                    continue
                c = cap[i]
                for t, v in w:
                    b = int((t + pre) // bw)
                    if b >= nb:
                        late += 1
                        b = nb - 1
                    unw[k, b] += 1
                    wt[k, b] += c
                    if v:
                        wr[k, b] += c
        out = {"unweighted": unw, "weighted": wt, "weighted_rise": wr, "late_events": late,
               "bin_ps": bw, "pre_ps": pre}
        if per_net:
            out["per_net"] = pn
            out["net_names"] = g.net_names
        return out


def _chunk(args):
    path, params, V, per_net, include_ports = args
    return TimingModel(path, **params)._traces_from_states(V, per_net, include_ports, True)


def glitch_traces(graph_path, stim, jobs=1, per_net=False, include_ports=True, chunk=5000, **params):
    """Level-2 traces for a whole stimulus, optionally split over `jobs` processes."""
    m = TimingModel(graph_path, **params)
    if jobs <= 1:
        return m.traces(stim, per_net, include_ports)
    V = m.graph.simulate(stim)
    n = len(V) - 1
    parts = [(graph_path, m.p, V[s:min(s + chunk, n) + 1], per_net, include_ports) for s in range(0, n, chunk)]
    with multiprocessing.Pool(jobs) as pool:
        res = pool.map(_chunk, parts)
    out = {k: np.concatenate([r[k] for r in res]) for k in ("unweighted", "weighted", "weighted_rise")}
    out["late_events"] = sum(r["late_events"] for r in res)
    out.update(bin_ps=m.p["bin_ps"], pre_ps=m.p["pre_ps"])
    if per_net:
        out["per_net"] = np.concatenate([r["per_net"] for r in res])
        out["net_names"] = m.graph.net_names
    return out


if __name__ == "__main__":
    import sys
    import time
    from stimulus import make_stimulus
    d = sys.argv[1] if len(sys.argv) > 1 else "build/N"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    stim, _ = make_stimulus(d, "random", n, 0)
    t0 = time.time()
    r = glitch_traces(d, stim, per_net=True)
    dt = time.time() - t0
    print("%s: %d windows in %.2f s (%.0f us/window); transitions/window %.1f; late events %d"
          % (d, n, dt, 1e6 * dt / n, r["unweighted"].sum() / n, r["late_events"]))
    act = r["weighted"].sum(0)
    nz = np.nonzero(act)[0]
    print("activity spans %.0f .. %.0f ps after the edge" % (nz[0] * r["bin_ps"] - r["pre_ps"],
                                                             (nz[-1] + 1) * r["bin_ps"] - r["pre_ps"]))
