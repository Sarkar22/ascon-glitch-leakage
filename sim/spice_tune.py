# SPDX-License-Identifier: Apache-2.0
"""Speed/accuracy tuning of the ngspice settings used by spice_campaign.py.

Runs one random stimulus through a tight-tolerance reference and a list of candidate settings,
and reports for each: speed (ngspice analysis seconds per simulated cycle, excluding the model
load; timepoints per cycle; peak RSS) and accuracy against the reference (per-window charge
error, waveform correlation, and correlation of the data-dependent part = traces minus the mean
trace), at the 10 ps bins and summed to 100 ps bins. A setting is accepted if the max
per-window charge error < 1% and the waveform correlation (10 ps bins) > 0.99.
A second reference with another integration method checks that the reference is converged.

  bash sim/docker_run.sh python3 sim/spice_tune.py --dut sim/mock/U --rows 60 --chunk 20 \
      --jobs 3 --out runs/tune_U
Results: <out>/tune.json and a printed table. One run dir per setting (rawfiles kept); a
finished run (traces.npy present) is reused as it is, so the table can be rebuilt cheaply.
"""
import argparse
import json
import os

import numpy as np

import spice_campaign as sc

TIGHT = "reltol=1e-4 vntol=1e-7 abstol=1e-13 chgtol=1e-16"
REFERENCES = [
    ("ref_trap_1ps", dict(tmax=0.001, options=TIGHT, method="trap")),
    ("ref_gear_1ps", dict(tmax=0.001, options=TIGHT, method="gear")),
]
CANDIDATES = [
    ("ngspice_default", dict(tmax=0.01, options="")),     # tmax = tstep = dt: ngspice default
    ("tmax50", dict(tmax=0.05, options="")),
    ("tmax100", dict(tmax=0.1, options="")),
    ("tmax200", dict(tmax=0.2, options="")),
    ("tmax20", dict(tmax=0.02, options="")),
    ("tmax10_klu", dict(tmax=0.01, options="klu")),
    ("tmax10_rel3e-3", dict(tmax=0.01, options="reltol=3e-3")),
    ("tmax50_trtol1", dict(tmax=0.05, options="trtol=1")),
    ("tmax100_trtol1", dict(tmax=0.1, options="trtol=1")),
    ("tmax50_xmu0.3", dict(tmax=0.05, options="xmu=0.3")),
    ("gear_tmax10", dict(tmax=0.01, options="", method="gear")),
    ("gear_tmax20", dict(tmax=0.02, options="", method="gear")),
    ("gear_tmax50", dict(tmax=0.05, options="", method="gear")),
    ("gear_tmax50_trtol1", dict(tmax=0.05, options="trtol=1", method="gear")),
    ("gear_tmax100_trtol1", dict(tmax=0.1, options="trtol=1", method="gear")),
    # chgtol (default 1e-14 C = 10 fC) is larger than the charge moved by one gate, so the
    # truncation-error step control never acts; tightening it lets the step grow when idle
    ("tmax100_chg1e-16", dict(tmax=0.1, options="chgtol=1e-16")),
    ("tmax200_chg1e-16", dict(tmax=0.2, options="chgtol=1e-16")),
    ("tmax200_chg1e-17", dict(tmax=0.2, options="chgtol=1e-17")),
    ("tmax500_chg1e-17", dict(tmax=0.5, options="chgtol=1e-17")),
    ("tmax200_chg1e-16_trtol1", dict(tmax=0.2, options="chgtol=1e-16 trtol=1")),
    ("tmax500_chg1e-16_trtol1", dict(tmax=0.5, options="chgtol=1e-16 trtol=1")),
    ("tmax200_chg1e-16_trtol2", dict(tmax=0.2, options="chgtol=1e-16 trtol=2")),
    ("tmax200_chg1e-16_trtol3", dict(tmax=0.2, options="chgtol=1e-16 trtol=3")),
    ("tmax200_chg3e-17", dict(tmax=0.2, options="chgtol=3e-17")),
    ("tmax20_chg1e-16_trtol3", dict(tmax=0.02, options="chgtol=1e-16 trtol=3")),
    # the chosen default and the fast alternative, re-run with the final deck code
    ("default_tmax10", dict(tmax=0.01, options="")),
    ("fast_tmax20", dict(tmax=0.02, options="")),
]
# the short list used on larger DUTs (--short)
SHORT = ["default_tmax10", "fast_tmax20", "tmax50", "tmax200_chg1e-17",
         "tmax200_chg1e-16_trtol3", "gear_tmax10"]


