# SPDX-License-Identifier: Apache-2.0
"""Transistor-level supply-current traces of a DUT with ngspice and the sky130 models.

Level 3 of the kill test (docs/KILL_TEST.md): the DUT's own supply current i(Vdut), simulated
with the foundry transistor models, sliced into one power window per stimulus row.

Inputs (interface contract with the netlist generator):
  <dut>/ports.json   subckt name, port order, input/output roles, latency (1 or 2)
  <dut>/dut.sp       .subckt <subckt> <ports...> built from sky130_fd_sc_hd cells
  stimulus .npy      uint8 array (n_rows, n_inputs) of 0/1 in ports.json 'inputs' order

Testbench (one ngspice deck per chunk of rows):
  Vdut vpwr_dut 0 VDD   ideal supply for the DUT only; VGND is node 0. Trace = -i(Vdut).
  Vclk                  ideal clock, 50% duty, finite edges (clk_rise); T = period
  one PWL source per input port; each output port loaded with out_load_fF to ground.

Timing (times relative to E_c, the 50% point of the c-th rising clock edge, E_c = T/2 + c*T):
  deck row r is presented during cycle r: its PWL edges (50% point, rise time `rise`) are at
  E_r + t_in*T, far from both clock edges for the default t_in = 0.75; it is captured by the
  DUT's input flip-flops at E_{r+1} and evaluated after that edge.
  The window of row r is [E_{r+1} - pre, E_{r+1} - pre + L*T), L = latency: it starts just
  before the capturing edge and covers the L evaluation cycles. For L = 2 consecutive windows
  overlap by one cycle (row r's second cycle is row r+1's first cycle).
  Within a window: capturing edge at t = pre, clock fall at pre + T/2, next row's input edges
  at pre + t_in*T, and (L = 2) the second rising edge at pre + T.

Chunks: rows are split into chunks simulated by independent ngspice processes. Each deck first
replays the `warmup` stimulus rows that precede the chunk (random rows, from `seed`, before
row 0), then the chunk's rows, then L+1 following rows (random after the last row). So every
row sees the same input history as in one long simulation; warm-up windows are discarded.

Resampling: ngspice's timepoints are kept as they are (no .options interp). Each simulator
step's charge (trapezoid of its end currents, exactly what the trapezoidal integrator moved)
is spread uniformly over the step and summed into bins of width dt (charge per bin). This is
what a bandwidth-limited probe sees, is charge-exact, removes the trapezoidal method's
step-to-step current ringing, and makes bins additive: a coarser grid is the sum of adjacent
bins. traces.npy holds the mean supply current per bin in uA (float32); charge.npy the charge
per window in fC (float64) = traces.sum(1) * dt.

Outputs in <out>/: traces.npy, charge.npy, outputs.npy (with --save-outputs: output ports
sampled at E_{r+1+L} + 0.4T, i.e. the registered result of row r), manifest.json (parameters,
ngspice version, PDK version, file hashes, per-chunk timings), chunks/cNNNNN/ (deck, log,
per-chunk results). A finished chunk (done.json) is reused on a re-run when its deck text and
post-processing parameters are unchanged, so runs are resumable, and with --rows a campaign can
be run on the first rows of a stimulus file and extended later (use a multiple of --chunk).

Simulator settings (defaults), validated by sim/spice_tune.py against a 1 ps / reltol 1e-4
reference on mock DUTs of 27 and 118 cells (results/spice_setup/tune_mock*.json): trapezoidal
integration, ngspice default tolerances, maximum step tmax = 10 ps (the step is then nearly
fixed, and the PWL breakpoints do not depend on the data): per-window charge error <= 0.14%,
waveform correlation >= 0.9994 at 10 ps bins, data-dependent part (traces minus mean trace)
>= 0.9987. --tmax 0.02 is ~1.7x faster and still passes (charge ~0.5%, correlation >= 0.994).
Parallelism on the 22-thread / 15 GB workstation: --jobs 11 --threads 2 (peak RSS 160-310 MB
per process, >= 3.7 GB left free); throughput 2.1 simulated cycles/s on build/N (88 cells) and
1.0 on build/D (118 cells), i.e. ~2.7 h and ~5.4 h per 20,000 rows (results/spice_setup/).

Runs inside the cac-sca docker image (ngspice-42), e.g.
  bash sim/docker_run.sh python3 sim/spice_campaign.py run --dut build/N --stim s.npy \
      --out runs/n --jobs 11 --threads 2 [--rows 5000]
  bash sim/docker_run.sh python3 sim/spice_campaign.py stim --dut build/U --rows 200 --out s.npy
  bash sim/docker_run.sh python3 sim/spice_campaign.py compare runs/fast runs/reference
PDK: env var PDK (default: realpath of ~/.ciel/sky130A).
"""
import argparse
import hashlib
import json
import multiprocessing
import os
import re
import subprocess
import time

