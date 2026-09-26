# SPDX-License-Identifier: Apache-2.0
"""Summary of the OpenLane runs: area, cells before/after, clock tree, timing, DRC/LVS/antenna.

  python3 layout/summarize.py [N DA U]

Reads runs/pex/ol/<V>/runs/pex/ (layout/run_flow.sh), runs/pex/klayout/<V>/drc.lyrdb
(layout/run_klayout.sh) and build/<V>_pex/ports.json (layout/make_pex.py) when present, and
writes results/layout/summary.json and results/layout/table.md (the table in layout/README.md).
It also checks that the netlist OpenLane placed is the generator's netlist: every instance of
build/<V>/dut.v appears in the synthesized and in the final netlist with the same cell type and
the same net on every pin, except that flip-flop CLK pins move to the clock-tree nets.
Host python3 (standard library only).
"""
import csv
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POWER_PINS = {"VPWR", "VGND", "VPB", "VNB"}


def run_dir(v):
    return os.path.join(REPO, "runs", "pex", "ol", v, "runs", "pex")


def parse_verilog(path):
    """Structural Verilog -> {instance: (cell, {pin: net})}; power pins and `ifdef lines dropped."""
    with open(path) as f:
        text = f.read()
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"`\w+[^\n]*", "", text)
    body = text[text.index(");") + 2:]                  # after the module port list
    inst = {}
    for m in re.finditer(r"\b(sky130_\w+)\s+(\\\S+|\w+)\s*\((.*?)\)\s*;", body, re.S):
        cell, name, conns = m.group(1), m.group(2).lstrip("\\"), m.group(3)
        pins = {}
        for pm in re.finditer(r"\.(\w+)\s*\(\s*(\\\S+|[\w\[\]]*)\s*\)", conns):
            if pm.group(1) not in POWER_PINS:
                pins[pm.group(1)] = pm.group(2).lstrip("\\")
        inst[name] = (cell, pins)
    return inst


def category(cell):
    for key, cat in (("__tap", "tap"), ("decap", "decap"), ("__fill", "fill"),
                     ("__diode", "diode"), ("clkbuf", "clock_buffer"), ("__buf", "buffer"),
                     ("__conb", "tie")):
        if key in cell:
            return cat
    return "logic"


def compare_netlists(ref, other):
    """Differences of `other` against the generator's netlist `ref`."""
    missing = [n for n in ref if n not in other]
    changed_type = [n for n in ref if n in other and other[n][0] != ref[n][0]]
    pin_changes, clk_moves = [], 0
    for n, (cell, pins) in ref.items():
        if n not in other:
            continue
        for p, net in pins.items():
            onet = other[n][1].get(p)
            if onet == net:
                continue
            if p == "CLK" and onet and onet.startswith("clknet_"):
                clk_moves += 1
            else:
                pin_changes.append("%s.%s: %s -> %s" % (n, p, net, onet))
    extra = {}
    for n, (cell, _) in other.items():
        if n not in ref:
            c = category(cell)
            extra.setdefault(c, {})
            extra[c][cell] = extra[c].get(cell, 0) + 1
    return {"missing_instances": missing, "changed_cell_type": changed_type,
            "changed_pins": pin_changes, "clk_pins_on_clock_tree_nets": clk_moves,
            "added_instances": extra,
            "logic_unchanged": not (missing or changed_type or pin_changes)}


def read_metrics(d):
    with open(os.path.join(d, "reports", "metrics.csv")) as f:
        return list(csv.DictReader(f))[0]


def first_match(path, pattern, cast=str):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        m = re.search(pattern, f.read(), re.M)
    return cast(m.group(1)) if m else None


def find(d, sub, pattern):
    base = os.path.join(d, sub)
    if not os.path.isdir(base):
        return None
    hits = sorted(f for f in os.listdir(base) if re.fullmatch(pattern, f))
    return os.path.join(base, hits[-1]) if hits else None


def klayout_drc_count(v):
    path = os.path.join(REPO, "runs", "pex", "klayout", v, "drc.lyrdb")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read().count("<item>")


