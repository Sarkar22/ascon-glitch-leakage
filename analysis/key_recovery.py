# SPDX-License-Identifier: Apache-2.0
"""Profiled key recovery on the kill-test SPICE traces (post hoc; not a registered criterion).

Why: K1's one-column CPA failed. With two key bits and four nonce values, the four key
guesses' non-profiled hypotheses are almost collinear (docs/KILL_TEST.md, A2 and Results).
The four keys do, however, map the nonces onto disjoint sets of S-box inputs, so an
attacker with a template for each of the 32 inputs can tell them apart.

Attack context (the CPA context of docs/KILL_TEST.md): x = iv<<4 | key<<2 | nonce, where x0 is
the IV bit (known, constant), x1 x2 are the key bits (secret) and x3 x4 are the nonce bits
(known, vary). There are 8 scenarios (iv, key), each with 4 key guesses.

Data: the random-class rows of a TVLA campaign (the fixed-class rows, x = 0x0B, are never
used), or every row of a random-vs-random campaign. The first L+1 rows of every campaign are
dropped, as in analysis/kill_test.py.

Strict split (one per seed): the stimulus rows are cut into blocks of BLOCK consecutive rows.
Each block goes to profiling or attack at random. The last GUARD rows of every block go to
neither set. The window of row r depends on the inputs of rows r-L-1 .. r+L (L = latency:
r-2 .. r+1 for L = 1, r-3 .. r+2 for L = 2). So the two sets share no row and no time sample,
and no trace of one set depends on the input of a row of the other set. Traces on both sides
of a guard can depend on the same guard-row input (for L = 2, rows 46 and 50 both depend on
row 47). A guard row belongs to neither set and its input is independent of every labelled
row, so this passes no key information from one set to the other.

Profiling (profiling rows only):
  * the mean trace of each of the 32 inputs, the pooled within-input variance, and the
    one-way ANOVA F over x per sample;
  * POIs of the default template: the k_tmpl samples with the largest F, at least SPACING
    samples apart. k_tmpl is chosen from K_TMPL_CANDIDATES by 5-fold cross-validation on the
    profiling rows (score: the held-out information about x). The small-leak variants
    overfit with many POIs, because their 32 per-input means rest on a few hundred traces;
  * POIs of the per-key-bit template: the top-F sample and, for each key bit (x1, x2), the
    sample with the largest in-cell contrast of that bit (key_bit_chi2); a candidate closer
    than SPACING to one already taken is dropped (1 to 3 POIs). F ranks samples by how much
    the 32 means differ overall, which a large main effect of one bit (x1 in N) dominates.
    The contrast measures one bit's effect inside every combination of the other four bits,
    so it also finds a bit that leaks only through interactions (the stage-2 review's claim
    for x2 in N, B1);
  * the K_CORR samples with the largest F, for the correlation distinguisher.

Attack (attack rows only): for each scenario, take the attack rows whose x has that iv and key
(the nonce varies). Draw TRIALS random orderings. After n traces, each key guess g gets three
scores:
  tmpl       PRIMARY. The Gaussian log-likelihood of the n traces under the guess (pooled
             covariance), default POIs. It compares the traces with the absolute level of
             the template means, so it sees a key bit's main effect.
  tmpl_bits  the same Gaussian template on the per-key-bit POIs. Post hoc: added after the
             stage-2 review showed that x2 leaks in N at first order through interactions,
             which the default POIs miss. Its POI rule uses profiling rows only.
  corr       SECONDARY. The correlation, pooled over the n traces and the K_CORR POIs,
             between the traces and the template means of the inputs x = iv<<4 | g<<2 | nonce
             that the guess predicts. Both are divided by the per-POI pooled standard
             deviation and centred per POI over the n traces. Limitation: the centring
             removes the level shift between keys, i.e. exactly a key bit's main effect, so
             this distinguisher cannot see the kind of leak N has (see the injection test).
The primary distinguisher was fixed on 2026-09-25 after the stage-2 review, for the structural
reason above; earlier outputs quoted whichever of tmpl and corr had the lower GE.
Key rank: the number of wrong guesses that score higher than the correct one; ties count one
half. 0 means the key is recovered; 1.5 is random guessing among 4 guesses. Guessing entropy
(GE) is the mean key rank; the success rate (SR) is P(rank = 0), with ties shared. Per key bit
(x1 = key>>1, x2 = key&1): the probability that the top-ranked guess has the right bit
(random: 0.5).
Results are averaged over TRIALS orderings, then over (split, scenario) units. The splits reuse
the same rows, so the standard error of GE is taken over the 8 scenario means.

Variants of the attack:
  noise   white Gaussian noise of f times the campaign's noise unit (the largest per-sample
          std of the noiseless traces, results/kill_test/summary.json), f = 0.5 and 1. It is
          added to every trace, in profiling and attack alike, seeded.
  null    the profiling rows' x labels are permuted (seeded, independently for every split,
          order, noise level and draw), so the templates carry no information, and the whole
          pipeline (POIs, cross-validation, attack) runs unchanged. NULL_PERMS draws
          (NULL_PERMS_NOISY with added noise) give the null distribution of GE. p_vs_null =
          (1 + number of draws with GE <= the real GE) / (draws + 1), one-sided.
  order 2 (masked variants) the same attack on the centred squares (t - m)^2. Here m is the
          mean trace of the profiling rows. This is a univariate second-order attack;
          two-share masking is not meant to stop it. For N it is not independent evidence:
          at samples with a first-order mean shift, the centred square carries that shift.
  inject  positive control for the variants without key recovery (INJECT_DATASETS): add
          alpha times N's first-order leak to the real traces and run the attack unchanged
          (order 1, no noise, real labels, the same splits and orderings). The pattern is
          N_pooled's per-input mean at its top-F sample, minus its mean over the inputs,
          divided by N's within-input SD (all N_pooled rows). It is added as
          alpha * pattern[x] * (the target's within-input SD at the target sample), at the
          same time after the evaluation edge: sample + (L-1) * period/dt. alpha = 1 gives
          N's per-sample effect size. A leak counts as detected when the final GE lies below
          every null draw of the same dataset (p_vs_null <= 1/(draws+1)).
  U_cpa   templates from all random-class rows of U_tvla; attack on the four U_cpa_k
          campaigns (iv = 1, key k; the K1 CPA traces). So profiling and attack come from
          different campaigns. At the final checkpoint every trace of a key is used, so each
          key contributes one deterministic outcome.

Outputs: results/key_recovery/summary.json and ge_vs_traces.csv. The figures are drawn by
analysis/plot_key_recovery.py in the cac-sca image.

  OPENBLAS_NUM_THREADS=1 python3 analysis/key_recovery.py --jobs 3   (host python3 + numpy;
                                                        about 25 min with 3 processes)
  python3 analysis/key_recovery.py --datasets D_tvla   (redo one dataset; the others are kept)
  python3 analysis/key_recovery.py --quick         (2 splits, 10 trials, 2 null draws; smoke test)
"""
import argparse
import csv
import datetime
import hashlib
import json
import multiprocessing
import os
import sys
import time

import numpy as np

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(REPO, "analysis"))

import kill_test as kt       # noqa: E402  (campaign loader and conventions)

