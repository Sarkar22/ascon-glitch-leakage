# SPDX-License-Identifier: Apache-2.0
"""Generate the S-box variants of the kill test (docs/KILL_TEST.md) as netlists.

    python3 gen/make_variants.py            # all variants into build/<V>/
    python3 gen/make_variants.py U N        # only some
    python3 gen/make_variants.py --out DIR  # into DIR/<V>/ instead of build/

Per variant V this writes build/<V>/{dut.v, dut.sp, ports.json, graph.json}
(see gen/netlist.py for the formats and the capacitance/timing estimates).

Variants (bit order x = x0<<4 | ... | x4; S-box as in model/ascon_sbox.py):
  U   unmasked: input regs -> S-box -> output regs.                     latency 1
  N   naive DOM: input regs (x shares + 5 fresh random bits) -> affine layer,
      DOM-indep ANDs and integration, all combinational -> output regs.  latency 1
  D   DOM with register barrier: as N, but the four partial products of every AND
      (p00, p11, p01^r, p10^r) and the linear terms a_i are registered before
      integration.                                                       latency 2
  DA  control (not in the pre-registered table): as D, but the S-box's input affine
      layer (x0^=x4, x4^=x3, x2^=x1) sits in front of the input registers, so each DOM
      AND sees independently shared inputs. In D (as the spec defines it) three of the
      five ANDs (t1, t3, t4) get inputs that share a variable (a1=x1 and a2=x1^x2, a3=x3
      and a4=x3^x4, a4 and a0=x0^x4), which the glitch-extended probing model flags on
      the cross-domain terms before the barrier. DA has the same ports and stimulus as D.

Masking (2 shares, share 1 is the mask: xs0 = x ^ m, xs1 = m): linear operations
share-wise, NOT only on share 0, and each t_i = ~a_i & a_{i+1} as DOM-indep with the
fresh bit r_i:
    p00 = ~a_i^0 & a_{i+1}^0   (and2b)      p01 = (~a_i^0 & a_{i+1}^1) ^ r_i
    p11 =  a_i^1 & a_{i+1}^1   (and2)       p10 = ( a_i^1 & a_{i+1}^0) ^ r_i
    t_i^0 = p00 ^ p01                        t_i^1 = p11 ^ p10
then b_i^s = a_i^s ^ t_{i+1}^s and the output layer y1=b1^b0, y0=b0^b4, y3=b3^b2,
y2=~b2 (share 0 only), y4=b4.

Net names: ports x_i / xs0_i, xs1_i, r_i; register outputs <signal>_q; affine outputs
a_i / as0_i, as1_i; DOM terms p00_i, m01_i (cross AND before r), p01_i, p11_i, m10_i,
p10_i; AND outputs t_i / ts0_i, ts1_i; chi outputs b_i / bs0_i, bs1_i; output-layer
nets y*_d; output ports y_i / ys0_i, ys1_i.
"""
import os
import sys

import netlist
import pdk
from netlist import Netlist

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def affine_in(nl, x, tag):
    """x0 ^= x4; x4 ^= x3; x2 ^= x1 on one share (tag "" or "s0"/"s1"); returns a[0..4]."""
    a = list(x)
    a[0] = nl.gate("xor2_1", "a%s_0" % tag, A=x[0], B=x[4])
    a[4] = nl.gate("xor2_1", "a%s_4" % tag, A=x[4], B=x[3])
    a[2] = nl.gate("xor2_1", "a%s_2" % tag, A=x[2], B=x[1])
    return a


def output_layer(nl, b, tag, share):
    """y1 = b1^b0, y0 = b0^b4, y3 = b3^b2, y2 = ~b2 (share 0 only), y4 = b4 -> D-pin nets."""
    y = [None] * 5
    y[1] = nl.gate("xor2_1", "y%s_1_d" % tag, A=b[1], B=b[0])
    y[0] = nl.gate("xor2_1", "y%s_0_d" % tag, A=b[0], B=b[4])
    y[3] = nl.gate("xor2_1", "y%s_3_d" % tag, A=b[3], B=b[2])
    y[2] = nl.gate("inv_1", "y%s_2_d" % tag, A=b[2]) if share == 0 else b[2]
    y[4] = b[4]
    return y


def build_unmasked():
    nl = Netlist("U", "unmasked Ascon S-box column: input regs -> S-box -> output regs", 1)
    x = [nl.dff(nl.input("x_%d" % i, "plain", i, "x"), "x_%d_q" % i) for i in range(5)]
    a = affine_in(nl, x, "")
    t = [nl.gate("and2b_1", "t_%d" % i, A_N=a[i], B=a[(i + 1) % 5]) for i in range(5)]
    b = [nl.gate("xor2_1", "b_%d" % i, A=a[i], B=t[(i + 1) % 5]) for i in range(5)]
    y = output_layer(nl, b, "", 0)
    for i in range(5):
        nl.output("y_%d" % i, "plain", i, y[i])
    return nl


