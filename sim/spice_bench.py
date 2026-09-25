# SPDX-License-Identifier: Apache-2.0
"""Throughput of spice_campaign.py vs parallelism (processes x OpenMP threads) on this machine.

For each configuration JxT, simulates J chunks of --rows rows with J parallel ngspice processes
of T threads each, and reports aggregate throughput (stimulus rows per wall second, and
simulated cycles per second incl. warm-up/tail), per-process peak RSS, and the lowest
MemAvailable seen during the run (the machine must keep >= 2 GB free).

  bash sim/docker_run.sh python3 sim/spice_bench.py --dut sim/mock/D --rows 20 \
      --configs 6x1 11x1 16x1 8x2 11x2 --out runs/bench_D
Writes <out>/bench.json.
"""
import argparse
import json
import os
import threading
import time

import spice_campaign as sc


def mem_available_MB():
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024
    return float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dut", required=True)
    ap.add_argument("--rows", type=int, default=20, help="rows per chunk")
    ap.add_argument("--configs", nargs="+", default=["6x1", "11x1", "16x1"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    res = {"dut": sc.load_dut(a.dut)["subckt"], "rows_per_chunk": a.rows,
           "params": dict(sc.DEFAULTS), "idle_mem_available_MB": round(mem_available_MB()),
           "configs": {}}
    for cfg in a.configs:
        jobs, threads = (int(x) for x in cfg.split("x"))
        stim = sc.random_stimulus(a.dut, jobs * a.rows, seed=11)
        low = [mem_available_MB()]
        stop = threading.Event()

        def watch():
            while not stop.is_set():
                low[0] = min(low[0], mem_available_MB())
                time.sleep(0.5)
        th = threading.Thread(target=watch, daemon=True)
        th.start()
        t0 = time.time()
        _, _, man = sc.run_campaign(a.dut, stim, os.path.join(a.out, cfg),
                                    dict(chunk=a.rows), jobs=jobs, threads=threads,
                                    log=lambda m: None)
        wall = time.time() - t0
        stop.set()
        th.join()
        ch = man["chunks"]
        r = {"jobs": jobs, "threads": threads, "wall_s": round(wall, 1),
             "rows_per_s": round(jobs * a.rows / wall, 4),
             "sim_cycles_per_s": round(sum(c["sim_cycles"] for c in ch) / wall, 4),
             "s_per_sim_cycle_per_process": round(
                 sum(c["sim_s"] for c in ch) / sum(c["sim_cycles"] for c in ch), 3),
             "load_s": round(sum(c["wall_s"] - c["sim_s"] for c in ch) / len(ch), 1),
             "peak_rss_MB": max(c["peak_rss_MB"] for c in ch),
             "min_mem_available_MB": round(low[0])}
        res["configs"][cfg] = r
        print("%-5s wall %6.1f s  %.3f rows/s  %.3f sim-cycles/s  %.2f s/cycle/process  "
              "rss %.0f MB  min MemAvailable %d MB" % (
                  cfg, wall, r["rows_per_s"], r["sim_cycles_per_s"],
                  r["s_per_sim_cycle_per_process"], r["peak_rss_MB"], r["min_mem_available_MB"]),
              flush=True)
        with open(os.path.join(a.out, "bench.json"), "w") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
