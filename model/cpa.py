# SPDX-License-Identifier: Apache-2.0
"""Correlation power analysis (Pearson, per time sample) with online accumulation.

CPA accumulates, for G key guesses and m samples, the sums of h, h^2, t, t^2 and h*t
around fixed offsets (the first batch's means) to avoid cancellation, and returns the
correlation matrix rho (G, m). A guess scores max over samples of |rho| (signed=True:
max of rho, for when the leakage sign is known, e.g. charge drawn from VPWR grows with
the Hamming weight); the rank of the correct guess is 1 + the number of other guesses
scoring at least as high (ties count against the correct guess).

hw_sbox_hypotheses(iv, nonce): the kill test's K1 model for the unmasked variant in the
Ascon initialization context: x = iv<<4 | g<<2 | nonce for the four guesses g of the
two key bits (x1, x2); hypothesis = Hamming weight of the S-box output.
Note: some guesses' hypothesis vectors are strongly correlated (up to |rho| = 0.93 over
the 4 nonces, see guess_correlation()), so a leakage that is not exactly HW(S(x)) can
rank a wrong guess first.
"""
import numpy as np

from ascon_sbox import SBOX_NP, hw


class CPA:
    def __init__(self, n_samples, n_guesses):
        self.n = 0
        self.kt = self.kh = None
        self.st = np.zeros(n_samples)
        self.stt = np.zeros(n_samples)
        self.sh = np.zeros(n_guesses)
        self.shh = np.zeros(n_guesses)
        self.sht = np.zeros((n_guesses, n_samples))

    def update(self, traces, hyps):
        t = np.asarray(traces, dtype=np.float64)
        if t.ndim == 1:
            t = t[:, None]
        h = np.asarray(hyps, dtype=np.float64)
        if self.kt is None:
            self.kt, self.kh = t.mean(0), h.mean(0)
        t = t - self.kt
        h = h - self.kh
        self.n += len(t)
        self.st += t.sum(0)
        self.stt += (t * t).sum(0)
        self.sh += h.sum(0)
        self.shh += (h * h).sum(0)
        self.sht += h.T @ t

    def corr(self):
        n = self.n
        num = n * self.sht - np.outer(self.sh, self.st)
        vh = n * self.shh - self.sh ** 2
        vt = n * self.stt - self.st ** 2
        den = np.sqrt(np.outer(np.maximum(vh, 0), np.maximum(vt, 0)))
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(den > 0, num / den, 0.0)
        return r


def scores(rho, signed=False):
    return rho.max(1) if signed else np.abs(rho).max(1)


def rank_of(rho, correct, signed=False):
    score = scores(rho, signed)
    others = np.delete(score, correct)
    return 1 + int((others >= score[correct]).sum())


def cpa_curve(traces, hyps, correct, checkpoints, signed=False):
    """Rank of the correct guess and each guess's score after each checkpoint."""
    traces = np.asarray(traces)
    if traces.ndim == 1:
        traces = traces[:, None]
    acc = CPA(traces.shape[1], np.shape(hyps)[1])
    done, ranks, score = 0, [], []
    cps = sorted(set(int(c) for c in checkpoints if 0 < c <= len(traces)))
    for cp in cps:
        acc.update(traces[done:cp], hyps[done:cp])
        done = cp
        rho = acc.corr()
        ranks.append(rank_of(rho, correct, signed))
        score.append(scores(rho, signed))
    return {"n": np.array(cps), "rank": np.array(ranks), "scores": np.array(score), "rho_final": acc.corr()}


def hw_sbox_hypotheses(iv, nonce, n_guesses=4):
    """(n, 4) hypotheses HW(S(iv<<4 | g<<2 | nonce)) for the key-bit guesses g = 0..3."""
    nonce = np.asarray(nonce, dtype=np.int64)
    return np.stack([hw(SBOX_NP[(iv << 4) | (g << 2) | nonce]) for g in range(n_guesses)], axis=1)


def guess_correlation(iv):
    """4x4 correlation of the guesses' hypotheses over the 4 equally likely nonces."""
    return np.corrcoef(hw_sbox_hypotheses(iv, np.arange(4)).T.astype(float))