def build_masked(variant):
    barrier = variant in ("D", "DA")
    affine_first = variant == "DA"
    desc = {"N": "2-share DOM Ascon S-box column without register barrier (naive)",
            "D": "2-share DOM Ascon S-box column with register barrier before integration",
            "DA": "as D, with the input affine layer in front of the input registers"}[variant]
    nl = Netlist(variant, desc, 2 if barrier else 1)
    xs = [[nl.input("xs%d_%d" % (s, i), "share%d" % s, i, "s%d" % s) for i in range(5)] for s in (0, 1)]
    r_in = [nl.input("r_%d" % i, "rand", i, "r") for i in range(5)]
    if affine_first:
        a = [[nl.dff(n, "as%d_%d_q" % (s, i)) for i, n in enumerate(affine_in(nl, xs[s], "s%d" % s))]
             for s in (0, 1)]
    else:
        a = [affine_in(nl, [nl.dff(n, n + "_q") for n in xs[s]], "s%d" % s) for s in (0, 1)]
    r = [nl.dff(n, n + "_q") for n in r_in]

    t = [[None] * 5, [None] * 5]
    for i in range(5):
        j = (i + 1) % 5
        p00 = nl.gate("and2b_1", "p00_%d" % i, A_N=a[0][i], B=a[0][j])
        m01 = nl.gate("and2b_1", "m01_%d" % i, dom="cross", A_N=a[0][i], B=a[1][j])
        p01 = nl.gate("xor2_1", "p01_%d" % i, dom="s0", A=m01, B=r[i])
        p11 = nl.gate("and2_1", "p11_%d" % i, A=a[1][i], B=a[1][j])
        m10 = nl.gate("and2_1", "m10_%d" % i, dom="cross", A=a[1][i], B=a[0][j])
        p10 = nl.gate("xor2_1", "p10_%d" % i, dom="s1", A=m10, B=r[i])
        if barrier:
            p00, p01, p11, p10 = (nl.dff(n, n + "_q") for n in (p00, p01, p11, p10))
        t[0][i] = nl.gate("xor2_1", "ts0_%d" % i, A=p00, B=p01)
        t[1][i] = nl.gate("xor2_1", "ts1_%d" % i, A=p11, B=p10)
    if barrier:
        suffix = "_qq" if affine_first else "_q"
        a = [[nl.dff(a[s][i], "as%d_%d%s" % (s, i, suffix)) for i in range(5)] for s in (0, 1)]
    for s in (0, 1):
        b = [nl.gate("xor2_1", "bs%d_%d" % (s, i), A=a[s][i], B=t[s][(i + 1) % 5]) for i in range(5)]
        y = output_layer(nl, b, "s%d" % s, s)
        for i in range(5):
            nl.output("ys%d_%d" % (s, i), "share%d" % s, i, y[i])
    return nl


BUILDERS = {"U": build_unmasked, "N": lambda: build_masked("N"),
            "D": lambda: build_masked("D"), "DA": lambda: build_masked("DA")}


def main(variants, out_root=None, verbose=True):
    """Build the variants into <out_root>/<V>/ (default: build/ in the repository)."""
    out_root = out_root or os.path.join(ROOT, "build")
    lib = pdk.Liberty()
    spice_pins = netlist.check_cells_against_pdk(lib)
    for v in variants:
        nl = BUILDERS[v]()
        nl.validate()
        nl.annotate(lib)
        out = os.path.join(out_root, v)
        os.makedirs(out, exist_ok=True)
        nl.write_verilog(os.path.join(out, "dut.v"))
        nl.write_spice(os.path.join(out, "dut.sp"), spice_pins)
        nl.write_ports(os.path.join(out, "ports.json"))
        nl.write_graph(os.path.join(out, "graph.json"))
        n_dff = sum(c["type"] == netlist.DFF for c in nl.cells)
        if verbose:
            print("%-2s cells %3d (dff %2d)  nets %3d  area %7.1f um2  reg->reg %6.1f ps  port->reg %5.1f ps  -> %s"
                  % (v, len(nl.cells), n_dff, len(nl.driver), nl.area_um2, nl.timing["reg_to_reg_ps"],
                     nl.timing["port_to_reg_ps"], os.path.relpath(out)))


if __name__ == "__main__":
    args = sys.argv[1:]
    out_root = None
    if "--out" in args:
        k = args.index("--out")
        out_root = args[k + 1]
        del args[k:k + 2]
    main(args or list(BUILDERS), out_root)
