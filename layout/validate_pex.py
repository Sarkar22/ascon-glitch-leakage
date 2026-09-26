# SPDX-License-Identifier: Apache-2.0
"""Post-layout sanity check: function, charge and timing of a PEX run against the pre-layout run.

  python3 layout/validate_pex.py --variant N --pex runs/pex/sanity_N_pex --pre runs/kt/N_tvla \
      --meta runs/kt/stim/M_tvla.meta.npz --out results/pex/sanity_N.json

Both runs must come from sim/spice_campaign.py on the same stimulus rows (same file, same first
rows, same window parameters); the pre-layout run may have more rows (its first rows are used).
Reports:
  function   registered outputs of every PEX row vs the S-box of its unshared input
  charge     charge per window, PEX / pre-layout (mean, min, max) and the correlation of the
             data-dependent part (charge minus its mean) between the two
  timing     per evaluation cycle of the window (latency 2: two), from the mean supply current
             between 0.2 ns before and 1.8 ns after that cycle's edge: time of the current peak,
             times at which 50/90/99 % of that charge has flowed, and the shift of the PEX
             waveform that best matches the pre-layout one; plus the per-row data-dependent
             waveform correlation at that shift. (With a new row every cycle, both cycles of a
             latency-2 window hold the same mix of first- and second-stage activity, so their
             means differ only by one row.)
Host python3 with numpy is enough.
"""
import argparse
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "model"))
from ascon_sbox import SBOX_NP  # noqa: E402


def registered_value(outputs, ports):
    """Output bits (rows, n_out) -> unshared 5-bit value (share XOR for masked designs)."""
    y = np.zeros(len(outputs), dtype=np.uint8)
    for k, p in enumerate(ports["outputs"]):
        y ^= outputs[:, k].astype(np.uint8) << (4 - p["bit"])
    return y


def completion_times(mean_trace, dt, pre, frac=(0.5, 0.9, 0.99), end_ns=1.8):
    """Times (ns after the edge) at which the given fractions of the charge up to end_ns flowed."""
    n = int(round((pre + end_ns) / dt))
    q = np.cumsum(np.clip(mean_trace[:n], 0, None))
    q = q / q[-1]
    return {"%d%%" % round(100 * f): round(float(np.searchsorted(q, f) + 1) * dt - pre, 4)
            for f in frac}


def best_shift(a, b, dt, max_ns=0.5):
    """Shift s (ns) that maximises corr(a(t), b(t - s)), i.e. a positive s = b comes later."""
    best = (-2.0, 0.0)
    k = int(round(max_ns / dt))
    for s in range(-k, k + 1):
        if s >= 0:
            x, y = a[:len(a) - s] if s else a, b[s:]
        else:
            x, y = a[-s:], b[:len(b) + s]
        x, y = x - x.mean(), y - y.mean()
        c = float((x * y).sum() / np.sqrt((x * x).sum() * (y * y).sum()))
        if c > best[0]:
            best = (c, s * dt)
    return round(best[1], 4), round(best[0], 4)


def compare(pex_dir, pre_dir, ports, meta_x):
    tp = np.load(os.path.join(pex_dir, "traces.npy")).astype(float)
    qp = np.load(os.path.join(pex_dir, "charge.npy"))
    n = len(tp)
    tr = np.load(os.path.join(pre_dir, "traces.npy"), mmap_mode="r")[:n].astype(float)
    qr = np.load(os.path.join(pre_dir, "charge.npy"))[:n]
    with open(os.path.join(pex_dir, "manifest.json")) as f:
        man = json.load(f)
    p = man["params"]
    dt, pre = p["dt"], p["pre"]
    res = {"rows": n, "pex_run": os.path.relpath(pex_dir, REPO),
           "pre_run": os.path.relpath(pre_dir, REPO)}

    out_path = os.path.join(pex_dir, "outputs.npy")
    if os.path.exists(out_path):
        y = registered_value(np.load(out_path), ports)
        res["function"] = {"mismatches": int((SBOX_NP[meta_x[:n]] != y).sum()), "rows": n}

    ratio = qp / qr
    dq_p, dq_r = qp - qp.mean(), qr - qr.mean()
    res["charge"] = {
        "pex_mean_fC": round(float(qp.mean()), 2), "pre_mean_fC": round(float(qr.mean()), 2),
        "ratio_mean": round(float(ratio.mean()), 4), "ratio_min": round(float(ratio.min()), 4),
        "ratio_max": round(float(ratio.max()), 4),
        "corr_data_dependent": round(float((dq_p * dq_r).sum() / np.sqrt(
            (dq_p ** 2).sum() * (dq_r ** 2).sum())), 4)}

    period, latency = p["period"], man["latency"]
    res["timing"] = {}
    for c in range(latency):                  # each evaluation cycle of the window
        a = int(round(c * period / dt))       # window index of this cycle's start (edge - pre)
        seg = slice(a, a + int(round((pre + 1.8) / dt)))
        mp, mr = tp[:, seg].mean(0), tr[:, seg].mean(0)
        shift, corr = best_shift(mr, mp, dt)
        t = {
            "peak_ns_after_edge": {"pex": round((int(np.argmax(mp)) + 0.5) * dt - pre, 4),
                                   "pre": round((int(np.argmax(mr)) + 0.5) * dt - pre, 4)},
            "charge_completion_ns_after_edge": {"pex": completion_times(mp, dt, pre),
                                                "pre": completion_times(mr, dt, pre)},
            "best_shift_ns_pex_later": shift, "mean_waveform_corr_at_shift": corr,
            "mean_waveform_corr_no_shift": best_shift(mr, mp, dt, 0.0)[1],
            "peak_current_uA": {"pex": round(float(mp.max()), 1),
                                "pre": round(float(mr.max()), 1)},
        }
        s = int(round(shift / dt))
        dp, dr = tp[:, seg] - mp, tr[:, seg] - mr
        if s > 0:
            dp, dr = dp[:, s:], dr[:, :dr.shape[1] - s]
        elif s < 0:
            dp, dr = dp[:, :dp.shape[1] + s], dr[:, -s:]
        t["data_dependent_corr_at_shift"] = round(float(
            (dp * dr).sum() / np.sqrt((dp ** 2).sum() * (dr ** 2).sum())), 4)
        res["timing"]["cycle%d" % (c + 1)] = t
    res["sim"] = {"s_per_cycle_per_process": man.get("s_per_cycle_per_process"),
                  "peak_rss_MB_max": man.get("peak_rss_MB_max"), "jobs": man.get("jobs"),
                  "threads": man.get("threads")}
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--variant", required=True)
    ap.add_argument("--pex", required=True, help="PEX run directory")
    ap.add_argument("--pre", required=True, help="pre-layout run directory (same stimulus)")
    ap.add_argument("--meta", required=True, help="stimulus .meta.npz (field x)")
    ap.add_argument("--out", required=True, help="JSON to write")
    a = ap.parse_args(argv)
    with open(os.path.join(REPO, "build", a.variant, "ports.json")) as f:
        ports = json.load(f)
    x = np.load(a.meta)["x"]
    res = compare(a.pex, a.pre, ports, x)
    res["variant"] = a.variant
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
