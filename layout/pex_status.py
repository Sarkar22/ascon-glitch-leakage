# SPDX-License-Identifier: Apache-2.0
"""Progress of the post-layout campaigns (runs/pex/queue.sh), with a first look at their TVLA.

  python3 layout/pex_status.py [runs/pex/N_pex_tvla:5000 runs/pex/DA_pex_tvla:10000]
  (each argument: out_dir:rows[:dut]; dut defaults to build/<out_dir name without _tvla>)

For each campaign: finished chunks and rows (from chunks/*/done.json), mean wall time per chunk,
the hours left at 6 parallel processes, and, over the finished rows that form a contiguous block
from row 0 (dropping the first latency+1 rows, as the kill test does), the first-order fixed-vs-random Welch
|t| (maximum over the 10 ps samples, and where it peaks) and the functional check of the registered
outputs. The TVLA numbers are a progress view only; the analysis of record is done on the full
campaign. Host python3 with numpy is enough.
"""
import glob
import json
import os
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "model"))
from ascon_sbox import SBOX_NP  # noqa: E402

META = os.path.join(REPO, "runs", "kt", "stim", "M_tvla.meta.npz")
DEFAULT = ("runs/pex/N_pex_tvla:5000", "runs/pex/DA_pex_tvla:10000")
JOBS = 6


def welch_t(tr, labels):
    a, b = tr[labels == 0], tr[labels == 1]
    va, vb = a.var(0, ddof=1), b.var(0, ddof=1)
    return (a.mean(0) - b.mean(0)) / np.sqrt(va / len(a) + vb / len(b) + 1e-30)


def status(out_dir, total_rows, dut=None):
    d = os.path.join(REPO, out_dir)
    dut = dut or os.path.join("build", os.path.basename(out_dir.rstrip("/")).replace("_tvla", ""))
    recs = []
    for f in glob.glob(os.path.join(d, "chunks", "c*", "done.json")):
        with open(f) as fh:
            r = json.load(fh)
        r["index"] = int(os.path.basename(os.path.dirname(f))[1:])
        recs.append(r)
    chunk = max(r["rows"] for r in recs) if recs else 125
    n_chunks = -(-total_rows // chunk)
    res = {"campaign": out_dir, "chunks_done": len(recs), "chunks_total": n_chunks,
           "rows_done": sum(r["rows"] for r in recs), "rows_total": total_rows}
    if not recs:
        return res
    wall = np.mean([r["wall_s"] for r in recs if not r.get("skipped")] or [0])
    left = n_chunks - len(recs)
    res["mean_chunk_wall_h"] = round(wall / 3600, 2)
    res["s_per_row_per_process"] = round(wall / chunk, 2)
    res["remaining_h_approx"] = round(-(-left // JOBS) * wall / 3600, 1)
    newest = max(os.path.getmtime(os.path.join(d, "chunks", "c%05d" % r["index"], "done.json"))
                 for r in recs)
    res["last_chunk_finished"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(newest))

    # contiguous block of finished chunks from row 0
    done = {r["index"] for r in recs}
    k = 0
    while k in done:
        k += 1
    if k == 0:
        return res
    parts = [os.path.join(d, "chunks", "c%05d" % i) for i in range(k)]
    tr = np.concatenate([np.load(os.path.join(p, "traces.npy")) for p in parts]).astype(float)
    meta = np.load(META)
    with open(os.path.join(REPO, dut, "ports.json")) as fh:
        ports = json.load(fh)
    drop = ports["latency"] + 1
    if SHOW_T:  # off by default: docs/POSTLAYOUT.md forbids interim looks at t
        labels = meta["label"][:len(tr)]
        t = welch_t(tr[drop:], labels[drop:])
        kmax = int(np.argmax(np.abs(t)))
        res["tvla_first_order"] = {"traces": int(len(tr) - drop),
                                   "max_abs_t": round(float(np.abs(t).max()), 2),
                                   "peak_ns_after_first_edge": round((kmax + 0.5) * 0.01 - 0.2, 3)}
    outs = [os.path.join(p, "outputs.npy") for p in parts]
    if all(os.path.exists(o) for o in outs):
        o = np.concatenate([np.load(x) for x in outs])
        y = np.zeros(len(o), dtype=np.uint8)
        for j, p in enumerate(ports["outputs"]):
            y ^= o[:, j].astype(np.uint8) << (4 - p["bit"])
        res["function_mismatches"] = int((SBOX_NP[meta["x"][:len(y)]] != y).sum())
    return res


SHOW_T = False


def main(argv=None):
    global SHOW_T
    args = argv if argv is not None else sys.argv[1:]
    SHOW_T = "--show-t" in args
    args = [a for a in args if a != "--show-t"] or list(DEFAULT)
    for a in args:
        f = a.split(":")
        print(json.dumps(status(f[0], int(f[1]), f[2] if len(f) > 2 else None)))


if __name__ == "__main__":
    main()
