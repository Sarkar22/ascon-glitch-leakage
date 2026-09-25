<!-- SPDX-License-Identifier: Apache-2.0 -->
# Review: side-channel methodology (kill test, run of 2026-09-24)

Reviewer lens: try to refute the kill-test conclusion. Is the masking correct? Are the stimulus, the TVLA and the
controls sound? Can any stimulus or simulator artifact create or hide first-order leakage? Is the summary
sentence "N leaks through glitches, D does not, zero-delay says both are safe" supported? I did not change any
code, result or pre-registered text. My extra SPICE run went to `runs/sca_review/` (git-ignored). My check
scripts were scratch files and are not committed; each check is described below well enough to redo it.

## Verdict

**The core finding survives every attempt to refute it:** N leaks at first order in transistor-level SPICE,
while the zero-delay model says it is secure. The leak comes from the timing of the combinational logic
(glitches and arrival order), not from settled values, the testbench or the simulator's numerics.

**Parts of the summary and of the Results text are not supported and need rewording (blocking for the doc,
not for the N finding):**
1. "D does not leak" is not supported. D's leak is real at the net level in SPICE. It is only not resolved in
   the supply current within 4,997 traces, and 4,997 is half of A3's minimum.
2. The GO/NO-GO paragraph answers "yes" to a question that has two parts. The second part, whether the register
   barrier removes the leak, is still open.
3. "N leaks in timing, not in energy" is contradicted by the data.
4. "Level 2 gets N at the right size" is a coincidence of max|t|. Level 2's leak waveform does not match
   SPICE's.

Verdict: **issues** (wording and claims; no defect in the measurement of N).

## What I re-ran or checked independently

