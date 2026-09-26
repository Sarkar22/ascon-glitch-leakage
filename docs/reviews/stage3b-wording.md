<!-- SPDX-License-Identifier: Apache-2.0 -->
# Review: wording fixes after the stage-3 review (stage 3b, 2026-09-25)

**Scope.** This review checks the fixes made for `docs/reviews/stage3-key-recovery.md` in:
- `notebook/make_notebook.py`, `notebook/nbdata.py`, `notebook/nbfigs.py` and the regenerated
  `notebook/ascon_glitch_leakage.ipynb`;
- `analysis/cost_table.py` and the regenerated `results/cost/cost.md` and `cost.csv`;
- `notebook/README.md`, `notebook/make_cached_data.py`, `notebook/data/` and the tests.

None of these changes is committed. The fix was meant to change wording and labels only, not numbers.

**Lens.** For each item of the stage-3 review I checked the generated notebook text, not only the generator. I then
compared every number in the changed sentences with `results/kill_test/summary.json`,
`results/key_recovery/summary.json` and `results/cost/cost.csv`. I computed the new D-versus-DA statement of §4.5
myself from the t-curves. I also re-ran the unit tests and the organizers' CI.

**What I changed.** Nothing except this file. I did not read `runs/pex`, `build/*_pex`, `layout/` or `results/pex`,
and I looked at no post-layout statistic. The host checks ran with numpy only and wrote no bytecode. I started two
kinds of container, both at `--cpus 1`, and both exited:
- the two CI containers of `notebook/tests/ci_container.sh`;
- one `python:3.10-slim` container for the notebook unit tests with matplotlib, with the repository mounted
  read-only.

The post-layout queue's `cac-sca` container was the only other one running, and I left it alone.

## Verdict

**Sound.** B1, the one blocking item, is fixed in all four places. Every non-blocking note of the stage-3 review
that was in the fix's scope is addressed. Every number in the changed sentences matches the result files, and the
numbers themselves did not change. The notebook's cells are exactly what `make_notebook.py` builds, and the executed outputs
differ from the committed run only in the two tables whose labels changed. The unit tests and the organizers' CI
pass.

Still open, and neither is a wording defect of this fix:
- the weighting in `docs/KILL_TEST.md`, which was outside the fix's scope;
- one marker that predates this fix, `TODO(setup)`.

Both are listed at the end, together with the cosmetic nits.

## Stage-3 items: status

