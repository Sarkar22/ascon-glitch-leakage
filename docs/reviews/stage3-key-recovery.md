<!-- SPDX-License-Identifier: Apache-2.0 -->
# Review: key-recovery fixes and the refreshed notebook (stage 3, 2026-09-25)

**Scope.** This review re-checks the fixes made for `docs/reviews/stage2-key-recovery.md` in
`analysis/key_recovery.py`, `analysis/cost_table.py`, `analysis/plot_key_recovery.py`, their tests, and the outputs in
`results/key_recovery/` and `results/cost/`. It also covers the notebook sections that were refreshed from them:
- the claim screen and the abstract;
- §4.4 and §4.5 (D and DA at 19,997 traces);
- §5 (key recovery) and §7 (cost);
- the conclusion, the team table and the AI-use disclosure.

None of these files is committed yet. The layout and post-layout work (§6, `layout/`, `results/layout`, `results/pex`)
is not reviewed here.

**Lens.** I tried to refute the fixes. For each stage-2 item I asked whether it was really addressed, and I re-ran
the parts where a mistake would change a number. I compared every number the notebook quotes in these sections
with `results/*.json` and `results/cost/cost.csv`. I re-ran the organizers' CI checks myself.

**What I changed.** Nothing in the repository except this file. The re-runs used scratch copies of the code, with
`runs/kt` linked read-only. While I set up the first copy I created a stray symlink `runs/kt/kt` inside the
git-ignored `runs/kt` by mistake, and I removed it at once. I did not touch `docs/KILL_TEST.md` or anything else under
`runs/`. The host analysis ran at low priority with 1 BLAS thread and 3 processes. The only containers I started were
the two CI containers of `notebook/tests/ci_container.sh`, at `--cpus 2`. I did not re-render the PNG figures,
because other SPICE containers were running on the machine. I viewed the saved figures instead.

## Verdict

**The fixes are sound, and every number I re-derived matches. One wording item from stage-2 B2 is only partly fixed.**

The per-key-bit template, the null distributions, the injection test and the new energy estimate all reproduce.
- An independent re-implementation gives the same key rank in 400 of 400 cases.
- The POIs match in every split.
- My own injection test gives the same detection limits.
- My own charge means match `cost.md` to the digit.

The notebook's quoted numbers in the checked sections all agree with the result files, and the CI checks pass.

The item that remains: four headline sentences still state "no key recovery" or "gets nothing" for D and DA
without the effect the attack can detect (B1 below). Stage-2 B2 asked for that bound "with every stays random", and
the fix report says that every such statement now carries it. §5, `cost.md` and `summary.json` do carry it. The
claim screen, the abstract, the last bullet of §7 and the conclusion do not.

Verdict: **issues**. This is one blocking wording fix, in `notebook/make_notebook.py` only. After it, the notebook
has to be rebuilt and re-executed, and the CI checks run again. No number changes.

## Stage-2 items: status