| # | Check | Result |
|---|---|---|
| 1 | Exhaustive masking check, re-implemented from scratch by parsing the simulated `build/<V>/dut.sp` (not `graph.json`): all 32,768 (x, mask, r) | N, D, DA: function correct; no net's value depends on x; **the joint settled inputs of every combinational cell are independent of x** (stronger than per-net, and covers cell-internal nodes); glitch-extended failures N 39, D 12, DA 0, identical to `results/probing/*.json` |
| 2 | Level-1 (zero-delay) model vs my own cycle simulator built from `dut.sp`, 3,000 rows of `M_tvla` | identical toggle count in every window for N, D and DA |
| 3 | Stimulus files | all regenerate bit for bit from their seeds; shares decode to `meta` x/mask/r; fixed rows are 0x0B; masks and r uniform per class (chi2, 31 dof: 21-49) and fresh (lag-1 bit correlation <= 0.021; mask-r <= 0.017); label runs as expected for random interleaving; masks-off rows have mask = r = 0; random-vs-random uses random x in both classes; every campaign's `stimulus_sha256` and `dut_sp_sha256` match the files on disk |
| 4 | Welch t recomputed two-pass from the raw traces (not the online accumulator) | every campaign's max\|t\| and peak sample match `summary.json` to 2 decimals |
| 5 | Permutation null of max\|t\| (200 label shuffles, keeps the correlation between samples) | 99th percentile 3.5-3.7 (N, D, DA, controls); largest of 200 is 4.40. The 4.5 threshold is conservative, and N's 13.2 is far outside the null |
| 6 | Split halves of N_tvla (odd/even rows, first/second half) | 7.9 / 10.9 / 8.1 / 10.6, all at the same 0.945 ns sample, all the same sign |
| 7 | Labels shifted by +-1 and +-2 rows (misalignment) | N falls to 2.4-2.7, so the leak belongs to the row's own evaluation. D and DA stay at 1.7-2.1, so no leak is hidden by a misaligned window. U stays high at -1/+1/-2, as expected for an unmasked design with transition and output-register terms |
| 8 | **Replication without a fixed class:** one-way ANOVA of the supply current over the current x, random rows only | N_rvr (seed 203, 9,998 rows): **F = 21.8 at 0.945 ns** (per-sample 1e-4 critical value about 2.2). N_tvla random class: F = 12.2 at 0.945 ns. D: 1.55; DA: 1.32 (both null) |
| 9 | Per-x mean current at 0.945 ns, random class of N_tvla vs N_rvr (independent seeds) | correlation 0.89: the same x-dependence in both campaigns |
| 10 | Fixed class vs random rows that happen to have x = 0x0B (N_tvla, 5,010 vs 173 rows) | t 1.06 at the peak (max 2.0 over the window): the fixed-vs-random difference is explained by the value, not by the labelling (e.g. not by the fact that consecutive fixed rows toggle both shares identically) |
| 11 | Another fixed value: "x == v vs the rest" in N_rvr, every v (about 310 "fixed" traces each) | 18 of 32 values already exceed 4.5; 0x0B gives 6.7, a typical value (median over v: 4.7) |
| 12 | D and DA with one-statistic tests (no multiple comparisons): projection on a level-2 template from 15,000 independent rows; cross-validated SPICE template (odd/even halves); charge in 0-1.6 ns | D: \|t\| 0.9 / 1.1 / 0.3; DA: 0.5 / 1.0 / 0.7. N as positive control: cross-validated 7.6 |
| 13 | Per-net localization, permutation null (30 shuffles over every net and 20 ps bin) | null max about 4.2. N: 9 nets above it, all flagged. D: 5 nets above it (m01_1 6.0, m10_1 5.6, m10_3 4.9, p10_1 4.9, m01_3 4.6), all flagged. The cross-domain nets that probing does *not* flag (the t0 and t2 ANDs, same cell types) stay at \|t\| <= 3.3 (N) and <= 2.9 (D) |
| 14 | Non-degenerate CPA on U (post hoc, not K1): U_tvla rows, 32 key-offset guesses x ^ d | true offset ranks 1 with HW(S), HD of S between rows, and HD of x plus S (scores 0.76 / 1.00 / 0.89 against best wrong 0.59 / 0.86 / 0.84) |
| 15 | Level-2 per-sample peaks: permutation null (100 shuffles) and replication on 5,000 independent rows of the same stimulus file | D 7.9 (null 99% 3.9) replicates at the same sample (6.4), so level 2 genuinely predicts a D leak that SPICE does not show. DA 3.0 does not replicate (0.7). N's level-2 peak (-12.1) replicates with the same sign (-8.6) |
| 16 | Numerical artifact: 240 N rows (M_tvla rows 0-239) re-simulated with the tight reference settings (tmax 1 ps, reltol 1e-4, vntol 1e-7, abstol 1e-13, chgtol 1e-16) and compared row by row with the campaign (237 rows after the dropped ones; 130 fixed, 107 random) | 0 functional mismatches; data-dependent correlation 0.99956; charge error <= 0.11%. **The numerical error does not depend on the class:** fixed-minus-random error at 0.945 ns 0.23 +- 0.43 uA (t 0.5), at most 2.1 uA over 0.6-1.2 ns, max\|t\| of the error 3.05 over 400 samples. The leak's bump on these rows: 27.4 uA (reference) vs 27.7 uA (campaign settings), waveform correlation 0.9986 over 0.6-1.2 ns |

## Findings

### F1. Supported: N leaks at first order, and the zero-delay model says it is secure

- **Zero-delay security is exact, not statistical.** Check 1 shows that in N, D and DA every net's settled value
  and every cell's settled input tuple is independent of x. Rows are independent (fresh masks and r), so the
  expected level-1 toggle count, under any weighting, is the same for both classes. K2 therefore holds by
  construction. The measured max\|t\| of 1.06-2.48 are sampling noise, and check 2 confirms the implementation.
- **The N leak is real and is a property of the data.** It is large (13.2) against a conservative threshold
  (permutation 99% point about 3.6). It sits at the same sample in every half of the data. It replicates in
  the random-vs-random campaign, which has a different seed and no fixed class (F = 21.8 at the same 0.945 ns),
  with the same per-x pattern (r = 0.89). The fixed class behaves like random rows with the same x. Many other
  fixed values would show it as well.
