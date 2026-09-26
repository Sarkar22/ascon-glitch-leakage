<!-- SPDX-License-Identifier: Apache-2.0 -->
# Review: profiled key recovery and cost table (stage 2, 2026-09-25)

**Scope.** This review covers `analysis/key_recovery.py`, `analysis/plot_key_recovery.py` and `analysis/cost_table.py`,
their tests, and the outputs in `results/key_recovery/` and `results/cost/`. None of these files is committed yet.

**Lens.** I tried to refute the reported results. I looked for:
- overlap between profiling and attack rows, or between POI selection and the attack data;
- fixed-class rows getting into the data;
- errors in the guessing-entropy (GE) and success-rate (SR) math;
- scenarios and splits that differ from what is claimed;
- a permuted-label control that is not really random;
- a DA "stays random" result that rests on too few traces;
- a cost table that disagrees with `ports.json`, `summary.json` and `charge.npy`.

**What I changed.** Nothing in the repository except this file. Every re-run happened in a scratch copy of the code, with
`runs/kt` linked read-only. I did not touch `runs/kt/D_tvla` or `runs/kt/ext.sh`, and I started no SPICE. The host
analysis ran with 2 BLAS threads at low priority. The only container was the plot render, capped at `--cpus 2`. My check
scripts were scratch files. Each check is described below in enough detail to redo it.

## Verdict

**The pipeline is sound, and its numbers reproduce exactly. Two of the claims built on it do not hold.**

I found no leak between the profiling and attack sets, no fixed-class rows in the data and no error in the GE/SR math. An
independent re-implementation gives the same key rank in 160 of 160 cases per dataset. The scenarios and splits are as
described, and the cost table matches its sources to the digit.

The two claims that do not hold:
1. **"At first order, N gives up only key bit x1; the full key needs a second-order attack" is refuted (B1).** Key bit
   x2 does leak at first order, through interactions with other bits, and the result replicates across two independent
   campaigns. A first-order template with one extra point of interest recovers the full key: SR 0.94 at 765 traces per
   key.
2. **"D and DA stay random" is stated without the effect it can detect, and part of its evidence has no power (B2).**
   At these trace counts the template attack detects a leak shaped like N's at half N's size, but not at 0.35×. DA's TVLA
   already rules out leaks of about 0.25× N's, so the key recovery adds no sensitivity beyond the TVLA. The correlation
   distinguisher cannot find even an injected leak of N's full size, yet `cost.md` cites it for DA.

Verdict: **issues**. Both are about claims and wording. No code bug changes a reported number.

## What I re-ran or checked