import numpy as np

DEFAULTS = dict(
    period=4.0,        # ns, clock period T
    t_in=0.75,         # input PWL edge time after the rising clock edge, fraction of T
    rise=0.1,          # ns, input PWL rise/fall time (10-90 is 80% of this)
    clk_rise=0.1,      # ns, clock rise/fall time
    pre=0.2,           # ns, window start before the capturing clock edge
    dt=0.01,           # ns, resample bin width
    chunk=500,         # stimulus rows per ngspice process
    warmup=4,          # replayed rows before each chunk (traces discarded)
    corner="tt",
    temp=27.0,         # deg C
    vdd=1.8,           # V
    out_load_fF=2.0,   # load on every output port
    tmax=0.01,         # ns, maximum internal time step (see sim/spice_tune.py)
    options="",        # extra .options, e.g. "reltol=1e-3 klu"
    method="trap",     # integration method (trap or gear)
    seed=0,            # random warm-up/tail rows
)
def pdk_root():
    return os.environ.get("PDK") or os.path.realpath(os.path.expanduser("~/.ciel/sky130A"))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_dut(dut_dir):
    with open(os.path.join(dut_dir, "ports.json")) as f:
        ports = json.load(f)
    names = ["CLK"] + [p["name"] for p in ports["inputs"]] + [p["name"] for p in ports["outputs"]]
    if ports["ports"] != names + ["VPWR", "VGND"]:
        raise ValueError("ports.json: 'ports' is not CLK, inputs, outputs, VPWR, VGND")
    if ports["latency"] not in (1, 2):
        raise ValueError("latency must be 1 or 2")
    return ports


def spice_name(prefix, name):
    return prefix + re.sub(r"[^A-Za-z0-9_]", "_", name).lower()


def edge_time(c, p):
    """50% point of rising clock edge c, in ns."""
    return p["period"] * (0.5 + c)


def n_samples(p, latency):
    n = latency * p["period"] / p["dt"]
    if abs(n - round(n)) > 1e-6:
        raise ValueError("latency*period must be a multiple of dt")
    return int(round(n))


def deck_rows_range(p, latency, n_rows):
    """Deck rows: warm-up rows, the chunk's n_rows rows, then latency+1 tail rows."""
    return p["warmup"] + n_rows + latency + 1


def extend_stimulus(stim, p, latency):
    """Prepend `warmup` and append latency+1 random rows (deterministic from seed)."""
    rng = np.random.default_rng(p["seed"])
    head = rng.integers(0, 2, size=(p["warmup"], stim.shape[1]), dtype=np.uint8)
    tail = rng.integers(0, 2, size=(latency + 1, stim.shape[1]), dtype=np.uint8)
    return np.concatenate([head, stim.astype(np.uint8), tail])


def t_stop(p, latency, n_rows):
    """End of the simulation: last window, and the output sample of the last row."""
    last = p["warmup"] + n_rows - 1
    end_window = edge_time(last + 1, p) - p["pre"] + latency * p["period"]
    end_sample = edge_time(last + 1 + latency, p) + 0.4 * p["period"]
    return max(end_window, end_sample) + 2 * p["dt"]