| Stage-2 item | Status | Evidence |
|---|---|---|
| B1: remove "x1 and x3 only" and "needs second order" | **fixed** | A search of the notebook generator, `cost.md`, `summary.json`, the analysis code and `docs/` finds neither claim. |
| B1: per-key-bit POI option, reported next to the default | **fixed** | `tmpl_bits` in `key_recovery.py`, in `summary.json`, `cost.md`, the figures and notebook §5. Re-derived in checks 5-6. |
| B1: N's second order is not independent evidence | **fixed** | This is stated in `summary.json` (`statements.N_order2`), `cost.md` (N, 2nd order) and §5. |
| B2: template primary everywhere, correlation secondary with its limitation | **fixed** | `summary.json` (`primary_distinguisher`, `distinguishers`, `statements.primary`), the `cost.md` footnote, the figure row labels and §5. |
| B2: injection test as a positive control | **fixed** | `run_injection` exists and I reproduced it independently (check 7). |
| B2: state the detectable effect with every "stays random" | **partly fixed** | This is done in §5, §8, `cost.md` and `summary.json`. It is missing from the claim screen, the abstract, the §7 "What the cost buys" bullet and the conclusion. See B1 below. |
| Null: one draw per split, U_cpa controls left out | **fixed** | There are now 20 draws (5 with noise) per configuration, independently seeded, with p against the null. The U_cpa nulls are in the table (1.46 ± 0.17). |
| U_cpa with noise: report both levels | **fixed** | 0.5x: template 1.25, correlation 0.50 (SR 0.75). 1x: 1.50 and 0.00 (SR 1.00). The "one deterministic outcome per key" caveat is stated. The charge deficit reads 18-27 %. |
| K1 wording | **fixed** | "Post hoc ... K1 stays failed as registered", in `summary.json` and §5. |
| Split wording (dependency range, shared guard-row inputs) | **fixed** | The docstring now gives r-L-1 .. r+L, with both cases spelled out, and explains the guard rows. §5 says "no trace of one set depends on an input of the other". |
| Cost: U energy bias | **fixed** | The mean is now taken over the rows whose whole neighbourhood is random-class: U 291.4 ± 6.1 fC, 524.6 fJ. The stage-2 regression estimate (297.7 fC, 536 fJ) lies about 1 SE away. The other variants move by 0.3 % or less. |
| Cost: pipelined-use caveat | **fixed** | This is in `cost.md` and in the §7 energy bullet. |
| Cost: latency in time | **fixed** | N 1.92 ns, D 2.46 ns (+28 %), DA 2.17 ns (+13 %). DA's 141 ps of port-to-register logic is stated separately. |
| D at 10,000 rows | **fixed** | The key recovery and the cost table use D_tvla with 20,000 rows (10,061 usable). |

## What I re-ran or checked

