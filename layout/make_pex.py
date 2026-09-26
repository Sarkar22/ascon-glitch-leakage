# SPDX-License-Identifier: Apache-2.0
"""Wrap a Magic-extracted flat netlist as the post-layout DUT of sim/spice_campaign.py.

Input (from layout/run_pex.sh):
  runs/pex/ext/<V>/dut_<V>_flat.spice   .subckt dut_<V>_flat <ports in Magic's order>, flat: every
                                         transistor of the layout (sky130_fd_pr devices with drawn
                                         W, L, ad, as, pd, ps) and every parasitic capacitor
  build/<V>/ports.json                   the pre-layout port contract (port order, roles, latency)
Output:
  build/<V>_pex/dut.sp       .subckt dut_<V> <ports.json order>: the extraction as one flat subckt
                             with exactly the pre-layout port order, so the runner's deck is
                             unchanged; node names made safe for ngspice (characters other than
                             [A-Za-z0-9_] become '_'); the routed nets keep their names, so a
                             deck can probe them as xdut.<net> as for the pre-layout netlist
  build/<V>_pex/ports.json   the pre-layout ports.json with the extraction statistics added
  build/<V>_pex/graph.json   a copy of build/<V>/graph.json (the logical netlist, so the node
                             tools find the nets; its wire caps and delays are pre-layout)
  results/pex/netcap_<V>.csv extracted parasitic capacitance of every named logic net next to the
                             pre-layout estimate (1 fF + 0.5 fF per fanout pin)

The runner includes the sky130 model library (which defines the sky130_fd_pr devices) and the
standard-cell library before dut.sp, so the extracted devices need nothing else. Device sizes are in
microns, as Magic writes them for sky130A; the model library sets `.option scale=1.0u`.

Extra ports of the extraction (a separate substrate or n-well node) are joined to a supply:
substrate names to VGND, n-well names to VPWR. Any other port that is not in ports.json is an
error. With --drop-supply-devices, transistors whose four terminals are all on VPWR/VGND (the
decap cells' MOS capacitors) are left out; with the testbench's ideal supply they carry only a
constant leakage current. The default keeps every device.
"""
import argparse
import csv
import hashlib
import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIE_TO_VGND = ("VSUBS", "VNB", "SUB", "VSUB")
TIE_TO_VPWR = ("VPB", "NWELL")
SUPPLY = ("VPWR", "VGND")


def read_lines(path):
    """SPICE text -> logical lines (continuations joined, comments and blank lines dropped)."""
    out = []
    with open(path) as f:
        for raw in f:
            line = raw.split(" $ ")[0].rstrip()          # Magic's inline "$ **FLOATING" notes
            if not line.strip() or line.lstrip().startswith("*"):
                continue
            if line.startswith("+"):
                if not out:
                    raise ValueError("continuation line without a previous line")
                out[-1] += " " + line[1:].strip()
            else:
                out.append(line.strip())
    return out


def parse_flat(path):
    """Magic's flat netlist -> (subckt name, ports, elements).

    Each element is (kind, name, nodes, model, params): kind 'X' (subcircuit device: nodes, model,
    params), 'C' (two nodes, value in params) or another SPICE letter with the same layout as 'C'.
    """
    lines = read_lines(path)
    heads = [k for k, l in enumerate(lines) if l.lower().startswith(".subckt")]
    if len(heads) != 1:
        raise ValueError("%s: expected one .subckt, found %d" % (path, len(heads)))
    k0 = heads[0]
    words = lines[k0].split()
    name, ports = words[1], words[2:]
    elements = []
    for line in lines[k0 + 1:]:
        if line.lower().startswith(".ends"):
            break
        words = line.split()
        kind = words[0][0].upper()
        if kind == "X":
            plain = [w for w in words[1:] if "=" not in w]
            params = [w for w in words[1:] if "=" in w]
            elements.append(("X", words[0], plain[:-1], plain[-1], params))
        elif kind in "CR":
            elements.append((kind, words[0], words[1:3], None, words[3:]))
        else:
            raise ValueError("unexpected element: %s" % line)
    return name, ports, elements


