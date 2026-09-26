# SPDX-License-Identifier: Apache-2.0
"""Net-level timing before and after layout, from two node runs of analysis/spice_nodes.py.

  bash sim/docker_run.sh python3 analysis/spice_nodes.py --dut build/N --stim runs/kt/stim/M_tvla.npy \
      --rows 40 --chunk 40 --out runs/pex/nodes_N_pre
  (same with --dut build/N_pex --out runs/pex/nodes_N_pex)
  python3 layout/node_timing.py --variant N --pre runs/pex/nodes_N_pre --pex runs/pex/nodes_N_pex \
      --out results/pex/node_timing_N.json

Both runs simulate the same stimulus rows; every net's VDD/2 crossings are compared per clock cycle
(times in ns after the capturing edge, 0 to 3.8 ns; logic nets can only switch after a flip-flop
output does, so every crossing in this span belongs to the evaluation that follows the edge):
  clk_to_q        first crossing of the Q net of a flip-flop that toggles
  last_logic      per cycle, the last crossing of any combinational net
  setup_margin    period minus the last crossing on the D pin of an output flip-flop
  crossings       per cycle, all crossings of the combinational nets, and the "extra" crossings
                  beyond the one a net needs to reach its new value (glitch crossings)
The first latency+1 rows are dropped, as in the campaigns. Host python3 with numpy is enough.
"""
import argparse
import json
import os

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(run):
    e = np.load(os.path.join(REPO, run, "events.npz"))
    return {k: e[k] for k in e.files}


def stats(x):
    x = np.asarray(x, dtype=float)
    if not len(x):
        return None
    return {"n": int(len(x)), "median": round(float(np.median(x)), 4),
            "mean": round(float(x.mean()), 4), "min": round(float(x.min()), 4),
            "max": round(float(x.max()), 4)}


def timing(ev, graph):
    names = [str(n) for n in ev["net_names"]]
    pre, period = float(ev["pre"]), float(ev["period"])
    drop = int(ev["latency"]) + 1
    types = graph["cell_types"]
    driver = {}
    for c in graph["cells"]:
        t = types[c["type"]]
        out = c["pins"]["Q"] if t.get("sequential") else c["pins"][t["output"]]
        driver[out] = (c, t.get("sequential", False))
    d_pins_out = set()                         # D nets of flip-flops that drive output ports
    outs = {q["name"] for q in graph["outputs"]}
    for c in graph["cells"]:
        if types[c["type"]].get("sequential") and c["pins"]["Q"] in outs:
            d_pins_out.add(c["pins"]["D"])
    seq = np.array([names[k] in driver and driver[names[k]][1] for k in range(len(names))])
    comb = np.array([names[k] in driver and not driver[names[k]][1] for k in range(len(names))])
    dnet = np.array([names[k] in d_pins_out for k in range(len(names))])

    t = ev["t_ns"] - pre                       # ns after the capturing edge
    ok = (ev["cycle"] >= drop) & (t >= 0) & (t < period - pre)
    net, cyc, t = ev["net"][ok], ev["cycle"][ok], t[ok]
    cycles = np.unique(cyc)
    clk2q, last, margin, cross, extra = [], [], [], [], []
    for c in cycles:
        m = cyc == c
        n_c, t_c = net[m], t[m]
        for k in np.unique(n_c[seq[n_c]]):
            clk2q.append(t_c[n_c == k].min())
        lc = comb[n_c]
        if lc.any():
            last.append(t_c[lc].max())
        ld = dnet[n_c]
        if ld.any():
            margin.append(period - t_c[ld].max())
        counts = np.bincount(n_c[lc], minlength=len(names))
        cross.append(int(counts.sum()))
        extra.append(int((counts - counts % 2).sum()))
    return {"cycles": int(len(cycles)), "clk_to_q_ns": stats(clk2q),
            "last_logic_crossing_ns": stats(last), "setup_margin_ns": stats(margin),
            "logic_crossings_per_cycle": stats(cross),
            "glitch_crossings_per_cycle": stats(extra)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--variant", required=True)
    ap.add_argument("--pre", required=True)
    ap.add_argument("--pex", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(os.path.join(REPO, "build", a.variant, "graph.json")) as f:
        graph = json.load(f)
    res = {"variant": a.variant, "pre_run": a.pre, "pex_run": a.pex,
           "pre_layout": timing(load(a.pre), graph), "post_layout": timing(load(a.pex), graph)}
    os.makedirs(os.path.dirname(os.path.join(REPO, a.out)), exist_ok=True)
    with open(os.path.join(REPO, a.out), "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