- **It must come from timing, and the testbench can't supply that timing on its own.** The supply, the clock and
  every input are ideal sources (`sim/spice_campaign.py`), VGND is node 0, and wire caps go to ground only (no
  coupling caps). So cells can interact only through the logic nets. Because no cell's settled inputs depend on
  x (check 1), whatever depends on x in first order must come from how and when the nets switch within a cycle:
  glitches, arrival order and residual charge. Input-port and D-pin activity is linear per share, and its
  region (2.8-3.8 ns) stays at 1.9 (ANOVA F 1.4).
  The localization has real specificity: flagged nets leak, and the unflagged cross-domain nets of the same
  cell types do not (check 13).
- **It is not a numerical artifact.** Adaptive time steps could in principle couple share-0 and share-1 cells
  through simultaneous switching. Check 16 re-simulates 240 rows at 1 ps with tight tolerances. The class-dependent
  part of the integrator error is at most 2.1 uA in the leak region (0.23 +- 0.43 uA at the peak), against a
  27 uA effect, and the reference reproduces the bump (27.4 vs 27.7 uA). Cost: 6.9 h of wall clock for these
  240 rows, because the machine was shared with other reviewers' runs (load about 25).

### F2. Not supported: "D does not leak" (blocking wording)

D as registered fails glitch-extended probing on 12 nets. The SPICE node run shows that 5 of them switch in a
class-dependent way, above a permutation null (check 13). D therefore leaks at the net level in SPICE. It does not
show in the supply current within 4,997 noiseless traces, under any statistic I tried (check 12). That trace
count is half of A3's minimum of 10,000. At 4,997 traces the per-sample TVLA can reach 4.5 on average only for
an effect of at least 0.127 standard deviations, which is **half of N's** (N: 0.262 SD at the peak, 26.5 µA
over 101 µA). So K4 excludes only a leak at least half as strong as N's. A rough estimate from the node
crossings, calibrated on N, puts D's supply-current t at about 2 at 4,997 traces and about 4 at 20,000.

**Fix:** never write "D does not leak". Write "D's leak is real at the net level but is not resolved in the
supply current within 4,997 traces". The doc's own Results sentences already come close to this; the run
summary's "D does not" does not.

### F3. Not supported: "On the question the kill test was built to answer, the answer is yes" (blocking wording)

The registered question has two parts: does naive masking leak through glitches, *and* does DOM with a register
barrier remove it? Only the first part is answered. D cannot answer the second part because its barrier is in
the wrong place (A1) and its net-level leak is confirmed (F2). DA can answer it, but DA is at 4,997 of the
registered 20,000 traces (K5 incomplete). At 4,997 traces it excludes only leaks at least half as strong as
N's. At 20,000 that falls to 0.24 of N's.

**Fix:** answer "yes" to the first part and state that the second part is open until K5 completes. Remove
"D and DA stay below 4.5" as support for the answer, or qualify it with the trace count and the
detectable-effect size.

### F4. Contradicted: "N leaks in timing, not in energy" (blocking wording)

On the charge per window, the fixed-vs-random t is 3.2 at 9,998 traces, which is below 4.5. But an ANOVA over x
on the same charge is significant in both campaigns: N_tvla random class F = 2.38, N_rvr F = 1.94, both with
permutation p < 5e-4 (2,000 shuffles). N does leak in total energy, only more weakly.

**Fix:** "N's leak is concentrated in the timing of the evaluation; the total charge also depends on x, but more
weakly (fixed-vs-random \|t\| 3.2 at 9,998)."

### F5. Overstated: level 2 "at the right size" (blocking wording for the model-trust claim)

Level 2's max\|t\| of 12.1 against SPICE's 13.2 on N is a coincidence. The two t-curves are uncorrelated at every
time shift (correlation 0.00 unshifted, at most 0.05 at +250 ps). SPICE's t is a smooth *positive* hump over
0.71-1.20 ns. Level 2's t alternates sign between 0.90 and 1.71 ns, and its peak is *negative* (-12.1 at
1.455 ns). A matched filter built from level 2's fixed-minus-random waveform, shifted by the measured lag, gives
t = -4.6 on the SPICE traces: the wrong sign. At 10 ps resolution level 2 produces deterministic spikes, so its
per-sample \|t\| is not comparable to SPICE's, and this is also why it overstates D (7.9 at 10 ps, 1.37 at 100 ps).

