# SPDX-License-Identifier: Apache-2.0
"""Short SPICE re-run that also records every net of the DUT, to localize leakage in time.

Same testbench, timing, chunking and simulator settings as sim/spice_campaign.py (it builds the
decks with the same functions); the only change is that the deck also saves the voltage of
every net of graph.json. Each net's voltage is turned into its VDD/2 crossings (glitches
included), and each crossing is assigned to the clock cycle ("window") it falls in:
  cycle c = the evaluation of stimulus row c, time t_ns from the window start
  (the window starts `pre` before the capturing edge of row c, like the runner's windows).
For a latency-2 design a row's events are those of cycles c and c+1 (the latter shifted by T).

  bash sim/docker_run.sh python3 analysis/spice_nodes.py --dut build/N \
      --stim runs/kt/stim/M_tvla.npy --rows 2000 --out runs/kt/N_nodes --jobs 10 --threads 2

Writes <out>/events.npz: net_names, net (index), cycle, t_ns, rise (1 = 0->1), period, pre,
n_rows; <out>/traces.npy and charge.npy (the supply current as in a campaign, for a
determinism check against the campaign run on the same rows).
"""
import argparse
import json
import multiprocessing
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import spice_campaign as sc   # noqa: E402


def net_nodes(dut_dir, ports):
    """(net name, ngspice vector) for every graph.json net except the clock and input ports."""
    with open(os.path.join(dut_dir, "graph.json")) as f:
        g = json.load(f)
    ins = {q["name"] for q in ports["inputs"]}
    outs = {q["name"] for q in ports["outputs"]}
    res = []
    for n in g["nets"]:
        if n in ins or n == "CLK":
            continue
        node = sc.spice_name("o_", n) if n in outs else "xdut." + n.lower()
        res.append((n, "v(%s)" % node))
    return res


def crossings(t, v, level):
    """Times (linear interpolation) and directions of the crossings of `level` by v(t)."""
    s = v > level
    k = np.nonzero(s[1:] != s[:-1])[0]
    tc = t[k] + (level - v[k]) * (t[k + 1] - t[k]) / (v[k + 1] - v[k])
    return tc, s[k + 1].astype(np.uint8)


def run_one(job):
    cdir, deck, p, latency, n_rows, threads, row0, keep_cycles, nodes = job
    rec = sc.run_chunk((cdir, deck, p, latency, n_rows, [], True, threads))
    ev_file = os.path.join(cdir, "events.npz")
    raw = os.path.join(cdir, "out.raw")
    if rec.get("skipped") and os.path.exists(ev_file):
        return rec
    data = sc.read_raw(raw)
    t = data["time"] * 1e9
    T, pre = p["period"], p["pre"]
    start0 = sc.edge_time(p["warmup"] + 1, p) - pre          # window start of chunk row 0
    net, cyc, tr, rise = [], [], [], []
    for k, (_, vec) in enumerate(nodes):
        tc, d = crossings(t, data[vec], p["vdd"] / 2)
        j = np.floor((tc - start0) / T).astype(np.int64)
        ok = (j >= 0) & (j < keep_cycles)
        net.append(np.full(ok.sum(), k, dtype=np.int16))
        cyc.append((row0 + j[ok]).astype(np.int32))
        tr.append((tc[ok] - start0 - j[ok] * T).astype(np.float32))
        rise.append(d[ok])
    np.savez(ev_file, net=np.concatenate(net), cycle=np.concatenate(cyc),
             t_ns=np.concatenate(tr), rise=np.concatenate(rise))
    os.remove(raw)
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dut", required=True)
    ap.add_argument("--stim", required=True)
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--chunk", type=int, default=100)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--threads", type=int, default=1)
    a = ap.parse_args()
    p = dict(sc.DEFAULTS, chunk=a.chunk)
    ports = sc.load_dut(a.dut)
    lat = ports["latency"]
    stim = np.load(a.stim)
    n = min(a.rows, len(stim))
    ext = sc.extend_stimulus(stim, p, lat)
    nodes = net_nodes(a.dut, ports)
    save = " ".join(v for _, v in nodes)
    jobs = []
    for ci, s in enumerate(range(0, n, p["chunk"])):
        e = min(s + p["chunk"], n)
        deck = sc.make_deck(ports, os.path.join(a.dut, "dut.sp"),
                            ext[s:s + sc.deck_rows_range(p, lat, e - s)], p, e - s,
                            title="nodes chunk %d rows %d-%d" % (ci, s, e - 1))
        deck = deck.replace(".save i(vdut)", ".save i(vdut)\n.save " + save)
        # keep the cycles of this chunk's rows; the last chunk also keeps the extra cycle(s)
        # that complete its last row's window (latency 2)
        keep = (e - s) + (lat - 1 if e == n else 0)
        jobs.append((os.path.join(a.out, "chunks", "c%05d" % ci), deck, p, lat, e - s,
                     a.threads, s, keep, nodes))
    print("%s: %d rows, %d chunks, %d nets saved, %d jobs" % (ports["subckt"], n, len(jobs),
                                                              len(nodes), a.jobs), flush=True)
    with multiprocessing.Pool(max(1, a.jobs)) as pool:
        for rec in pool.imap_unordered(run_one, jobs):
            print("  %s: wall %.1f s, rss %.0f MB" % (rec["chunk"], rec["wall_s"], rec["peak_rss_MB"]),
                  flush=True)
    parts = [np.load(os.path.join(j[0], "events.npz")) for j in jobs]
    ev = {k: np.concatenate([q[k] for q in parts]) for k in ("net", "cycle", "t_ns", "rise")}
    np.savez(os.path.join(a.out, "events.npz"), net_names=np.array([m for m, _ in nodes]),
             period=p["period"], pre=p["pre"], n_rows=n, latency=lat, **ev)
    np.save(os.path.join(a.out, "traces.npy"),
            np.concatenate([np.load(os.path.join(j[0], "traces.npy")) for j in jobs]))
    np.save(os.path.join(a.out, "charge.npy"),
            np.concatenate([np.load(os.path.join(j[0], "charge.npy")) for j in jobs]))
    print("done: %d events on %d nets" % (len(ev["net"]), len(nodes)))


if __name__ == "__main__":
    main()
