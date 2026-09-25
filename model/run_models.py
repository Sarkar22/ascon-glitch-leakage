# SPDX-License-Identifier: Apache-2.0
"""TVLA / CPA on the level-1 (zero-delay) and level-2 (timing-aware) models of one variant.

    python3 model/run_models.py --dut build/N --mode tvla --n 100000 --level 1
    python3 model/run_models.py --dut build/N --mode tvla --n 20000 --level 2 --jobs 8
    python3 model/run_models.py --dut build/U --mode cpa --n 2000 --level 1 --key 2
    python3 model/run_models.py ... --noise 0.5 --order 2 --json out.json
    python3 model/run_models.py ... --level 2 --manifest runs/<run>/manifest.json   # SPICE grid

Stimulus from model/stimulus.py (same seed -> same rows as a SPICE run fed with it).
Traces per row as the SPICE runner builds them (row k = windows k .. k+L-1); the first
L+1 rows start from the reset state and are dropped. For each weighting (unweighted,
weighted, weighted_rise) it prints max|t| (or the CPA rank) at log-spaced trace counts.
--noise adds white Gaussian noise with that standard deviation, in units of the
per-sample standard deviation of the noiseless traces (pooled over samples).
"""
import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cpa import cpa_curve, hw_sbox_hypotheses          # noqa: E402
from glitch import glitch_traces, params_from_manifest  # noqa: E402
from stimulus import MODES, make_stimulus               # noqa: E402
from toggle import rows_from_cycles, toggle_traces      # noqa: E402
from tvla import THRESHOLD, add_noise, log_checkpoints, tvla_curve   # noqa: E402

KEYS = ("unweighted", "weighted", "weighted_rise")


def model_rows(dut, stim, level, jobs=1, **params):
    """Per-row traces {weighting: (n_rows, samples)} and the number of dropped rows."""
    from netgraph import Graph
    lat = Graph(dut).latency
    t = toggle_traces(dut, stim) if level == 1 else glitch_traces(dut, stim, jobs=jobs, **params)
    skip = lat + 1
    return {k: rows_from_cycles(t[k], lat)[skip:] for k in KEYS}, skip


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dut", required=True)
    ap.add_argument("--mode", required=True, choices=MODES)
    ap.add_argument("--n", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--level", type=int, choices=(1, 2), default=1)
    ap.add_argument("--order", type=int, choices=(1, 2), default=1)
    ap.add_argument("--noise", type=float, default=0.0)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--key", type=int, default=None)
    ap.add_argument("--iv", type=int, default=1)
    ap.add_argument("--signed", action="store_true", help="CPA: score by signed rho (leakage grows with HW)")
    ap.add_argument("--min-pulse", type=float, default=0.0, help="level 2: drop pulses narrower (ps)")
    ap.add_argument("--manifest", default=None, help="level 2: take period/pre/t_in/dt from a SPICE run")
    ap.add_argument("--json", default=None, help="write the summary here")
    a = ap.parse_args()

    t0 = time.time()
    stim, meta = make_stimulus(a.dut, a.mode, a.n, a.seed, iv=a.iv, key=a.key)
    timing = params_from_manifest(a.manifest) if a.manifest else {}
    rows, skip = model_rows(a.dut, stim, a.level, a.jobs, min_pulse_ps=a.min_pulse, **timing)
    n = len(rows["weighted"])
    cps = log_checkpoints(n)
    summary = {"dut": os.path.basename(os.path.normpath(a.dut)), "mode": a.mode, "n_rows": n, "seed": a.seed,
               "level": a.level, "order": a.order, "noise": a.noise, "dropped_rows": skip, "results": {}}
    for k in KEYS:
        tr = rows[k]
        if a.noise > 0:
            tr = add_noise(tr, a.noise * float(tr.std(0).mean()), a.seed)
        if a.mode == "cpa":
            nonce = meta["nonce"][skip:skip + n]
            r = cpa_curve(tr, hw_sbox_hypotheses(meta["iv"], nonce), meta["key"], cps, a.signed)
            first = next((int(c) for c, rk in zip(r["n"], r["rank"])
                          if all(x == 1 for x in r["rank"][list(r["n"]).index(c):])), None)
            res = {"n": r["n"].tolist(), "rank": r["rank"].tolist(),
                   "final_scores": r["scores"][-1].tolist(), "stable_rank1_from": first}
            print("%-13s CPA key %d%s: final rank %d, scores %s, rank 1 from %s traces"
                  % (k, meta["key"], " (signed)" if a.signed else "", r["rank"][-1], np.round(r["scores"][-1], 3).tolist(), first))
        else:
            labels = meta["label"][skip:skip + n]
            r = tvla_curve(tr, labels, cps, order=a.order)
            first = next((int(c) for c, m in zip(r["n"], r["max_abs_t"]) if m > THRESHOLD), None)
            res = {"n": r["n"].tolist(), "max_abs_t": r["max_abs_t"].tolist(), "argmax": r["argmax"].tolist(),
                   "first_above_threshold": first}
            print("%-13s max|t| = %8.2f at sample %4d (%d rows); first > %.1f at %s rows"
                  % (k, r["max_abs_t"][-1], r["argmax"][-1], n, THRESHOLD, first))
        summary["results"][k] = res
    summary["seconds"] = round(time.time() - t0, 1)
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, "w") as f:
            json.dump(summary, f, indent=1)


if __name__ == "__main__":
    main()