**Fix:** "Level 2 flags N and names the right nets; it does not reproduce the leak's waveform, sign or timing,
and its per-sample \|t\| magnitude is not a prediction of SPICE's."

### F6. Non-blocking notes

- **N's quiet region, 1.3-1.8 ns (open issue in the doc), is partly resolved.** Settled-value static current
  cannot leak at first order (check 1). Yet an ANOVA over x in N_rvr gives F = 5.3 at 1.455 ns, where the mean
  current is about 1 µA, and the node run has only 23 VDD/2 crossings after 1.3 ns in 2,000 rows (all on the
  output-layer XORs). So this is a sub-threshold effect of the evaluation's dynamics: slow tails, partial swings,
  or residual charge on floating internal nodes left by glitches. It is not data-dependent static current. It
  belongs to the same timing mechanism.
- **The random-vs-random control is weak by construction.** Its labels are independent of the data, so it can
  only catch harness faults (label-dependent processing, chunk effects). It passes (1.87 in SPICE). Checks 8-10
  are the stronger control that the fixed-vs-random result is not an artifact; I suggest adding one of them to
  the notebook.
- **K1's CPA part fails because of how the check was designed.** With two key bits and four nonce values, every
  key guess maps the nonces one-to-one, so only a parametric model can separate the guesses, and the model's
  error decides the ranking. The doc says this. Check 14 shows the U traces are CPA-exploitable as soon as the
  guesses partition the inputs differently. This is post hoc and does not change K1's letter. A redesigned CPA
  check (e.g. a 5-bit key added to 32 input values) should be pre-registered before the notebook relies on it.
- **The pre-registration cannot be verified.** The repository has no commits, so nothing timestamps the
  criteria and amendments A1-A3 before the SPICE campaigns. The queue log and file times are consistent with
  the doc's account but are not proof. Commit the pre-registered text (or record its hash) before K5 is
  completed.
- **The absence claims need a detectable-effect size.** A max\|t\| below 4.5 means "no leak at least as large
  as X". Report X for D and DA: at N traces, 2 x 4.5 / sqrt(N) SD per sample, which is 0.127 SD at 4,997 and
  0.064 SD at 20,000, against N's 0.262.
- **Multiple comparisons are handled conservatively.** Max over 400-800 correlated samples with a fixed 4.5
  gives a family-wise false-positive rate well below 1% (check 5). The per-net localization tests about 1,500
  informative (net, bin) pairs, where the null maximum is about 4.2, so nets reported "above 4.5" there are
  near that bound. I calibrated them in check 13, and they hold.
- **Clock/data alignment, D pipeline overlap and the masks-off definition are sound.** Inputs switch at 0.75 T,
  and every campaign's output check shows 0 mismatches. D's two-cycle windows overlap by design, and the label
  shifts show nothing hidden. Masks-off (mask = r = 0) is as registered. It is an easy positive control: a
  leak as small as N's would be a stronger test of whether the harness can see small leaks.

## How to redo my checks

- Check 1: parse the `X...` lines of `build/<V>/dut.sp` with the PDK pin orders (for example `xor2_1: A B VGND VNB
  VPB VPWR X`), evaluate every cell with the flip-flops transparent over all 32^3 (x, mask, r), with
  xs0 = x ^ mask, xs1 = mask. Compare the per-x histograms of each net, of each cell's input tuple, and of each
  net's stable-source cone.
- Checks 4-15: plain numpy (check 15 also uses `analysis/kill_test.py`'s `model_rows`) on `runs/kt/<campaign>/traces.npy` and `charge.npy`, with labels from
  `runs/kt/stim/<stem>.meta.npz`, dropping the first L+1 rows as `analysis/kill_test.py` does.
- Check 16: `bash sim/docker_run.sh python3 sim/spice_campaign.py run --dut build/N --stim
  runs/kt/stim/M_tvla.npy --out runs/sca_review/N_ref1ps --chunk 40 --jobs 6 --threads 1 --rows 240 --tmax 0.001
  --options "reltol=1e-4 vntol=1e-7 abstol=1e-13 chgtol=1e-16" --save-outputs`, then compare with rows 3-239 of
  `runs/kt/N_tvla/traces.npy`.