def safe_names(nodes):
    """Map node names to ngspice-safe ones, unique without regard to case."""
    mapping, used = {}, set()
    for n in nodes:
        base = re.sub(r"[^A-Za-z0-9_]", "_", n)
        cand, k = base, 1
        while cand.lower() in used:
            cand, k = "%s_%d" % (base, k), k + 1
        used.add(cand.lower())
        mapping[n] = cand
    return mapping


def cap_value_fF(word):
    """'0.0518f', '8.41e-21', '1.2p' -> fF."""
    m = re.fullmatch(r"([-+0-9.eE]+)([a-zA-Z]*)", word)
    if not m:
        raise ValueError("cannot read capacitance %r" % word)
    scale = {"": 1e15, "f": 1.0, "p": 1e3, "n": 1e6, "a": 1e-3}[m.group(2).lower()[:1]]
    return float(m.group(1)) * scale


def port_map(flat_ports, want):
    """Wrapper connection of each flat port: its own name, or the supply it is tied to."""
    conn = {}
    for p in flat_ports:
        if p in want:
            conn[p] = p
        elif p.upper() in TIE_TO_VGND:
            conn[p] = "VGND"
        elif p.upper() in TIE_TO_VPWR:
            conn[p] = "VPWR"
        else:
            raise ValueError("extracted port %r is not in ports.json and not a well/substrate" % p)
    missing = [p for p in want if p not in flat_ports]
    if missing:
        raise ValueError("ports.json ports missing from the extraction: %s" % missing)
    return conn


def cap_stats(elements):
    """Totals of the parasitic capacitors (fF) by what they connect, and per named node."""
    tot = {"to_VGND": 0.0, "to_VPWR": 0.0, "VPWR_VGND": 0.0, "signal_signal": 0.0}
    per_node = {}
    n = 0
    for kind, _, nodes, _, params in elements:
        if kind != "C":
            continue
        n += 1
        a, b = nodes
        c = cap_value_fF(params[0])
        s = {a, b}
        if s == set(SUPPLY):
            tot["VPWR_VGND"] += c
        elif "VGND" in s:
            tot["to_VGND"] += c
        elif "VPWR" in s:
            tot["to_VPWR"] += c
        else:
            tot["signal_signal"] += c
        for x, y in ((a, b), (b, a)):
            d = per_node.setdefault(x, {"ground": 0.0, "supply": 0.0, "coupling": 0.0})
            if y == "VGND":
                d["ground"] += c
            elif y == "VPWR":
                d["supply"] += c
            else:
                d["coupling"] += c
    tot = {k: round(v, 3) for k, v in tot.items()}
    tot["count"] = n
    return tot, per_node


def domain_coupling(elements, graph_path):
    """Coupling capacitance (fF) between named logic nets, summed per pair of share domains
    (domains from build/<V>/graph.json: s0, s1, r, cross, x)."""
    if not os.path.exists(graph_path):
        return {}
    with open(graph_path) as f:
        dom = {n: d["domain"] for n, d in json.load(f)["nets"].items()}
    acc = {}
    for kind, _, nodes, _, params in elements:
        if kind == "C" and nodes[0] in dom and nodes[1] in dom:
            key = "-".join(sorted((dom[nodes[0]], dom[nodes[1]])))
            n, c = acc.get(key, (0, 0.0))
            acc[key] = (n + 1, c + cap_value_fF(params[0]))
    return {k: {"caps": n, "fF": round(c, 3)} for k, (n, c) in sorted(acc.items())}


