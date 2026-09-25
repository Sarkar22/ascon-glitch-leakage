# SPDX-License-Identifier: Apache-2.0
"""Mock DUTs for developing the SPICE campaign runner (not the kill-test netlists).

The real netlists come from the generator in gen/ (build/<V>/). These mocks follow the same
interface contract so the runner can be developed and benchmarked before the generator exists:
  sim/mock/<V>/dut.v, dut.sp, ports.json, graph.json

Variants (hand-built from sky130_fd_sc_hd cells, all inputs and outputs registered in dfxtp_1):
  U  unmasked Ascon S-box, latency 1                              (27 cells, 10 DFF)
  N  2-share DOM-indep S-box, no register barrier, latency 1      (88 cells, 25 DFF)
  D  same with the DOM partial products and linear terms
     registered before integration, latency 2                     (118 cells, 55 DFF)

Bit order: x = x0<<4 | ... | x4 (x0 is the MSB). Each internal net and each output gets a wire
capacitor of WIRE_CAP_FF to VGND (a fixed pre-layout estimate).

Usage:  python3 sim/mock/make_mock.py [U N D]     (needs the PDK: env PDK or ~/.ciel/sky130A)
"""
import json
import os
import sys

WIRE_CAP_FF = 1.0
LIB = "sky130_fd_sc_hd__"
SBOX = [0x4, 0xB, 0x1F, 0x14, 0x1A, 0x15, 0x9, 0x2, 0x1B, 0x5, 0x8, 0x12, 0x1D, 0x3, 0x6, 0x1C,
        0x1E, 0x13, 0x7, 0xE, 0x0, 0xD, 0x11, 0x18, 0x10, 0xC, 0x1, 0x19, 0x16, 0xA, 0xF, 0x17]
OUT_PIN = {"dfxtp_1": "Q", "xor2_1": "X", "and2_1": "X", "and2b_1": "X", "inv_1": "Y"}


def pdk_root():
    return os.environ.get("PDK") or os.path.realpath(os.path.expanduser("~/.ciel/sky130A"))


def cell_pin_order(cell_types):
    """Pin order of each cell's .subckt line in the PDK SPICE library."""
    path = os.path.join(pdk_root(), "libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice")
    order = {}
    with open(path) as f:
        for line in f:
            if line.lower().startswith(".subckt " + LIB):
                parts = line.split()
                name = parts[1][len(LIB):]
                if name in cell_types:
                    order[name] = parts[2:]
    return order


class Netlist:
    def __init__(self):
        self.cells = []   # (name, type, {pin: net})
        self.n = 0

    def add(self, typ, out, **pins):
        self.n += 1
        pins[OUT_PIN[typ]] = out
        self.cells.append(("u%d_%s" % (self.n, typ.split("_")[0]), typ, pins))
        return out

    def dff(self, d, q):
        return self.add("dfxtp_1", q, CLK="CLK", D=d)

    def xor(self, a, b, out):
        return self.add("xor2_1", out, A=a, B=b)


def sbox_linear_in(nl, q, s):
    """x0 ^= x4; x4 ^= x3; x2 ^= x1 on share s; q[i] are the share's input nets."""
    a = list(q)
    a[0] = nl.xor(q[0], q[4], "a0_%d" % s)
    a[4] = nl.xor(q[4], q[3], "a4_%d" % s)
    a[2] = nl.xor(q[2], q[1], "a2_%d" % s)
    return a


def sbox_linear_out(nl, b, s, out_suffix):
    """x1 ^= x0; x0 ^= x4; x3 ^= x2; x2 = ~x2 (NOT only on share 0)."""
    c = list(b)
    c[1] = nl.xor(b[1], b[0], "c1" + out_suffix)
    c[0] = nl.xor(b[0], b[4], "c0" + out_suffix)
    c[3] = nl.xor(b[3], b[2], "c3" + out_suffix)
    c[2] = nl.add("inv_1", "c2" + out_suffix, A=b[2]) if s == 0 else b[2]
    return c


