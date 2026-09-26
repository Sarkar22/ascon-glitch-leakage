<!-- SPDX-License-Identifier: Apache-2.0 -->
# Review: post-layout analysis and notebook §6 (stage 4, 2026-09-26)

**Scope.** This review covers the analysis of the two registered post-layout campaigns and the text built on it:
- `analysis/postlayout.py`, `analysis/plot_postlayout.py`, `analysis/test_postlayout.py`;
- the outputs in `results/pex/` (`summary_postlayout.json`, the t-curve and max|t| CSV files, the two figures) and
  `results/layout/placement_<V>.csv`;
- the Results section appended to `docs/POSTLAYOUT.md`, and the edits to `layout/README.md`;
- the notebook: the claim screen, the abstract, "How to run", §6, the post-layout parts of §7, §8 and §9, the
  closing notes, and `nbdata.py`, `nbfigs.py`, `make_notebook.py`, `make_layout_media.py`, `data/`, `media/`.

None of these files is committed yet.

**Lens.** I tried to refute seven claims:
- the analysis follows `docs/POSTLAYOUT.md` exactly: the kill test's TVLA code path, the fixed counts, the dropped
  rows, the threshold and the registered cycle parts;
- PL1 and PL2 are right, which I recomputed from the traces without the repository's code;
- the pre-layout comparison uses the same rows;
- the detectable-effect statement is right;
- every number in the Results section and in the notebook matches `results/pex/summary_postlayout.json` or
  `results/layout/summary.json`;
- nothing overclaims (silicon, proofs, "secure");
- the notebook executes, passes the organizers' CI and holds only the intended TODO markers, and no committed file
  contains a host path.

**What I changed.** Nothing in the repository except this file. I re-ran `analysis/postlayout.py` with its output
directory redirected to a scratch folder outside the repository, and wrote my own check scripts there. The only
containers I started were the two CI containers of `notebook/tests/ci_container.sh` and one `python:3.10-slim`
container that executed a scratch copy of the notebook. All three ran at `--cpus 2`. No SPICE job was running.

## Verdict

**The analysis is sound, and both verdicts are right. One sentence contradicts the data and must be fixed before
the commit. The rest are wording and provenance notes.**

- **PL1 and PL2 reproduce independently.** My own two-pass Welch t on `runs/pex/*/traces.npy` gives exactly the
  reported values. I rebuilt the labels from the stimulus seed and decoded the fixed input from the stimulus bits.
  PL1: max|t| 8.192 at 1.655 ns, above 4.5 from 1,902 traces on. PL2: 3.363, at most 3.625 at any checkpoint.
- **It is the kill test's code path.** Re-running `postlayout.py` gives byte-identical files, and its
  `reproduces_kill_test` check (the full pre-layout N and DA campaigns reproduce their `spice` blocks) holds.
- **The registered text is unchanged.** The first 3,106 bytes of `docs/POSTLAYOUT.md` are byte-identical to the
  committed version.
- **The notebook's saved outputs are what the code produces.** A fresh execution gives identical outputs in every
  code cell, PNG bytes included. The organizers' CI passes.

**Blocking, a one-line fix in two places.** Both documents say that at 1x added noise "neither reaches 4.5 within
4,998 traces". The summary file shows that both do, at small trace counts (B1 below).

## What I checked or re-ran

