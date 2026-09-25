# SPDX-License-Identifier: Apache-2.0
"""Sanity checks of a SPICE campaign run against a zero-delay simulation of the same netlist.

1. Function: the output ports recorded by the run (--save-outputs) equal the registered outputs
   of a cycle-accurate zero-delay simulation of graph.json driven by the same stimulus.
2. Data dependence: per-window charge correlates with the Hamming-distance (toggle count)
   estimate of the activity in that window: combinational nets, flip-flop outputs, and the
   input-port changes that happen mid-window.
3. Alignment: mean supply current vs time within the window, and per time bin the correlation
   of the current with the evaluation toggles and with the input-port toggles. Evaluation
   activity must start right after the capturing edge (t = pre), input-port activity at
   pre + t_in*T.

  bash sim/docker_run.sh python3 sim/sanity_check.py --run runs/sanity_U --stim s.npy \
      [--dut sim/mock/U] [--plot runs/sanity_U/sanity.png]
Prints a report and writes <run>/sanity.json.
"""
import argparse
import json
import os
import re

import numpy as np

import spice_campaign as sc

LIB = "sky130_fd_sc_hd__"
# Boolean function of each supported cell (base name without library prefix and drive size).
FUNCS = {
    "inv": lambda p: 1 - p["A"], "clkinv": lambda p: 1 - p["A"],
    "buf": lambda p: p["A"], "clkbuf": lambda p: p["A"], "dlygate4sd3": lambda p: p["A"],
    "and2": lambda p: p["A"] & p["B"], "and2b": lambda p: (1 - p["A_N"]) & p["B"],
    "nand2": lambda p: 1 - (p["A"] & p["B"]), "nand2b": lambda p: 1 - ((1 - p["A_N"]) & p["B"]),
    "or2": lambda p: p["A"] | p["B"], "or2b": lambda p: p["A"] | (1 - p["B_N"]),
    "nor2": lambda p: 1 - (p["A"] | p["B"]), "nor2b": lambda p: (1 - (p["A"] | (1 - p["B_N"]))),
    "xor2": lambda p: p["A"] ^ p["B"], "xnor2": lambda p: 1 - (p["A"] ^ p["B"]),
    "xor3": lambda p: p["A"] ^ p["B"] ^ p["C"], "xnor3": lambda p: 1 - (p["A"] ^ p["B"] ^ p["C"]),
    "and3": lambda p: p["A"] & p["B"] & p["C"], "nand3": lambda p: 1 - (p["A"] & p["B"] & p["C"]),
    "or3": lambda p: p["A"] | p["B"] | p["C"], "nor3": lambda p: 1 - (p["A"] | p["B"] | p["C"]),
    "a21oi": lambda p: 1 - ((p["A1"] & p["A2"]) | p["B1"]),
    "o21ai": lambda p: 1 - ((p["A1"] | p["A2"]) & p["B1"]),
    "a21o": lambda p: (p["A1"] & p["A2"]) | p["B1"],
    "o21a": lambda p: (p["A1"] | p["A2"]) & p["B1"],
    "mux2": lambda p: p["A1"] if p["S"] else p["A0"],
}
OUTPUT_PINS = ("X", "Y", "Q", "HI", "LO")


def base_type(t):
    t = t[len(LIB):] if t.startswith(LIB) else t
    return re.sub(r"_\d+$", "", t)