def build_u():
    nl = Netlist()
    ins = [("x_%d" % i, "plain", i) for i in range(5)]
    q = [nl.dff("x_%d" % i, "q_%d" % i) for i in range(5)]
    a = sbox_linear_in(nl, q, 0)
    t = [nl.add("and2b_1", "t_%d" % i, A_N=a[i], B=a[(i + 1) % 5]) for i in range(5)]
    b = [nl.xor(a[i], t[(i + 1) % 5], "b_%d" % i) for i in range(5)]
    c = sbox_linear_out(nl, b, 0, "")
    outs = [("y_%d" % i, "plain", i) for i in range(5)]
    for i in range(5):
        nl.dff(c[i], "y_%d" % i)
    return nl, ins, outs, 1


def build_masked(barrier):
    nl = Netlist()
    ins = [("xs%d_%d" % (s, i), "share%d" % s, i) for s in (0, 1) for i in range(5)]
    ins += [("r_%d" % i, "rand", i) for i in range(5)]
    q = [[nl.dff("xs%d_%d" % (s, i), "q%d_%d" % (s, i)) for i in range(5)] for s in (0, 1)]
    r = [nl.dff("r_%d" % i, "qr_%d" % i) for i in range(5)]
    a = [sbox_linear_in(nl, q[s], s) for s in (0, 1)]
    t = [[None] * 5, [None] * 5]
    for i in range(5):
        j = (i + 1) % 5   # t_i = ~a_i & a_j; ~ on share 0 only
        p00 = nl.add("and2b_1", "p00_%d" % i, A_N=a[0][i], B=a[0][j])
        p01 = nl.xor(nl.add("and2b_1", "m01_%d" % i, A_N=a[0][i], B=a[1][j]), r[i], "p01_%d" % i)
        p11 = nl.add("and2_1", "p11_%d" % i, A=a[1][i], B=a[1][j])
        p10 = nl.xor(nl.add("and2_1", "m10_%d" % i, A=a[1][i], B=a[0][j]), r[i], "p10_%d" % i)
        if barrier:
            p00, p01, p11, p10 = [nl.dff(p, "R" + p) for p in (p00, p01, p11, p10)]
        t[0][i] = nl.xor(p00, p01, "z0_%d" % i)
        t[1][i] = nl.xor(p11, p10, "z1_%d" % i)
    if barrier:
        a = [[nl.dff(a[s][i], "Ra%d_%d" % (s, i)) for i in range(5)] for s in (0, 1)]
    outs = []
    for s in (0, 1):
        b = [nl.xor(a[s][i], t[s][(i + 1) % 5], "b%d_%d" % (s, i)) for i in range(5)]
        c = sbox_linear_out(nl, b, s, "_%d" % s)
        for i in range(5):
            nl.dff(c[i], "ys%d_%d" % (s, i))
            outs.append(("ys%d_%d" % (s, i), "share%d" % s, i))
    return nl, ins, outs, 2 if barrier else 1


def evaluate(nl, values):
    """Settled value of every net for given DFF outputs/ports (dict net->0/1), topological sweep."""
    v = dict(values)
    pending = [c for c in nl.cells if c[1] != "dfxtp_1"]
    while pending:
        rest = []
        for name, typ, p in pending:
            ins = [p[k] for k in p if k != OUT_PIN[typ]]
            if not all(n in v for n in ins):
                rest.append((name, typ, p))
                continue
            if typ == "xor2_1":
                v[p["X"]] = v[p["A"]] ^ v[p["B"]]
            elif typ == "and2_1":
                v[p["X"]] = v[p["A"]] & v[p["B"]]
            elif typ == "and2b_1":
                v[p["X"]] = (1 - v[p["A_N"]]) & v[p["B"]]
            elif typ == "inv_1":
                v[p["Y"]] = 1 - v[p["A"]]
        if len(rest) == len(pending):
            raise RuntimeError("combinational loop or undriven net")
        pending = rest
    return v


def check_function(nl, ins, outs, latency):
    """Cycle-accurate check against the S-box table (all 32 inputs, random masks)."""
    import random
    rng = random.Random(1)
    dffs = [c for c in nl.cells if c[1] == "dfxtp_1"]
    state = {c[2]["Q"]: 0 for c in dffs}
    rows = []
    for x in list(range(32)) + [0] * latency:
        m, rr = rng.randrange(32), rng.randrange(32)
        port = {}
        for name, role, bit in ins:
            val = {"plain": x, "share0": x ^ m, "share1": m, "rand": rr}[role]
            port[name] = (val >> (4 - bit)) & 1
        v = evaluate(nl, {**state, **port})
        state = {c[2]["Q"]: v[c[2]["D"]] for c in dffs}   # rising edge
        v = evaluate(nl, {**state, **port})
        y = 0
        for name, role, bit in outs:
            y ^= v[name] << (4 - bit)
        rows.append(y)
    got = rows[latency:latency + 32]   # output regs hold S(x) latency edges after capture
    assert got == SBOX, "S-box mismatch: %s" % got