def pwl_source(name, node, values, p):
    """PWL voltage source: value of row r from E_r + t_in*T (edge centred there).

    Both corners are written in every cycle, also when the value does not change, so the
    simulator's breakpoints (and hence its time grid) do not depend on the data.
    """
    vdd, half = p["vdd"], p["rise"] / 2
    pts = [(0.0, values[0] * vdd)]
    for r in range(1, len(values)):
        tc = edge_time(r, p) + p["t_in"] * p["period"]
        pts += [(tc - half, values[r - 1] * vdd), (tc + half, values[r] * vdd)]
    words = ["%.6fn %g" % (t, v) for t, v in pts]
    lines = ["%s %s 0 PWL(" % (name, node)]
    for k in range(0, len(words), 8):
        lines.append("+ " + " ".join(words[k:k + 8]))
    lines.append("+ )")
    return "\n".join(lines)


def make_deck(ports, dut_sp, rows, p, n_rows, save_outputs=False, title="chunk"):
    """ngspice deck text for one chunk; rows = the deck's stimulus rows (see deck_rows_range).

    The deck text (it names the PDK and DUT files and records the DUT's hash) and the
    post-processing parameters determine a chunk's result, so a finished chunk is reused only if
    both are unchanged (run_chunk keys done.json on their hash).
    """
    pdk = pdk_root()
    latency = ports["latency"]
    T, cr = p["period"], p["clk_rise"]
    ins = [spice_name("i_", q["name"]) for q in ports["inputs"]]
    outs = [spice_name("o_", q["name"]) for q in ports["outputs"]]
    if len(set(ins + outs)) != len(ins + outs):
        raise ValueError("port names collide after sanitising")
    lines = [
        "* %s: %s, %d rows" % (title, ports["subckt"], n_rows),
        "* dut.sp sha256 %s" % sha256_file(dut_sp),
        '.lib "%s/libs.tech/ngspice/sky130.lib.spice" %s' % (pdk, p["corner"]),
        '.include "%s/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"' % pdk,
        '.include "%s"' % os.path.abspath(dut_sp),
        ".temp %g" % p["temp"],
        ".options method=%s %s" % (p["method"], p["options"]),
        "Vdut vpwr_dut 0 %g" % p["vdd"],
        "Vclk clk 0 PULSE(0 %g %.6fn %gn %gn %.6fn %gn)" % (
            p["vdd"], edge_time(0, p) - cr / 2, cr, cr, T / 2 - cr, T),
    ]
    for k, node in enumerate(ins):
        lines.append(pwl_source("V" + node, node, rows[:, k], p))
    for node in outs:
        lines.append("Cl%s %s 0 %gf" % (node, node, p["out_load_fF"]))
    lines.append("Xdut clk %s vpwr_dut 0 %s" % (" ".join(ins + outs), ports["subckt"]))
    saves = ["i(vdut)"] + (["v(%s)" % o for o in outs] if save_outputs else [])
    lines.append(".save " + " ".join(saves))
    lines.append(".tran %gn %.6fn 0 %gn" % (p["dt"], t_stop(p, latency, n_rows), p["tmax"]))
    lines.append(".end")
    return "\n".join(lines) + "\n"


SPICEINIT = "set ngbehavior=hsa\nset ng_nomodcheck\nset num_threads=%d\n"
POST_VERSION = 2   # bump when the post-processing of a chunk changes (invalidates chunks)