OUT = os.path.join(REPO, "results", "key_recovery")
KT_SUMMARY = os.path.join(REPO, "results", "kill_test", "summary.json")

N_INPUTS = 32
N_GUESSES = 4
SCENARIOS = [(iv, key) for iv in (0, 1) for key in range(4)]
KEY_BITS = {"x1": 3, "x2": 2}   # key bit -> bit position in x (x0 is bit 4)

BLOCK = 50          # rows per split block
GUARD = 3           # last rows of every block, used by neither set
K_CORR = 20         # POIs of the correlation distinguisher
K_TMPL = 2          # POIs of the Gaussian template if the inner split cannot choose
K_TMPL_CANDIDATES = (1, 2, 4, 8)
INNER_BLOCK, INNER_GUARD, INNER_FOLDS = 10, 1, 5   # cross-validation of the profiling rows
SPACING = 3         # minimum distance between POIs, in samples (10 ps each)
NOISE = (0.0, 0.5, 1.0)
GRID = (1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 70, 100, 150, 200, 300, 500, 700, 1000, 1500, 2000)
SR_GOAL = 0.9
NULL_PERMS = 20          # null draws without added noise
NULL_PERMS_NOISY = 5     # null draws with added noise (the null does not depend on the noise)
INJECT_DATASETS = ("D_tvla", "DA_tvla")
INJECT_SOURCE = "N_pooled"
INJECT_ALPHAS = (1.0, 0.5, 0.35, 0.25)
DISTS = ("tmpl", "tmpl_bits", "corr")
PRIMARY = "tmpl"

# dataset: variant, source campaigns (the first one gives the noise unit), orders to run
DATASETS = {
    "U_tvla": ("U", ("U_tvla",), (1,)),
    "N_tvla": ("N", ("N_tvla",), (1, 2)),
    "N_pooled": ("N", ("N_tvla", "N_rvr"), (1, 2)),
    "D_tvla": ("D", ("D_tvla",), (1, 2)),
    "DA_tvla": ("DA", ("DA_tvla",), (1, 2)),
}

DIST_TEXT = {
    "tmpl": ("primary: Gaussian template with pooled covariance on the default POIs (top ANOVA F, "
             "number chosen by cross-validation on the profiling rows); it compares the traces with "
             "the absolute level of the template means, so it sees a key bit's main effect"),
    "tmpl_bits": ("post hoc (added after stage-2 review B1): the same Gaussian template on 1-3 POIs, the "
                  "top-F sample plus, for each key bit x1 and x2, the sample with the largest in-cell "
                  "contrast of that bit (chi2 over the 16 cells of the other four bits), dropping a "
                  "candidate within 3 samples of one already taken; profiling rows only"),
    "corr": ("secondary: correlation between the traces and the guess's template means, both centred "
             "per POI over the attack traces; limitation: the centring removes the level shift "
             "between keys, which is a key bit's main effect, so it cannot see a leak like N's "
             "(see the injection test)"),
}


# ------------------------------------------------------------------ building blocks

def guess_inputs(iv, guess, nonce):
    """S-box inputs x = iv<<4 | guess<<2 | nonce predicted by a key guess (array of nonces)."""
    return (int(iv) << 4) | (int(guess) << 2) | (np.asarray(nonce, dtype=np.int64) & 3)


def scenario_of(x):
    """Scenario id s = iv<<2 | key (0..7) of S-box inputs x; iv = s >> 2, key = s & 3."""
    return np.asarray(x, dtype=np.int64) >> 2


def block_split(rows, seed, block=BLOCK, guard=GUARD, frac=0.5):
    """Boolean masks (profiling, attack) over the stimulus row indices `rows`.

    Blocks of `block` consecutive rows are assigned to profiling (probability `frac`) or to
    attack; the last `guard` rows of every block belong to neither set."""
    rows = np.asarray(rows, dtype=np.int64)
    blk = rows // block
    usable = (rows % block) < block - guard
    rng = np.random.default_rng(seed)
    to_prof = rng.random(int(blk.max()) + 1) < frac
    prof = usable & to_prof[blk]
    att = usable & ~to_prof[blk]
    return prof, att


