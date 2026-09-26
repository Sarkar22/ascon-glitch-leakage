# SPDX-License-Identifier: Apache-2.0
"""RC bracket of the C-only post-layout netlist: the same stimulus rows through both, compared.

  bash layout/run_pex_rc.sh N                       # runs/pex/rc/N_rc (layout/make_pex_rc.py)
  S=runs/kt/stim/M_tvla.npy; O="--jobs 4 --threads 1"
  bash sim/docker_run.sh python3 sim/spice_campaign.py run --dut build/N_pex --stim $S \
      --out runs/pex/rc/sim_N_c --rows 120 --chunk 30 --options klu --save-outputs $O
  (the same with --dut runs/pex/rc/N_rc --out runs/pex/rc/sim_N_rc)
  bash sim/docker_run.sh python3 analysis/spice_nodes.py --dut build/N_pex --stim $S --rows 40 \
      --chunk 10 --out runs/pex/rc/nodes_N_c $O      (the same with runs/pex/rc/N_rc -> nodes_N_rc)
  python3 layout/rc_check.py --variant N            # -> results/pex/rc_check.json

This is a sanity bracket, not a TVLA: 120 rows cannot show or rule out a first-order leak. It
asks whether adding wire, via and in-cell resistance to the extracted netlist changes the supply
current or the timing enough to question the C-only campaigns. Reported (RC against C-only;
the C-only run is also compared with the first rows of its campaign, c_only_vs_campaign):
  function     registered outputs of both runs against the S-box, and against each other
  charge       charge per window: (RC - C) / C per row (mean, min, max) and the correlation of the
               data-dependent part (charge minus its mean over rows)
  waveform     10 ps traces over the whole window: largest and mean |RC - C| per bin (uA) against
               the peak current; correlation of the mean trace; correlation of the data-dependent
               part (each row minus the mean trace), at no shift and at the best shift of the mean
               trace; the class-mean difference (fixed minus random mean current, the numerator of
               the TVLA t on these rows): correlation and largest |RC - C| (against C's own
               largest value), unshifted and at that shift, and where each peaks
  current_timing  layout/validate_pex.py's timing block (peak, 50/90/99 % charge times, best
               shift) with RC in place of "pex" and C-only in place of "pre"
  net_timing   node runs of the first 40 rows (first latency+1 rows dropped): per cycle the last
               crossing of any logic net, per flip-flop the clock-to-Q time, per logic net and
               cycle its last crossing, and the number of crossings (glitches included); RC minus
               C for each matched pair
Host python3 with numpy.
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import validate_pex  # noqa: E402
import node_timing  # noqa: E402

REPO = validate_pex.REPO


def rel(p):
    return os.path.relpath(os.path.abspath(p), REPO)


def corr(a, b):
    a, b = np.asarray(a, float).ravel(), np.asarray(b, float).ravel()
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum()))


def q(x, p):
    return round(float(np.percentile(x, p)), 4)


def stat(x):
    x = np.asarray(x, float)
    return {"n": int(x.size), "median": q(x, 50), "mean": round(float(x.mean()), 4),
            "min": round(float(x.min()), 4), "max": round(float(x.max()), 4)}


def rename(obj, words={"pex": "rc", "pre": "c_only"}):
    """validate_pex output with RC/C-only names ('pex' -> 'rc', 'pre' -> 'c_only' in keys)."""
    if isinstance(obj, dict):
        return {"_".join(words.get(w, w) for w in k.split("_")): rename(v, words)
                for k, v in obj.items()}
    return obj


def waveform(tc, tr, labels, dt, pre):
    """Traces (rows, samples) of C-only and RC on the same rows -> comparison dict."""
    mc, mr = tc.mean(0), tr.mean(0)
    dc, dr = tc - mc, tr - mr
    shift, c_at = validate_pex.best_shift(mc, mr, dt)
    s = int(round(shift / dt))

    def align(c, r):
        """Crop so that sample j of c lines up with sample j + s of r (RC later by s)."""
        n = c.shape[-1]
        if s > 0:
            return c[..., :n - s], r[..., s:]
        if s < 0:
            return c[..., -s:], r[..., :n + s]
        return c, r

    dcs, drs = align(dc, dr)
    fc = tc[labels == 0].mean(0) - tc[labels == 1].mean(0)
    fr = tr[labels == 0].mean(0) - tr[labels == 1].mean(0)
    fcs, frs = align(fc, fr)

    def at(x):
        return round((int(np.argmax(np.abs(x))) + 0.5) * dt - pre, 3)

    diff = np.abs(tr - tc)
    return {
        "peak_current_uA": {"c_only": round(float(tc.max()), 1), "rc": round(float(tr.max()), 1)},
        "max_abs_diff_uA": round(float(diff.max()), 2),
        "mean_abs_diff_uA": round(float(diff.mean()), 3),
        "mean_trace_corr": round(corr(mc, mr), 6),
        "best_shift_ns_rc_later": shift, "mean_trace_corr_at_shift": c_at,
        "data_dependent_corr": round(corr(dc, dr), 6),
        "data_dependent_corr_at_shift": round(corr(dcs, drs), 6),
        "class_mean_diff": {
            "rows_fixed_random": [int((labels == 0).sum()), int((labels == 1).sum())],
            "corr": round(corr(fc, fr), 6),
            "corr_at_shift": round(corr(fcs, frs), 6),
            "max_abs_c_only_uA": round(float(np.abs(fc).max()), 2),
            "max_abs_rc_minus_c_uA": round(float(np.abs(fr - fc).max()), 2),
            "max_abs_rc_minus_c_at_shift_uA": round(float(np.abs(frs - fcs).max()), 2),
            "peak_ns_after_edge": {"c_only": at(fc), "rc": at(fr)}},
    }


def net_events(ev, graph):
    """Node-run events -> per cycle: last logic crossing, clock-to-Q per flip-flop, last crossing
    and crossing count per logic net (times in ns after the capturing edge)."""
    names = [str(n) for n in ev["net_names"]]
    pre, period = float(ev["pre"]), float(ev["period"])
    drop = int(ev["latency"]) + 1
    types = graph["cell_types"]
    kind = {}
    for c in graph["cells"]:
        t = types[c["type"]]
        if t.get("sequential"):
            kind[c["pins"]["Q"]] = "ff"
        else:
            kind[c["pins"][t["output"]]] = "logic"
    t = ev["t_ns"] - pre
    ok = (ev["cycle"] >= drop) & (t >= 0) & (t < period - pre)
    out = {}
    for net, cyc, tt in zip(ev["net"][ok], ev["cycle"][ok], t[ok]):
        k = kind.get(names[net])
        if k is None:
            continue
        d = out.setdefault(int(cyc), {"last_logic": None, "ff_first": {}, "net_last": {},
                                      "net_count": {}})
        name = names[net]
        if k == "ff":
            d["ff_first"][name] = min(d["ff_first"].get(name, np.inf), float(tt))
        else:
            d["net_last"][name] = max(d["net_last"].get(name, -np.inf), float(tt))
            d["net_count"][name] = d["net_count"].get(name, 0) + 1
            d["last_logic"] = max(d["last_logic"] or -np.inf, float(tt))
    return out


def net_timing(ev_c, ev_r, graph):
    if [str(n) for n in ev_c["net_names"]] != [str(n) for n in ev_r["net_names"]]:
        raise ValueError("the two node runs saved different nets")
    a, b = net_events(ev_c, graph), net_events(ev_r, graph)
    cycles = sorted(set(a) & set(b))
    last_c, last_r, ff, nets, cnt_c, cnt_r, unmatched = [], [], [], [], [], [], 0
    for c in cycles:
        if a[c]["last_logic"] is not None and b[c]["last_logic"] is not None:
            last_c.append(a[c]["last_logic"])
            last_r.append(b[c]["last_logic"])
        for n, tc in a[c]["ff_first"].items():
            if n in b[c]["ff_first"]:
                ff.append(b[c]["ff_first"][n] - tc)
        for n in set(a[c]["net_count"]) | set(b[c]["net_count"]):
            cnt_c.append(a[c]["net_count"].get(n, 0))
            cnt_r.append(b[c]["net_count"].get(n, 0))
            if n in a[c]["net_last"] and n in b[c]["net_last"]:
                nets.append(b[c]["net_last"][n] - a[c]["net_last"][n])
            else:
                unmatched += 1
    last_c, last_r = np.array(last_c), np.array(last_r)
    cnt_c, cnt_r = np.array(cnt_c), np.array(cnt_r)
    return {
        "cycles": len(cycles),
        "last_logic_crossing_ns": {"c_only": stat(last_c), "rc": stat(last_r),
                                   "rc_minus_c": stat(last_r - last_c)},
        "clk_to_q_rc_minus_c_ns": stat(ff),
        "per_net_last_crossing_rc_minus_c_ns": dict(stat(nets), p95_abs=q(np.abs(nets), 95)),
        "logic_crossings": {"c_only": int(cnt_c.sum()), "rc": int(cnt_r.sum()),
                            "net_cycles_with_different_count": int((cnt_c != cnt_r).sum()),
                            "net_cycles": int(cnt_c.size),
                            "net_cycles_switching_in_one_run_only": unmatched},
    }


def same_rows(run, campaign):
    """A short run against the first rows of a campaign on the same netlist (chunking differs)."""
    a = np.load(os.path.join(run, "traces.npy")).astype(float)
    b = np.load(os.path.join(campaign, "traces.npy"), mmap_mode="r")[:len(a)].astype(float)
    qa = np.load(os.path.join(run, "charge.npy"))
    qb = np.load(os.path.join(campaign, "charge.npy"))[:len(a)]
    res = {"campaign": rel(campaign), "rows": len(a),
           "max_abs_diff_uA": round(float(np.abs(a - b).max()), 3),
           "charge_max_rel_diff": float("%.3g" % np.abs(qa / qb - 1).max()),
           "data_dependent_corr": round(corr(a - a.mean(0), b - b.mean(0)), 8)}
    oa, ob = (os.path.join(d, "outputs.npy") for d in (run, campaign))
    if os.path.exists(oa) and os.path.exists(ob):
        res["outputs_equal"] = bool((np.load(oa) == np.load(ob)[:len(a)]).all())
    return res


def check(variant, c_dir, rc_dir, nodes_c=None, nodes_rc=None, meta=None, campaign=None):
    with open(os.path.join(REPO, "build", variant, "ports.json")) as f:
        ports = json.load(f)
    with open(os.path.join(REPO, "build", variant, "graph.json")) as f:
        graph = json.load(f)
    meta = meta or os.path.join(REPO, "runs", "kt", "stim", "M_tvla.meta.npz")
    m = np.load(meta)
    x, labels_all = m["x"], m["label"]
    man = {}
    for k, d in (("c_only", c_dir), ("rc", rc_dir)):
        with open(os.path.join(d, "manifest.json")) as f:
            man[k] = json.load(f)
    keys = ("params", "stimulus_sha256", "rows")
    same = {k: man["c_only"][k] == man["rc"][k] for k in keys}
    if not all(same.values()):
        raise ValueError("the two runs differ in %s" % [k for k, v in same.items() if not v])
    p = man["rc"]["params"]
    lat = man["rc"]["latency"]
    tc = np.load(os.path.join(c_dir, "traces.npy")).astype(float)
    tr = np.load(os.path.join(rc_dir, "traces.npy")).astype(float)
    qc = np.load(os.path.join(c_dir, "charge.npy"))
    qr = np.load(os.path.join(rc_dir, "charge.npy"))
    n = len(tc)
    drop = lat + 1                              # as in the campaigns' TVLA
    labels = labels_all[:n]
    res = {
        "what": ("RC bracket of the C-only post-layout netlist of %s on the same stimulus rows. "
                 "A sanity check of the extraction, not a TVLA: %d rows cannot show or rule out a "
                 "first-order leak." % (variant, n)),
        "netlists": {
            k: {"dut": man[k]["dut"], "dut_sp_sha256": man[k]["dut_sp_sha256"]}
            for k in ("c_only", "rc")},
        "runs": {"c_only": rel(c_dir), "rc": rel(rc_dir), "rows": n,
                 "stimulus": "runs/kt/stim/M_tvla.npy rows 0-%d" % (n - 1),
                 "solver": p["options"] or "sparse (default)", "corner": p["corner"],
                 "temp_C": p["temp"], "vdd": p["vdd"], "dt_ns": p["dt"], "chunk": p["chunk"],
                 "jobs": man["rc"].get("jobs"),
                 "s_per_cycle_per_process": {"c_only": man["c_only"].get("s_per_cycle_per_process"),
                                             "rc": man["rc"].get("s_per_cycle_per_process")},
                 "peak_rss_MB": {"c_only": man["c_only"].get("peak_rss_MB_max"),
                                 "rc": man["rc"].get("peak_rss_MB_max")}},
    }
    rc_ports = os.path.join(REPO, man["rc"]["dut"], "ports.json")
    if os.path.exists(rc_ports):
        with open(rc_ports) as f:
            pex = json.load(f)["pex"]
        res["netlists"]["rc"].update({k: pex.get(k) for k in (
            "resistors", "capacitance_rebuild", "devices_identical_to_c_only",
            "device_parameters_taken_from_c_only", "caps_fF")})

    cr = res["netlists"]["rc"].get("capacitance_rebuild") or {}
    res["method"] = {
        "extraction": ("Magic 8.3.413 extresist on every net except VPWR and VGND "
                       "(layout/pex/extract_rc.tcl, tolerance 10): resistor networks through the "
                       "routing, vias, contacts and the cells' poly and li1; the supply rails stay "
                       "one ideal node each, as in the C-only netlist and the testbench"),
        "capacitance": ("Magic's extresist netlist keeps only %s of the C-only extraction's "
                        "%s fF "
                        "(coupling to resistor-extracted nodes is dropped), so the RC netlist takes "
                        "its transistors and resistors and the C-only capacitors "
                        "(layout/make_pex_rc.py): capacitance to a supply rail (%s fF) split "
                        "evenly over the net's network nodes, coupling between signal nets "
                        "(%s fF) at one node of each net; the capacitance per pair of nets is the "
                        "C-only one" % (
                            cr.get("magic_rc_capacitance_fF"), cr.get("c_only_capacitance_fF"),
                            cr.get("rail_split_fF"), cr.get("coupling_one_node_fF"))),
        "reproducibility": ("Magic's extresist output is not byte-identical between runs (4,425 to "
                            "4,429 resistors, total within 0.005 % in five runs); the simulated "
                            "netlist is identified by its sha256 above"),
        "simulation": ("the unchanged runner, both netlists on the same rows, chunks and solver; "
                       "node runs with analysis/spice_nodes.py (default solver) on both"),
    }
    fn = {}
    outs = {}
    for k, d in (("c_only", c_dir), ("rc", rc_dir)):
        o = np.load(os.path.join(d, "outputs.npy"))
        outs[k] = o
        fn[k + "_mismatches_vs_sbox"] = int((validate_pex.SBOX_NP[x[:n]]
                                             != validate_pex.registered_value(o, ports)).sum())
    fn["rc_vs_c_only_output_bits_differing"] = int((outs["c_only"] != outs["rc"]).sum())
    fn["rows"] = n
    res["function"] = fn

    rd = (qr - qc) / qc
    res["charge"] = {
        "c_only_mean_fC": round(float(qc.mean()), 2), "rc_mean_fC": round(float(qr.mean()), 2),
        "rel_diff_rc_minus_c": {k: round(float(f(rd)), 6) for k, f in (
            ("mean", np.mean), ("min", np.min), ("max", np.max),
            ("max_abs", lambda z: np.abs(z).max()))},
        "corr_data_dependent": round(corr(qc, qr), 6)}
    res["waveform"] = dict(waveform(tc[drop:], tr[drop:], labels[drop:], p["dt"], p["pre"]),
                           rows_used=n - drop, note="first latency+1 rows dropped, as in TVLA")
    if campaign and os.path.exists(os.path.join(campaign, "traces.npy")):
        res["c_only_vs_campaign"] = same_rows(c_dir, campaign)
    vp = validate_pex.compare(os.path.abspath(rc_dir), os.path.abspath(c_dir), ports, x)
    res["current_timing"] = rename(vp["timing"])
    if nodes_c and nodes_rc:
        res["net_timing"] = dict(net_timing(node_timing.load(rel(nodes_c)),
                                            node_timing.load(rel(nodes_rc)), graph),
                                 runs={"c_only": rel(nodes_c), "rc": rel(nodes_rc)})
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--variant", default="N")
    d = os.path.join(REPO, "runs", "pex", "rc")
    ap.add_argument("--c", help="C-only run [runs/pex/rc/sim_<V>_c]")
    ap.add_argument("--rc", help="RC run [runs/pex/rc/sim_<V>_rc]")
    ap.add_argument("--nodes-c", help="C-only node run [runs/pex/rc/nodes_<V>_c]")
    ap.add_argument("--nodes-rc", help="RC node run [runs/pex/rc/nodes_<V>_rc]")
    ap.add_argument("--campaign", help="C-only campaign on the same stimulus, to tie the "
                    "C-only run to it [runs/pex/<V>_pex_tvla]")
    ap.add_argument("--out", default=os.path.join(REPO, "results", "pex", "rc_check.json"))
    a = ap.parse_args(argv)
    v = a.variant
    c = a.c or os.path.join(d, "sim_%s_c" % v)
    r = a.rc or os.path.join(d, "sim_%s_rc" % v)
    nc = a.nodes_c or os.path.join(d, "nodes_%s_c" % v)
    nr = a.nodes_rc or os.path.join(d, "nodes_%s_rc" % v)
    have_nodes = all(os.path.exists(os.path.join(p, "events.npz")) for p in (nc, nr))
    camp = a.campaign or os.path.join(REPO, "runs", "pex", "%s_pex_tvla" % v)
    res = check(v, c, r, nc if have_nodes else None, nr if have_nodes else None, campaign=camp)
    res["variant"] = v
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({k: res[k] for k in ("function", "charge", "waveform")
                      + (("net_timing",) if have_nodes else ())}, indent=1))
    print("->", rel(a.out))


if __name__ == "__main__":
    main()