def read_raw(path):
    """ngspice binary rawfile (one real plot) -> dict name -> float64 array."""
    with open(path, "rb") as f:
        buf = f.read()
    k = buf.find(b"Binary:\n")
    if k < 0:
        raise ValueError("%s: not a binary rawfile" % path)
    header = buf[:k].decode("ascii", "replace").splitlines()
    names, nvars, in_vars = [], None, False
    for line in header:
        if line.startswith("Flags:") and "complex" in line:
            raise ValueError("complex rawfile not supported")
        if line.startswith("No. Variables:"):
            nvars = int(line.split(":")[1])
        elif line.startswith("Variables:"):
            in_vars = True
        elif in_vars and line.strip():
            names.append(line.split()[1])
    if nvars is None or len(names) != nvars:
        raise ValueError("%s: bad header" % path)
    data = np.frombuffer(buf, dtype="<f8", offset=k + 8)
    npts = len(data) // nvars   # the header's point count can be stale if the run was cut
    data = data[:npts * nvars].reshape(npts, nvars)
    return {n: data[:, j].copy() for j, n in enumerate(names)}


def bin_charge(t, i, edges):
    """Charge delivered in each bin [edges[k], edges[k+1]) by the current samples (t, i).

    The charge of each simulator step is the trapezoid h*(i[n-1] + i[n])/2, which is exactly
    the charge the trapezoidal integrator moved in that step; within a step it is spread
    uniformly (the cumulative charge is interpolated linearly). This is charge-exact at every
    timepoint and, unlike integrating the straight line between the current samples, does not
    turn the trapezoidal method's step-to-step current ringing into bin-to-bin noise.
    edges may have any shape (bins along the last axis) and must lie within [t[0], t[-1]].
    """
    e = np.asarray(edges, dtype=float)
    if e.min() < t[0] - 1e-18 or e.max() > t[-1] + 1e-18:
        raise ValueError("bin edges outside the simulated time span")
    q = np.concatenate([[0.0], np.cumsum(0.5 * (i[1:] + i[:-1]) * np.diff(t))])
    return np.diff(np.interp(e, t, q), axis=-1)


def window_edges(p, latency, n_rows):
    """Bin edges (ns), shape (n_rows, n_samples+1), of the chunk rows' windows."""
    ns = n_samples(p, latency)
    r = p["warmup"] + np.arange(n_rows)
    start = edge_time(r + 1, p) - p["pre"]
    return start[:, None] + p["dt"] * np.arange(ns + 1)[None, :]


def ngspice_version():
    try:
        out = subprocess.run(["ngspice", "-v"], capture_output=True, text=True).stdout
    except OSError:
        return "ngspice not found"
    m = re.search(r"ngspice-\S+", out)
    return m.group(0) if m else out.strip()[:80]


def pdk_info():
    pdk = pdk_root()
    m = re.search(r"[0-9a-f]{40}", pdk)
    files = {"sky130.lib.spice": "libs.tech/ngspice/sky130.lib.spice",
             "sky130_fd_sc_hd.spice": "libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"}
    info = {"version": m.group(0) if m else "unknown"}
    for k, rel in files.items():
        path = os.path.join(pdk, rel)
        info[k] = sha256_file(path) if os.path.exists(path) else "missing"
    return info


