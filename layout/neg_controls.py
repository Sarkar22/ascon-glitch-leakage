# SPDX-License-Identifier: Apache-2.0
"""Negative controls of the layout sign-off: LVS against wrong netlists, DRC on a damaged GDS.

A clean DRC and an LVS match only mean something if the same checks fail when the layout or the
netlist is wrong. layout/run_controls.sh runs the checks; this script makes the wrong netlists
and turns the tool reports into results/layout/negative_controls.json.

  python3 layout/neg_controls.py mutants --variant N      # runs/controls/<V>/*.v + mutations.json
  python3 layout/neg_controls.py summarize [N DA]         # results/layout/negative_controls.json

LVS cases (netgen, the OpenLane v1 setup: sky130A_setup.tcl, the layout netlist that Magic
extracts from the committed final GDS results/layout/gds/dut_<V>.gds):
  correct      OpenLane's final powered netlist (the one its own LVS step used)     -> must match
  share_swap   one input of the first cross-domain gate (inputs from share 0 and share 1, first
               by instance name) moved from its share-0 net to the share-1 net of the same name
               (e.g. as0_0 -> as1_0)                                                 -> must fail
  gate_type    the first and2_1 (by instance name) turned into an or2_1 (same pins) -> must fail
  missing_ff   the first flip-flop (dfxtp_1, by instance name) deleted             -> must fail
DRC case: layout/controls/inject_drc.py adds a met1 spacing and a via1 enclosure violation to a
copy of the GDS; Magic (layout/controls/magic_drc.tcl, OpenLane's signoff commands) and KLayout
(the PDK's sky130A_mr.drc deck, as layout/run_klayout.sh runs it) must report those two and
nothing else, and 0 on the unchanged GDS.
Host python3, standard library only.
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTL = os.path.join(REPO, "runs", "controls")
CASES = ("correct", "share_swap", "gate_type", "missing_ff")
EXPECT = {"correct": "match", "share_swap": "mismatch", "gate_type": "mismatch",
          "missing_ff": "mismatch"}
INST_RE = re.compile(r"\b(sky130_\w+)\s+(\\\S+|\w+)\s*\((.*?)\)\s*;", re.S)


def run_dir(v):
    return os.path.join(REPO, "runs", "pex", "ol", v, "runs", "pex")


def final_netlist(v):
    return os.path.join(run_dir(v), "results", "final", "verilog", "gl", "dut_%s.v" % v)


def same_text(a, b):
    """Two netlists equal up to whitespace."""
    with open(a) as f, open(b) as g:
        return f.read().split() == g.read().split()


def same_spice(a, b):
    """Two SPICE netlists equal apart from comment lines."""
    def body(p):
        with open(p) as f:
            return [line for line in f if not line.startswith("*")]
    return body(a) == body(b)


def instances(text):
    """Structural Verilog -> [(cell, name, span of the whole statement, {pin: net})]."""
    out = []
    for m in INST_RE.finditer(text):
        pins = {p: n.lstrip("\\") for p, n in
                re.findall(r"\.(\w+)\s*\(\s*(\\\S+|[\w\[\]]*)\s*\)", m.group(3))}
        out.append((m.group(1), m.group(2).lstrip("\\"), m.span(), pins))
    return out


def replace_pin(text, name, pin, old, new):
    """Reconnect pin `pin` of instance `name` from net `old` to net `new` (exactly one place)."""
    for cell, n, (a, b), pins in instances(text):
        if n == name:
            stmt = text[a:b]
            pat = re.compile(r"(\.%s\s*\(\s*)%s(\s*\))" % (re.escape(pin), re.escape(old)))
            new_stmt, k = pat.subn(r"\g<1>%s\g<2>" % new, stmt)
            if k != 1:
                raise ValueError("%s.%s is not connected to %s" % (name, pin, old))
            return text[:a] + new_stmt + text[b:]
    raise ValueError("instance %s not found" % name)


def share_swap(text, graph):
    """Move the share-0 input of the first cross-domain gate to the share-1 net of that name."""
    types, nets = graph["cell_types"], graph["nets"]
    for c in sorted(graph["cells"], key=lambda c: c["name"]):
        t = types[c["type"]]
        if t["sequential"]:
            continue
        doms = {p: nets[c["pins"][p]]["domain"] for p in t["inputs"]}
        if sorted(doms.values()) != ["s0", "s1"]:
            continue
        pin = next(p for p in t["inputs"] if doms[p] == "s0")
        old = c["pins"][pin]
        new = old.replace("s0", "s1", 1)
        if nets.get(new, {}).get("domain") != "s1" or new in c["pins"].values():
            continue
        info = {"instance": c["name"], "cell": c["type"], "pin": pin, "from_net": old,
                "to_net": new, "from_domain": "s0", "to_domain": "s1",
                "inputs_before": {p: c["pins"][p] for p in t["inputs"]}}
        return replace_pin(text, c["name"], pin, old, new), info
    raise ValueError("no cross-domain gate with a share-1 counterpart net")


def gate_type(text, old="sky130_fd_sc_hd__and2_1", new="sky130_fd_sc_hd__or2_1"):
    """Change the cell type of the first `old` instance (by name) to `new` (same pin names)."""
    cands = sorted((n, a) for cell, n, (a, b), _ in instances(text) if cell == old)
    if not cands:
        raise ValueError("no %s instance" % old)
    name, a = cands[0]
    assert text[a:a + len(old)] == old
    return text[:a] + new + text[a + len(old):], {"instance": name, "from_cell": old,
                                                  "to_cell": new}


def missing_ff(text, cell="sky130_fd_sc_hd__dfxtp_1"):
    """Delete the first flip-flop instance (by name), statement and line break."""
    cands = sorted((n, a, b, pins) for c, n, (a, b), pins in instances(text) if c == cell)
    if not cands:
        raise ValueError("no %s instance" % cell)
    name, a, b, pins = cands[0]
    a = text.rfind("\n", 0, a) + 1            # from the start of its line
    if text[b:b + 1] == "\n":
        b += 1
    return text[:a] + text[b:], {"instance": name, "cell": cell,
                                 "D": pins.get("D"), "Q": pins.get("Q")}


def make_mutants(v, src=None, out_dir=None):
    src = src or final_netlist(v)
    out_dir = out_dir or os.path.join(CTL, v)
    with open(src) as f:
        ref = f.read()
    with open(os.path.join(REPO, "build", v, "graph.json")) as f:
        graph = json.load(f)
    lvs_in = os.path.join(run_dir(v), "tmp", "signoff", "29-dut_%s.pnl.v" % v)
    texts = {"correct": ref}
    info = {"correct": {"source": "OpenLane's final powered netlist, runs/pex/ol/%s/runs/pex/"
                                  "results/final/verilog/gl/dut_%s.v" % (v, v),
                        "same_as_openlane_lvs_input": (same_text(src, lvs_in)
                                                       if os.path.exists(lvs_in) else None)}}
    texts["share_swap"], info["share_swap"] = share_swap(ref, graph)
    texts["gate_type"], info["gate_type"] = gate_type(ref)
    texts["missing_ff"], info["missing_ff"] = missing_ff(ref)
    os.makedirs(out_dir, exist_ok=True)
    for case, t in texts.items():
        with open(os.path.join(out_dir, case + ".v"), "w") as f:
            f.write(t)
    n_ref = len(instances(ref))
    for case in CASES:
        info[case]["instances"] = len(instances(texts[case]))
        info[case]["instances_correct"] = n_ref
    with open(os.path.join(out_dir, "mutations.json"), "w") as f:
        json.dump(info, f, indent=1)
    return info


def parse_netgen(log_text, out_text=""):
    """netgen LVS log (and its stdout) -> verdict and the top cell's device/net counts.

    The verdict is the last "Final result" of the log (the top cell is compared last). The counts
    come from the last "Circuit 1 contains ..." lines of the stdout; when netgen cannot match a
    cell class it flattens it, so after a mismatch they may count transistors, not cells.
    """
    finals = re.findall(r"Final result:\s*(.+)", log_text)
    final = finals[-1].strip().rstrip(".") if finals else None
    text = out_text or log_text
    dev = re.findall(r"Circuit 1 contains (\d+) devices,\s*Circuit 2 contains (\d+) devices", text)
    net = re.findall(r"Circuit 1 contains (\d+) nets,\s*Circuit 2 contains (\d+) nets", text)
    low = (final or "").lower()
    ok = "match uniquely" in low and "property" not in low and "not" not in low
    return {"verdict": "match" if ok else "mismatch", "final_result": final,
            "devices_layout_vs_netlist": [int(x) for x in dev[-1]] if dev else None,
            "nets_layout_vs_netlist": [int(x) for x in net[-1]] if net else None}


def parse_magic_drc(text):
    """magic_drc.tcl report -> [{'box_um': [...], 'rule': ...}], reported COUNT."""
    items, count = [], None
    for line in text.splitlines():
        if line.startswith("COUNT"):
            count = int(line.split()[1])
            continue
        if "\t" in line:
            coords, rule = line.split("\t", 1)
            items.append({"box_um": [float(x) for x in coords.split()[:4]], "rule": rule})
    return items, count


def parse_lyrdb(text):
    """KLayout report database -> [{'box_um': bbox of the marker, 'rule': category}]."""
    root = ET.fromstring(text)
    items = []
    for it in root.iter("item"):
        cat = (it.findtext("category") or "").strip().strip("'")
        nums = []
        for val in it.iter("value"):
            nums += [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?",
                                                  (val.text or "").split(":", 1)[-1])]
        xs, ys = nums[0::2], nums[1::2]
        box = [min(xs), min(ys), max(xs), max(ys)] if xs else None
        items.append({"box_um": box, "rule": cat})
    return items


def inside(box, bbox, margin=0.3):
    return (box is not None and box[0] >= bbox[0] - margin and box[1] >= bbox[1] - margin
            and box[2] <= bbox[2] + margin and box[3] <= bbox[3] + margin)


def check_drc(items, injected):
    """Every marker must sit on an injected structure, and every structure must be flagged."""
    per = {s["name"]: [] for s in injected}
    stray = []
    for it in items:
        hit = [s["name"] for s in injected if inside(it["box_um"], s["bbox_um"])]
        if hit:
            per[hit[0]].append(it["rule"])
        else:
            stray.append(it)
    return {"markers": len(items),
            "markers_by_structure": {k: {"n": len(r), "rules": sorted(set(r))}
                                     for k, r in per.items()},
            "markers_elsewhere": len(stray), "stray_examples": stray[:5],
            "exactly_the_injected": not stray and all(per.values())}


def read(path):
    with open(path) as f:
        return f.read()


def summarize(variants, drc_variant="N"):
    res = {"description": "Negative controls of the layout sign-off (layout/neg_controls.py, "
                          "layout/run_controls.sh): the same LVS and DRC checks that pass on "
                          "the real layout must fail on a wrong netlist and a damaged GDS.",
           "tools": "OpenLane v1 image ff5509f: Magic 8.3.413, netgen 1.5.255, KLayout 0.28.2; "
                    "sky130A (ciel 0fe599b2)",
           "lvs": {}, "drc": {}}
    all_ok = True
    for v in variants:
        d = os.path.join(CTL, v)
        muts = json.loads(read(os.path.join(d, "mutations.json")))
        rows = {}
        for case in CASES:
            r = parse_netgen(read(os.path.join(d, "lvs_%s.log" % case)),
                             read(os.path.join(d, "lvs_%s.out" % case)))
            r["expected"] = EXPECT[case]
            r["as_expected"] = r["verdict"] == EXPECT[case]
            r["change"] = {k: x for k, x in muts[case].items()
                           if k not in ("instances_correct",)}
            r["change"]["instances_in_netlist"] = r["change"].pop("instances")
            all_ok &= r["as_expected"]
            rows[case] = r
        ol = os.path.join(run_dir(v), "results", "signoff", "dut_%s.gds.spice" % v)
        res["lvs"][v] = {"layout_netlist": "Magic LVS extraction of results/layout/gds/dut_%s.gds"
                                           " (layout/controls/lvs_extract.tcl)" % v,
                         "layout_netlist_same_as_openlane_signoff":
                             same_spice(os.path.join(d, "layout.spice"), ol)
                             if os.path.exists(ol) else None,
                         "cases": rows}
    d = os.path.join(CTL, "drc")
    inj = json.loads(read(os.path.join(d, "injected.json")))
    for g in ("clean", "injected"):
        m_items, m_count = parse_magic_drc(read(os.path.join(d, "magic_%s.rpt" % g)))
        k_items = parse_lyrdb(read(os.path.join(d, "klayout_%s.lyrdb" % g)))
        if g == "clean":
            res["drc"]["clean"] = {"gds": "results/layout/gds/dut_%s.gds" % drc_variant,
                                   "magic_markers": len(m_items), "magic_count": m_count,
                                   "klayout_markers": len(k_items)}
            all_ok &= not m_items and not k_items
        else:
            mc, kc = check_drc(m_items, inj["injected"]), check_drc(k_items, inj["injected"])
            res["drc"]["injected"] = {
                "magic_note": ("Magic's via1 contact type includes the 0.055 um via.4a "
                               "enclosure, so its message counts the missing surround from "
                               "that edge"),
                "gds": "copy of results/layout/gds/dut_%s.gds with two added structures "
                       "(layout/controls/inject_drc.py)" % drc_variant,
                "structures": inj["injected"], "cell_rows_bbox_um": inj.get("cell_rows_bbox_um"),
                "magic": mc, "klayout": kc}
            all_ok &= mc["exactly_the_injected"] and kc["exactly_the_injected"]
    res["all_as_expected"] = bool(all_ok)
    return res


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["mutants"]:
        v = argv[argv.index("--variant") + 1] if "--variant" in argv else "N"
        info = make_mutants(v)
        for case in CASES[1:]:
            print(v, case, {k: x for k, x in info[case].items() if not k.startswith("instances")})
    elif argv[:1] == ["summarize"]:
        variants = argv[1:] or ["N", "DA"]
        res = summarize(variants, variants[0])
        out = os.path.join(REPO, "results", "layout", "negative_controls.json")
        with open(out, "w") as f:
            json.dump(res, f, indent=1)
        for v in variants:
            for case, r in res["lvs"][v]["cases"].items():
                print("LVS %-3s %-10s %-8s (expected %s) %s" % (
                    v, case, r["verdict"], r["expected"], r["final_result"]))
        c, i = res["drc"]["clean"], res["drc"]["injected"]
        print("DRC clean: Magic %d, KLayout %d markers" % (
            c["magic_markers"], c["klayout_markers"]))
        for tool in ("magic", "klayout"):
            print("DRC injected, %s: %s" % (tool, json.dumps(i[tool]["markers_by_structure"])))
        print("all as expected:", res["all_as_expected"], "->", os.path.relpath(out, REPO))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