class Graph:
    """Zero-delay model of graph.json: flip-flops (dfxtp) and combinational cells."""

    def __init__(self, path):
        with open(path) as f:
            g = json.load(f)
        self.dffs, comb, driver = [], [], {}
        for c in g["cells"]:
            pins = c.get("pins") or c.get("conn") or c.get("connections")
            typ = base_type(c["type"])
            outs = {k: v for k, v in pins.items() if k in OUTPUT_PINS}
            ins = {k: v for k, v in pins.items() if k not in OUTPUT_PINS and
                   k not in ("VPWR", "VGND", "VPB", "VNB", "CLK")}
            if typ.startswith("dfxtp"):
                self.dffs.append((ins["D"], outs["Q"]))
            elif typ == "conb":
                continue
            elif typ in FUNCS:
                comb.append((typ, ins, outs[[k for k in outs][0]]))
            else:
                raise ValueError("cell type %s not supported by the zero-delay model" % c["type"])
            for net in outs.values():
                driver[net] = c["name"]
        # topological order of the combinational cells
        known = {q for _, q in self.dffs}
        self.comb = []
        while comb:
            rest = [c for c in comb if not all(n in known or n not in driver
                                               for n in c[1].values())]
            ready = [c for c in comb if c not in rest]
            if not ready:
                raise ValueError("combinational loop")
            self.comb += ready
            known |= {c[2] for c in ready}
            comb = rest
        self.nets = [q for _, q in self.dffs] + [c[2] for c in self.comb]
        fanout = {}
        for _, ins, _ in self.comb:
            for n in ins.values():
                fanout[n] = fanout.get(n, 0) + 1
        for d, _ in self.dffs:
            fanout[d] = fanout.get(d, 0) + 1
        self.fanout = np.array([fanout.get(n, 0) for n in self.nets])
        self.is_q = np.array([k < len(self.dffs) for k in range(len(self.nets))])

    def settle(self, v):
        for typ, ins, out in self.comb:
            v[out] = FUNCS[typ]({k: v[n] for k, n in ins.items()})
        return v

    def run(self, port_names, rows):
        """Net values after each rising edge: V[c] = state after edge c (row c-1 captured)."""
        v = {n: 0 for n in list(self.nets) + list(port_names)}
        out = np.zeros((len(rows) + 1, len(self.nets)), dtype=np.uint8)
        self.settle(v)
        out[0] = [v[n] for n in self.nets]
        for c, row in enumerate(rows):
            v.update(zip(port_names, (int(b) for b in row)))
            self.settle(v)                            # logic in front of input registers
            nxt = {q: v[d] for d, q in self.dffs}     # edge c+1 captures row c
            v.update(nxt)
            self.settle(v)
            out[c + 1] = [v[n] for n in self.nets]
        return out