| # | Check | Result |
|---|---|---|
| 1 | Registered text | `git show HEAD:docs/POSTLAYOUT.md` (3,106 bytes) is a byte-identical prefix of the current file. Only the Results subsection is appended |
| 2 | Campaigns as registered | `runs/pex/queue.log`: N_pex 19:24:37-23:25:09 (5,000 rows), DA_pex 23:25:09-04:19:07 (10,000 rows), DONE. Manifests: 5,000 / 10,000 rows, latency 1 / 2, KLU, tt, 27 C, 1.8 V, 4 ns, 10 ps. Both counts were in `queue.sh` from its first start (19:19), before the interim looks |
| 3 | Netlist actually simulated | Each of the 40 N and 80 DA chunk decks records `dut.sp sha256` `b1999858…` / `8517658f…`. These equal the current `build/<V>_pex/dut.sp` and the manifests. The 19:36 rewrite left the content unchanged (stage 3, check 11) |
| 4 | Labels and stimulus | `default_rng(202).integers(0, 2, 20000)` equals `meta["label"]`. XOR of the share-0 and share-1 port bits of `M_tvla.npy`, decoded with `build/<V>_pex/ports.json`, equals `meta["x"]` on every row, and every label-0 row has x = 0x0B. The stimulus array hash equals the pre-layout campaigns' |
| 5 | Independent PL1/PL2 (plain two-pass Welch, `ddof=1`, first L+1 rows dropped, my own checkpoint grid) | N_pex: 4,998 traces (2,511 / 2,487), max\|t\| 8.192 at 1.655 ns, 39 samples above 4.5 in 1.415-1.795 ns, first and stable above 4.5 from 1,902. DA_pex: 9,997 traces (5,009 / 4,988), 3.363 at 2.945 ns, none above, at most 3.625 at any checkpoint. Pre-layout on the same rows: 8.074 at 0.945 ns (first 1,657, 33 samples in 0.765-1.115) and 3.347 at 2.415 ns. 100 ps bins 7.971 / 7.794 / 3.298 / 3.317, charge per window 2.344 / 2.477 / 1.812 / 2.005, second order 10.599 / 10.648 / 22.292 / 14.960, max\|t\| by registered part as reported. All match the summary to 3 decimals |
| 6 | Same code path | `spice_tvla` repeats the SPICE part of `kill_test.analyse_tvla` line for line: `checkpoints`, `tvla_block`, `tvla_curve(order=2)`, the 100 ps reshape, charge, `noise_sigma`, the noise seeds `1000 + 10 f`. Only the part boundaries differ, as registered. I re-ran `postlayout.main()` into a scratch folder: `summary_postlayout.json` and the four CSV files are byte-identical, and `reproduces_kill_test.all_identical` is true |
| 7 | Registered parts | `PARTS_POST` = (-0.2, 2.1), (2.1, 2.9), (2.9, 3.8), repeated in DA's second cycle. Together they cover the whole window. Neither peak lies in the 2.0-2.2 overlap |
| 8 | Same rows before layout | `load_run(..., rows=5000/10000)` on `runs/kt/{N,DA}_tvla`, the same skip, and `assert np.array_equal(labels, labels_pre)`. Row 4,999 (9,999) sees the next file row's input edges in both runs, because the runner takes the rows that follow from the file |
| 9 | Function | My own S-box table and XOR of the two output shares: 0 mismatches in 5,000 and 10,000 rows. `outputs.npy` equals the pre-layout campaign's outputs row for row |
| 10 | Detectable effect | d_N = 2 x 8.192 / sqrt(4,998) = 0.2318, d_DA = 2 x 4.5 / sqrt(9,997) = 0.0900, ratio 0.388. The exact class sizes give the same result to 4 decimals |
| 11 | Numbers in `POSTLAYOUT.md` Results | Every row of the PL table, the pre/post table (including noise units, noise finals, mean charge, peak currents 25.47 uA at 1.485 ns etc. from the CSV), the solver and N2 tables, the capacitance views, energy (305 / 179 rows), area ratios (1.606, 1.439), wall clock and chunk medians. All match their sources, except the items in B1, N1 and N2 below. DA's "mean current decayed from 761 to 7 uA" and the flat stretch at 2.6-2.95 ns match `tcurve_DA_pex.csv` |
| 12 | Numbers in the notebook | Claim screen, abstract, §6 (text, layout table, PL table, figures), §7 post-layout table and bullets, §8, §9. All filled from `data/` by `nbdata.postlayout_values()`. `test_text_matches_results` ties the cells to `make_notebook.build()`. The coupling figures 7.0 / 7.8 fF match `results/layout/summary.json` (`s0-s1` 6.959 / 7.807) |
| 13 | Solver claim, re-derived | On the 120 benchmark rows the KLU-minus-Sparse difference is sporadic: a few rows reach 4.9 uA (N) and 11.0 uA (DA). Its class-mean difference (fixed minus random) is at most 0.13 uA (N) and 0.28 uA (DA), against a 25.5 uA class effect in N. The conclusion stands, but see N2 |
| 14 | The slow N_pex wave | Chunks 24-29 each took 9,410-9,422 s, and ngspice's own analysis time was 9,407 s. The host's system log shows a suspend at 20:31 on 09-25. The explanation is right, but see N1 |
| 15 | Tests | Host (numpy only): analysis 44 OK, layout 8 OK, notebook 33 OK (1 skipped: figures). `python3 -m unittest analysis/test_postlayout.py` as written in Reproduce: 12 OK |
| 16 | Organizers' CI (`CPUS=2 bash notebook/tests/ci_container.sh <scratch>`) | flake8 PASS, has colab-badge PASS, colab-badge is sscs-ose PASS, `pytest --nbmake` 2 passed (7.6 s for the notebook), nbmake PASS |
| 17 | Saved outputs | Fresh execution of a copy of `notebook/` in `python:3.10-slim` (numpy 2.2.6, matplotlib 3.10.9, nbconvert, no ipywidgets): every output of all 24 code cells equals the saved one (text, markdown and PNG bytes) |
| 18 | TODO markers | In the notebook, only `TODO(user): e-mail`, `Acknowledgments. TODO(user)` and `TODO(setup): measure; target 10 min`. None in the new source files |
| 19 | `data/` and media | 69 files plus `MANIFEST.csv`, 4.61 MB. Every sha256 matches, and nothing is unlisted or missing. The `pex__*` and `layout__*` copies are byte-identical to `results/`. `media/layout_{N,DA}.png` are 54 KB and 66 KB, 500 x 500 px. The notebook is 1.91 MB, 1.35 MB of it embedded PNGs (the layout figure 380 KB) |
| 20 | Host paths and SPDX | No home-directory or mount path, user name, hostname or e-mail address in the 42 changed or new files. The one path-like match is inside a csrc.nist.gov URL. The new PNGs carry only a Matplotlib "Software" tag or no text chunk. The 5 new or changed Python files start with the SPDX line |
| 21 | Overclaiming | "Secure" appears only for the zero-delay model. "Not silicon" / "not a statement about silicon" appears in the claim screen, §8 and the Results. There is no proof language. The DA claims say "no first-order leak detected/shown within 9,997 traces". See N4 for the registered PL2 wording in the table |

