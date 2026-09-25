# SPDX-License-Identifier: Apache-2.0
"""Welch t-test (TVLA, fixed vs random), first and second order, accumulated online.

WelchT keeps, per class and per time sample, the count, mean and central moments M2..M4
and merges each new batch with the pairwise update formulas (Pebay 2008; the TVLA use is
Schneider & Moradi, CHES 2015), so any number of traces can be streamed in float64
without the cancellation of raw power sums.
  order 1: t = (m0 - m1) / sqrt(s0^2/n0 + s1^2/n1), s^2 = M2/(n-1)
  order 2: the same test on the centred squares (x - mean_class)^2, whose class mean is
           M2/n and variance M4/n - (M2/n)^2 (univariate second order)
A sample where both classes have zero variance gets t = 0 if the means agree, else +-inf.
Threshold: |t| > 4.5 means leakage (THRESHOLD).

tvla_curve(traces, labels, checkpoints) -> max|t| after each checkpoint trace count.
add_noise(traces, sigma, seed) adds white Gaussian noise (for the noise sweep).
"""
import numpy as np

THRESHOLD = 4.5


class WelchT:
    def __init__(self, n_samples):
        z = lambda: np.zeros(n_samples)
        self.n = [0, 0]
        self.mean = [z(), z()]
        self.m2 = [z(), z()]
        self.m3 = [z(), z()]
        self.m4 = [z(), z()]

    def update(self, traces, labels):
        traces = np.asarray(traces, dtype=np.float64)
        if traces.ndim == 1:
            traces = traces[:, None]
        labels = np.asarray(labels)
        for c in (0, 1):
            x = traces[labels == c]
            nb = len(x)
            if nb == 0:
                continue
            mb = x.mean(0)
            d = x - mb
            d2 = d * d
            m2b, m3b, m4b = d2.sum(0), (d2 * d).sum(0), (d2 * d2).sum(0)
            na = self.n[c]
            if na == 0:
                self.n[c], self.mean[c], self.m2[c], self.m3[c], self.m4[c] = nb, mb, m2b, m3b, m4b
                continue
            n = na + nb
            delta = mb - self.mean[c]
            ma2, ma3, ma4 = self.m2[c], self.m3[c], self.m4[c]
            self.mean[c] = self.mean[c] + delta * nb / n
            self.m4[c] = (ma4 + m4b + delta ** 4 * na * nb * (na * na - na * nb + nb * nb) / n ** 3
                          + 6 * delta ** 2 * (na * na * m2b + nb * nb * ma2) / n ** 2
                          + 4 * delta * (na * m3b - nb * ma3) / n)
            self.m3[c] = (ma3 + m3b + delta ** 3 * na * nb * (na - nb) / n ** 2
                          + 3 * delta * (na * m2b - nb * ma2) / n)
            self.m2[c] = ma2 + m2b + delta ** 2 * na * nb / n
            self.n[c] = n

    def t(self, order=1):
        n0, n1 = self.n
        if min(n0, n1) < 2:
            return np.zeros_like(self.mean[0])
        if order == 1:
            m0, m1 = self.mean
            v0, v1 = self.m2[0] / (n0 - 1), self.m2[1] / (n1 - 1)
        elif order == 2:
            m0, m1 = self.m2[0] / n0, self.m2[1] / n1
            v0 = self.m4[0] / n0 - m0 * m0
            v1 = self.m4[1] / n1 - m1 * m1
        else:
            raise ValueError("order must be 1 or 2")
        num = m0 - m1
        den = np.sqrt(np.maximum(v0, 0) / n0 + np.maximum(v1, 0) / n1)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = num / den
        zero = den == 0
        t[zero] = np.where(num[zero] == 0, 0.0, np.copysign(np.inf, num[zero]))
        return t


def tvla_curve(traces, labels, checkpoints, order=1):
    """max|t| and its sample index after each checkpoint (number of traces processed)."""
    traces = np.asarray(traces)
    if traces.ndim == 1:
        traces = traces[:, None]
    acc = WelchT(traces.shape[1])
    done, out = 0, []
    for cp in sorted(set(int(c) for c in checkpoints if 0 < c <= len(traces))):
        acc.update(traces[done:cp], labels[done:cp])
        done = cp
        t = np.abs(acc.t(order))
        k = int(np.argmax(t))
        out.append((cp, float(t[k]), k))
    return {"n": np.array([o[0] for o in out]), "max_abs_t": np.array([o[1] for o in out]),
            "argmax": np.array([o[2] for o in out]), "t_final": acc.t(order)}


def log_checkpoints(n, first=100, per_decade=10):
    """Roughly log-spaced trace counts from `first` up to n (n included)."""
    if n < first:
        return [n]
    k = np.unique(np.round(np.logspace(np.log10(first), np.log10(n), 1 + int(per_decade * np.log10(n / first)))))
    return sorted(set(int(v) for v in k) | {n})


def add_noise(traces, sigma, seed=0):
    rng = np.random.default_rng(seed)
    return np.asarray(traces, dtype=np.float64) + sigma * rng.standard_normal(np.shape(traces))