def profile(tr, x, n_classes=N_INPUTS):
    """Per-input means (n_classes, S), counts, pooled within-input variance (S,) and the
    one-way ANOVA F over x (S,). Every class must occur at least once."""
    tr = np.asarray(tr, dtype=np.float64)
    x = np.asarray(x, dtype=np.int64)
    onehot = np.zeros((n_classes, len(x)))
    onehot[x, np.arange(len(x))] = 1.0
    cnt = onehot.sum(1)
    if (cnt == 0).any():
        raise ValueError("inputs without profiling rows: %s" % np.flatnonzero(cnt == 0).tolist())
    means = (onehot @ tr) / cnt[:, None]
    res = tr - means[x]
    within = (res * res).sum(0) / (len(x) - n_classes)
    grand = tr.mean(0)
    between = (cnt[:, None] * (means - grand) ** 2).sum(0) / (n_classes - 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        f = np.where(within > 0, between / within, 0.0)
    return {"means": means, "counts": cnt, "var": within, "F": f, "residual": res}


def key_bit_chi2(p, bit):
    """In-cell contrast of one input bit, per sample.

    For each of the 16 cells c with that bit clear (the other four bits fixed),
    t_c = (mean[c | 1<<bit] - mean[c]) / sqrt(var * (1/n_c + 1/n_c')); the result is
    sum_c t_c^2 (about chi2 with 16 degrees of freedom when the bit has no effect).
    p: the output of profile(). Unlike F, it also sees a bit that leaks only through
    interactions with the other bits."""
    m, n, v = p["means"], p["counts"], p["var"]
    lo = np.array([c for c in range(len(m)) if not (c >> bit) & 1])
    hi = lo | (1 << bit)
    d = m[hi] - m[lo]
    se2 = v[None, :] * (1.0 / n[hi] + 1.0 / n[lo])[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        t2 = np.where(se2 > 0, d * d / se2, 0.0)
    return t2.sum(0)


def select_pois(score, k, spacing=SPACING, chosen=()):
    """Indices of the k largest scores, at least `spacing` samples apart and from the
    already `chosen` indices (greedy). Returns only the new indices."""
    taken = [int(c) for c in chosen]
    new = []
    for j in np.argsort(-np.asarray(score), kind="stable"):
        if all(abs(int(j) - c) >= spacing for c in taken):
            taken.append(int(j))
            new.append(int(j))
            if len(new) == k:
                break
    return np.array(new, dtype=np.int64)


def per_bit_pois(p, spacing=SPACING):
    """POIs of the per-key-bit template: the top-F sample and, for each key bit (x1, x2),
    the sample with the largest key_bit_chi2. A candidate closer than `spacing` to a POI
    already taken is dropped, not replaced: its information is already there, and a
    replacement would only add a noise sample. So there are 1 to 3 POIs."""
    cand = [int(np.argmax(p["F"]))] + [int(np.argmax(key_bit_chi2(p, b))) for b in KEY_BITS.values()]
    chosen = []
    for j in cand:
        if all(abs(j - c) >= spacing for c in chosen):
            chosen.append(j)
    return np.array(chosen, dtype=np.int64)


def top_bit_success(scores, correct):
    """P(the top-ranked guess has the correct key bit), ties shared, for bit x1 (key>>1) and
    bit x2 (key&1). scores: (4, ...). Returns (p_x1, p_x2) of shape (...)."""
    scores = np.asarray(scores, dtype=np.float64)
    top = scores == scores.max(0, keepdims=True)
    g = np.arange(len(scores)).reshape((-1,) + (1,) * (scores.ndim - 1))
    out = []
    for sh in (1, 0):
        match = ((g >> sh) & 1) == ((correct >> sh) & 1)
        out.append((top & match).sum(0) / top.sum(0))
    return tuple(out)


def key_rank(scores, correct):
    """Expected 0-based rank of the correct guess and the expected success, ties shared.

    scores: (G, ...) array, higher is better. Returns (rank, success) of shape (...)."""
    scores = np.asarray(scores, dtype=np.float64)
    c = scores[correct]
    others = np.delete(scores, correct, axis=0)
    gt = (others > c).sum(0)
    eq = (others == c).sum(0)
    return gt + 0.5 * eq, (gt == 0) / (1.0 + eq)


class Templates:
    """Profiling result: template means at the POIs, per-POI scale, pooled covariance.

    poi_tmpl: the k_tmpl top-F samples, or the given `pois` (e.g. per_bit_pois)."""

    def __init__(self, tr, x, k_corr=K_CORR, k_tmpl=K_TMPL, spacing=SPACING, prof=None, pois=None):
        p = prof if prof is not None else profile(tr, x)
        self.F = p["F"]
        self.poi_corr = select_pois(p["F"], k_corr, spacing)
        self.poi_tmpl = np.asarray(pois, dtype=np.int64) if pois is not None else select_pois(
            p["F"], k_tmpl, spacing)
        self.ref = np.asarray(tr, dtype=np.float64).mean(0)          # shift for numerics only
        sd = np.sqrt(p["var"][self.poi_corr])
        self.scale = np.where(sd > 0, sd, 1.0)
        self.m_corr = (p["means"][:, self.poi_corr] - self.ref[self.poi_corr]) / self.scale
        self.m_tmpl = p["means"][:, self.poi_tmpl]
        r = p["residual"][:, self.poi_tmpl]
        cov = r.T @ r / (len(r) - N_INPUTS)
        ridge = 1e-9 * max(float(np.trace(cov)) / len(cov), 1e-30)
        self.cov_inv = np.linalg.inv(cov + ridge * np.eye(len(cov)))

    def corr_view(self, tr):
        return (np.asarray(tr)[:, self.poi_corr] - self.ref[self.poi_corr]) / self.scale

    def tmpl_view(self, tr):
        return np.asarray(tr)[:, self.poi_tmpl]


def heldout_info(tm, tr, x):
    """Information the Gaussian templates carry about x on held-out traces, in nats per trace:
    the mean log posterior of the true input (uniform prior) plus log 32; 0 means none."""
    d = tm.tmpl_view(tr)[:, None, :] - tm.m_tmpl[None]
    ll = -0.5 * np.einsum("nci,ij,ncj->nc", d, tm.cov_inv, d)
    lp = ll - np.logaddexp.reduce(ll, axis=1, keepdims=True)
    return float(lp[np.arange(len(x)), np.asarray(x)].mean() + np.log(N_INPUTS))


def choose_k_tmpl(tr, x, row, src, seed, candidates=K_TMPL_CANDIDATES, folds=INNER_FOLDS):
    """Number of template POIs, chosen on the profiling rows alone by K-fold cross-validation:
    blocks of INNER_BLOCK rows (the last INNER_GUARD rows of each unused) are dealt to `folds`
    folds at random; each fold is scored by heldout_info of templates fitted on the other
    folds. Returns (k, {k: mean score}); falls back to K_TMPL if no fold can be fitted."""
    fold = np.full(len(x), -1)
    for k in np.unique(src):
        sel = np.flatnonzero(src == k)
        r = np.asarray(row[sel], dtype=np.int64)
        blk = r // INNER_BLOCK
        usable = (r % INNER_BLOCK) < INNER_BLOCK - INNER_GUARD
        f_of_blk = np.random.default_rng(seed_of("inner", seed, int(k))).integers(0, folds, int(blk.max()) + 1)
        fold[sel[usable]] = f_of_blk[blk[usable]]
    scores = {kk: [] for kk in candidates}
    for f in range(folds):
        fit, hold = (fold >= 0) & (fold != f), fold == f
        if not hold.any():
            continue
        try:
            p = profile(tr[fit], x[fit])
        except ValueError:                      # an input missing from the fitting folds
            continue
        for kk in candidates:
            tm = Templates(tr[fit], x[fit], k_corr=1, k_tmpl=kk, prof=p)
            scores[kk].append(heldout_info(tm, tr[hold], x[hold]))
    mean = {kk: float(np.mean(v)) for kk, v in scores.items() if v}
    if not mean:
        return K_TMPL, {}
    return max(mean, key=mean.get), mean


def attack(tm, tr, x, iv, key, cps, trials, rng, extra=None):
    """Key ranks of one scenario's attack traces after each checkpoint.

    tm: Templates; tr (m, S) attack traces whose inputs x all have this iv and key.
    extra: optional {name: Templates} whose Gaussian template is scored on the same random
    orderings (e.g. {"tmpl_bits": ...}).
    Returns {"corr": (rank, success, p_x1, p_x2), "tmpl": (...), name: (...)}, each
    (trials, len(cps)): key rank, success, and the per-bit success of the top guess."""
    x = np.asarray(x, dtype=np.int64)
    if not (scenario_of(x) == ((iv << 2) | key)).all():
        raise ValueError("attack rows do not belong to scenario iv=%d key=%d" % (iv, key))
    nonce = x & 3
    cps = np.asarray(cps, dtype=np.int64)
    n_max = int(cps.max())
    m = len(x)
    if n_max > m:
        raise ValueError("checkpoint %d > %d attack rows" % (n_max, m))
    xg = np.stack([guess_inputs(iv, g, nonce) for g in range(N_GUESSES)])      # (4, m)

    def mahalanobis(t):                                                        # (4, m)
        d = t.tmpl_view(tr)[None] - t.m_tmpl[xg]
        return np.einsum("gmi,ij,gmj->gm", d, t.cov_inv, d)
    a = tm.corr_view(tr)                                                       # (m, P)
    h = tm.m_corr[xg]                                                          # (4, m, P)
    # random orderings, prefix sums at the checkpoints
    idx = np.argsort(rng.random((trials, m)), axis=1)[:, :n_max]               # (T, n)
    at = cps - 1

    def prefix(v, axis):
        return np.take(np.cumsum(v, axis=axis), at, axis=axis)
    ap = a[idx]                                                                # (T, n, P)
    sa, saa = prefix(ap, 1), prefix(ap * ap, 1)                                # (T, C, P)
    hp = h[:, idx]                                                             # (4, T, n, P)
    sh, shh, sah = prefix(hp, 2), prefix(hp * hp, 2), prefix(hp * ap[None], 2)  # (4, T, C, P)
    nn = cps[None, :, None].astype(np.float64)
    cov = (sah - sa[None] * sh / nn[None]).sum(-1)                             # (4, T, C)
    va = (saa - sa * sa / nn).sum(-1)                                          # (T, C)
    vh = (shh - sh * sh / nn[None]).sum(-1)                                    # (4, T, C)
    den = np.sqrt(np.maximum(va[None] * vh, 0.0))
    tiny = 1e-12 * max(float(np.abs(va).max()), 1e-300)
    with np.errstate(divide="ignore", invalid="ignore"):
        rho = np.where(den > tiny, cov / den, 0.0)
    out = {"corr": key_rank(rho, key) + top_bit_success(rho, key)}
    for name, t in [("tmpl", tm)] + sorted((extra or {}).items()):
        ll = -0.5 * prefix(mahalanobis(t)[:, idx], 2)                          # (4, T, C)
        out[name] = key_rank(ll, key) + top_bit_success(ll, key)
    return out


def guess_collinearity(tm):
    """How alike the four guesses' predictions are within a scenario: for every scenario, the
    pooled correlation over the 4 nonces and the corr POIs between the correct guess's
    (centred) template pattern and each wrong guess's. Values near 1 mean the centred
    correlation distinguisher can hardly separate the keys (the K1 problem); the Gaussian
    template also uses the level of the patterns, which centring removes."""
    h = tm.m_corr.reshape(8, 4, -1)
    h = h - h.mean(1, keepdims=True)
    out = []
    for iv, key in SCENARIOS:
        a = h[(iv << 2) | key]
        for g in range(N_GUESSES):
            if g != key:
                b = h[(iv << 2) | g]
                out.append(float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum())))
    return out


