# SPDX-License-Identifier: Apache-2.0
"""Simulation cost of the post-layout netlists and the projected wall time of the TVLA campaigns.

  python3 layout/bench_summary.py

Reads the benchmark runs of sim/spice_campaign.py (6 processes x 1 thread in one container capped
at 6 CPUs, 20-row chunks) listed in RUNS, and writes results/pex/bench.json:
  s_per_sim_cycle   wall time of one ngspice process per simulated clock cycle (the chunk's rows
                    plus its 4 warm-up and latency+1 tail cycles), with 6 processes running
  peak_rss_MB       largest resident set of one ngspice process
and the projection for the campaigns of runs/pex/queue.sh (125-row chunks, 6 processes):
  waves = ceil(chunks / 6), wall = waves x (LOAD_S + s_per_sim_cycle x (125 + 4 + latency + 1)).
Host python3 (standard library only).
"""
import json
import math
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOAD_S = 5.0          # model loading per ngspice process (about 3.5 s alone, more when 6 run)
CHUNK, JOBS = 125, 6
RUNS = {  # name: (run directory, netlist, solver)
    "DA_pre_sparse": ("runs/kt/DA_tvla", "pre-layout (kill-test extension: 10 jobs x 2 threads)",
                      "sparse"),
    "N_pex_sparse": ("runs/pex/bench_N_pex", "post-layout", "sparse"),
    "N_pex_klu": ("runs/pex/bench_N_pex_klu", "post-layout", "klu"),
    "DA_pex_sparse": ("runs/pex/bench_DA_pex", "post-layout", "sparse"),
    "DA_pex_klu": ("runs/pex/bench_DA_pex_klu", "post-layout", "klu"),
}
CAMPAIGNS = (("N_pex", "N_pex_klu", 5000), ("DA_pex", "DA_pex_klu", 10000),
             ("DA_pex", "DA_pex_klu", 5000))


def run_cost(path):
    with open(os.path.join(REPO, path, "manifest.json")) as f:
        m = json.load(f)
    recs = [r for r in m["chunks"] if not r.get("skipped")]
    per_cycle = [(r["wall_s"] - LOAD_S) / r["sim_cycles"] for r in recs]
    return {"run": path, "jobs": m["jobs"], "threads": m["threads"], "chunk_rows": recs[0]["rows"],
            "latency": m["latency"],
            "s_per_row_per_process_incl_overhead": round(m["s_per_cycle_per_process"], 2),
            "s_per_sim_cycle": round(sum(per_cycle) / len(per_cycle), 2),
            "peak_rss_MB": m["peak_rss_MB_max"],
            "throughput_rows_per_s": m["throughput_cycles_per_s"],
            "options": m["params"].get("options", "")}


def main():
    res = {"note": "container capped at 6 CPUs; jobs x threads per run as given",
           "runs": {}, "projection": {}}
    for name, (path, netlist, solver) in RUNS.items():
        if os.path.exists(os.path.join(REPO, path, "manifest.json")):
            r = run_cost(path)
            r.update(netlist=netlist, solver=solver)
            res["runs"][name] = r
    for dut, bench, rows in CAMPAIGNS:
        if bench not in res["runs"]:
            continue
        b = res["runs"][bench]
        chunks = math.ceil(rows / CHUNK)
        waves = math.ceil(chunks / JOBS)
        cycles = CHUNK + 4 + b["latency"] + 1
        wall = waves * (LOAD_S + b["s_per_sim_cycle"] * cycles)
        res["projection"]["%s_%d" % (dut, rows)] = {
            "rows": rows, "chunks": chunks, "waves_of_6": waves,
            "wall_h": round(wall / 3600, 1), "from": bench}
    os.makedirs(os.path.join(REPO, "results", "pex"), exist_ok=True)
    with open(os.path.join(REPO, "results", "pex", "bench.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