def corr(x, y):
    x, y = x - x.mean(), y - y.mean()
    den = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / den) if den > 0 else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--stim", required=True)
    ap.add_argument("--dut", help="default: the dut recorded in the run manifest")
    ap.add_argument("--plot", help="PNG path (needs matplotlib)")
    a = ap.parse_args()
    with open(os.path.join(a.run, "manifest.json")) as f:
        man = json.load(f)
    dut = a.dut or man["dut"]
    ports = sc.load_dut(dut)
    p, lat = man["params"], man["latency"]
    stim = np.load(a.stim)
    traces = np.load(os.path.join(a.run, "traces.npy")).astype(float)
    charge = np.load(os.path.join(a.run, "charge.npy"))
    ext = sc.extend_stimulus(stim, p, lat)
    g = Graph(os.path.join(dut, "graph.json"))
    V = g.run([q["name"] for q in ports["inputs"]], ext)
    w = p["warmup"]
    n = len(stim)
    rep = {"run": a.run, "rows": n}

    # 1. function: output ports sampled after edge r+1+lat hold V[r+1+lat] at the output nets
    outp = os.path.join(a.run, "outputs.npy")
    if os.path.exists(outp):
        got = np.load(outp)
        idx = [g.nets.index(q["name"]) for q in ports["outputs"]]
        exp = V[w + np.arange(n) + 1 + lat][:, idx]
        rep["output_match_fraction"] = float((got == exp).all(1).mean())

    # 2. activity estimates per window (edges w+k+1 .. w+k+lat, port changes in those cycles)
    tog = (V[1:] != V[:-1])                  # tog[c] = toggles at edge c+1
    port_tog = (ext[1:] != ext[:-1]).sum(1)  # port_tog[c] = row c+1 vs row c (mid cycle c+1)
    rows = w + np.arange(n)
    hd_comb = sum(tog[rows + j][:, ~g.is_q].sum(1) for j in range(lat))
    hd_q = sum(tog[rows + j][:, g.is_q].sum(1) for j in range(lat))
    hd_w = sum((tog[rows + j] * (1 + g.fanout)).sum(1) for j in range(lat))
    hd_port = sum(port_tog[rows + j] for j in range(lat))
    X = np.column_stack([np.ones(n), hd_comb, hd_q, hd_port])
    coef, *_ = np.linalg.lstsq(X, charge, rcond=None)
    rep.update({
        "charge_fC_mean": float(charge.mean()), "charge_fC_std": float(charge.std()),
        "corr_charge_hd_all_nets": corr(charge, hd_comb + hd_q),
        "corr_charge_hd_comb": corr(charge, hd_comb), "corr_charge_hd_dff_q": corr(charge, hd_q),
        "corr_charge_hd_fanout_weighted": corr(charge, hd_w),
        "corr_charge_hd_ports": corr(charge, hd_port),
        "fit_R_comb_q_ports": corr(charge, X @ coef),
        "fit_fC_per_toggle": {"offset": coef[0], "comb": coef[1], "dff_q": coef[2],
                              "port": coef[3]}})

    # 3. alignment: 100 ps bins
    dt, pre, T = p["dt"], p["pre"], p["period"]
    k = int(round(0.1 / dt))
    nb = traces.shape[1] // k
    tb = traces[:, :nb * k].reshape(n, nb, k).mean(2)
    prof = []
    for b in range(nb):
        prof.append((round(b * k * dt, 3), float(tb[:, b].mean()),
                     corr(tb[:, b], (hd_comb + hd_q).astype(float)),
                     corr(tb[:, b], hd_port.astype(float))))
    rep["profile_100ps"] = [dict(t_ns=t, mean_uA=m, corr_eval=ce, corr_ports=cp)
                            for t, m, ce, cp in prof]
    rep["events_ns"] = {"capture_edge": pre, "clock_fall": pre + T / 2,
                        "input_edges": pre + p["t_in"] * T}
    if lat == 2:
        rep["events_ns"]["second_edge"] = pre + T

    print("run %s: %d windows of %d samples (dt %g ns)" % (a.run, n, traces.shape[1], dt))
    if "output_match_fraction" in rep:
        print("function: SPICE output registers match the zero-delay model in %.1f%% of rows"
              % (100 * rep["output_match_fraction"]))
    print("charge per window: %.1f +- %.1f fC" % (charge.mean(), charge.std()))
    for key in ("corr_charge_hd_all_nets", "corr_charge_hd_comb", "corr_charge_hd_dff_q",
                "corr_charge_hd_fanout_weighted", "corr_charge_hd_ports", "fit_R_comb_q_ports"):
        print("  %-32s %.3f" % (key, rep[key]))
    print("  fit fC/toggle: " +
          ", ".join("%s %.2f" % kv for kv in rep["fit_fC_per_toggle"].items()))
    print("events (ns into window): " +
          ", ".join("%s %.2f" % kv for kv in rep["events_ns"].items()))
    print("   t(ns)  mean(uA)  corr(eval HD)  corr(port HD)")
    for t, m, ce, cp in prof:
        bar = "#" * int(min(60, max(0, m) / 10))
        print("  %5.2f  %8.1f  %8.2f  %8.2f  %s" % (t, m, ce, cp, bar))
    with open(os.path.join(a.run, "sanity.json"), "w") as f:
        json.dump(rep, f, indent=1)

    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        t = np.arange(traces.shape[1]) * dt - pre
        fig, ax = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
        ax[0].plot(t, traces.mean(0), lw=1, label="mean")
        ax[0].fill_between(t, traces.mean(0) - traces.std(0), traces.mean(0) + traces.std(0),
                           alpha=0.3, label="+-1 std")
        ax[0].set_ylabel("supply current (uA)")
        ax[0].legend()
        ce = [corr(traces[:, j], (hd_comb + hd_q).astype(float)) for j in range(len(t))]
        cp = [corr(traces[:, j], hd_port.astype(float)) for j in range(len(t))]
        ax[1].plot(t, ce, lw=1, label="corr with evaluation toggles")
        ax[1].plot(t, cp, lw=1, label="corr with input-port toggles")
        ax[1].set_ylabel("correlation")
        ax[1].set_xlabel("time from capturing clock edge (ns)")
        ax[1].legend()
        for axx in ax:
            for name, te in rep["events_ns"].items():
                axx.axvline(te - pre, color="gray", ls=":", lw=0.8)
        fig.suptitle("%s: %d windows" % (man["subckt"], n))
        fig.tight_layout()
        fig.savefig(a.plot, dpi=120)
        print("plot:", a.plot)


if __name__ == "__main__":
    main()