def checkpoints(n_max, grid=GRID):
    c = [g for g in grid if g < n_max] + [int(n_max)]
    return np.array(sorted(set(c)), dtype=np.int64)


# ------------------------------------------------------------------ data

def stimulus_hash(stim):
    """The SPICE runner's stimulus hash (sha256 of the uint8 array bytes)."""
    return hashlib.sha256(np.ascontiguousarray(np.asarray(stim).astype(np.uint8)).tobytes()).hexdigest()


def load_source(name, check_hash=True):
    """Usable rows of one campaign: traces (float64), x, stimulus row index and metadata.

    TVLA campaigns: random-class rows only. Random-vs-random and CPA campaigns: every row.
    The first L+1 rows are dropped (kill_test.py convention)."""
    variant, stem = (kt.TVLA_RUNS[name][:2] if name in kt.TVLA_RUNS else kt.CPA_RUNS[name])
    c = kt.load_campaign(name, variant, stem)
    if c is None:
        raise FileNotFoundError("campaign %s has no traces.npy" % name)
    if check_hash and c["man"].get("stimulus_sha256") not in (None, stimulus_hash(c["stim"])):
        raise ValueError("%s: stimulus file differs from the one the SPICE run used" % name)
    n = c["n_sim"]
    meta = c["meta"]
    mode = str(meta["mode"])
    rows = np.arange(n)
    keep = rows >= c["skip"]
    if mode == "tvla":
        keep &= meta["label"][:n] == 1
    elif mode not in ("rvr", "cpa", "random"):
        raise ValueError("%s: unsupported stimulus mode %s" % (name, mode))
    p = c["man"]["params"]
    out = {"name": name, "variant": variant, "mode": mode, "traces": c["traces"][keep],
           "x": meta["x"][:n][keep].astype(np.int64), "row": rows[keep], "rows_simulated": n,
           "latency": c["lat"], "dt": p["dt"], "pre": p["pre"], "period": p["period"],
           "run": kt.rel(c["run"])}
    if mode == "cpa":
        out.update(iv=int(meta["iv"]), key=int(meta["key"]))
    return out


def noise_units():
    with open(KT_SUMMARY) as f:
        s = json.load(f)
    return {k: v["spice"]["noise_unit_uA"] for k, v in s["campaigns"].items()}


def seed_of(*parts):
    """Deterministic seed from strings and numbers."""
    return int.from_bytes(hashlib.sha256(repr(parts).encode()).digest()[:8], "little")


# ------------------------------------------------------------------ experiments

def transform(tr, prof_mask, order):
    if order == 1:
        return tr
    m = tr[prof_mask].mean(0)
    return (tr - m) ** 2


def stable_from(values, cps, goal=SR_GOAL):
    """First checkpoint from which values stay >= goal (None if never)."""
    good = np.asarray(values) >= goal
    return next((int(cps[i]) for i in range(len(cps)) if good[i:].all()), None)


def aggregate(units, cps, groups):
    """units: list of (rank, success, p_x1, p_x2) arrays of shape (trials, C) -> summary per
    checkpoint, averaged over trials within a unit and then over units.

    groups: the scenario of each unit. The splits reuse the same rows, so the standard error
    of GE is taken over the scenario means (splits averaged first), not over the units."""
    m = np.array([[a.mean(0) for a in u] for u in units])     # (U, 4, C)
    k = len(units)
    ge = m[:, 0]
    groups = np.asarray(groups)
    gm = np.array([ge[groups == g].mean(0) for g in np.unique(groups)])
    out = {"n": cps.tolist(), "ge": ge.mean(0),
           "ge_sem": gm.std(0, ddof=1) / np.sqrt(len(gm)) if len(gm) > 1 else np.zeros(len(cps)),
           "sr": m[:, 1].mean(0), "sr_x1": m[:, 2].mean(0), "sr_x2": m[:, 3].mean(0), "units": k,
           "scenarios": int(len(gm))}
    out["traces_to_sr90"] = stable_from(out["sr"], cps)
    out["traces_to_sr90_x1"] = stable_from(out["sr_x1"], cps)
    out["traces_to_sr90_x2"] = stable_from(out["sr_x2"], cps)
    for key in ("ge", "sr", "sr_x1", "sr_x2"):
        out["final_" + key] = float(out[key][-1])
    out["final_ge_per_scenario"] = gm[:, -1]
    return out


def split_masks(ds, splits):
    """The strict splits of a dataset: [(profiling mask, attack mask)] per split seed."""
    x, row, src = ds["x"], ds["row"], ds["src"]
    masks = []
    for s in range(splits):
        prof = np.zeros(len(x), dtype=bool)
        att = np.zeros(len(x), dtype=bool)
        for k in np.unique(src):          # blocks never span two campaigns
            sel = src == k
            p, a = block_split(row[sel], seed_of("split", ds["name"], s, int(k)))
            prof[sel], att[sel] = p, a
        masks.append((prof, att))
    return masks


