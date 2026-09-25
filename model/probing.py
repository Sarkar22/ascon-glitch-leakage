# SPDX-License-Identifier: Apache-2.0
"""Exact first-order probing checks of a masked netlist, by exhaustive enumeration.

All 32 x 32 x 32 combinations of unshared input x, mask (= share 1) and fresh bits r are
evaluated with the flip-flops transparent (netgraph.Graph.unrolled: every net's value for
that input). A probe on one net is secure when what it observes is independent of x:
  (a) value model: the net's value. Check: P(net = 1 | x) equal for all 32 x.
  (b) glitch-extended model (robust probing as in SILVER / PROLEAD): a probe on a net
      observes every stable signal in its combinational fan-in cone, i.e. the register
      outputs and input ports reached backwards without crossing a register. Check: the
      joint distribution of those signals is equal for all 32 x.
The exact distributions are compared (no sampling, no threshold).
For a failing glitch-extended probe the report lists which x bits have both shares among
the input ports that feed the cone ("both_shares_of"), which usually names the leak.

python3 model/probing.py build/N [build/D ...]    prints per-net results and writes
results/probing/<V>.json (use --no-write to skip).
"""
import json
import os
import sys

import numpy as np

from netgraph import Graph
from stimulus import encode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cone_sources(g, net):
    """Stable signals (input ports and register outputs) in the combinational fan-in of net."""
    drv = {c["out"]: c["ins"] for c in g.comb}
    seen, todo, src = set(), [net], set()
    while todo:
        k = todo.pop()
        if k in seen:
            continue
        seen.add(k)
        if k in drv:
            todo.extend(drv[k])
        else:
            src.add(k)
    return sorted(src)


def port_fanin(g, nets):
    """Input ports in the full (through registers) fan-in of a set of nets."""
    drv = {c["out"]: c["ins"] for c in g.comb}
    drv.update({q: [d] for d, q, _ in g.dffs})
    seen, todo = set(), list(nets)
    while todo:
        k = todo.pop()
        if k not in seen:
            seen.add(k)
            todo.extend(drv.get(k, []))
    return {k for k in seen if g.kind[k] == "port"}


def independent_of_x(x, code, n_codes):
    """True when the distribution of code (ints < n_codes) is the same for every x."""
    h = np.bincount(x.astype(np.int64) * n_codes + code, minlength=32 * n_codes).reshape(32, n_codes)
    return bool((h == h[0]).all()), h


def check(graph):
    """Per-net results of both probing models, as a list of dicts (net order of graph.json)."""
    g = graph if isinstance(graph, Graph) else Graph(graph)
    grid = np.arange(32 ** 3)
    x, mask, r = grid >> 10, (grid >> 5) & 31, grid & 31
    ports = {"variant": g.variant, "inputs": g.inputs}
    V = g.unrolled(encode(ports, x, mask, r)).astype(np.int64)
    port_info = {g.idx[p["name"]]: p for p in g.inputs}
    res = []
    for k, name in enumerate(g.net_names):
        val_ok, h = independent_of_x(x, V[:, k], 2)
        p1 = h[:, 1] / h.sum(1)
        src = cone_sources(g, k)
        code = np.zeros(len(x), dtype=np.int64)
        for j, s in enumerate(src):
            code |= V[:, s] << j
        gl_ok, _ = independent_of_x(x, code, 1 << len(src))
        pf = [port_info[p] for p in port_fanin(g, src)]
        both = sorted({p["bit"] for p in pf if p["role"] == "share0"} &
                      {p["bit"] for p in pf if p["role"] == "share1"})
        res.append({"net": name, "kind": g.kind[k], "domain": g.domain[k],
                    "value_ok": val_ok, "p1_min": float(p1.min()), "p1_max": float(p1.max()),
                    "glitch_ok": gl_ok, "cone": [g.net_names[s] for s in src],
                    "both_shares_of": both})
    return res


def report(graph, write=True):
    g = graph if isinstance(graph, Graph) else Graph(graph)
    res = check(g)
    bad_v = [r["net"] for r in res if not r["value_ok"]]
    bad_g = [r for r in res if not r["glitch_ok"]]
    print("== %s: %d nets; value model: %d fail; glitch-extended model: %d fail"
          % (g.variant, len(res), len(bad_v), len(bad_g)))
    if bad_v:
        print("   value-model failures: " + " ".join(bad_v))
    for r in bad_g:
        print("   glitch-extended FAIL %-10s %-5s cone %2d signals, both shares of x%s: %s"
              % (r["net"], r["kind"], len(r["cone"]), ",x".join(map(str, r["both_shares_of"])),
                 " ".join(r["cone"])))
    if write:
        out = os.path.join(ROOT, "results", "probing")
        os.makedirs(out, exist_ok=True)
        path = os.path.join(out, "%s.json" % g.variant)
        with open(path, "w") as fp:
            json.dump({"variant": g.variant, "n_nets": len(res), "value_fail": bad_v,
                       "glitch_fail": [r["net"] for r in bad_g], "nets": res}, fp, indent=1)
        print("   wrote " + os.path.relpath(path, ROOT))
    return res


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for d in args or [os.path.join(ROOT, "build", v) for v in ("N", "D", "DA")]:
        report(d, write="--no-write" not in sys.argv)