| # | Check | Result |
|---|---|---|
| 1 | Full `python3 analysis/key_recovery.py --jobs 3` in a scratch copy | Exit 0 after 1,869 s (the machine was also running other SPICE containers). `summary.json` equals the repository's in every field except `runtime_s_last_invocation` (a recursive JSON diff finds 0 differences). `ge_vs_traces.csv` is byte-identical. The log matches `runs/kr/full.log` line for line. |
| 2 | `python3 analysis/cost_table.py` in the same copy, on the outputs of #1 | `cost.csv` and `cost.md` are byte-identical to the repository's. |
| 3 | Unit tests on the host (scratch copy) | analysis 32 OK. model 39 OK (1 skipped). sim 8 OK (1 skipped). notebook 29 OK (1 skipped: the figure class needs matplotlib). |
| 4 | Organizers' CI: `CPUS=2 bash notebook/tests/ci_container.sh <scratch>` (python:3.10-slim, with the workflows' commands) | flake8 PASS, has colab-badge PASS, colab-badge is sscs-ose PASS. `pytest --nbmake`: 2 passed (the main notebook and `ci_smoke.ipynb`, 12.3 s). |
| 5 | Per-key-bit POIs, re-implemented: per-input means, pooled variance, F, and my own in-cell chi2 per key bit, on the profiling rows of each of the 10 splits of N_pooled | These equal `per_bit_pois` in 10 of 10 splits. The x2 candidate sits at samples 147-149 (1.275-1.295 ns). Its chi2 is 75-116 against a 99.9 % point of 39.3 for chi2(16). The x1 candidate lies within 1-2 samples of the top-F sample, so it is dropped in 9 splits and kept in split 2 (top F 111, x1 115). So the "x2 POI at 1.275-1.295 ns" in §5 is x2's own POI. |
| 6 | Gaussian template, re-implemented (pooled covariance, same ridge): key rank on each unit's full attack set | This agrees with `attack()` in **400/400** cases: N_pooled `tmpl_bits` 80/80, and `tmpl` and `tmpl_bits` 80/80 each on D_tvla, DA_tvla and N_tvla. With my own random subsets at n = 765 on N_pooled, the per-key-bit template gives GE 0.061 and SR 0.94 (reported 0.07 / 0.93). |
| 7 | Injection, re-implemented. The pattern is N_pooled's per-input mean at its top-F sample (114, 0.945 ns), minus its mean, over the within-input SD (pattern SD 0.2572, as reported). It is added at sample 514 of D and DA. Then my own 1-POI template runs on the module's splits, with 20 subsets per unit | D at 521 per key, α 0 / 0.25 / 0.35 / 0.5 / 1: GE 1.46 / 1.52 / 1.19 / 0.77 / 0.31 (reported 1.48 / 1.55 / 1.22 / 0.83 / 0.35). DA at 533: 1.54 / 1.58 / 1.41 / 0.94 / 0.39 (reported 1.54 / 1.58 / 1.38 / 1.03 / 0.45). The detection limits agree: D from 0.35, DA from 0.5. My fixed single POI is slightly stronger than the cross-validated choice. |
| 8 | Null distributions and p values (`summary.json`) | Every order-1 and order-2 configuration without noise has 20 draws, and every noisy one has 5. p = (1 + draws ≤ real) / (draws + 1), and the unit test checks it by hand. "p = 0.048" is the floor for 20 draws, and §5 says so. The null SD of the template is 0.066-0.10 on N_pooled, D and DA (the "0.07-0.10" in §5). |
| 9 | Energy, re-implemented from `charge.npy` and the stimulus labels (rows r-L-1 .. r+L all random-class) | U: 78 rows, 291.45 ± 6.12 fC, 524.6 fJ. N: 635 rows, 944.55 fC, 1700.2 fJ. D: 395 rows, 2705.55 fC per 8 ns window, 2435.0 fJ. DA: 395 rows, 2635.24 fC, 2371.7 fJ. N_rvr: 943.84 fC. Over all random-class rows: 281.72 / 947.32 / 2712.50 / 2643.93 fC. All of these equal `cost.md`. D and DA have more clean rows than independent labels would give (395 against about 324), because the class labels come in runs. That is a property of the stimulus, not an error. |
| 10 | TVLA sensitivity | 4.5 / 13.23 × sqrt(9,998 / 19,997) = 0.2405 of N's effect. δ_N = 2 × 13.23 / sqrt(9,998) = 0.2646. δ at 19,997 traces = 9 / sqrt(19,997) = 0.0636. These match `cost.md` ("0.24 x"), §2.5 ("0.265") and §4.5 ("0.064", "a quarter"). |
| 11 | Every number in the claim screen, the abstract, §4.4, §4.5, §5, §7 and §9, against `results/kill_test/summary.json`, `results/key_recovery/summary.json` and `results/cost/cost.csv` | All agree, for example: D 3.08 at 19,997 (at most 3.622); level 2 cap-weighted 15.159, worst 16.734, 100 ps 2.705; level 1 D 2.113; DA 3.08 (at most 3.605), level 2 2.964, second order 21.475; N 0.38 / 0.62 / P(x1) 0.998 / P(x2) 0.626, per-key-bit 0.066 / 0.934 / 0.934, null 1.476 ± 0.092; N_tvla 0.43 / 0.64; N at 1x 0.97 / 0.99; D 1.475 (null 1.512 ± 0.066, p 0.286), DA 1.537 (1.505 ± 0.085, p 0.667); order 2 DA 0.266 / 0.783, D 0.568 / 0.614; U_cpa SR ≥ 0.9 from 2; area +59 %, energy +39 % (SPICE) and +46 % (with CLK pins), latency +13 % / +28 %, 141 ps. The saved outputs (the key-recovery table, the cost table and Figures 10-12) show the same values. `test_text_matches_results` confirms that the saved cells are what the generator builds from these files. |
| 12 | `notebook/data/` copies | `key_recovery__summary.json`, `key_recovery__ge_vs_traces.csv`, `cost__cost.csv` and `kill_test_summary.json` are byte-identical to `results/`. MANIFEST lists 53 files. |
| 13 | Team table and AI-use disclosure | Author row: IEEE member **yes**, SSCS member **no**, contact `TODO(user)`. The advisor row is `TODO(user)`. The disclosure sentence is in the closing cell. |
| 14 | Hygiene of all new files (the untracked files except `layout/`, `results/layout`, `results/pex`) | No absolute home-directory or mount path, host name or e-mail address. The only hits of the scan are the generic `~/.ciel` default in the setup helper and a NIST reference URL. Every new `.py`, `.sh` and `.md` file has the SPDX line (the shell scripts on line 2, after the shebang). |

## Findings

### B1. The key-recovery headline sentences state "no key recovery" for D and DA without the detectable effect (blocking, wording)

