# SPDX-License-Identifier: Apache-2.0
"""Build the RC bracket of a post-layout netlist: Magic's resistor networks plus the C-only
extraction's capacitance, wrapped as a DUT of sim/spice_campaign.py.

  python3 layout/make_pex_rc.py --variant N --rc runs/pex/rc/ext_N_rc/dut_N_flat.spice \
      --out runs/pex/rc/N_rc [--conly runs/pex/ext/N/dut_N_flat.spice]

Inputs: the flat netlist of layout/pex/extract_rc.tcl (Magic extresist: every transistor, and a
resistor network per net through its routing, vias, contacts and the cells' poly and li1) and the
flat netlist of layout/pex/extract.tcl (C-only, the source of build/<V>_pex).
Why both: Magic 8.3.413 does not carry all of the capacitance into the extresist netlist. Coupling
capacitors that touch a resistor-extracted node are dropped and most new network nodes get no
capacitance, so for N it keeps 745 of the 1,032 fF of the C-only extraction. Simulated as it is,
that netlist would show the effect of lost capacitance, not of resistance. So this script
  - keeps the RC netlist's transistors and resistors and drops its capacitors;
  - adds every capacitor of the C-only netlist: one between a net with nodes a_1..a_p and a
    supply rail (one node) becomes p capacitors c/p, one on each node of the net's resistor
    network; a coupling capacitor between two signal nets goes between one node of each net (the
    node that carries the net's own name if there is one), see redistribute(). Capacitors below
    0.01 fF are not split.
So the capacitance per pair of nets equals the C-only netlist's exactly, the transistors are the
same (names, models and nets checked; parameters taken from the C-only netlist), and the only
additions are the resistors and the placement of each net's capacitance on its network (the
capacitance to the rails uniform over the nodes, not by geometry).
Node names: extresist splits a net into nodes <net>.n<k> and <net>.t<k> (device terminals); a
routed net keeps a node of its own name, so xdut.<net> can still be probed.
The wrapper is layout/make_pex.py's build() (port order of build/<V>/ports.json, ngspice-safe
names, graph.json copied); results/pex/netcap_<V>.csv is not written. The output goes under runs/
(git-ignored): this netlist is a sanity bracket, not a campaign netlist. Host python3.
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_pex  # noqa: E402

REPO = make_pex.REPO
MIN_SPLIT_FF = 0.01


def net_of(node):
    """Magic node name -> net: 'm01_0.n3' -> 'm01_0', 'a_75_69.t0' and 'a_75_69#' -> 'a_75_69'."""
    b = node.split(".")[0]
    return b[:-1] if b.endswith("#") else b


def ohms(word):
    """'300.296', '1.2k', '4meg', '0.5m' -> ohms."""
    m = re.fullmatch(r"([-+0-9.eE]+)(meg|[a-zA-Z]?)", word.lower())
    if not m:
        raise ValueError("cannot read resistance %r" % word)
    scale = {"": 1.0, "k": 1e3, "meg": 1e6, "m": 1e-3, "g": 1e9}[m.group(2)]
    return float(m.group(1)) * scale


def resistor_stats(elements, supplies=make_pex.SUPPLY):
    """Counts and totals of the resistors, and the nets that have them."""
    vals, nets = [], set()
    for kind, _, nodes, _, params in elements:
        if kind == "R":
            vals.append(ohms(params[0]))
            nets.update(net_of(n) for n in nodes)
    vals.sort()
    if not vals:
        return {"count": 0, "nets_with_resistors": 0, "supply_nets_with_resistors": []}
    return {"count": len(vals), "total_ohm": round(sum(vals), 1),
            "median_ohm": round(vals[len(vals) // 2], 2), "max_ohm": round(vals[-1], 1),
            "nets_with_resistors": len(nets),
            "supply_nets_with_resistors": sorted(n for n in nets if n in supplies)}


def align_devices(rc_elements, c_elements):
    """Give each RC transistor the parameters of the C-only transistor of the same name.

    Both extractions come from the same GDS with the same commands, so the transistors have the
    same names, models and terminal nets (checked: a mismatch raises). Magic's extresist run
    assigns a whole supply rail's diffusion to the source of a few decap transistors whose source
    and bulk are the same rail (no electrical effect); taking the C-only values makes the two
    netlists' transistors identical. Returns the new element list and the names that differed.
    """
    cdev = {e[1]: e for e in c_elements if e[0] == "X"}
    rdev = [e for e in rc_elements if e[0] == "X"]
    if set(cdev) != {e[1] for e in rdev} or len(rdev) != len(cdev):
        raise ValueError("RC and C-only netlists have different transistor names")
    out, changed = [], []
    for e in rc_elements:
        if e[0] == "X":
            c = cdev[e[1]]
            if (c[3], [net_of(n) for n in c[2]]) != (e[3], [net_of(n) for n in e[2]]):
                raise ValueError("transistor %s differs between RC and C-only" % e[1])
            if c[4] != e[4]:
                changed.append(e[1])
            e = (e[0], e[1], e[2], e[3], c[4])
        out.append(e)
    return out, changed


def network_nodes(elements):
    """net -> sorted node names of the RC netlist (nodes of its transistors and resistors)."""
    nodes = collections.defaultdict(set)
    for kind, _, ns, _, _ in elements:
        if kind in "XR":
            for n in ns:
                nodes[net_of(n)].add(n)
    return {k: sorted(v, key=lambda n: (n != k, n)) for k, v in nodes.items()}   # own name first


def redistribute(rc_elements, c_elements, min_split=MIN_SPLIT_FF, supplies=make_pex.SUPPLY):
    """RC transistors and resistors + the C-only capacitors placed on the networks' nodes.

    A capacitor between a net and a supply rail is split evenly over the net's nodes. A coupling
    capacitor between two signal nets is placed between one node of each (the node with the net's
    own name if there is one): splitting it over both networks ties them into a dense mesh whose
    LU factorization costs about 300 times more (measured for N with ngspice's KLU: 355 ms per
    factorization instead of 1.1 ms; C-only 0.63 ms), while the placement error is about
    R x C_coupling (100 ohm x 0.1 fF = 0.01 ps). Capacitors below min_split fF are not split
    either.
    """
    nodes = network_nodes(rc_elements)
    out = [e for e in rc_elements if e[0] != "C"]
    dropped = [make_pex.cap_value_fF(e[4][0]) for e in rc_elements if e[0] == "C"]
    k, total, n_src = 0, 0.0, 0
    split = {"rail_split_fF": 0.0, "rail_not_split_fF": 0.0, "coupling_one_node_fF": 0.0,
             "rail_to_rail_fF": 0.0}
    for kind, _, ns, _, params in c_elements:
        if kind != "C":
            continue
        n_src += 1
        c = make_pex.cap_value_fF(params[0])
        la, lb = (nodes.get(net_of(n)) for n in ns)
        if not la or not lb:
            raise ValueError("C-only nodes %s have no node in the RC netlist" % ns)
        sa, sb = (net_of(n) in supplies for n in ns)
        if sa and sb:
            pieces, key = [(la[0], lb[0])], "rail_to_rail_fF"
        elif not (sa or sb):
            pieces, key = [(la[0], lb[0])], "coupling_one_node_fF"
        elif c < min_split:
            pieces, key = [(la[0], lb[0])], "rail_not_split_fF"
        else:
            m = max(len(la), len(lb))            # the rail side has one node
            pieces = [(la[i % len(la)], lb[i % len(lb)]) for i in range(m)]
            key = "rail_split_fF"
        split[key] += c
        for x, y in pieces:
            out.append(("C", "Cr%d" % k, [x, y], None, ["%.6gf" % (c / len(pieces))]))
            k += 1
        total += c
    stats = {"magic_rc_capacitors_dropped": len(dropped),
             "magic_rc_capacitance_fF": round(sum(dropped), 2),
             "c_only_capacitors": n_src, "c_only_capacitance_fF": round(total, 2),
             "capacitors_written": k, "not_split_below_fF": min_split,
             "network_nodes": sum(len(v) for v in nodes.values()), "nets": len(nodes)}
    stats.update({key: round(v, 2) for key, v in split.items()})
    return out, stats


def write_flat(path, name, ports, elements):
    lines = ["* flat RC netlist: layout/make_pex_rc.py (RC transistors and resistors, C-only "
             "capacitance)", ".subckt %s %s" % (name, " ".join(ports))]
    for kind, ename, nodes, model, params in elements:
        if kind == "X":
            lines.append("%s %s %s %s" % (ename, " ".join(nodes), model, " ".join(params)))
        else:
            lines.append("%s %s %s" % (ename, " ".join(nodes), " ".join(params)))
    lines.append(".ends")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def header(variant, rstats, cstats, keep):
    return [
        "* SPDX-License-Identifier: Apache-2.0",
        "* %s post-layout RC bracket (layout/run_pex_rc.sh, layout/make_pex_rc.py); do not edit."
        % variant,
        "* Transistors and resistor networks from Magic extresist (layout/pex/extract_rc.tcl):",
        "* %d resistors (%.0f ohm in total) on %d nets; the supply rails have none (one ideal"
        % (rstats["count"], rstats.get("total_ohm", 0.0), rstats["nets_with_resistors"]),
        "* node each, as in the C-only netlist).",
        "* Capacitance: the C-only extraction's %d capacitors (%.1f fF); capacitance to a rail"
        % (cstats["c_only_capacitors"], cstats["c_only_capacitance_fF"]),
        "* split evenly over the net's network nodes, coupling between signal nets at one node",
        "* of each net. Ports in the order of build/%s/ports.json; each routed net keeps a node"
        % variant,
        "* of its own name.",
    ] + keep


def build(variant, rc_flat, c_flat, out_dir, min_split=MIN_SPLIT_FF):
    name, ports, rc_el = make_pex.parse_flat(rc_flat)
    cname, cports, c_el = make_pex.parse_flat(c_flat)
    if (name, ports) != (cname, cports):
        raise ValueError("RC and C-only netlists have different subckt names or ports")
    rstats = resistor_stats(rc_el)
    if rstats["supply_nets_with_resistors"]:
        raise ValueError("supply nets %s have resistors: the capacitance rebuild needs one "
                         "node per rail (extract with PEX_RIGNORE='VPWR VGND')"
                         % rstats["supply_nets_with_resistors"])
    rc_el, changed = align_devices(rc_el, c_el)
    elements, cstats = redistribute(rc_el, c_el, min_split)
    os.makedirs(out_dir, exist_ok=True)
    merged = os.path.join(out_dir, "flat_rc_merged.spice")
    write_flat(merged, name, ports, elements)
    prov = {"rc_flat_spice_sha256": make_pex.sha256_file(rc_flat),
            "c_only_flat_spice_sha256": make_pex.sha256_file(c_flat)}
    stats = make_pex.build(variant, merged, out_dir, netcap_csv=None, provenance=prov)
    sp = os.path.join(out_dir, "dut.sp")
    with open(sp) as f:
        lines = f.read().split("\n")
    k = next(i for i, line in enumerate(lines) if line.lower().startswith(".subckt"))
    keep = [line for line in lines[:k] if line.startswith(("* Needs", "* Devices", "* extraction"))]
    with open(sp, "w") as f:
        f.write("\n".join(header(variant, rstats, cstats, keep) + lines[k:]))
    pj = os.path.join(out_dir, "ports.json")
    with open(pj) as f:
        pdata = json.load(f)
    pdata["variant"] = variant + "_rc"
    pdata["description"] = pdata["description"].replace("(post-layout extraction)",
                                                        "(post-layout RC bracket)")
    pdata["pex"]["source"] = ("Magic extresist netlist (layout/pex/extract_rc.tcl) with the "
                              "C-only extraction's capacitance (layout/make_pex_rc.py)")
    pdata["pex"]["resistance"] = "resistor networks from Magic extresist"
    pdata["pex"]["resistors"] = rstats
    pdata["pex"]["capacitance_rebuild"] = cstats
    pdata["pex"]["devices_identical_to_c_only"] = True
    pdata["pex"]["device_parameters_taken_from_c_only"] = changed
    with open(pj, "w") as f:
        json.dump(pdata, f, indent=1)
    stats.update(resistors=rstats, capacitance_rebuild=cstats, devices_identical_to_c_only=True,
                 device_parameters_taken_from_c_only=changed)
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--variant", required=True)
    ap.add_argument("--rc", required=True, help="flat netlist of layout/pex/extract_rc.tcl")
    ap.add_argument("--conly", help="flat C-only netlist [runs/pex/ext/<V>/dut_<V>_flat.spice]")
    ap.add_argument("--out", required=True, help="output directory (under runs/)")
    ap.add_argument("--min-split", type=float, default=MIN_SPLIT_FF,
                    help="capacitors below this (fF) are not split [%(default)s]")
    a = ap.parse_args(argv)
    conly = a.conly or os.path.join(REPO, "runs", "pex", "ext", a.variant,
                                    "dut_%s_flat.spice" % a.variant)
    st = build(a.variant, a.rc, conly, a.out, a.min_split)
    r, c = st["resistors"], st["capacitance_rebuild"]
    print("%s: %d devices; %d resistors (%.0f ohm) on %d nets; transistor parameters taken "
          "from the C-only netlist for %s" % (
              os.path.relpath(os.path.abspath(a.out), REPO), st["n_devices"], r["count"],
              r.get("total_ohm", 0), r["nets_with_resistors"],
              st["device_parameters_taken_from_c_only"] or "none"))
    print("capacitance: Magic RC kept %.1f fF (dropped), C-only %.1f fF -> %d capacitors; "
          "to the rails split %.1f fF, coupling at one node %.1f fF" % (
              c["magic_rc_capacitance_fF"], c["c_only_capacitance_fF"], c["capacitors_written"],
              c["rail_split_fF"], c["coupling_one_node_fF"]))


if __name__ == "__main__":
    main()