def run_chunk(job):
    """Simulate one chunk (in a worker process); returns its timing record."""
    cdir, deck, p, latency, n_rows, out_nodes, keep_raw, threads = job
    done = os.path.join(cdir, "done.json")
    post = {k: p[k] for k in ("period", "pre", "dt", "warmup", "vdd")}
    post.update(latency=latency, n_rows=n_rows, out_nodes=out_nodes, version=POST_VERSION)
    key = hashlib.sha256((deck + json.dumps(post, sort_keys=True)).encode()).hexdigest()
    if os.path.exists(done):
        with open(done) as f:
            rec = json.load(f)
        if rec.get("key_sha256") == key:
            rec["skipped"] = True
            return rec
        os.remove(done)                            # stale: other parameters or stimulus
    os.makedirs(cdir, exist_ok=True)
    with open(os.path.join(cdir, "deck.sp"), "w") as f:
        f.write(deck)
    with open(os.path.join(cdir, ".spiceinit"), "w") as f:
        f.write(SPICEINIT % threads)
    raw = os.path.join(cdir, "out.raw")
    if os.path.exists(raw):
        os.remove(raw)
    t0 = time.time()
    with open(os.path.join(cdir, "ngspice.log"), "w") as log:
        proc = subprocess.Popen(["ngspice", "-b", "-r", "out.raw", "deck.sp"], cwd=cdir,
                                stdout=log, stderr=subprocess.STDOUT,
                                env=dict(os.environ, OMP_NUM_THREADS=str(threads)))
        _, status, usage = os.wait4(proc.pid, 0)   # rusage of this ngspice process only
        rc = os.waitstatus_to_exitcode(status)
        proc.returncode = rc
    wall = time.time() - t0
    with open(os.path.join(cdir, "ngspice.log")) as f:
        log_text = f.read()
    data = read_raw(raw) if rc == 0 and os.path.exists(raw) else None
    stop = t_stop(p, latency, n_rows)
    if data is None or data["time"][-1] * 1e9 < stop - 1e-6:
        raise RuntimeError("ngspice failed or stopped early in %s (rc %d):\n%s"
                           % (cdir, rc, log_text[-3000:]))
    m = re.search(r"Total analysis time \(seconds\) = ([\d.]+)", log_text)
    t = data["time"] * 1e9                     # ns
    cur = -data["i(vdut)"]                     # A, positive = drawn from the supply
    q = bin_charge(t, cur, window_edges(p, latency, n_rows)) * 1e-9   # A*ns -> C
    np.save(os.path.join(cdir, "traces.npy"),
            (q / (p["dt"] * 1e-9) * 1e6).astype(np.float32))           # mean current, uA
    np.save(os.path.join(cdir, "charge.npy"), q.sum(axis=1) * 1e15)   # fC per window
    if out_nodes:
        ts = edge_time(p["warmup"] + np.arange(n_rows) + 1 + latency, p) + 0.4 * p["period"]
        volts = np.array([np.interp(ts, t, data["v(%s)" % o]) for o in out_nodes]).T
        np.save(os.path.join(cdir, "outputs.npy"), (volts > p["vdd"] / 2).astype(np.uint8))
    if not keep_raw:
        os.remove(raw)
    rec = {"chunk": os.path.basename(cdir), "key_sha256": key,
           "rows": n_rows, "wall_s": round(wall, 3),
           "sim_s": float(m.group(1)) if m else None,
           "s_per_cycle": round(wall / n_rows, 4),
           "sim_cycles": round(stop / p["period"], 2),   # incl. warm-up and tail
           "peak_rss_MB": round(usage.ru_maxrss / 1024, 1), "timepoints": int(len(t))}
    tmp = done + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, done)
    return rec