def run_split_dataset(ds, order, noise_f, perm, splits, trials, noise_unit, traces=None):
    """Strict-split experiment on one dataset; returns per-distinguisher aggregates and info.

    perm: None for the real labels, else the index of a null draw (permuted profiling labels).
    traces: replaces ds["traces"] (injection test); the splits, noise and orderings stay."""
    tr0 = ds["traces"] if traces is None else traces
    x, row, src = ds["x"], ds["row"], ds["src"]
    masks = split_masks(ds, splits)
    sizes = [int((att & (scenario_of(x) == sc)).sum()) for prof, att in masks for sc in range(8)]
    cps = checkpoints(min(sizes))
    units = {d: [] for d in DISTS}
    groups = []
    poi_info = []
    for s, (prof, att) in enumerate(masks):
        tr = tr0
        if noise_f > 0:
            rng = np.random.default_rng(seed_of("noise", ds["name"], s, noise_f))
            tr = tr0 + noise_f * noise_unit * rng.standard_normal(tr0.shape)
        tr = transform(tr, prof, order)
        xp = x[prof]
        if perm is not None:
            xp = np.random.default_rng(seed_of("perm", ds["name"], s, order, noise_f, perm)).permutation(xp)
        k_t, cv = choose_k_tmpl(tr[prof], xp, row[prof], src[prof], ("cv", ds["name"], s))
        p = profile(tr[prof], xp)
        tm = Templates(tr[prof], xp, k_tmpl=k_t, prof=p)
        tb = Templates(tr[prof], xp, prof=p, pois=per_bit_pois(p))
        poi_info.append({"max_F": float(tm.F.max()), "poi_corr": tm.poi_corr.tolist(),
                         "poi_bits": tb.poi_tmpl.tolist(),
                         "collinearity": guess_collinearity(tm), "k_tmpl": k_t,
                         "cv": {str(k): round(v, 4) for k, v in cv.items()}})
        if perm is None:        # the seed of the real run is the one used before the null draws
            rng = np.random.default_rng(seed_of("order", ds["name"], s, order, noise_f, False))
        else:
            rng = np.random.default_rng(seed_of("order", ds["name"], s, order, noise_f, True, perm))
        for iv, key in SCENARIOS:
            sel = att & (scenario_of(x) == ((iv << 2) | key))
            r = attack(tm, tr[sel], x[sel], iv, key, cps, trials, rng, extra={"tmpl_bits": tb})
            groups.append((iv << 2) | key)
            for d in units:
                units[d].append(r[d])
    res = {d: aggregate(u, cps, groups) for d, u in units.items()}
    info = {"rows_profiling_mean": float(np.mean([p.sum() for p, _ in masks])),
            "rows_attack_mean": float(np.mean([a.sum() for _, a in masks])),
            "attack_rows_per_scenario_min": int(min(sizes)),
            "attack_rows_per_scenario_max": int(max(sizes)),
            "profiling_max_F_mean": float(np.mean([p["max_F"] for p in poi_info])),
            "poi_corr_split0": poi_info[0]["poi_corr"],
            "poi_bits_per_split": [p["poi_bits"] for p in poi_info],
            "k_tmpl_chosen": [p["k_tmpl"] for p in poi_info],
            "heldout_info_nats_split0": poi_info[0]["cv"],
            "guess_pattern_corr_split0": [round(min(poi_info[0]["collinearity"]), 3),
                                          round(float(np.mean(poi_info[0]["collinearity"])), 3),
                                          round(max(poi_info[0]["collinearity"]), 3)]}
    return res, info


def run_cpa_attack(prof_ds, targets, noise_f, perm, trials, noise_unit):
    """Templates from all of prof_ds; attack on the U_cpa_k campaigns (one scenario each).
    perm: None for the real labels, else the index of a null draw."""
    tr = prof_ds["traces"]
    if noise_f > 0:
        tr = tr + noise_f * noise_unit * np.random.default_rng(
            seed_of("noise", "U_cpa_prof", noise_f)).standard_normal(tr.shape)
    xp = prof_ds["x"]
    if perm is not None:
        xp = np.random.default_rng(seed_of("perm", "U_cpa_prof", noise_f, perm)).permutation(xp)
    k_t, cv = choose_k_tmpl(tr, xp, prof_ds["row"], np.zeros(len(xp), dtype=int), ("cv", "U_cpa"))
    p = profile(tr, xp)
    tm = Templates(tr, xp, k_tmpl=k_t, prof=p)
    tb = Templates(tr, xp, prof=p, pois=per_bit_pois(p))
    cps = checkpoints(min(len(t["x"]) for t in targets))
    units = {d: [] for d in DISTS}
    for t in targets:
        ta = t["traces"]
        if noise_f > 0:
            ta = ta + noise_f * noise_unit * np.random.default_rng(
                seed_of("noise", t["name"], noise_f)).standard_normal(ta.shape)
        if perm is None:
            rng = np.random.default_rng(seed_of("order", t["name"], noise_f, False))
        else:
            rng = np.random.default_rng(seed_of("order", t["name"], noise_f, True, perm))
        r = attack(tm, ta, t["x"], t["iv"], t["key"], cps, trials, rng, extra={"tmpl_bits": tb})
        for d in units:
            units[d].append(r[d])
    res = {d: aggregate(u, cps, [t["key"] for t in targets]) for d, u in units.items()}
    info = {"k_tmpl_chosen": k_t, "heldout_info_nats": {str(k): round(v, 4) for k, v in cv.items()},
            "poi_bits": tb.poi_tmpl.tolist()}
    return res, info


# ------------------------------------------------------------------ null distribution

_WORK = {}        # the job of the worker processes (inherited through fork, not pickled)


def _null_draw(perm):
    w = _WORK
    if w["kind"] == "split":
        return run_split_dataset(w["ds"], w["order"], w["noise_f"], perm, w["splits"], w["trials"],
                                 w["noise_unit"])[0]
    return run_cpa_attack(w["prof_ds"], w["targets"], w["noise_f"], perm, w["trials"], w["noise_unit"])[0]


def null_draws(work, perms, jobs):
    """Run the null draws 0..perms-1 of one configuration, in `jobs` processes (fork)."""
    _WORK.clear()
    _WORK.update(work)
    if jobs <= 1 or perms <= 1:
        return [_null_draw(p) for p in range(perms)]
    with multiprocessing.get_context("fork").Pool(min(jobs, perms)) as pool:
        return pool.map(_null_draw, range(perms))


def null_summary(draws, real):
    """Null distribution per distinguisher from a list of run results (one per draw), and the
    real result's one-sided p value against it."""
    out = {}
    for d in DISTS:
        ge = np.array([r[d]["ge"] for r in draws])            # (draws, C)
        fin = ge[:, -1]
        sr = np.array([r[d]["final_sr"] for r in draws])
        g = real[d]["final_ge"]
        out[d] = {"draws": int(len(draws)), "n": draws[0][d]["n"], "ge_mean": rounded(ge.mean(0)),
                  "ge_sd": rounded(ge.std(0, ddof=1) if len(draws) > 1 else np.zeros(ge.shape[1])),
                  "final_ge": rounded(fin), "final_ge_mean": round(float(fin.mean()), 4),
                  "final_ge_sd": round(float(fin.std(ddof=1)), 4) if len(fin) > 1 else 0.0,
                  "final_ge_min": round(float(fin.min()), 4), "final_ge_max": round(float(fin.max()), 4),
                  "final_ge_p05": round(float(np.percentile(fin, 5)), 4),
                  "final_ge_p95": round(float(np.percentile(fin, 95)), 4),
                  "final_sr_mean": round(float(sr.mean()), 4),
                  "p_vs_null": round(float((1 + (fin <= g).sum()) / (len(fin) + 1)), 4)}
    return out


# ------------------------------------------------------------------ injection test

def injection_pattern(src_ds):
    """N's first-order leak as a per-input pattern: at the top-F sample of all rows of the
    source dataset, the per-input means minus their mean over the inputs, divided by the
    within-input SD. Returns (sample, pattern (32,))."""
    p = profile(src_ds["traces"], src_ds["x"])
    s = int(np.argmax(p["F"]))
    m = p["means"][:, s]
    return s, (m - m.mean()) / np.sqrt(p["var"][s])