| # | Check | Result |
|---|---|---|
| 1 | Full `python3 analysis/key_recovery.py` in the scratch copy | `summary.json` identical to the repository's apart from `runtime_s_last_invocation` (480 s here; the stored 13.9 s comes from a single-dataset re-run). `ge_vs_traces.csv` byte-identical. So the merged file is consistent with one full run. |
| 2 | `python3 analysis/cost_table.py` in the copy | `cost.csv` and `cost.md` byte-identical |
| 3 | `plot_key_recovery.py` in cac-sca at `--cpus 2` | `fig_ge.png` and `fig_bits.png` byte-identical |
| 4 | `python3 -m unittest discover -s analysis -p 'test_*.py'` | 24 OK |
| 5 | Fixed-class rows, labels and row alignment | In every TVLA stimulus, label 0 rows are all x = 0x0B (U 1,064 rows; M_tvla 5,012 of 10,000 and 9,939 of 20,000), and label 1 rows take all 32 values. `load_source` keeps label 1 only and drops the first L+1 rows. Every kept trace equals `traces.npy` at its stimulus row, and its x equals the meta x of that row. N_rvr uses all 9,998 rows. |
| 6 | Splits, rebuilt exactly as `run_split_dataset` does, for every dataset and all 10 seeds | The profiling and attack sets never share a row. The nearest profiling and attack rows are 4 apart (3 guard rows between them), and 5.6-6.3 % of rows are unused. Attack rows per scenario, min/max: U 27/88, N_tvla 231/358, N_pooled 765/990, D 236/362, DA 533/718. Blocks are drawn per source campaign. A latency-2 window covers two cycles, so the sets share no time sample. |
| 7 | Where every fitted quantity comes from (code read, confirmed by #8) | These are all fitted on profiling rows only: ANOVA F, POIs, the cross-validated `k_tmpl`, the second-order centring mean, the template means and the pooled covariance. The attack rows enter only the scores and the checkpoint grid (`min(sizes)`). |
| 8 | Independent re-implementation (my own per-input means, F, greedy POIs, pooled-covariance template, pooled centred correlation; only the split masks and `k_tmpl` are taken from the module) | On each scenario's full attack set my key rank equals `attack()`'s in **160/160** (split, scenario, distinguisher) cases. That holds for N_pooled, D, DA and U first order, and for DA second order. GE at the reported n with my own random subsets (template / correlation) vs the reported values: N_pooled 0.374 / 1.16 vs 0.38 / 1.17; D 1.69 / 1.81 vs 1.71 / 1.79; DA 1.52 / 1.52 vs 1.54 / 1.52; DA order 2 0.26 / 0.98 vs 0.27 / 0.99; U 0.000 / 0.004 vs 0.00 / 0.003. The tie handling of `key_rank` and `top_bit_success` checks out by hand. |
| 9 | N bit main effects at the 0.945 ns peak (N_pooled rows) | x1 t 16.5, x3 t 20.4, x2 t -0.3, x4 1.3, x0 0.2. The report's numbers reproduce. |
| 10 | **x2 inside cells:** contrast x2 = 1 vs 0 with the other four bits fixed, 16 cells, chi2(16) per sample (99.9 % point 39.3) | N_rvr: up to **122.9** at 1.285 ns, and 54 samples above the 99.9 % point. N_tvla (independent seed): up to **68.2** at 1.295 ns. The 16 per-cell contrasts correlate **0.83** between the two campaigns at the peak sample. x2 leaks at first order through interactions, about 0.35 ns after the main peak. |
| 11 | **Per-key-bit POIs (first order):** the top-F sample plus the top sample of #10's x2 contrast, both chosen on profiling rows, fed to a 2-POI Gaussian template; same 10 splits, n = 765 | N_pooled: **GE 0.06, SR 0.94, P(x1) 1.00, P(x2) 0.94** (reported attack: 0.38 / 0.62 / 1.00 / 0.62). With x1's contrast POI added (3 POIs): 0.09 / 0.91. Null with 5 permutations of the profiling labels: GE 1.41-1.61, P(x2) <= 0.53. N_tvla alone, n = 231: GE 0.43 (reported 0.64). D and DA stay random under the same attack: GE 1.69-1.70 and 1.51-1.59, against nulls of 1.29-1.68 and 1.37-1.55. |
| 12 | Generic key POIs: F of the key bits inside the 8 (x0, x3, x4) cells | No better than the default (N_pooled GE 0.31-0.36, P(x2) 0.64-0.70). x1's main effect dominates that criterion, so x2 needs its own POI (#11). |
| 13 | Permutation null of the reported pipeline's final GE (20 fresh label permutations, the reported splits, 10 trials) | D: real correlation GE 1.806 against a null mean of 1.496 (sd 0.093, max 1.748), so p < 0.05. Real template GE 1.706 against 1.516 (sd 0.095, max 1.715), p ~ 0.05-0.1. DA: 1.535 and 1.541 against 1.517 and 1.486, both inside the null. |
| 14 | Real labels on 12 fresh split seeds | D template GE: mean 1.64, min 1.54 (correlation 1.65). DA: 1.56 and 1.49. So D's GE > 1.5 comes from its data, not from one unlucky split. |
| 15 | Half replication: per-input mean patterns of even vs odd 50-row blocks, standardized, correlated over inputs × samples | N +0.28 (0.72 at the top POIs); U +0.91; **D -0.190**, below all 40 x-permutations (null mean -0.010, sd 0.074); DA -0.104 (5th percentile). **The zero-delay (level-1) model on the same D rows also anti-replicates:** -0.238 cap-weighted, below all 30 permutations. Level 1 has no first-order dependence on x by construction, so the effect lies in these stimulus rows, not in the circuit. |
| 16 | Power: add α × N's first-order leak to the real D/DA traces (per-input means of N_pooled, scaled so the per-sample SNR is α² × N's; α = 1 matches N's peak: std over inputs 0.257 SD) and run `run_split_dataset` unchanged (10 splits, 20 trials) | **Single sample (N's peak), 1-POI template** (N's own attack also chose 1 POI): DA at 533/key α 1 → GE 0.40, 0.7 → 0.58, **0.5 → 0.95 ± 0.17** (P(x1) 0.84), **0.35 → 1.41 ± 0.18**. D at 236/key: 0.42 / 0.65 / **1.01 ± 0.10** / **1.44 ± 0.04**. With the cross-validated k (up to 8 POIs): about the same (DA 0.5 → 1.04, 0.35 → 1.38). **Correlation distinguisher: GE 1.49 (DA) and 1.74 (D) even at α = 1.** A leak spread over N's 86-sample window lands on DA's own, less correlated noise, which favours the attacker: the template then succeeds down to α 0.25-0.35 (DA 0.35 → 0.31, 0.25 → 0.79), while correlation still gets only 1.08 at α = 1. |
| 17 | Cost table sources | Liberty areas (xor2_1, and2b_1, and2_1, inv_1, dfxtp_1) sum to 337.824 / 1009.718 / 1610.294 / 1610.294 µm², matching `ports.json`. dfxtp_1 CLK = 1.794 fF, giving 58.1 / 145.3 / 319.7 fJ per cycle. Cells, flip-flops, latency, reg-to-reg, port-to-reg and the r/share1 port roles all match `ports.json`. `charge.npy` equals sum(traces) × 10 ps to 1e-8. Random-row means are 281.7 / 947.3 / 2713.1 / 2643.9 fC, the N_rvr cross-check gives 943.8, and energy is Q/L × 1.8 V. TVLA max\|t\| and trace counts match `results/kill_test/summary.json` (D 3.347 at 9,997). |
| 18 | Energy bias from the fixed neighbours (U) | U's random rows next to fixed rows draw less: 262.9 fC after two fixed rows against 290.7 after two random ones. A linear fit on the labels of rows r-2, r-1 and r+1 predicts **297.7 fC (536 fJ)** for all-random inputs, against the reported 507 fJ (-5 to -6 %). Masked variants are unaffected: N 947.3 vs N_rvr 943.8; D and DA random rows with all-random neighbours are within 0.3 %. |
| 19 | Hygiene | Every new source file and `cost.md` has an SPDX line. No absolute paths, host names or e-mail addresses in the new files or outputs (`summary.json` stores relative `runs/kt/...`). |

## Findings

### B1. Refuted: "At first order N gives up only key bit x1; the full key falls only to a second-order attack" (blocking)

**What the report says.** "N's first-order leak depends on x1 and x3, the variables shared through the affine layer
by the flagged t1/t3 gates. x2 has no main effect (t -0.3)." Also: "The full key falls to a second-order attack (about
500 traces)." `cost.md` puts "key not recovered at 765 traces per key" in N's first-order row.

**What the data show.** x2 has no *main* effect at the peak (check 9), but it leaks at first order through interactions
with the other bits, at 1.28-1.45 ns (check 10). The per-cell pattern replicates across N_rvr and N_tvla (r = 0.83),
which were simulated from different stimulus seeds. A first-order template that adds one POI chosen on the profiling
rows by the x2 contrast recovers the full key: GE 0.06, SR 0.94 at 765 traces per key (check 11), against a null of
GE ~1.5. The default attack misses x2 for three reasons:
- it ranks POIs by the overall F, which x1 and x3 dominate;
- the cross-validation then picks a 1-POI template;
- the correlation distinguisher centres the level away (see B2).

The x2 contrast criterion was chosen after seeing x2 fail, so this attack is post hoc as well. But it uses profiling
data only, and its permuted-label null stays at 1.5.

**Fix:**
- Do not write that N's first-order leak depends on x1 and x3 only, and do not write that the full key needs second
  order.
- Write instead: "the default profiled attack (POIs by overall F) recovers key bit x1 only. x2 also leaks at first order
  through interactions (at 1.3 ns), and a template with one POI chosen for x2 recovers the full key (SR 0.94 at 765
  traces per key)."
- Better: add a per-key-bit POI option to `key_recovery.py`, report it next to the default, and change N's row in
  `cost.md`.
- N's "second-order" result (GE 0.05) is not independent evidence either. The centred square at samples with a
  first-order mean shift also carries that shift, so for N it mixes first-order information in. DA's second-order
  result has no such mix and stays valid.

### B2. "D and DA stay random at first order" needs the effect it can detect; the correlation distinguisher has no power (blocking)

The key-recovery attack on DA uses about 145 profiling traces per input and 533 attack traces per key. On D it is 74 and
236. Check 16 injects N's first-order leak at scale α into these real traces. With the reported pipeline, a
significant result (GE clearly below 1.5) needs α ≈ 0.5 in a single sample:
- α = 0.5 gives GE 0.95 ± 0.17 on DA and 1.01 ± 0.10 on D;
- α = 0.35 gives 1.41 ± 0.18 and 1.44 ± 0.04.

So "no key recovery on DA at 533 traces per key" rules out only leaks of at least about half N's per-sample effect. The
kill test's TVLA on DA already rules out about a quarter of N's at 19,997 traces, and D's TVLA at 9,997 traces about a
third. The key recovery is therefore a consistency check. It adds no sensitivity and should not be presented as extra
evidence that DA is secure.

The correlation distinguisher fails even on an injected leak of N's full size (GE 1.49 on DA, 1.74 on D). The cause is
structural: centring over the attack traces removes the level shift between keys, which is exactly the key-bit main
effect that N leaks. Yet `cost.md` picks "the better of the two distinguishers" by the lower GE, so DA's row cites
the correlation result ("GE 1.52 (correlation)"). For a variant with no leak, the lower of two random numbers means
nothing.

**Fix:**
- Make the template the primary distinguisher everywhere, declared in advance. Show correlation only as the weaker
  method, with a note that it cannot see key main effects.
- State the detectable effect with every "stays random": "no key recovery at 533 attack traces per key; at this data
  volume the attack detects a leak shaped like N's at half N's strength (injection test), and TVLA at 19,997 traces is
  about twice as sensitive".
- Consider adding the injection test to `key_recovery.py` as a positive control at each variant's own data volume.

## Non-blocking notes

- **D's GE sits above 1.5 because of these stimulus rows (checks 13-15).** The effect is systematic, not one bad
  split: the template gives 1.64 on average over 12 fresh splits, and the correlation's 1.81 lies outside all 20
  permutations. The zero-delay model shows the same anti-replication on the same rows, and it cannot leak at first
  order, so the cause is this finite draw of masks and neighbours (p ≈ 0.03), not the circuit. So "1.8 standard errors
  above 1.5, consistent with random" understates it for the correlation distinguisher. More importantly, a GE above 1.5
  is no extra margin. Write "no key recovery". The injection test (B2) was run on these same rows, so its detectable
  effect already includes this bias.
- **The controls.** The label permutation is a uniform, seeded permutation of the profiling labels, and it is truly
  random. It is one permutation per split, though, reused across noise levels and orders, so each control GE is a single
  draw from the null, not a null distribution, and the 12 controls per dataset are correlated. The report's "controls
  1.32-1.76" leaves out the U_cpa controls, which reach GE 1.00 ± 0.58 (correlation, no noise) and 1.00 ± 0.71 (template,
  1x noise). With 4 keys (4 units) the U_cpa control has almost no power. Across 20 permutations the null has an sd of
  about 0.07-0.10 on D and DA.