def speed(manifest):
    ch = [c for c in manifest["chunks"] if c.get("sim_s") is not None]
    cycles = sum(c["sim_cycles"] for c in ch)
    return {"s_per_sim_cycle": sum(c["sim_s"] for c in ch) / cycles,
            "load_s": float(np.mean([c["wall_s"] - c["sim_s"] for c in ch])),
            "timepoints_per_cycle": sum(c["timepoints"] for c in ch) / cycles,
            "peak_rss_MB": max(c["peak_rss_MB"] for c in ch)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dut", required=True)
    ap.add_argument("--rows", type=int, default=60)
    ap.add_argument("--chunk", type=int, default=20)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", required=True)
    ap.add_argument("--period", type=float, default=sc.DEFAULTS["period"])
    ap.add_argument("--only", nargs="*", help="run only these setting names")
    ap.add_argument("--short", action="store_true",
                    help="first reference + the SHORT list (+ --only names)")
    a = ap.parse_args()
    stim = sc.random_stimulus(a.dut, a.rows, a.seed)
    os.makedirs(a.out, exist_ok=True)
    results = {}
    settings = REFERENCES + CANDIDATES
    if a.short or a.only:
        want = set(a.only or []) | (set(SHORT) if a.short else set())
        settings = [s for s in settings if s[0] in want or s[0] == REFERENCES[0][0]]
    for name, over in settings:
        params = dict(chunk=a.chunk, period=a.period, **over)
        run = os.path.join(a.out, name)
        if os.path.exists(os.path.join(run, "traces.npy")):     # finished experiment: reuse
            with open(os.path.join(run, "manifest.json")) as f:
                man = json.load(f)
        else:
            _, _, man = sc.run_campaign(a.dut, stim, run, params, a.jobs, keep_raw=True,
                                        log=lambda msg: None)
        results[name] = dict(params=over, **speed(man))
        if name != REFERENCES[0][0]:
            results[name].update(sc.compare(os.path.join(a.out, name),
                                            os.path.join(a.out, REFERENCES[0][0])))
        r = results[name]
        r["accepted"] = bool(r.get("charge_rel_err_max", 0) < 0.01 and r.get("corr_all", 1) > 0.99)
        print("%-24s %7.4f s/cyc %5.0f pts/cyc  rss %4.0f MB  dQmax %6s  dQmean %6s  "
              "corr %7s  corr_dd %7s  corr_dd_100ps %8s  %s" % (
                  name, r["s_per_sim_cycle"], r["timepoints_per_cycle"], r["peak_rss_MB"],
                  "%.3f%%" % (100 * r["charge_rel_err_max"]) if "charge_rel_err_max" in r else "-",
                  "%.3f%%" % (100 * r["charge_rel_err_mean"]) if "charge_rel_err_mean" in r
                  else "-",
                  "%.5f" % r["corr_all"] if "corr_all" in r else "-",
                  "%.4f" % r["corr_data_dependent"] if "corr_data_dependent" in r else "-",
                  "%.5f" % r["corr_data_dependent_100ps"] if "corr_data_dependent_100ps" in r
                  else "-", "ok" if r["accepted"] else "REJECT"), flush=True)
    ports = sc.load_dut(a.dut)
    with open(os.path.join(a.out, "tune.json"), "w") as f:
        json.dump({"dut": ports["subckt"], "n_cells": ports.get("n_cells"),
                   "n_dff": ports.get("n_dff"), "rows": a.rows, "chunk": a.chunk,
                   "jobs": a.jobs, "seed": a.seed,
                   "base_params": dict(sc.DEFAULTS, period=a.period),
                   "results": results}, f, indent=1)


if __name__ == "__main__":
    main()
