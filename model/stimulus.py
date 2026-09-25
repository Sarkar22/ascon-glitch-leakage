# SPDX-License-Identifier: Apache-2.0
"""Deterministic (seeded) stimulus for the kill test, in the SPICE runner's format.

make_stimulus(ports, mode, n, seed) -> (stim, meta)
  stim  uint8 array (n, n_inputs) of 0/1, columns in ports.json 'inputs' order
        (bit i of a 5-bit value is x_i, x0 = MSB).
  meta  dict of numpy arrays, one entry per row: label, x (unshared input), mask, r,
        plus the scalar parameters of the mode.

Sharing (masked variants): share 1 is the mask, share 0 carries the data:
  xs1 = mask, xs0 = x ^ mask; r = the five fresh random bits (r_i feeds AND t_i).
Unmasked variant (role 'plain'): the ports carry x; mask and r are recorded as 0.

Modes (random draws in this order from numpy.random.default_rng(seed): label, x, mask, r):
  tvla       fixed vs random: label 0 = fixed (x = x_fixed, default 0x0B), label 1 = random
             x; labels drawn per row (classes interleaved randomly); mask and r uniform
             and fresh in every row for both classes.
  rvr        random vs random control: labels drawn as in tvla, x uniform for both.
  masks_off  as tvla (same labels and x draws) but mask = 0 and r = 0, so the DUT computes
             on the unmasked value in share 0 (xs0 = x, xs1 = 0).
  cpa        Ascon initialization context for one column: x0 = iv (constant), x1 x2 = key
             (fixed, 2 bits; the round constant folds into it), x3 x4 = nonce (uniform,
             known). x = iv<<4 | key<<2 | nonce. Masked variants get fresh mask and r.
             label = 0. meta has iv, key (scalars) and nonce (per row).
  random     x, mask, r uniform; label 0.
  exhaustive every (x, mask, r) once (masked: 32768 rows, x slowest) or every x (unmasked);
             n and seed are ignored.

CLI: python3 model/stimulus.py --dut build/N --mode tvla --n 20000 --seed 1 --out runs/n_tvla.npy
     writes the stimulus .npy and <out>.meta.npz next to it.
"""
import argparse
import json
import os

import numpy as np

X_FIXED = 0x0B
MODES = ("tvla", "rvr", "masks_off", "cpa", "random", "exhaustive")


def load_ports(ports):
    if isinstance(ports, dict):
        return ports
    if os.path.isdir(ports):
        ports = os.path.join(ports, "ports.json")
    with open(ports) as f:
        return json.load(f)


def is_masked(ports):
    return any(p["role"] in ("share0", "share1") for p in load_ports(ports)["inputs"])


def encode(ports, x, mask, r):
    """Port bits (n, n_inputs) from unshared x, mask (= share 1) and r."""
    ports = load_ports(ports)
    x, mask, r = (np.asarray(v, dtype=np.uint8) for v in (x, mask, r))
    value = {"plain": x, "share0": x ^ mask, "share1": mask, "rand": r}
    cols = [(value[p["role"]] >> (4 - p["bit"])) & 1 for p in ports["inputs"]]
    return np.stack(cols, axis=1).astype(np.uint8)


def make_stimulus(ports, mode, n=0, seed=0, x_fixed=X_FIXED, iv=1, key=None):
    ports = load_ports(ports)
    masked = is_masked(ports)
    rng = np.random.default_rng(seed)
    meta = {"mode": mode, "seed": seed, "variant": ports["variant"]}
    if mode == "exhaustive":
        if masked:
            g = np.arange(32 * 32 * 32)
            x, mask, r = g >> 10, (g >> 5) & 31, g & 31
        else:
            x = np.arange(32)
            mask = r = np.zeros(32, dtype=int)
        label = np.zeros(len(x), dtype=np.uint8)
    elif mode in ("tvla", "rvr", "masks_off", "random"):
        label = rng.integers(0, 2, n).astype(np.uint8)
        xr = rng.integers(0, 32, n)
        mask = rng.integers(0, 32, n)
        r = rng.integers(0, 32, n)
        if mode in ("tvla", "masks_off"):
            x = np.where(label == 0, x_fixed, xr)
            meta["x_fixed"] = x_fixed
        else:
            x = xr
        if mode == "masks_off":
            mask = np.zeros(n, dtype=int)
            r = np.zeros(n, dtype=int)
        if mode == "random":
            label = np.zeros(n, dtype=np.uint8)
    elif mode == "cpa":
        if key is None:
            key = int(rng.integers(0, 4))     # secret drawn from the seed, recorded in meta
        label = np.zeros(n, dtype=np.uint8)
        nonce = rng.integers(0, 4, n)
        mask = rng.integers(0, 32, n)
        r = rng.integers(0, 32, n)
        x = (iv << 4) | (key << 2) | nonce
        meta.update(iv=iv, key=key, nonce=nonce.astype(np.uint8))
    else:
        raise ValueError("mode must be one of %s" % (MODES,))
    if not masked:
        mask = np.zeros(len(x), dtype=int)
        r = np.zeros(len(x), dtype=int)
    meta.update(label=label, x=np.asarray(x, dtype=np.uint8), mask=np.asarray(mask, dtype=np.uint8),
                r=np.asarray(r, dtype=np.uint8), numpy_version=np.__version__)
    return encode(ports, x, mask, r), meta


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dut", required=True, help="build/<V> directory (ports.json)")
    ap.add_argument("--mode", required=True, choices=MODES)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--x-fixed", type=lambda s: int(s, 0), default=X_FIXED)
    ap.add_argument("--iv", type=int, default=1)
    ap.add_argument("--key", type=int, default=None)
    ap.add_argument("--out", required=True, help="output .npy (meta goes to <out>.meta.npz)")
    a = ap.parse_args()
    stim, meta = make_stimulus(a.dut, a.mode, a.n, a.seed, a.x_fixed, a.iv, a.key)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    np.save(a.out, stim)
    np.savez(a.out[:-4] + ".meta.npz" if a.out.endswith(".npy") else a.out + ".meta.npz", **meta)
    print("wrote %s %s (%s, %d rows)" % (a.out, stim.shape, a.mode, len(stim)))


if __name__ == "__main__":
    main()