- **U_cpa with noise is fragile.** At the final checkpoint all 1,998 traces are used, so each key is one deterministic
  outcome, and the 50 orderings coincide. At 0.5x noise the correlation ranks key 3 second (GE 0.50, SR 0.75), but at
  1x all four keys come first. The template fails at both. Report both levels, not only "the correlation still finds
  the key at 1x". "20-30 % less charge" is 18-27 % (225 / 209 / 215 / 229 against 309 / 284 / 262 / 303 fC).
- **K1 wording.** "A profiled attack fixes K1's weakness" should read: "post hoc, a profiled attack recovers U's key
  from the K1 CPA traces within 7 traces (templates from U_tvla). This answers the question K1 was meant to settle,
  whether the traces carry exploitable key information, but K1 stays failed as registered." The report's own open
  issues say so. The summary line should match.
- **Split wording.** The sets share no row and no time sample, and no trace depends on the input of a row in the other
  set. But traces on both sides of a guard can depend on the same guard-row input (for example rows 46 and 50 both
  depend on row 47, for L = 2). This carries no key information. The phrase "no input that a trace depends on" should
  be narrowed. The docstring's "rows r-3 .. r+2" holds for L = 2. For L = 1 it is r-2 .. r+1.
- **Cost table.** The numbers reproduce and every column traces to its source. Three things should be stated:
  1. U's energy per evaluation is biased low by about 5-6 % (about 536 fJ for all-random inputs; check 18), because half
     of its random rows follow a 0x0B row (a quarter follow two). U has no all-random campaign. This does not affect the N/D/DA ratios.
  2. Energy = window charge / L assumes a new input every cycle. In a round-based core that does not interleave two
     independent states, a latency-2 S-box needs 2 cycles per round. It then pays about one extra cycle of
     clock and register overhead per evaluation that the pipelined figure leaves out.
  3. Latency in time is N 1 × 1.92 ns, D 2 × 1.23 ns and DA 2 × 1.085 ns (+0.14 ns in front of the registers). So the
     fix costs about 13-28 % more latency in time, not 2x. It can be clocked faster.