def inject(traces, x, sample, pattern, alpha):
    """traces with alpha * pattern[x] * (within-input SD at `sample`) added at `sample`."""
    p = profile(traces, x)
    out = np.array(traces, dtype=np.float64, copy=True)
    out[:, sample] += alpha * pattern[np.asarray(x)] * np.sqrt(p["var"][sample])
    return out


def run_injection(ds, src_ds, null, splits, trials, noise_unit):
    """Positive control: the attack on ds with alpha x N's leak added (order 1, no noise)."""
    s_n, pattern = injection_pattern(src_ds)
    shift = int(round((ds["latency"] - 1) * ds["period"] / ds["dt"]))
    target = s_n + shift
    entry = {"source": INJECT_SOURCE, "source_sample": s_n,
             "source_sample_ns_after_edge": round((s_n + 0.5) * ds["dt"] - ds["pre"], 4),
             "target_sample": target, "target_ns_after_first_edge": round((target + 0.5) * ds["dt"] - ds["pre"], 4),
             "pattern_sd_over_inputs": round(float(pattern.std()), 4),
             "note": ("alpha x N's first-order leak (per-input mean pattern at N's top-F sample, in units "
                      "of the within-input SD) added at one sample of the real traces; alpha = 1 is N's "
                      "per-sample effect size; detected = final GE below every null draw of order1_noise0"),
             "alphas": {}, "smallest_detected_alpha": {}}
    for a in INJECT_ALPHAS:
        tr = inject(ds["traces"], ds["x"], target, pattern, a)
        res, _ = run_split_dataset(ds, 1, 0.0, None, splits, trials, noise_unit, traces=tr)
        entry["alphas"]["%g" % a] = {d: dict(pack(res[d]), p_vs_null=round(float(
            (1 + sum(v <= res[d]["final_ge"] for v in null[d]["final_ge"])) / (null[d]["draws"] + 1)), 4),
            detected=bool(res[d]["final_ge"] < null[d]["final_ge_min"])) for d in DISTS}
    for d in DISTS:             # the smallest alpha from which every stronger leak is detected
        smallest = None
        for a in sorted(INJECT_ALPHAS, reverse=True):
            if not entry["alphas"]["%g" % a][d]["detected"]:
                break
            smallest = a
        entry["smallest_detected_alpha"][d] = smallest
    return entry


# ------------------------------------------------------------------ driver

def build_dataset(name, sources, cache):
    parts = [cache[s] for s in sources]
    return {"name": name, "traces": np.concatenate([p["traces"] for p in parts]),
            "x": np.concatenate([p["x"] for p in parts]),
            "row": np.concatenate([p["row"] for p in parts]),
            "src": np.concatenate([np.full(len(p["x"]), i) for i, p in enumerate(parts)]),
            "latency": parts[0]["latency"], "dt": parts[0]["dt"], "pre": parts[0]["pre"],
            "period": parts[0]["period"]}


def rounded(a, nd=4):
    return [round(float(v), nd) for v in a]


def perms_for(noise_f, a):
    return a.perms if noise_f == 0 else a.perms_noisy