def prelayout_caps(sp_path):
    """Pre-layout wire caps of build/<V>/dut.sp: net -> fF."""
    caps = {}
    with open(sp_path) as f:
        for line in f:
            w = line.split()
            if w and w[0].startswith("Cw_"):
                caps[w[1]] = cap_value_fF(w[3])
    return caps


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def build(variant, flat_path, out_dir, drop_supply=False, netcap_csv=None, provenance=None):
    """Write <out_dir>/dut.sp and ports.json; returns the statistics written to ports.json."""
    with open(os.path.join(REPO, "build", variant, "ports.json")) as f:
        ports = json.load(f)
    want = ports["ports"]
    flat_name, flat_ports, elements = parse_flat(flat_path)
    conn = port_map(flat_ports, want)

    kept, dropped = [], 0
    for e in elements:
        if drop_supply and e[0] == "X" and set(e[2]) <= set(SUPPLY):
            dropped += 1
            continue
        kept.append(e)
    order = dict.fromkeys(flat_ports)          # ports first, then nodes by first appearance
    for e in kept:
        for n in e[2]:
            order.setdefault(n)
    ren = safe_names(order)
    for p in flat_ports:                       # port names must survive unchanged
        if ren[p] != p:
            raise ValueError("port name %r is not ngspice-safe" % p)
    for p, c in conn.items():                  # extra well/substrate ports join their supply
        ren[p] = c
    clash = [n for n in order if n not in conn and ren[n].lower() in {w.lower() for w in want}]
    if clash:
        raise ValueError("internal nodes clash with port names: %s" % clash)

    devices = {}
    for kind, _, nodes_, model, _ in kept:
        if kind == "X":
            devices[model] = devices.get(model, 0) + 1
    supply_only = sum(1 for e in elements if e[0] == "X" and set(e[2]) <= set(SUPPLY))
    caps, per_node = cap_stats(kept)
    sub = ports["subckt"]

    lines = [
        "* SPDX-License-Identifier: Apache-2.0",
        "* %s, post-layout: Magic extraction of the OpenLane v1 GDS (layout/run_pex.sh)." % sub,
        "* Generated by layout/make_pex.py from %s; do not edit." % flat_name,
        "* Transistors as drawn (W, L, ad/as/pd/ps from the layout), parasitic capacitance to",
        "* substrate and between nets (no threshold), no wire resistance. Ports in the order of",
        "* build/%s/ports.json; the routed nets keep their names (e.g. xdut.<net> in a deck)."
        % variant,
        "* Needs in the top deck: .lib <PDK>/libs.tech/ngspice/sky130.lib.spice tt",
        "* Devices: %s; capacitors: %d (%.1f fF in total)." % (
            ", ".join("%d %s" % (v, k) for k, v in sorted(devices.items())), caps["count"],
            sum(caps[k] for k in ("to_VGND", "to_VPWR", "VPWR_VGND", "signal_signal"))),
    ]
    if drop_supply:
        lines.append("* %d supply-only transistors (decap MOS capacitors) left out." % dropped)
    tied = {p: c for p, c in conn.items() if p != c}
    if tied:
        lines.append("* extraction ports joined to a supply: %s" % ", ".join(
            "%s -> %s" % kv for kv in sorted(tied.items())))
    lines.append(".subckt %s %s" % (sub, " ".join(want)))
    for kind, name, nodes_, model, params in kept:
        nn = " ".join(ren[n] for n in nodes_)
        if kind == "X":
            lines.append("%s %s %s %s" % (name, nn, model, " ".join(params)))
        else:
            lines.append("%s %s %s" % (name, nn, " ".join(params)))
    lines.append(".ends %s" % sub)
    os.makedirs(out_dir, exist_ok=True)
    sp = os.path.join(out_dir, "dut.sp")
    with open(sp, "w") as f:
        f.write("\n".join(lines) + "\n")

    pre = prelayout_caps(os.path.join(REPO, "build", variant, "dut.sp"))
    rows = []
    for net in sorted(pre):
        d = per_node.get(net)
        rows.append({"net": net, "prelayout_fF": round(pre[net], 3),
                     "extracted_total_fF": round(sum(d.values()), 3) if d else "",
                     "to_VGND_fF": round(d["ground"], 3) if d else "",
                     "to_VPWR_fF": round(d["supply"], 3) if d else "",
                     "coupling_fF": round(d["coupling"], 3) if d else ""})
    found = [r for r in rows if r["extracted_total_fF"] != ""]
    if netcap_csv:
        os.makedirs(os.path.dirname(netcap_csv), exist_ok=True)
        with open(netcap_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    stats = {
        "source": "Magic flat extraction of the final GDS (layout/pex/extract.tcl)",
        "flat_subckt": flat_name, "flat_ports": flat_ports,
        "tied_ports": {p: c for p, c in conn.items() if p != c},
        "devices": devices, "n_devices": sum(devices.values()),
        "supply_only_devices": supply_only, "supply_only_devices_dropped": dropped,
        "caps_fF": caps,
        "named_nets_with_extracted_cap": len(found), "named_nets_prelayout": len(rows),
        "named_nets_cap_fF_sum": {
            "prelayout": round(sum(r["prelayout_fF"] for r in found), 2),
            "extracted": round(sum(r["extracted_total_fF"] for r in found), 2)},
        "coupling_between_named_nets_by_domain": domain_coupling(
            kept, os.path.join(REPO, "build", variant, "graph.json")),
        "resistance": "none (C-only extraction)",
        "flat_spice_sha256": sha256_file(flat_path),
    }
    if provenance:
        stats.update(provenance)
    out_ports = dict(ports)
    out_ports["variant"] = variant + "_pex"
    out_ports["base_variant"] = variant
    out_ports["description"] = ports.get("description", "") + " (post-layout extraction)"
    for k in ("wire_cap_fF", "wire_cap_per_fanout_fF"):
        out_ports[k] = None
    out_ports["wire_cap_note"] = ("post-layout: parasitic capacitance extracted by Magic from the "
                                  "layout (to substrate and coupling), no estimate")
    out_ports["pex"] = stats
    with open(os.path.join(out_dir, "ports.json"), "w") as f:
        json.dump(out_ports, f, indent=1)
    graph = os.path.join(REPO, "build", variant, "graph.json")
    if os.path.exists(graph):
        with open(graph) as f:
            g = json.load(f)
        g["note"] = ("copy of build/%s/graph.json for the post-layout netlist dut.sp: the logical "
                     "netlist and net names are the same; wire_cap, load caps and delays are the "
                     "pre-layout estimates, not the extraction" % variant)
        with open(os.path.join(out_dir, "graph.json"), "w") as f:
            json.dump(g, f, indent=1)
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--variant", required=True, help="N, DA, U or D")
    ap.add_argument("--flat", help="Magic flat netlist [runs/pex/ext/<V>/dut_<V>_flat.spice]")
    ap.add_argument("--out", help="output directory [build/<V>_pex]")
    ap.add_argument("--drop-supply-devices", action="store_true",
                    help="leave out transistors with all terminals on VPWR/VGND (decaps)")
    a = ap.parse_args(argv)
    v = a.variant
    flat = a.flat or os.path.join(REPO, "runs", "pex", "ext", v, "dut_%s_flat.spice" % v)
    out = a.out or os.path.join(REPO, "build", v + "_pex")
    gds = os.path.join(REPO, "runs", "pex", "ol", v, "runs", "pex", "results", "final", "gds",
                       "dut_%s.gds" % v)
    prov = {"gds_sha256": sha256_file(gds)} if os.path.exists(gds) else {}
    stats = build(v, flat, out, a.drop_supply_devices,
                  os.path.join(REPO, "results", "pex", "netcap_%s.csv" % v), prov)
    print("%s: %d devices %s, %d supply-only (%d dropped), %d caps %s" % (
        os.path.relpath(out, REPO), stats["n_devices"], stats["devices"],
        stats["supply_only_devices"], stats["supply_only_devices_dropped"],
        stats["caps_fF"]["count"], {k: v for k, v in stats["caps_fF"].items() if k != "count"}))
    print("named nets: %d of %d found; cap sum pre-layout %.1f fF, extracted %.1f fF" % (
        stats["named_nets_with_extracted_cap"], stats["named_nets_prelayout"],
        stats["named_nets_cap_fF_sum"]["prelayout"], stats["named_nets_cap_fF_sum"]["extracted"]))


if __name__ == "__main__":
    main()