**Where** (all in `notebook/make_notebook.py`):
- **Claim screen:** "A profiled attack ... reaches a success rate of 0.93 on N's two key bits at 765 traces per key
  and **gets nothing from DA at first order**."
- **Abstract:** "... and **gives no first-order key recovery on D or DA**."
- **§7, "What the cost buys":** "DA shows no first-order leak at 19,997 traces and **no first-order key
  recovery**."
- **§9 Conclusion:** "A profiled attack on the same traces recovers N's two key bits at first order and **gets
  nothing from D or DA at first order**."

**Why it matters.** At these data volumes the attack finds an N-shaped leak only from 0.35 × (D) or 0.5 × (DA) N's
strength (check 7). TVLA already excludes about 0.24 ×. So "gets nothing" is literally true, but it says nothing
more than TVLA does. A reader of the abstract or the conclusion will take it as extra evidence that DA is secure.
Stage-2 B2 made exactly this blocking, and §5 and §8 of the notebook already say it correctly ("a consistency check:
it adds no sensitivity beyond the TVLA").

**Fix** (template text only; the numbers exist in `nbdata`):
- **Claim screen:** "... and finds no key in DA at first order (at 533 traces per key it would find a leak half as
  strong as N's; TVLA is more sensitive)." Also consider "with one point of interest per key bit, chosen after the
  default attack missed x2 (default: SR 0.62)". The 0.93 comes from the post hoc variant.
- **Abstract:** "... and finds no first-order key in D or DA, where it would detect a leak 0.35-0.5 times as strong
  as N's (TVLA: about 0.24)."
- **§7 and §9:** add the same bound, or refer to §5 ("no first-order key recovery, down to half of N's leak (§5)").

Then:
1. run `python3 notebook/make_notebook.py`;
2. re-execute the notebook in cached mode;
3. run the notebook tests and `notebook/tests/ci_container.sh` again.

## Non-blocking notes

- **Level 2's number for D differs between documents.** `docs/KILL_TEST.md` (addendum) says level 2 "predicts 16.7"
  (worst weighting). `cost.md`, the claim screen and the abstract say 15.2 (cap-weighted) without naming the
  weighting. §4.4 gives both. Name the weighting in `cost.md` (`VERDICT_NOTES`) and in the abstract, or quote the
  worst weighting everywhere.
- **"46 % more energy"** in the claim screen, the abstract and §9 includes the Liberty estimate of the CLK-pin charge.
  The simulated current alone gives +39 %, and both figures assume pipelined use. The notebook's cost table labels
  the ratio column "energy vs N", but it holds `total_vs_N` (with CLK pins), while `cost.md`'s "Energy vs N" is the
  SPICE-only 1.39. Label it "total vs N (incl. CLK pins)".
- **The primary distinguisher was fixed after the stage-2 review.** The code, `summary.json` and `cost.md` say so;
  §5 of the notebook does not. One clause is enough: "fixed after a review, for the structural reason below". It
  changes no D or DA verdict, because both distinguishers are at chance there.
- **`cost.md` wording:** "at this count TVLA detects a leak of 0.24 x N's effect size or more" should read "reaches
  4.5 on average for a leak of 0.24 x N's effect size". At 0.24 exactly the detection probability is about one half.
  The notebook already words it this way.
- **§5's null SD "0.07-0.10"** covers N_pooled, D and DA. The U_cpa null in the same table has an SD of 0.17 (4 keys),
  and the N_tvla per-key-bit null 0.11. Say "on N, D and DA". The table's "null GE" column is the default
  template's null, and the per-key-bit column has its own null (N: 1.48 ± 0.09), so name it in the header.
- **DA's per-key-bit GE of 1.66 lies above all 20 null draws** (null maximum 1.649). Like D's anti-replication in
  stage 2, this belongs to the finite stimulus rows and is no extra margin. The notebook does not read it as margin.
  It should stay that way.
- **D and DA have the same max\|t\|, 3.08, at the same sample** (2.175 ns, the clock fall). Their t-curves agree to 3
  decimals there (-3.0797 and -3.0798) and in the samples around it. The likely source is circuitry that D and DA share, for
  example the registers of the input bits that the affine layer leaves unchanged, driven by the same stimulus rows.
  I did not check this at the net level. If it holds, the two maxima are one observation, not two. One sentence in
  §4.5 would prevent the question.
- **§4.7:** "DA stays below 4.5 at every noise level" is not true at every checkpoint. At 1x noise DA reaches 4.93
  at an early checkpoint (`first_above` 34 in `summary.json`), and D reaches 5.97. These are the small-sample
  false alarms that `docs/KILL_TEST.md` explains. Write "ends below 4.5 at every noise level, and never stays
  above it".
- **Stale counts.**
  - The notebook's "How to run" table, its closing cell and `notebook/README.md` say `data/` holds "CSV plus one
    JSON". It now holds two JSON files.
  - §3.6 says "Three adversarial reviews". There are four now, five with this one.
  - §3.6 says the author continued "on the strength of K2, K3, K5 and the controls". K5 was still incomplete when
    that decision was made (`docs/KILL_TEST.md`: "K2, K3, C and the localization").
  - `notebook/README.md` says every quoted number is filled in from the data. Several are quoted from the reviews
    as fixed text, for example 7.20 against 9.20, 2.30 against 2.29 and 28 % against 8.7 %. The abstract's "read from
    a committed result file or review" is the accurate wording.
- **Data copies.** After the layout work is final, re-run `python3 notebook/make_cached_data.py` without
  `--optional`, so that `results/layout` and `results/pex` reach `data/`. Then rebuild and re-execute the notebook
  and run the CI checks again (an open item of the fix report).

## How to redo my checks

Copy the repository without `.git` and `runs/` to a scratch folder, and link `runs/kt` to the real one. Run everything
there with `PYTHONDONTWRITEBYTECODE=1`, so the repository's `results/` and `notebook/` are never rewritten.

- **Checks 1-2.** Run `OPENBLAS_NUM_THREADS=1 nice python3 analysis/key_recovery.py --jobs 3`, then
  `python3 analysis/cost_table.py`, in the copy. Compare with a JSON diff that ignores `runtime_s_last_invocation`,
  and with `cmp` for the CSV and `cost.md`.
- **Check 4.** From the repository root, run `CPUS=2 bash notebook/tests/ci_container.sh <scratch dir>`. It mounts
  `notebook/` read-only and writes only the logs.
- **Checks 5-6.**
  1. For each `(prof, att)` in `kr.split_masks(ds, 10)`, compute on `tr[prof]` the per-input means, the pooled
     variance and F.
  2. For bit b (x1 = 3, x2 = 2), compute chi2 = Σ over the cells c with bit b clear of
     (μ[c|1<<b] − μ[c])² / (var (1/n_c + 1/n_c')).
  3. The POIs are argmax F, then argmax chi2(x1), then argmax chi2(x2); drop a candidate within 3 samples of one
     already taken.
  4. For each scenario, score each guess g by −½ Σ dᵀ Σ⁻¹ d, where d = trace − μ[iv<<4 | g<<2 | nonce] at the POIs and
     Σ is the pooled residual covariance with a ridge of 1e-9 × mean diagonal.
  5. Compare with `kr.attack(tm, tr[sel], x[sel], iv, key, [len(sel)], 1, rng, extra={"tmpl_bits": tb})`.
  6. For the default template, take `k` from `kr.choose_k_tmpl(..., ("cv", name, s))` and use greedy top-F POIs,
     spaced 3 apart.
- **Check 7.**
  1. Build the pattern from all N_pooled rows at argmax F: (μ[x] − mean) / sqrt(within-input variance).
  2. Add α × pattern[x] × sqrt(the target's within-input variance at sample 114 + 400) to the D and DA traces.
  3. Run the 1-POI template on the module's splits, with random subsets of n = min(rows per scenario).
- **Check 9.**
  1. Take `charge.npy`, and the stimulus labels from `runs/kt/stim/<stem>.meta.npz`.
  2. Keep row r if r ≥ L+1 and rows r-L-1 .. r+L are all label 1 (every row for N_rvr).
  3. Energy = mean / L × 1.8 V.
- **Check 11.** Use `nbdata.fmt_headline()` (it prints every quoted value) and the extracted notebook cells.
  Compare them with the three result files.