def summarize(v):
    d = run_dir(v)
    top = "dut_" + v
    met = read_metrics(d)
    with open(os.path.join(d, "results", "final", "def", top + ".def")) as f:
        text = f.read()
    dbu = int(re.search(r"UNITS DISTANCE MICRONS (\d+)", text).group(1))
    m = re.search(r"DIEAREA \( (-?\d+) (-?\d+) \) \( (\d+) (\d+) \)", text)
    die_w = (int(m.group(3)) - int(m.group(1))) / dbu
    die_h = (int(m.group(4)) - int(m.group(2))) / dbu

    gen = parse_verilog(os.path.join(REPO, "build", v, "dut.v"))
    syn = parse_verilog(os.path.join(d, "results", "synthesis", top + ".v"))
    fin = parse_verilog(os.path.join(d, "results", "final", "verilog", "gl", top + ".nl.v"))
    counts = {}
    for cell, _ in fin.values():
        c = category(cell)
        counts.setdefault(c, {})
        counts[c][cell] = counts[c].get(cell, 0) + 1

    lvs_log = find(d, "logs/signoff", r"\d+-" + top + r"\.gds\.lvs\.log") or \
        find(d, "logs/signoff", r".*lvs.*\.log")
    lvs = first_match(lvs_log, r"^Final result:\s*\n?(.*)$") if lvs_log else None
    if lvs_log and lvs is None:
        with open(lvs_log) as f:
            txt = f.read()
        lvs = "Circuits match uniquely." if "Circuits match uniquely" in txt else "see log"
    arc = find(d, "logs/signoff", r"\d+-arc\.log")
    summ = os.path.join(d, "reports", "signoff", "25-rcx_sta.summary.rpt")
    checks = os.path.join(d, "reports", "signoff", "25-rcx_sta.checks.rpt")
    skew = os.path.join(d, "reports", "signoff", "25-rcx_sta.skew.rpt")
    fanout = []
    if os.path.exists(checks):
        with open(checks) as f:
            fanout = re.findall(r"^(\S+)\s+(\d+)\s+(\d+)\s+(-\d+) \(VIOLATED\)", f.read(), re.M)

    res = {
        "variant": v, "design": top,
        "die_um": [die_w, die_h], "die_area_um2": round(die_w * die_h, 1),
        "core_area_um2": round(float(met["CoreArea_um^2"]), 1),
        "placement_utilisation_pct": float(met["OpenDP_Util"]),
        "fp_core_util_pct": float(met["FP_CORE_UTIL"]),
        "cells_generator": len(gen),
        "cells_synthesized": len(syn),
        "cells_final_by_category": {c: sum(x.values()) for c, x in sorted(counts.items())},
        "cells_final_by_type": {c: dict(sorted(x.items())) for c, x in sorted(counts.items())},
        "cells_final_total": len(fin),
        "synthesis_vs_generator": compare_netlists(gen, syn),
        "final_vs_generator": compare_netlists(gen, fin),
        "clock_tree": {"buffers": counts.get("clock_buffer", {}),
                       "skew_ns": first_match(skew, r"^\s+[-\d.]+\s+[-\d.]+\s+([-\d.]+)\s*$", float),
                       "max_fanout_violations": [
                           {"pin": a, "limit": int(b), "fanout": int(c)} for a, b, c, _ in fanout]},
        "timing_tt_ns": {"clock_period": float(met["CLOCK_PERIOD"]),
                         "setup_worst_slack": first_match(summ, r"Setup\)\s*\n=+\s*\nworst slack ([-\d.]+)", float),
                         "hold_worst_slack": first_match(summ, r"Hold\)\s*\n=+\s*\nworst slack ([-\d.]+)", float),
                         "critical_path": float(met["critical_path_ns"])},
        "wire_length_um": int(float(met["wire_length"])), "vias": int(float(met["vias"])),
        "drc_router": int(float(met["tritonRoute_violations"])),
        "drc_magic": int(float(met["Magic_violations"])),
        "drc_klayout": klayout_drc_count(v),
        "lvs": lvs,
        "antenna_pin_violations": first_match(arc, r"Found (\d+) pin violations", int) if arc else None,
        "antenna_net_violations": first_match(arc, r"Found (\d+) net violations", int) if arc else None,
        "klayout_xor_vs_magic_gds": first_match(os.path.join(d, "logs", "signoff", "28-xor.log"),
                                                 r"(XOR differences: \d+|No XOR differences)") or
        "see logs/signoff/28-xor.log",
        "run_dir": os.path.relpath(d, REPO),
    }
    pex = os.path.join(REPO, "build", v + "_pex", "ports.json")
    if os.path.exists(pex):
        with open(pex) as f:
            s = json.load(f)["pex"]
        res["pex"] = {k: s[k] for k in ("n_devices", "devices", "supply_only_devices",
                                        "supply_only_devices_dropped", "caps_fF",
                                        "named_nets_cap_fF_sum",
                                        "coupling_between_named_nets_by_domain")}
    return res