- **D at 10,000 rows.** D's key-recovery and cost numbers use the 10k campaign; the 20k run is still going. Re-run as
  the report says once `runs/kt/ext.log` shows DONE and `kill_test.py` has refreshed D's noise unit.

## How to redo my checks

Work in a scratch copy of `analysis/ model/ sim/ gen/ build/` and `results/kill_test/summary.json`, with `runs/kt` linked
to the real one. Run the module there, so the repository's `results/` is never rewritten.

- **Checks 1-4.** Run the module's own commands in the copy, then `cmp` and a JSON diff against the repository's
  outputs. Render the plots with `DOCKER_OPTS="--cpus 2" bash sim/docker_run.sh python3 analysis/plot_key_recovery.py`.
- **Checks 5-6.** Use `kr.load_source` and `kr.block_split(row[src == k], kr.seed_of("split", name, s, k))`, and
  compare with `np.load(traces.npy)[row]` and with the meta label and x.
- **Check 8.** Recompute, for each split and scenario, with plain numpy:
  - the per-input means and the pooled within-input variance on the profiling rows;
  - the POIs: greedy top-F with spacing 3;
  - the template score: -0.5 Σ dᵀ Σ⁻¹ d with the pooled residual covariance (ridge 1e-9 × mean diagonal);
  - the correlation score: over the n × 20 POI values, the centred attack values against the centred predicted means,
    both divided by the per-POI pooled SD.

  Rank ties count one half. Compare with `kr.attack(tm, tr[sel], x[sel], iv, key, [len(sel)], 1, rng)`.
