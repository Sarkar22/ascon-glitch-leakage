# SPDX-License-Identifier: Apache-2.0
"""Placement map of a routed variant: every cell coloured by the share domain of the net it drives.

  bash sim/docker_run.sh python3 layout/plot_placement.py N DA U     (needs matplotlib)

Reads the final DEF (runs/pex/ol/<V>/runs/pex/results/final/def/dut_<V>.def), the cell sizes from
the PDK LEF ($PDK/libs.ref/sky130_fd_sc_h{d,d}/lef), the net domains of build/<V>/graph.json (s0,
s1, r, cross = the cross-domain DOM products, x = unmasked) and, if present, the nets flagged by the
glitch-extended probing model (results/probing/<V>.json). Writes results/layout/<V>_placement.png.
Colour = domain of the cell's output net; hatching = that net is flagged by glitch-extended
probing; dark grey = clock-tree buffers; light grey = tap, decap and fill cells.
"""
import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDK = os.environ.get("PDK") or os.path.realpath(os.path.expanduser("~/.ciel/sky130A"))
SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
DOMAIN = {  # fill colour and legend text per domain (first three: validated categorical slots)
    "s0": ("#2a78d6", "share 0"),
    "s1": ("#eb6834", "share 1"),
    "r": ("#1baf7a", "fresh random bits r"),
    "cross": ("#262625", "cross-domain AND (a0 b1, a1 b0)"),
    "x": ("#2a78d6", "unmasked logic"),
}
CLOCK, PHYSICAL = "#8f8e89", "#e4e3df"


def lef_sizes():
    sizes = {}
    for lib in ("sky130_fd_sc_hd", "sky130_ef_sc_hd"):
        path = os.path.join(PDK, "libs.ref", "sky130_fd_sc_hd", "lef", lib + ".lef")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            text = f.read()
        for m in re.finditer(r"MACRO (\S+)(.*?)END \1", text, re.S):
            s = re.search(r"SIZE ([\d.]+) BY ([\d.]+)", m.group(2))
            if s:
                sizes[m.group(1)] = (float(s.group(1)), float(s.group(2)))
    return sizes


def read_def(path):
    with open(path) as f:
        text = f.read()
    dbu = int(re.search(r"UNITS DISTANCE MICRONS (\d+)", text).group(1))
    die = [int(v) / dbu for v in re.search(
        r"DIEAREA \( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \)", text).groups()]
    block = re.search(r"COMPONENTS \d+ ;(.*?)END COMPONENTS", text, re.S).group(1)
    comps = []
    for m in re.finditer(r"-\s+(\S+)\s+(\S+)(.*?);", block, re.S):
        p = re.search(r"(?:PLACED|FIXED) \( (-?\d+) (-?\d+) \)", m.group(3))
        if p:
            comps.append((m.group(1).replace("\\", ""), m.group(2),
                          int(p.group(1)) / dbu, int(p.group(2)) / dbu))
    return die, comps


def output_domains(v):
    """instance name -> (domain of its output net, output net)."""
    with open(os.path.join(REPO, "build", v, "graph.json")) as f:
        g = json.load(f)
    out = {}
    for c in g["cells"]:
        t = g["cell_types"][c["type"]]
        pin = "Q" if t.get("sequential") else t["output"]
        net = c["pins"].get(pin)
        if net is not None:
            out[c["name"]] = (g["nets"][net]["domain"], net)
    return out


def flagged(v):
    path = os.path.join(REPO, "results", "probing", v + ".json")
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        return set(json.load(f)["glitch_fail"])


def plot(v, sizes, ax):
    die, comps = read_def(os.path.join(REPO, "runs", "pex", "ol", v, "runs", "pex", "results",
                                       "final", "def", "dut_%s.def" % v))
    dom = output_domains(v)
    flag = flagged(v)
    used = set()
    for name, cell, x, y in comps:
        w, h = sizes.get(cell, (0.46, 2.72))
        hatch = None
        if name in dom:
            d, net = dom[name]
            face = DOMAIN[d][0]
            used.add(d)
            if net in flag:
                hatch = "////"
                used.add("flagged")
        elif "clkbuf" in cell:
            face = CLOCK
            used.add("clock")
        else:
            face = PHYSICAL
            used.add("physical")
        ax.add_patch(Rectangle((x, y), w, h, facecolor=face, edgecolor=SURFACE, linewidth=0.6,
                               hatch=hatch))
    ax.add_patch(Rectangle((die[0], die[1]), die[2] - die[0], die[3] - die[1], fill=False,
                           edgecolor=INK2, linewidth=0.8))
    ax.set_xlim(die[0] - 1, die[2] + 1)
    ax.set_ylim(die[1] - 1, die[3] + 1)
    ax.set_aspect("equal")
    ax.set_xlabel("x (um)", color=INK2)
    ax.set_ylabel("y (um)", color=INK2)
    ax.tick_params(colors=INK2, labelsize=8)
    for s in ax.spines.values():
        s.set_visible(False)
    return used, die


def main(argv=None):
    vs = (argv if argv is not None else sys.argv[1:]) or ["N", "DA", "U"]
    sizes = lef_sizes()
    plt.rcParams["hatch.color"] = SURFACE
    plt.rcParams["hatch.linewidth"] = 1.0
    out_dir = os.path.join(REPO, "results", "layout")
    os.makedirs(out_dir, exist_ok=True)
    for v in vs:
        fig, ax = plt.subplots(figsize=(6.4, 6.0), facecolor=SURFACE)
        ax.set_facecolor(SURFACE)
        used, die = plot(v, sizes, ax)
        handles = [Patch(facecolor=DOMAIN[d][0], edgecolor=SURFACE, label=DOMAIN[d][1])
                   for d in ("s0", "s1", "r", "cross", "x") if d in used]
        if "flagged" in used:
            handles.append(Patch(facecolor=INK2, edgecolor=SURFACE, hatch="////",
                                 label="output net flagged by glitch-extended probing"))
        if "clock" in used:
            handles.append(Patch(facecolor=CLOCK, label="clock-tree buffer (CTS)"))
        handles.append(Patch(facecolor=PHYSICAL, label="tap / decap / fill"))
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False,
                  fontsize=8, labelcolor=INK)
        ax.set_title("dut_%s after place and route: %.1f x %.1f um" % (
            v, die[2] - die[0], die[3] - die[1]), color=INK, fontsize=10, loc="left")
        path = os.path.join(out_dir, "%s_placement.png" % v)
        fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURFACE)
        plt.close(fig)
        print("wrote", os.path.relpath(path, REPO))


if __name__ == "__main__":
    main()