| Stage-3 item | Status | Evidence in the regenerated notebook or file |
|---|---|---|
| **B1**, claim screen: "gets nothing from DA" | **fixed** | "It finds no key in DA at first order: at 533 traces per key it would find a leak half as strong as N's, so TVLA is more sensitive." The 0.93 is now marked post hoc: "with one point of interest per key bit, chosen after the default attack had missed key bit $x_2$ (default: success rate 0.62)". The TVLA bound, "a quarter as strong", is two sentences earlier. |
| **B1**, abstract: "no first-order key recovery on D or DA" | **fixed** | "It finds no first-order key in D or DA, where it would detect a leak 0.35-0.5 times as strong as N's (TVLA: about 0.24)." The post hoc POI choice and the default SR 0.62 are stated. |
| **B1**, §7 "What the cost buys" | **fixed** | "... no first-order key recovery, down to a leak half as strong as N's (§5). TVLA on the same traces is more sensitive: it excludes a leak a quarter as strong (§4.5)." N's key recovery is marked "with the post hoc per-key-bit points of interest". See nit 1. |
| **B1**, §9 conclusion | **fixed** | "... finds no first-order key in D or DA, where it would detect a leak 0.35-0.5 times as strong as N's. TVLA on the same traces is more sensitive (about 0.24), so for D and DA the attack adds no evidence beyond it (§5)." |
| Level 2's weighting for D | **fixed** in the notebook and `cost.md` | The claim screen, the abstract and §4.4 say "15.2 (cap-weighted; 16.7 with the worst ... weighting[s])". `cost.md` and `cost.csv` (`VERDICT_NOTES`) say the same. §4.5 now says DA's 2.96 is the worst of three weightings, and §4.6 says N's 12.1 is cap-weighted. `docs/KILL_TEST.md` was not in scope (open item 1). |
| "46 % more energy" | **fixed** | The claim screen, the abstract and §9 now say 39 % in the simulated supply current and 46 % with the estimated clock-pin charge, both for pipelined use. The notebook's cost table has a new "SPICE energy vs N" column (0.31 / 1.00 / 1.43 / 1.39), and the old column is now "total vs N (incl. CLK pins)" (0.32 / 1.00 / 1.49 / 1.46). In `cost.md` the columns are "Energy vs N (SPICE only)" and "Total vs N (incl. CLK pins)", and the heading says which columns add the CLK-pin estimate. |
| Primary distinguisher fixed after a review | **fixed** | §5: "It was made primary after a review (`docs/reviews/stage2-key-recovery.md`, B2), for the structural reason given in the third point; on D and DA both distinguishers are at chance at first order, so no verdict there depends on that choice." The third point is the correlation distinguisher's centring. The claim holds: at first order without noise, D is at correlation 1.52 and template 1.48, and DA at 1.52 and 1.54. |
| `cost.md`: "detects a leak of 0.24 x ... or more" | **fixed** | D and DA now read "at this count TVLA reaches \|t\| 4.5 on average for a leak of 0.24 x N's effect size". "or more" appears nowhere in `cost.md`, and `test_cost_table.py` asserts that. |
| §5 null SD, and the table's null column | **fixed** | "0.07-0.10 for the default template and 0.07-0.11 for the per-key-bit template on U, N, D and DA (TVLA campaigns), and 0.17 for U on the K1 CPA traces". The table header now reads "null GE of the default template". The Figure 10 caption gives the per-key-bit null (N: 1.48 ± 0.09). See nit 3. |
| DA's per-key-bit GE 1.66 above the null | **unchanged, correctly** | 1.66 appears only in the table. No text reads it as margin. |
| D and DA share their peak | **fixed** | The new §4.5 sentence is scoped correctly and carries the "not checked at the net level" caveat. My own check is below, and a new unit test holds the sentence to the data. |
| §4.7: "DA stays below 4.5 at every noise level" | **fixed** | "DA ends below 4.5 at every noise level, and never stays above it: at 1x it touches 4.93 at an early checkpoint (above 4.5 first at 34 traces; D reaches 6.0) and falls back." See nit 2. |
| Stale counts | **fixed** | "CSV plus one JSON" is gone from the "How to run" table, the closing cell, `README.md`, `nbdata.py` and `make_cached_data.py`. `data/` holds two JSON files, so "a few JSON summaries" is accurate. "Three adversarial reviews" is now "Adversarial reviews (`docs/reviews/`, one file each)". The continue decision now reads "K2, K3, the controls (C) and the localization of §4.3. K5 was still incomplete at that point; it passed later", which matches `docs/KILL_TEST.md` ("the strength of K2, K3, C and the localization"). The `README.md` row names the fixed-text numbers, and all three of its examples are fixed text in the notebook. |
| Data copies: `make_cached_data.py` without `--optional` | **open (by design)** | The author row reads IEEE yes, SSCS no. `results/layout` and `results/pex` are not yet in `data/`. See open item 2. |

## Numbers in the changed sentences

Every value below was read directly from the result files. I did not go through `nbdata`.

