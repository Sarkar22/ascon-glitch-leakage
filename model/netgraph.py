# SPDX-License-Identifier: Apache-2.0
"""Load a generated gate graph (build/<V>/graph.json) and evaluate it with numpy.

Shared by the zero-delay model (toggle.py), the timing-aware model (glitch.py), the
probing checks (probing.py) and the functional checks.

Cycle convention (same as the SPICE runner in sim/): stimulus row k is on the input
ports during cycle k and is captured by the input flip-flops at the rising edge that
starts "window k"; window k is the evaluation of row k (for latency L the result sits
in the output registers during window k+L). Inside window k the ports change to row
k+1 (the SPICE runner does this at 0.75 T).

Graph.simulate(stim) returns the settled value of every net, shape (n+1, n_nets):
  row 0    the state before window 0: registers 0 (reset), ports at row 0
  row k+1  the settled state at the end of window k: register outputs Q = the D value
           at the end of window k-1, ports at row k+1 (held at the last row at the end)
so the toggles of window k are V[k+1] ^ V[k].

Graph.unrolled(X) evaluates one input row per line with every flip-flop transparent:
each net's value "for that input" (used by the probing checks and functional tests).
"""
import json
import os

import numpy as np


class Graph:
    def __init__(self, path):
        if os.path.isdir(path):
            path = os.path.join(path, "graph.json")
        with open(path) as f:
            g = json.load(f)
        self.g = g
        self.variant = g["variant"]
        self.latency = g["latency"]
        self.inputs = g["inputs"]
        self.outputs = g["outputs"]
        self.net_names = list(g["nets"])
        self.idx = {n: k for k, n in enumerate(self.net_names)}
        self.n_nets = len(self.net_names)
        info = [g["nets"][n] for n in self.net_names]
        self.load_cap = np.array([i["load_cap_fF"] for i in info])
        self.wire_cap = np.array([i["wire_cap_fF"] for i in info])
        self.domain = [i["domain"] for i in info]
        self.kind = ["port" if i["driver"] is None else ("dff" if i["driver"].startswith("ff_") else "comb")
                     for i in info]
        self.input_idx = [self.idx[p["name"]] for p in self.inputs]
        self.output_idx = [self.idx[p["name"]] for p in self.outputs]
        types = g["cell_types"]
        self.cells = g["cells"]
        self.dffs = []           # (d_idx, q_idx, cell)
        comb = []
        for c in self.cells:
            t = types[c["type"]]
            if t["sequential"]:
                self.dffs.append((self.idx[c["pins"]["D"]], self.idx[c["pins"]["Q"]], c))
            else:
                ins = [self.idx[c["pins"][p]] for p in t["inputs"]]
                code = compile(t["function"], c["type"], "eval")
                # truth table indexed by sum(in_k << k) for the event-driven model
                tt = [int(eval(code, {}, {p: (m >> k) & 1 for k, p in enumerate(t["inputs"])}))
                      for m in range(1 << len(ins))]
                comb.append({"name": c["name"], "out": self.idx[c["pins"][t["output"]]], "ins": ins,
                             "pins": t["inputs"], "code": code, "tt": tt, "cell": c})
        self.comb = self._order(comb)

    def _order(self, comb):
        """Topological order of the combinational cells (sources: ports and DFF outputs)."""
        ready = {k for k, kind in enumerate(self.kind) if kind != "comb"}
        order, todo = [], list(comb)
        while todo:
            rest = [c for c in todo if not all(i in ready for i in c["ins"])]
            for c in todo:
                if all(i in ready for i in c["ins"]):
                    order.append(c)
                    ready.add(c["out"])
            if len(rest) == len(todo):
                raise ValueError("combinational loop in graph")
            todo = rest
        return order

    def _eval_cell(self, c, V):
        env = {p: V[:, i] for p, i in zip(c["pins"], c["ins"])}
        V[:, c["out"]] = eval(c["code"], {}, env)

    def unrolled(self, X):
        """X: (n, n_inputs) 0/1 -> (n, n_nets) uint8, flip-flops transparent."""
        X = np.asarray(X, dtype=np.uint8)
        V = np.zeros((len(X), self.n_nets), dtype=np.uint8)
        V[:, self.input_idx] = X
        pending = list(self.comb)
        dffs = list(self.dffs)
        done = set(self.input_idx)
        while pending or dffs:
            progress = False
            for d, q, _ in list(dffs):
                if d in done:
                    V[:, q] = V[:, d]
                    done.add(q)
                    dffs.remove((d, q, _))
                    progress = True
            rest = []
            for c in pending:
                if all(i in done for i in c["ins"]):
                    self._eval_cell(c, V)
                    done.add(c["out"])
                    progress = True
                else:
                    rest.append(c)
            pending = rest
            if not progress:
                raise ValueError("cannot unroll graph (feedback?)")
        return V

    def simulate(self, stim, init=0):
        """Cycle-accurate settled values, shape (n+1, n_nets); see the module docstring."""
        stim = np.asarray(stim, dtype=np.uint8)
        n = len(stim)
        V = np.zeros((n + 1, self.n_nets), dtype=np.uint8)
        V[:, self.input_idx] = np.concatenate([stim, stim[-1:]])
        pending = list(self.comb)
        dffs = list(self.dffs)
        done = set(self.input_idx)
        while pending or dffs:              # pipeline without feedback: stage by stage
            progress = False
            for item in list(dffs):
                d, q, _ = item
                if d in done:
                    V[0, q] = init
                    V[1:, q] = V[:-1, d]
                    done.add(q)
                    dffs.remove(item)
                    progress = True
            rest = []
            for c in pending:
                if all(i in done for i in c["ins"]):
                    self._eval_cell(c, V)
                    done.add(c["out"])
                    progress = True
                else:
                    rest.append(c)
            pending = rest
            if not progress:
                raise ValueError("graph has feedback through registers; not supported")
        return V

    def output_values(self, V):
        """Output-port values (n, n_outputs) of the windows of a simulate() result."""
        return V[1:, self.output_idx]

    def recombine(self, out_bits):
        """(n, n_outputs) output-port bits -> unshared 5-bit values (XOR of the shares)."""
        y = np.zeros(len(out_bits), dtype=np.uint8)
        for k, p in enumerate(self.outputs):
            y ^= out_bits[:, k].astype(np.uint8) << (4 - p["bit"])
        return y