def table(rows):
    head = ["", *[r["variant"] for r in rows]]
    def line(label, f):
        return [label, *[f(r) for r in rows]]
    def cats(r, keys):
        return str(sum(r["cells_final_by_category"].get(k, 0) for k in keys))
    body = [
        line("die (um)", lambda r: "%.2f x %.2f" % tuple(r["die_um"])),
        line("core area (um^2)", lambda r: "%.0f" % r["core_area_um2"]),
        line("placement utilisation", lambda r: "%.1f %%" % r["placement_utilisation_pct"]),
        line("logic cells: generator / synthesized / final",
             lambda r: "%d / %d / %s" % (r["cells_generator"], r["cells_synthesized"],
                                         cats(r, ["logic"]))),
        line("logic netlist unchanged (types, pins)",
             lambda r: "yes" if r["final_vs_generator"]["logic_unchanged"] and
             r["synthesis_vs_generator"]["logic_unchanged"] else "NO"),
        line("CTS buffers added", lambda r: ", ".join("%d x %s" % (n, c.split("__")[1])
                                                     for c, n in r["clock_tree"]["buffers"].items()) or "0"),
        line("other buffers added", lambda r: cats(r, ["buffer"])),
        line("tap / decap / fill cells", lambda r: "%s / %s / %s" % (
            cats(r, ["tap"]), cats(r, ["decap"]), cats(r, ["fill"]))),
        line("antenna diodes", lambda r: cats(r, ["diode"])),
        line("clock skew (ns)", lambda r: str(r["clock_tree"]["skew_ns"])),
        line("setup / hold worst slack at 4 ns (ns)", lambda r: "%s / %s" % (
            r["timing_tt_ns"]["setup_worst_slack"], r["timing_tt_ns"]["hold_worst_slack"])),
        line("wire length (um) / vias", lambda r: "%d / %d" % (r["wire_length_um"], r["vias"])),
        line("DRC: router / Magic / KLayout", lambda r: "%d / %d / %s" % (
            r["drc_router"], r["drc_magic"], "-" if r["drc_klayout"] is None else r["drc_klayout"])),
        line("LVS (netgen)", lambda r: "clean" if r["lvs"] and "match uniquely" in r["lvs"] else str(r["lvs"])),
        line("antenna violations (pins / nets)", lambda r: "%s / %s" % (
            r["antenna_pin_violations"], r["antenna_net_violations"])),
    ]
    if all("pex" in r for r in rows):
        body += [
            line("extracted transistors (of them decap)", lambda r: "%d (%d)" % (
                r["pex"]["n_devices"], r["pex"]["supply_only_devices"])),
            line("extracted capacitors", lambda r: "%d" % r["pex"]["caps_fF"]["count"]),
            line("logic-net cap, pre-layout estimate / extracted (fF)", lambda r: "%.0f / %.0f" % (
                r["pex"]["named_nets_cap_fF_sum"]["prelayout"],
                r["pex"]["named_nets_cap_fF_sum"]["extracted"])),
            line("coupling share 0 - share 1 nets (fF, capacitors)", lambda r: (
                "%.1f (%d)" % (r["pex"]["coupling_between_named_nets_by_domain"]["s0-s1"]["fF"],
                               r["pex"]["coupling_between_named_nets_by_domain"]["s0-s1"]["caps"])
                if "s0-s1" in r["pex"]["coupling_between_named_nets_by_domain"] else "-")),
        ]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(b) + " |" for b in body]
    return "\n".join(out) + "\n"


def main(argv=None):
    vs = (argv if argv is not None else sys.argv[1:]) or ["N", "DA", "U"]
    rows = [summarize(v) for v in vs if os.path.isdir(run_dir(v))]
    out = os.path.join(REPO, "results", "layout")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump({r["variant"]: r for r in rows}, f, indent=1)
    t = table(rows)
    with open(os.path.join(out, "table.md"), "w") as f:
        f.write(t)
    print(t)


if __name__ == "__main__":
    main()