## Blocking

**B1. "At 1x noise neither reaches 4.5 within 4,998 traces" is false as written.** It appears in `docs/POSTLAYOUT.md`
("What this shows", added-noise bullet) and in notebook §6.2 ("Added noise" bullet, `make_notebook.py` line 846).
`summary_postlayout.json` gives `noise["1.0"].first_above` = 20 for both N_pex and N pre-layout on the same rows:
- N_pex reaches 5.62 at 20 traces and 4.54 at 105;
- pre-layout N reaches 5.20 at 20.

These are the small-sample false alarms that §4.7 and `docs/KILL_TEST.md` explain. The statement contradicts the
committed summary and the notebook's own §4.7. Suggested fix: "At 1x noise neither stays above 4.5: both end below it
(3.84 after layout, 4.24 before). The only crossings are small-sample false alarms at 20-105 traces (§4.7)." After the
edit, rebuild the notebook cells (`make_notebook.py`, then execute).

## Notes (non-blocking)

**N1. "One chunk took 9,422 s" should be "one wave of six chunks".** Chunks 24-29 ran together from 20:23 and each
took 9,410-9,422 s (`POSTLAYOUT.md`, "SPICE cost"). The suspend explanation is right.

**N2. Solver paragraph: "The solvers differ by the same amount whatever the data" is not what the files show.** The
differences are sporadic per row (check 13). What makes the conclusion hold is that their class-mean difference is at
most 0.13 uA (N) and 0.28 uA (DA) on the 120 rows. That is two orders of magnitude below N's 25.5 uA effect. Say that
instead, or drop the sentence and keep the correlation argument.