| Where | Quoted | Source value |
|---|---|---|
| Claim screen, abstract | SR 0.93 at 765; default SR 0.62 | `N_pooled` `order1_noise0`: `tmpl_bits` `final_sr` 0.9345; `tmpl` 0.625; n 765 |
| Claim screen, §7 | DA at 533 traces per key, "half as strong" | `DA_tvla` n 533; `injection.smallest_detected_alpha.tmpl` 0.5 (GE 1.032 at 0.5, 1.384 at 0.35) |
| Abstract, §9 | 0.35-0.5 | `D_tvla` 0.35 (GE 1.223), `DA_tvla` 0.5 |
| Abstract, §9, §7, claim screen | TVLA about 0.24, "a quarter" | 4.5 / 13.23 × sqrt(9,998 / 19,997) = 0.2405 |
| Claim screen, abstract, §4.4, `cost.md` | 15.2 cap-weighted, 16.7 worst | `D_tvla.level2`: weighted 15.159, unweighted 15.159, weighted_rise 16.734 |
| §4.5 | DA level 2 2.96, worst of three | `DA_tvla.level2`: 2.360 / 2.964 / 2.964 (so the table's cap-weighted "3.0" is the same number) |
| §4.5 | same max\|t\| at the same sample, 2.175 ns, clock-fall region; difference at most 0.004 within 30 ps | Both `spice.final_argmax` 237, `final_peak_ns_after_edge` 2.175, final 3.08. `max_abs_t_by_region.cycle1_clock_fall` 3.08 for both. From `tcurve_D_tvla.csv` and `tcurve_DA_tvla.csv` (10 ps grid, identical time axes): t -3.0797 and -3.0798 at the peak, and max\|t_D − t_DA\| 0.0036 over ±3 samples (0.011 over ±5). Over the whole window the curves differ by up to 3.27 (correlation 0.67), so the agreement is local to the peak, as the sentence says. |
| §4.6 | N level 2 12.1 (cap-weighted) | `N_tvla.level2.weighted` 12.125 |
| §4.7 | DA 4.93 at 1x, first above 4.5 at 34, never stays above; D 6.0 | `DA_tvla.spice.noise["1.0"]`: max 4.931 at n = 34, `first_above` 34, `stable_from` null. The finals are 3.644 / 3.042 / 3.559 at 0.5x / 1x / 2x, and the maxima at 0.5x and 2x are 4.429 and 3.921. For D at 1x: max 5.969 at n = 34, `stable_from` null, final 3.042. |
| §5 | null SD 0.07-0.10 (default), 0.07-0.11 (per-key-bit), 0.17 (U on the CPA traces) | No-noise configurations of U_tvla, N_tvla, N_pooled, D_tvla and DA_tvla, orders 1 and 2: `tmpl` 0.0656-0.1014 and `tmpl_bits` 0.0679-0.1094. `U_cpa` `tmpl` 0.1677. |
| Figure 10 caption | per-key-bit null for N 1.48 ± 0.09 | `N_pooled` `order1_noise0` `null.tmpl_bits` 1.4756 ± 0.0915 |
| Claim screen, abstract, §7, §9 | +59 % area, +39 % SPICE energy, +46 % with CLK pins, +13 % latency | `cost.csv` DA: `area_vs_N` 1.59, `energy_vs_N` 1.39 (2371.7 / 1700.2 fJ), `total_vs_N` 1.46 (2691.4 / 1845.5 fJ), `latency_vs_N` 1.13 |
| §3.6 | K5 passed at 19,997 | `criteria` K5 pass, DA 3.08 at 19,997 |
| Notebook cost table | new column 0.31 / 1.00 / 1.43 / 1.39 | `cost.csv` `energy_vs_N` for U / N / D / DA |

Nothing else in `cost.csv` changed: the diff touches only the D and DA verdict strings, and every number in them is
the same as before.

## Searches of the generated notebook

- **"no key", "nothing", "no first-order key", "key recovery".** Every statement about D or DA now carries the bound
  or points to it. The hits are the claim screen, the abstract, §7 and §9 (all with the bound), and §5's heading
  "no key recovery, and what that rules out" (the bound follows in the same paragraph). The contents table points
  to §5's "what 'no key recovery' rules out". "gets nothing" no longer appears.
- **"secure", "safe", "certif", "protect".** Every hit either states a model's verdict or defines a term:
  - the zero-delay model's column of the claim table, and "in the zero-delay sense";
  - the title "Safe on Paper";
  - the definitions in §2;
  - "This is not a proof that D is secure";
  - "not a certificate for D or DA".

  No sentence calls D or DA secure without a qualifier.
- **TODO markers.**
  - `TODO(user)`: 7 times (e-mail, the advisor row, acknowledgments).
  - `TODO(layout)`: once (§6).
  - **`TODO(setup)`: once**, in the "How to run" table ("Live ... TODO(setup): measure; target 10 min"). It was
    already in the committed notebook (HEAD 36a8a13), and `notebook/README.md` documents it as the live-mode timing
    marker. See open item 3.
  - There are no other TODO, FIXME or XXX markers in `make_notebook.py` or in the other `notebook/*.py` files.
- **No unfilled `<<key>>` placeholders**, and **no error outputs** in the executed notebook.

## What I re-ran or checked

| # | Check | Result |
|---|---|---|
| 1 | `git status` and `git diff` | 13 modified files, as the fix report lists them. Nothing untracked in `notebook/data/`. `notebook/data/` changes only in `cost__cost.csv` and `MANIFEST.csv`. |
| 2 | Notebook unit tests on the host (numpy only) | 30 OK, 1 skipped (the figure class needs matplotlib). This includes `test_text_matches_results` (the saved cells equal `make_notebook.build()` on the current results), the new `test_d_and_da_share_their_peak` and `test_key_recovery_and_cost_copies_are_current`. |
| 3 | Analysis unit tests on the host | 32 OK, including the new wording asserts in `test_cost_table.py`. |
| 4 | Notebook unit tests in `python:3.10-slim` with numpy 2.2.6 and matplotlib 3.10.9, `--cpus 1`, repository mounted read-only | 32 OK, nothing skipped, including `test_tables` with the new cost column. |
| 5 | Executed notebook against the committed run (HEAD) | 52 cells, 18 code cells, all sources equal. Only the outputs of code cells 15 (the key-recovery table) and 17 (the cost table) differ, as the fix report says. The execution counts run 1-18 in order, with no errors. The first cell's output shows Python 3.10.21, numpy 2.2.6 and matplotlib 3.10.9, in cached mode. |
| 6 | `data/` copy of the cost table | The SHA-256 of `results/cost/cost.csv` and `notebook/data/cost__cost.csv` agree (`00e87178…`), and `MANIFEST.csv` records the same hash and size (2,760 bytes). |
| 7 | The fix's own CI logs, kept outside the repository and not in `runs/` | lint ran 20:12:44-20:12:55 and nbmake finished at 20:14:11. The notebook was last written at 20:12:22, so these logs cover the final file. flake8 PASS, has colab-badge PASS, colab-badge is sscs-ose PASS, and `pytest --nbmake`: 2 passed in 12.60 s. |
| 8 | Organizers' CI, re-run: `CPUS=1 bash notebook/tests/ci_container.sh <scratch dir>` | flake8 PASS, has colab-badge PASS, colab-badge is sscs-ose PASS. `pytest --nbmake`: 2 passed in 13.63 s (the main notebook and `ci_smoke.ipynb`), exit 0. |
| 9 | Hygiene of the diff | No absolute home-directory, mount or temp path, user name, university address or e-mail string on any added line. |

## Nits (non-blocking, cosmetic)

1. **§7, "it excludes a leak a quarter as strong (§4.5)".** At 0.24 × N's effect, TVLA reaches 4.5 on average, so it
   detects such a leak about half the time. That is why `cost.md` now avoids "or more". "Excludes" is as strong as
   §4.5's existing "rules out leaks of that size and larger", which the stage-3 review accepted, so this is not a
   defect. For consistency with `cost.md`, it could read "it reaches 4.5 on average for a leak a quarter as strong
   (§4.5)".
2. **§4.7, "D reaches 6.0".** The source value is 5.969, and the same sentence quotes DA to two decimals (4.93).
   "5.97" would match, and the stage-3 review used that figure.
3. **§5, "0.17 for U on the K1 CPA traces".** This is the default template's null SD. The per-key-bit null SD there
   is 0.26, which is not quoted. Adding "(default template)" would remove the ambiguity.
4. `nbdata`'s `kr_D_alpha_words` gives "a third" for α = 0.35, as the fix report says. No text uses it, and the text
   quotes the numeric range. Leave it unused for D, or tighten `fraction_words`.

## Open items

1. **Weighting outside the notebook.** The addendum of `docs/KILL_TEST.md` says "level 2 predicts 16.7" (worst
   weighting). Its later line "level 2 predicts 12.2" at 9,997 traces also names no weighting. The notebook and
   `cost.md` now name both weightings, so adding "(worst of three weightings; 15.2 cap-weighted)" in `KILL_TEST.md`
   would make the documents agree.
2. **Before the PR.**
   - After the layout and post-layout work is final, run `python3 notebook/make_cached_data.py` without
     `--optional`, so that `results/layout` and `results/pex` reach `data/`.
   - Then rebuild and re-execute the notebook, and run the CI checks again.
3. **`TODO(setup)`** in the "How to run" table. This predates this fix and is outside the stage-3 review. It needs a
   measured live-mode (Colab) run time before submission, or the marker must go.
4. **Remaining `TODO(user)` entries** (the author's e-mail, the advisor row, acknowledgments) and **`TODO(layout)`**
   (§6).

## How to redo my checks

- **Text.** Extract the markdown cells and outputs of `notebook/ascon_glitch_leakage.ipynb` with a short `json`
  script. Search them for the phrases above, and for `TODO` and `<<`.
- **Numbers.** Read `results/kill_test/summary.json` (`campaigns.<C>.spice`, `.level2`, `.spice.noise`),
  `results/key_recovery/summary.json` (`datasets.<D>.results.<tag>.{tmpl,tmpl_bits}` and `.null`, and
  `datasets.<D>.injection.smallest_detected_alpha`) and `results/cost/cost.csv` directly. Compare them with the
  sentences.
- **D and DA peak.** Load `t_spice` and `ns_after_edge` from `results/kill_test/tcurve_D_tvla.csv` and
  `tcurve_DA_tvla.csv`. Take the argmax of \|t\| for each, then max\|t_D − t_DA\| over ±3 samples around it.
- **Outputs against HEAD.** Run `git show HEAD:notebook/ascon_glitch_leakage.ipynb`, then compare each code cell's
  source and a hash of its outputs.
- **Tests.**
  - On the host: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -p 'test_*.py'` in `notebook/` and in
    `analysis/`.
  - In a container: the same command in `python:3.10-slim`, with the repository mounted read-only, after
    `pip install numpy==2.2.6 matplotlib==3.10.9`, at `--cpus 1`.
- **CI.** From the repository root, run `CPUS=1 bash notebook/tests/ci_container.sh <scratch dir>`.