def log_line(name, tag, res, null, extra, t0):
    print("%-9s %-14s tmpl GE %.2f SR %.2f (x1 %.2f x2 %.2f) | bits GE %.2f SR %.2f | corr GE %.2f | "
          "null tmpl %.2f+-%.2f p %.3f | %s  %.0fs" % (
              name, tag, res["tmpl"]["final_ge"], res["tmpl"]["final_sr"], res["tmpl"]["final_sr_x1"],
              res["tmpl"]["final_sr_x2"], res["tmpl_bits"]["final_ge"], res["tmpl_bits"]["final_sr"],
              res["corr"]["final_ge"], null["tmpl"]["final_ge_mean"], null["tmpl"]["final_ge_sd"],
              null["tmpl"]["p_vs_null"], extra, time.time() - t0), flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--splits", type=int, default=10)
    ap.add_argument("--trials", type=int, default=50)
    ap.add_argument("--perms", type=int, default=NULL_PERMS, help="null draws without added noise")
    ap.add_argument("--perms-noisy", type=int, default=NULL_PERMS_NOISY, help="null draws with noise")
    ap.add_argument("--jobs", type=int, default=1, help="processes for the null draws")
    ap.add_argument("--datasets", nargs="*", default=list(DATASETS) + ["U_cpa"])
    ap.add_argument("--quick", action="store_true", help="2 splits, 10 trials, 2 null draws, no files")
    a = ap.parse_args(argv)
    if a.quick:
        a.splits, a.trials, a.perms, a.perms_noisy = 2, 10, 2, 2
    units = noise_units()
    cache = {}
    need = {s for d in a.datasets if d in DATASETS for s in DATASETS[d][1]}
    need |= {"U_tvla"} if "U_cpa" in a.datasets else set()
    need |= set(DATASETS[INJECT_SOURCE][1]) if set(a.datasets) & set(INJECT_DATASETS) else set()
    for s in sorted(need):
        cache[s] = load_source(s)
        print("loaded %-8s %5d usable rows of %d" % (s, len(cache[s]["x"]), cache[s]["rows_simulated"]),
              flush=True)
    summary = {"generated": datetime.date.today().isoformat(),
               "note": ("post hoc profiled attack, not a pre-registered criterion; key rank = number of "
                        "wrong guesses scored above the correct one (ties count 1/2): 0 = recovered, "
                        "1.5 = random for 4 guesses; GE = mean key rank, SR = P(rank 0)"),
               "primary_distinguisher": PRIMARY,
               "distinguishers": DIST_TEXT,
               "method": {"block_rows": BLOCK, "guard_rows": GUARD, "profiling_fraction": 0.5,
                          "splits": a.splits, "trials_per_unit": a.trials, "k_poi_corr": K_CORR,
                          "k_poi_template_candidates": list(K_TMPL_CANDIDATES),
                          "k_poi_template_fallback": K_TMPL,
                          "k_poi_template_choice": "%d-fold cross-validation on the profiling rows (blocks "
                                                   "of %d rows, guard %d); held-out information about x" % (
                                                       INNER_FOLDS, INNER_BLOCK, INNER_GUARD),
                          "poi_min_spacing_samples": SPACING,
                          "poi_selection": "top ANOVA F over the 32 inputs, profiling rows only",
                          "poi_selection_tmpl_bits": "top-F sample plus the top in-cell contrast sample of "
                                                     "key bit x1 and of x2, near-duplicates dropped; "
                                                     "profiling rows only",
                          "noise_factors": list(NOISE), "sr_goal": SR_GOAL,
                          "null_draws": {"no_noise": a.perms, "with_noise": a.perms_noisy},
                          "null": ("profiling labels permuted independently per split, order, noise and "
                                   "draw; whole pipeline rerun; p_vs_null = (1 + #draws with GE <= real) / "
                                   "(draws + 1)"),
                          "injection_alphas": list(INJECT_ALPHAS),
                          "scenarios": ["iv=%d key=%d" % s for s in SCENARIOS],
                          "units": "one (split, scenario) pair; GE/SR averaged over trials within a unit",
                          "ge_sem": "standard error over the scenario means (splits averaged first; the "
                                    "splits reuse the same rows): 8 scenarios, 4 keys for U_cpa"},
               "sources": {s: {"run": c["run"], "mode": c["mode"], "rows_simulated": c["rows_simulated"],
                               "usable_rows": int(len(c["x"])), "latency": c["latency"]}
                           for s, c in cache.items()},
               "datasets": {}}
    rows_csv = []
    t0 = time.time()
    for name in a.datasets:
        if name == "U_cpa":
            summary["datasets"][name] = run_u_cpa(cache, units, a, rows_csv, t0)
            continue
        variant, sources, orders = DATASETS[name]
        ds = build_dataset(name, sources, cache)
        unit = units[sources[0]]
        entry = {"variant": variant, "sources": list(sources), "noise_unit_uA": unit, "results": {}}
        for order in orders:
            for f in NOISE:
                res, info = run_split_dataset(ds, order, f, None, a.splits, a.trials, unit)
                draws = null_draws({"kind": "split", "ds": ds, "order": order, "noise_f": f,
                                    "splits": a.splits, "trials": a.trials, "noise_unit": unit},
                                   perms_for(f, a), a.jobs)
                null = null_summary(draws, res)
                tag = "order%d_noise%g" % (order, f)
                entry["results"][tag] = {d: dict(pack(r), p_vs_null=null[d]["p_vs_null"]) for d, r in res.items()}
                entry["results"][tag]["null"] = null
                entry["results"][tag]["split_info"] = info
                for d, r in res.items():
                    rows_csv += csv_rows(name, variant, order, d, f, f * unit, "real", None, r, None)
                    rows_csv += csv_null_rows(name, variant, order, d, f, f * unit, null[d])
                log_line(name, tag, res, null, "n=%d k %s" % (res["tmpl"]["n"][-1], info["k_tmpl_chosen"]), t0)
        if name in INJECT_DATASETS:
            src_ds = build_dataset(INJECT_SOURCE, DATASETS[INJECT_SOURCE][1], cache)
            entry["injection"] = run_injection(ds, src_ds, entry["results"]["order1_noise0"]["null"],
                                               a.splits, a.trials, unit)
            for al, rr in entry["injection"]["alphas"].items():
                for d in DISTS:
                    rows_csv += csv_rows(name, variant, 1, d, 0.0, 0.0, "real", float(al), rr[d], None)
                print("%-9s inject alpha %-4s tmpl GE %.2f SR %.2f det %s | bits GE %.2f | corr GE %.2f det %s" % (
                    name, al, rr["tmpl"]["final_ge"], rr["tmpl"]["final_sr"], rr["tmpl"]["detected"],
                    rr["tmpl_bits"]["final_ge"], rr["corr"]["final_ge"], rr["corr"]["detected"]), flush=True)
        summary["datasets"][name] = entry
    summary["statements"] = statements(summary)
    summary["runtime_s_last_invocation"] = round(time.time() - t0, 1)
    summary["sources_by_dataset"] = {n: (["U_tvla"] + ["U_cpa_k%d" % k for k in range(4)] if n == "U_cpa"
                                         else list(DATASETS[n][1])) for n in summary["datasets"]}
    if a.quick:
        return summary
    os.makedirs(OUT, exist_ok=True)
    summary, rows_csv = merge_previous(summary, rows_csv, a.datasets)
    summary["statements"] = statements(summary)
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    with open(os.path.join(OUT, "ge_vs_traces.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEAD)
        w.writerows(rows_csv)
    print("wrote", kt.rel(os.path.join(OUT, "summary.json")), "and ge_vs_traces.csv")
    return summary


def run_u_cpa(cache, units, a, rows_csv, t0):
    """Templates from U_tvla, attack on the K1 CPA campaigns, at every noise level."""
    targets = [load_source("U_cpa_k%d" % k) for k in range(4)]
    unit = units["U_tvla"]
    prof = profile(cache["U_tvla"]["traces"], cache["U_tvla"]["x"])
    dt = cache["U_tvla"]["dt"]
    charge = [[round(float(t["traces"].sum(1).mean() * dt), 1),
               round(float(prof["means"][t["x"]].sum(1).mean() * dt), 1)] for t in targets]
    deficit = [round(100.0 * (1.0 - q / m), 1) for q, m in charge]
    entry = {"variant": "U", "profiling": "all random-class rows of U_tvla",
             "attack": "U_cpa_k0..3 (iv 1, keys 0-3)", "noise_unit_uA": unit,
             "attack_rows_per_key": [len(t["x"]) for t in targets],
             "charge_per_window_fC_attack_vs_templates": charge,
             "charge_deficit_pct_per_key": deficit,
             "note": ("the CPA campaigns' neighbouring rows share the IV and key bits, so fewer input "
                      "bits toggle than in U_tvla and the traces draw %.0f-%.0f %% less charge than the "
                      "templates predict; the Gaussian template (absolute level) suffers from this "
                      "mismatch between campaigns, the centred correlation does not. At the final "
                      "checkpoint every trace of a key is used, so each of the 4 keys is one "
                      "deterministic outcome" % (min(deficit), max(deficit))),
             "results": {}}
    for f in NOISE:
        res, info = run_cpa_attack(cache["U_tvla"], targets, f, None, a.trials, unit)
        draws = null_draws({"kind": "cpa", "prof_ds": cache["U_tvla"], "targets": targets, "noise_f": f,
                            "trials": a.trials, "noise_unit": unit}, perms_for(f, a), a.jobs)
        null = null_summary(draws, res)
        tag = "order1_noise%g" % f
        entry["results"][tag] = {d: dict(pack(r), p_vs_null=null[d]["p_vs_null"]) for d, r in res.items()}
        entry["results"][tag]["null"] = null
        entry["results"][tag]["profiling_info"] = info
        for d, r in res.items():
            rows_csv += csv_rows("U_cpa", "U", 1, d, f, f * unit, "real", None, r, None)
            rows_csv += csv_null_rows("U_cpa", "U", 1, d, f, f * unit, null[d])
        log_line("U_cpa", tag, res, null, "n=%d" % res["tmpl"]["n"][-1], t0)
    return entry


def bit_words(r):
    """'key bit x1 P 1.00, x2 P 0.63' from a packed result."""
    return "P(x1) %.2f, P(x2) %.2f" % (r["final_sr_x1"], r["final_sr_x2"])


def detect_words(inj, d):
    """What the injection test detects for distinguisher d, in words."""
    al = inj["smallest_detected_alpha"][d]
    ge = {a: inj["alphas"]["%g" % a][d]["final_ge"] for a in INJECT_ALPHAS}
    if al is None:
        return "none of the injected leaks, not even at N's full strength (GE %.2f)" % ge[max(INJECT_ALPHAS)]
    below = [b for b in INJECT_ALPHAS if b < al]
    text = "an injected leak shaped like N's down to %g x N's strength (GE %.2f)" % (al, ge[al])
    if below:
        text += ", not at %s" % " or ".join("%g x (GE %.2f)" % (b, ge[b]) for b in below)
    else:
        text += ", the smallest strength tried"
    return text


def statements(summary):
    """Short statements that follow from the numbers (kept next to them, so that cost.md,
    the notebook and this file say the same thing). Every claim is conditional on the data."""
    ds = summary["datasets"]
    out = {"primary": ("The Gaussian template (tmpl) is the primary distinguisher; tmpl_bits is a post hoc "
                       "variant of it with per-key-bit POIs; the correlation (corr) is secondary and cannot "
                       "see a key bit's main effect.")}
    n = ds.get("N_pooled", {}).get("results", {}).get("order1_noise0")
    if n:
        t, b = n["tmpl"], n["tmpl_bits"]
        out["N"] = ("N, first order, %d attack traces per key. Default template (POIs by overall F): GE %.2f, "
                    "SR %.2f, %s. Template with per-key-bit POIs (post hoc): GE %.2f, SR %.2f, %s "
                    "(null GE %.2f +- %.2f; p = %.3f)." % (
                        t["n"][-1], t["final_ge"], t["final_sr"], bit_words(t), b["final_ge"], b["final_sr"],
                        bit_words(b), n["null"]["tmpl_bits"]["final_ge_mean"],
                        n["null"]["tmpl_bits"]["final_ge_sd"], b["p_vs_null"]))
        o2 = ds["N_pooled"]["results"].get("order2_noise0")
        if o2:
            out["N_order2"] = ("Second order on N (template GE %.2f) is not independent evidence: the centred "
                               "square at samples with a first-order mean shift carries that shift."
                               % o2["tmpl"]["final_ge"])
    for name in INJECT_DATASETS:
        e = ds.get(name)
        if not e or "injection" not in e:
            continue
        r = e["results"]["order1_noise0"]
        nl = r["null"]["tmpl"]
        inj = e["injection"]
        out[e["variant"]] = (
            "%s, first order, %d attack traces per key: template GE %.2f against a null of %.2f +- %.2f "
            "(%d permutations; p = %.3f). At this data volume the template detects %s; the correlation "
            "detects %s." % (e["variant"], r["tmpl"]["n"][-1], r["tmpl"]["final_ge"], nl["final_ge_mean"],
                             nl["final_ge_sd"], nl["draws"], r["tmpl"]["p_vs_null"],
                             detect_words(inj, "tmpl"), detect_words(inj, "corr")))
    u = ds.get("U_cpa")
    if u:
        r = u["results"]
        t = r["order1_noise0"]["tmpl"]
        got = ("template SR >= 0.9 from %d traces per key" % t["traces_to_sr90"]
               if t["traces_to_sr90"] is not None else "template GE %.2f, SR %.2f" % (t["final_ge"], t["final_sr"]))
        out["K1"] = ("Post hoc, a profiled attack on the K1 CPA traces (templates from U_tvla, no added noise): "
                     "%s. This answers the question K1 was meant to settle, whether the traces carry "
                     "exploitable key information, but K1 stays failed as registered." % got)
        per = []
        for f in NOISE[1:]:
            rr = r["order1_noise%g" % f]
            per.append("%gx noise: template GE %.2f (SR %.2f), correlation GE %.2f (SR %.2f)" % (
                f, rr["tmpl"]["final_ge"], rr["tmpl"]["final_sr"], rr["corr"]["final_ge"], rr["corr"]["final_sr"]))
        lo, hi = min(u["attack_rows_per_key"]), max(u["attack_rows_per_key"])
        out["U_cpa_noise"] = ("With added noise, on all %s traces per key (4 keys, one outcome each): %s. "
                              "The CPA traces draw %.0f-%.0f %% less charge than the U_tvla templates predict." % (
                                  "%d" % lo if lo == hi else "%d-%d" % (lo, hi), "; ".join(per),
                                  min(u["charge_deficit_pct_per_key"]), max(u["charge_deficit_pct_per_key"])))
    return out


def merge_previous(summary, rows_csv, done):
    """A run on some datasets keeps the other datasets' entries of an earlier run (same
    method settings), so e.g. D can be redone alone when its campaign grows."""
    path = os.path.join(OUT, "summary.json")
    if not os.path.exists(path):
        return summary, rows_csv
    with open(path) as f:
        old = json.load(f)
    if old.get("method") != summary["method"]:
        print("earlier summary.json used other settings: not merged")
        return summary, rows_csv
    for name, entry in old.get("datasets", {}).items():
        if name not in done:
            summary["datasets"][name] = entry
            if name in old.get("sources_by_dataset", {}):
                for src in old["sources_by_dataset"][name]:
                    summary["sources"].setdefault(src, old["sources"].get(src))
    summary["sources_by_dataset"] = {n: (["U_tvla"] + ["U_cpa_k%d" % k for k in range(4)] if n == "U_cpa"
                                         else list(DATASETS[n][1])) for n in summary["datasets"]}
    with open(os.path.join(OUT, "ge_vs_traces.csv")) as f:
        kept = [r for r in list(csv.reader(f))[1:] if r and r[0] not in done]
    order = {n: i for i, n in enumerate(list(DATASETS) + ["U_cpa"])}
    rows = sorted(kept + [[str(v) for v in r] for r in rows_csv], key=lambda r: order.get(r[0], 99))
    summary["datasets"] = {n: summary["datasets"][n] for n in sorted(summary["datasets"], key=lambda n: order.get(n, 99))}
    return summary, rows


def pack(r):
    out = {"n": r["n"], "ge": rounded(r["ge"]), "ge_sem": rounded(r["ge_sem"]), "sr": rounded(r["sr"]),
           "sr_x1": rounded(r["sr_x1"]), "sr_x2": rounded(r["sr_x2"]), "units": r["units"],
           "scenarios": r["scenarios"]}
    for k in ("final_ge", "final_sr", "final_sr_x1", "final_sr_x2"):
        out[k] = round(r[k], 4)
    for k in ("traces_to_sr90", "traces_to_sr90_x1", "traces_to_sr90_x2"):
        out[k] = r[k]
    out["final_ge_per_scenario"] = rounded(r["final_ge_per_scenario"], 3)
    return out


CSV_HEAD = ["dataset", "variant", "order", "distinguisher", "noise_factor", "noise_uA", "labels",
            "injected_alpha", "attack_traces", "guessing_entropy", "ge_sem", "ge_null_sd", "success_rate",
            "success_key_bit_x1", "success_key_bit_x2", "units_or_draws"]


def csv_rows(name, variant, order, dist, f, noise_ua, labels, alpha, r, null_sd):
    """One CSV row per checkpoint of a real (or injected) result."""
    return [[name, variant, order, dist, f, round(noise_ua, 3), labels, "" if alpha is None else alpha, n,
             "%.4f" % g, "%.4f" % e, "", "%.4f" % s, "%.4f" % b1, "%.4f" % b2, r["units"]]
            for n, g, e, s, b1, b2 in zip(r["n"], r["ge"], r["ge_sem"], r["sr"], r["sr_x1"], r["sr_x2"])]


def csv_null_rows(name, variant, order, dist, f, noise_ua, nl):
    """One CSV row per checkpoint of a null distribution: mean GE and its SD over the draws."""
    return [[name, variant, order, dist, f, round(noise_ua, 3), "permuted", "", n, "%.4f" % g, "",
             "%.4f" % s, "", "", "", nl["draws"]] for n, g, s in zip(nl["n"], nl["ge_mean"], nl["ge_sd"])]


if __name__ == "__main__":
    main()