def run_campaign(dut_dir, stim, out_dir, params=None, jobs=1, save_outputs=False,
                 keep_raw=False, log=print, threads=1, rows=None):
    """Simulate the stimulus rows; returns (traces, charge, manifest).

    jobs = parallel ngspice processes, threads = OpenMP threads per process (device model
    evaluation); neither changes the traces. rows = simulate only the first `rows` rows; the
    following rows of the file still drive the tail cycles, so a later run of more rows into
    the same out_dir reuses every finished chunk (campaigns can be extended step by step).
    """
    p = dict(DEFAULTS)
    p.update(params or {})
    ports = load_dut(dut_dir)
    latency = ports["latency"]
    stim = np.asarray(stim)
    if stim.ndim != 2 or stim.shape[1] != len(ports["inputs"]) or \
            not np.isin(stim, (0, 1)).all():
        raise ValueError("stimulus must be (n_rows, %d) of 0/1" % len(ports["inputs"]))
    ns = n_samples(p, latency)
    t_edge = p["t_in"] * p["period"]
    if not (p["rise"] / 2 < t_edge and t_edge + p["rise"] / 2 < p["period"]):
        raise ValueError("input edges must lie inside the cycle")
    os.makedirs(out_dir, exist_ok=True)
    stim_hash = hashlib.sha256(np.ascontiguousarray(stim.astype(np.uint8)).tobytes()).hexdigest()
    ext = extend_stimulus(stim, p, latency)
    n = len(stim) if rows is None else min(rows, len(stim))
    starts = list(range(0, n, p["chunk"]))
    jobs_list = []
    for ci, a in enumerate(starts):
        b = min(a + p["chunk"], n)
        deck_rows = ext[a:a + deck_rows_range(p, latency, b - a)]
        deck = make_deck(ports, os.path.join(dut_dir, "dut.sp"), deck_rows, p, b - a,
                         save_outputs, title="chunk %d rows %d-%d" % (ci, a, b - 1))
        cdir = os.path.join(out_dir, "chunks", "c%05d" % ci)
        out_nodes = [spice_name("o_", q["name"]) for q in ports["outputs"]] if save_outputs \
            else []
        jobs_list.append((cdir, deck, p, latency, b - a, out_nodes, keep_raw, threads))

    log("%s: %d rows, %d chunks of <= %d, %d samples/window, %d jobs" %
        (ports["subckt"], n, len(starts), p["chunk"], ns, jobs))
    t0 = time.time()
    records = []
    with multiprocessing.Pool(max(1, jobs)) as pool:
        for rec in pool.imap_unordered(run_chunk, jobs_list):
            records.append(rec)
            log("  %s %s rows %d: wall %.1f s, %.3f s/cycle, rss %.0f MB, %d points" % (
                rec["chunk"], "skipped (done)" if rec.get("skipped") else "done",
                rec["rows"], rec["wall_s"], rec["s_per_cycle"], rec["peak_rss_MB"],
                rec["timepoints"]))
    wall = time.time() - t0
    records.sort(key=lambda r: r["chunk"])

    traces = np.concatenate([np.load(os.path.join(j[0], "traces.npy")) for j in jobs_list])
    charge = np.concatenate([np.load(os.path.join(j[0], "charge.npy")) for j in jobs_list])
    np.save(os.path.join(out_dir, "traces.npy"), traces)
    np.save(os.path.join(out_dir, "charge.npy"), charge)
    if save_outputs:
        outputs = np.concatenate([np.load(os.path.join(j[0], "outputs.npy")) for j in jobs_list])
        np.save(os.path.join(out_dir, "outputs.npy"), outputs)

    fresh = [r for r in records if not r.get("skipped")]
    manifest = {
        "tool": "sim/spice_campaign.py", "dut": os.path.relpath(dut_dir),
        "subckt": ports["subckt"], "variant": ports.get("variant"), "latency": latency,
        "n_cells": ports.get("n_cells"), "n_dff": ports.get("n_dff"),
        "wire_cap_fF": ports.get("wire_cap_fF"), "rows": n, "samples_per_window": ns,
        "params": p, "jobs": jobs, "threads": threads, "ngspice": ngspice_version(),
        "pdk": pdk_info(),
        "stimulus_sha256": stim_hash, "stimulus_rows_in_file": len(stim),
        "dut_sp_sha256": sha256_file(os.path.join(dut_dir, "dut.sp")),
        "units": {"traces": "mean supply current per bin, uA", "charge": "fC per window",
                  "time": "ns"},
        "window": "row r: [E_{r+1} - pre, E_{r+1} - pre + latency*period), E = rising clock edge",
        "wall_s_this_invocation": round(wall, 1),
        "s_per_cycle_per_process": round(float(np.mean([r["s_per_cycle"] for r in fresh])), 4)
        if fresh else None,
        "throughput_cycles_per_s": round(sum(r["rows"] for r in fresh) / wall, 3)
        if fresh else None,
        "peak_rss_MB_max": max(r["peak_rss_MB"] for r in records),
        "chunks": records,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    log("done: %d rows in %.1f s wall (%s cycles/s), traces %s" %
        (n, wall, manifest["throughput_cycles_per_s"], traces.shape))
    return traces, charge, manifest


def compare(run_dir, ref_dir):
    """Accuracy of run_dir against ref_dir (same stimulus and window parameters)."""
    a = np.load(os.path.join(run_dir, "traces.npy")).astype(float)
    b = np.load(os.path.join(ref_dir, "traces.npy")).astype(float)
    qa = np.load(os.path.join(run_dir, "charge.npy"))
    qb = np.load(os.path.join(ref_dir, "charge.npy"))
    if a.shape != b.shape:
        raise ValueError("trace shapes differ: %s vs %s" % (a.shape, b.shape))
    rel = np.abs(qa - qb) / np.abs(qb)

    def corr(x, y):
        x, y = x - x.mean(), y - y.mean()
        return float((x * y).sum() / np.sqrt((x * x).sum() * (y * y).sum()))

    per_win = np.array([corr(a[k], b[k]) for k in range(len(a))])
    da, db = a - a.mean(0), b - b.mean(0)      # data-dependent part (minus the mean trace)
    res = {"windows": int(len(a)),
           "charge_rel_err_max": float(rel.max()), "charge_rel_err_mean": float(rel.mean()),
           "corr_window_min": float(per_win.min()), "corr_window_mean": float(per_win.mean()),
           "corr_all": corr(a.ravel(), b.ravel()),
           "corr_data_dependent": corr(da.ravel(), db.ravel()),
           "corr_charge_data_dependent": corr(qa, qb)}
    # the same at a 100 ps grid (sum of adjacent bins), closer to what a probe resolves
    k = 10
    if a.shape[1] % k == 0:
        a10 = a.reshape(len(a), -1, k).mean(2)
        b10 = b.reshape(len(b), -1, k).mean(2)
        res["corr_all_100ps"] = corr(a10.ravel(), b10.ravel())
        res["corr_data_dependent_100ps"] = corr((a10 - a10.mean(0)).ravel(),
                                                (b10 - b10.mean(0)).ravel())
    return res


def random_stimulus(dut_dir, rows, seed):
    ports = load_dut(dut_dir)
    rng = np.random.default_rng(seed)
    return rng.integers(0, 2, size=(rows, len(ports["inputs"])), dtype=np.uint8)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="simulate a stimulus file")
    r.add_argument("--dut", required=True, help="directory with ports.json and dut.sp")
    r.add_argument("--stim", required=True, help=".npy (n_rows, n_inputs) uint8")
    r.add_argument("--out", required=True, help="output directory (resumable)")
    r.add_argument("--jobs", type=int, default=1, help="parallel ngspice processes")
    r.add_argument("--threads", type=int, default=1, help="OpenMP threads per process")
    r.add_argument("--save-outputs", action="store_true",
                   help="also record the output ports (functional check)")
    r.add_argument("--keep-raw", action="store_true", help="keep ngspice rawfiles")
    r.add_argument("--rows", type=int, help="simulate only the first ROWS rows (extendable)")
    for k, v in DEFAULTS.items():
        r.add_argument("--" + k.replace("_", "-"), type=type(v), default=v)
    s = sub.add_parser("stim", help="write a uniformly random stimulus file")
    s.add_argument("--dut", required=True)
    s.add_argument("--rows", type=int, required=True)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--out", required=True)
    c = sub.add_parser("compare", help="accuracy of a run against a reference run")
    c.add_argument("run")
    c.add_argument("ref")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        params = {k: getattr(a, k) for k in DEFAULTS}
        run_campaign(a.dut, np.load(a.stim), a.out, params, a.jobs, a.save_outputs, a.keep_raw,
                     threads=a.threads, rows=a.rows)
    elif a.cmd == "stim":
        np.save(a.out, random_stimulus(a.dut, a.rows, a.seed))
    else:
        print(json.dumps(compare(a.run, a.ref), indent=1))


if __name__ == "__main__":
    main()