def write_variant(v, outdir):
    nl, ins, outs, latency = {"U": build_u, "N": lambda: build_masked(False),
                              "D": lambda: build_masked(True)}[v]()
    check_function(nl, ins, outs, latency)
    types = sorted({c[1] for c in nl.cells})
    order = cell_pin_order(types)
    ports = ["CLK"] + [n for n, _, _ in ins] + [n for n, _, _ in outs] + ["VPWR", "VGND"]
    in_nets = {"CLK", "VPWR", "VGND"} | {n for n, _, _ in ins}
    driven = [c[2][OUT_PIN[c[1]]] for c in nl.cells]
    os.makedirs(outdir, exist_ok=True)
    sub = "dut_" + v

    sp = ["* SPDX-License-Identifier: Apache-2.0",
          "* Mock DUT %s (sim/mock/make_mock.py): %d cells, %d DFF" %
          (v, len(nl.cells), sum(c[1] == "dfxtp_1" for c in nl.cells)),
          ".subckt %s %s" % (sub, " ".join(ports))]
    for name, typ, p in nl.cells:
        conn = [{"VNB": "VGND", "VPB": "VPWR"}.get(pin, p.get(pin, pin)) for pin in order[typ]]
        sp.append("X%s %s %s%s" % (name, " ".join(conn), LIB, typ))
    for k, net in enumerate(driven):
        sp.append("Cw%d %s VGND %gf" % (k, net, WIRE_CAP_FF))
    sp.append(".ends %s" % sub)
    with open(os.path.join(outdir, "dut.sp"), "w") as f:
        f.write("\n".join(sp) + "\n")

    vl = ["// SPDX-License-Identifier: Apache-2.0",
          "// Mock DUT %s generated by sim/mock/make_mock.py" % v,
          "module %s(%s);" % (sub, ", ".join(ports)),
          "  input CLK, VPWR, VGND;"]
    vl += ["  input %s;" % n for n, _, _ in ins]
    vl += ["  output %s;" % n for n, _, _ in outs]
    port_set = set(ports)
    vl += ["  wire %s;" % n for n in driven if n not in port_set]
    for name, typ, p in nl.cells:
        conn = dict(p, VPWR="VPWR", VGND="VGND", VPB="VPWR", VNB="VGND")
        vl.append("  %s%s %s (%s);" % (LIB, typ, name,
                                       ", ".join(".%s(%s)" % (k, conn[k]) for k in order[typ])))
    vl.append("endmodule")
    with open(os.path.join(outdir, "dut.v"), "w") as f:
        f.write("\n".join(vl) + "\n")

    meta = {"variant": v, "subckt": sub, "ports": ports,
            "inputs": [{"name": n, "role": r, "bit": b} for n, r, b in ins],
            "outputs": [{"name": n, "role": r, "bit": b} for n, r, b in outs],
            "latency": latency, "n_cells": len(nl.cells),
            "n_dff": sum(c[1] == "dfxtp_1" for c in nl.cells), "wire_cap_fF": WIRE_CAP_FF,
            "note": "mock DUT for runner development, not a kill-test netlist"}
    with open(os.path.join(outdir, "ports.json"), "w") as f:
        json.dump(meta, f, indent=1)
    graph = {"cells": [{"name": n, "type": LIB + t, "pins": p} for n, t, p in nl.cells],
             "nets": sorted(in_nets | set(driven)),
             "dffs": [n for n, t, _ in nl.cells if t == "dfxtp_1"],
             "wire_cap_fF": WIRE_CAP_FF}
    with open(os.path.join(outdir, "graph.json"), "w") as f:
        json.dump(graph, f, indent=1)
    print("%s: %d cells (%d DFF), latency %d -> %s" %
          (v, meta["n_cells"], meta["n_dff"], latency, outdir))


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    for v in sys.argv[1:] or ["U", "N", "D"]:
        write_variant(v, os.path.join(here, v))