- **Checks 10-12.** For key bit b (x1 = bit 3, x2 = bit 2) and every cell c with bit b clear, compute
  t_c = (μ[c | 1<<b] - μ[c]) / sqrt(var (1/n_c + 1/n_c')), and take chi2 = Σ_c t_c². The attack uses
  POIs {argmax F} ∪ {argmax chi2 for x2}, spaced 3 apart, all on profiling rows. It runs a Gaussian template with the
  pooled residual covariance, the same 10 splits, and 10 random subsets of n = 765 per unit. For the null, permute the
  profiling labels.
- **Checks 13-14.** Wrap `kr.seed_of` so that keys starting with "perm" (or "split") get an extra salt, then call
  `kr.run_split_dataset(ds, 1, 0.0, control, 10, 10, 1.0)`.
- **Check 15.** Put blocks with `row // 50` even in half A and odd in half B, and drop guard rows (`row % 50 >= 47`).
  For each half, compute the per-input means minus their mean over the inputs, divided by the pooled SD, and correlate
  the two halves over inputs × samples. Build the null from permutations of x. For the level-1 run, use
  `kill_test.model_rows("D", stim, n_sim, 1, man)` on the same rows.
- **Check 16.** Take Δ = the per-input means of N_pooled minus their mean, divided by N's within-input SD, at N's
  top-F sample (or at every sample with F > 5). Add α Δ[x] × (the target's within-input SD) at the same time after the
  evaluation edge: sample + 400 for L = 2. Then run `kr.run_split_dataset` on the modified traces. For the 1-POI
  variant, set `kr.choose_k_tmpl.__defaults__ = ((1,), kr.INNER_FOLDS)`; setting `K_TMPL_CANDIDATES` alone has no
  effect, because the default argument is bound when the function is defined.
- **Checks 17-18.** Sum the Liberty `area` of each cell type in `graph.json`; take the CLK `capacitance` of dfxtp_1.
  Compare `charge.npy` with sum(traces) × dt. Regress U's random-row charge on the labels of rows r-2, r-1 and r+1.