**N3. The DA bound: "rules out" and the reason it is weaker.**
- The bound is where the *expected* t equals 4.5, so a leak exactly 0.39 times N's would be missed about half the
  time. At 80 % power the fraction is 0.46. The notebook's "reaches 4.5 on average" is exact. The Results' and §8's
  "rules out only leaks at least 0.39 times as strong" reads stronger. It is the kill test's convention, but "on
  average" could be added.
- The notebook says the bound is weaker than 0.24 "because the registered post-layout campaign is half as long". Half
  the traces alone gives 0.34 (0.090 / 0.265). The rest comes from the smaller reference: N's effect on its first
  4,998 rows is 0.232, against 0.265 at 9,998.

**N4. PL3's evaluation part was registered after N's interim peak position was known.** The stage-3 review (N3) had
already recorded the second look as 3.00 at **1.645 ns**. The registration discloses the interim max|t| values but not
that position. Then it set the post-layout evaluation part to -0.2 to 2.1 ns. The node timing (last transition up to
2.01 ns) justifies 2.1 on its own, and PL3 is informational. Still, the Results sentence "the whole post-layout leak
lies inside the registered evaluation part" should add that the interim peak position (1.645 ns) was known when the
parts were written. Relatedly, the PL table repeats the registered label "the fix survives place and route" next to
**pass** for PL2. That is the registered wording and cannot change, but the notebook's PL2 row could add "(no
detection at 9,997 traces)".

**N5. "The same verdicts" (claim screen, abstract) and "the verdicts ... hold after place and route" (§9).** For DA
the post-layout verdict rests on half the traces and a 0.39 bound, against 0.24 before layout. The claim screen gives
0.39 right after. The abstract and §9 do not. Adding "(at half the traces)" would close this.

**N6. Two numbers are not from a file under `results/`, although the Results header asks for that.**
- "The clock tree adds about 0.33 ns of insertion delay" comes from `layout/README.md` prose. No results file holds
  it: `node_timing_N.json` has clock-to-Q and last-transition times only, and `summary.json` has the skew.
- The campaign times 19:24-23:25 and 23:25-04:19 come from the git-ignored `runs/pex/queue.log`.

Cite the sources, or add the insertion delay to `node_timing_N.json`.

**N7. §6 "the same net on every pin".** The flip-flops' CLK pins moved to the clock tree's leaf nets (25 in N, 55 in
DA; `final_vs_generator.clk_pins_on_clock_tree_nets`). "Except the flip-flops' clock pins, which now hang on the clock
tree" would make the sentence exact.

**N8. `layout/README.md` still reads as if the campaigns were pending.**
- It still says "The post-layout TVLA campaigns are queued".
- It gives projected wall times.
- It comments `pex_status.py` as showing "first-look TVLA", which is off by default since the registration.

A one-line pointer to `docs/POSTLAYOUT.md` (Results) and the actual times (N 4.0 h including the suspend, DA 4.9 h)
would fix this.

**N9. Small items.**
- The setup cell prints "results dated 2026-09-25". That is the kill-test summary's date; the post-layout results are
  dated 2026-09-26.
- `postlayout.py` skips the solver, netlist-text and capacitance checks when `runs/pex/bench_*` or the OpenLane SPEF
  are absent. It also needs the full `runs/kt/{N,DA}_tvla` for `reproduces_kill_test`. The Reproduce block does not
  say so.
- The notebook grew to 1.91 MB. The layout figure (380 KB) could be drawn at a lower dpi if size matters.

## What remains open (by design)

- `TODO(user)` (e-mail, acknowledgments) and `TODO(setup)` (measured live-mode Colab time), the submission README
  and the final polish.
- The post-layout model's limits are stated in both documents: C-only, tt only, one placement, ideal supply and
  sources at the block pins, noiseless traces, D not laid out, U not simulated.
