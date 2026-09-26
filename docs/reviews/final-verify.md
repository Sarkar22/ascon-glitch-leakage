<!-- SPDX-License-Identifier: Apache-2.0 -->
# Review: verification of the final fixes (2026-09-26)

**Scope.** This review covers the working tree as it will be pushed: the tracked files plus the 22 untracked files
that are not ignored (280 files). It covers two must-fix lists:
- the one in `final-hygiene.md`;
- the one from the final jury-perspective review. That review is not a file in this repository, so its items are
  checked here as the fix report lists them.

For every item this file quotes the new text, or it says that the item is left for the author. It also re-runs the
unit tests, the organizers' CI emulation and the submission check. It checks the numbers in the claim screen, the
abstract, `README.md`, `docs/PR_BODY.md` and the submission README against `results/`.

**What I changed.** Nothing except this file. Every container ran at `--cpus 2`. No SPICE campaign was started, and
nothing was committed or pushed (HEAD is still 7a544e9, equal to `origin/main`).

## Verdict

**Ready, apart from the steps only the author can take.**
- Both blocking items of `final-hygiene.md` (B1, B2) are fixed.
- Every jury-perspective item is fixed, or it is left for the author and named below.
- The notebook's text, the unit tests, the organizers' checks and the submission check all pass.
- Every number checked matches `results/`.
- The registered text is byte-identical.

Five optional nits are listed at the end. None of them blocks the PR.

## Items of `final-hygiene.md`

| Item | Status | Evidence |
|---|---|---|
| **B1** (blocking), PR body overstates the attack | **fixed** | `docs/PR_BODY.md`, summary point 3: "A profiled first-order attack recovers the naive design's key (success rate 0.93 at 765 traces per key, with points of interest chosen per key bit after the default attack missed one bit; 0.62 with the default ones) and finds no first-order key in DA (a second-order template partly does, as expected for two-share masking)." |
| **B2** (blocking), PR copy taken from the clone | **fixed** | Header comment of `docs/PR_BODY.md`: "The fork's commit must come from the pristine build: a fresh copy of runs/submission/ISSCC27/submitted_notebooks/ascon_glitch_leakage/ ... never from runs/submission/upstream/ ... The folder must hold no \_\_pycache\_\_ and no \*.pyc." `tools/check_submission.sh` step 4 now counts and deletes the bytecode in the clone's copy. It fails if the build holds bytecode, and it fails unless `diff -r` finds the clone's copy equal to the build. `tools/make_submission.py` skips bytecode when it selects files, and `build()` stops if any appears. Re-run today: "bytecode written by the notebook run in the clone's copy: 6 entries, deleted", "no bytecode in the build", "the clone's copy equals the build (45 files)" |
| N1, pin `REPO_REF` to a tag | **left for the author** | `setup_env.DEFAULT_REPO_REF` is still `main`. This needs a push and a tag |
| N2, push before the "run now" link is used; one run in real Colab | **left for the author** | The live path was measured in an Ubuntu 22.04 container that stands in for Colab (`runs/colab_live_final`), not in Colab itself |
| N3, dead badge in `ci_smoke.ipynb` | **fixed** | The badge line is gone. `test_setup_env.py::test_no_colab_badge` asserts that the smoke notebook has none |
| N4, "not run" in the DA column of the controls table | **fixed** | Saved output of cell 56, both DRC rows, DA column: "not repeated (sign-off: 0, §6)" |
| N5, project files named in plain code spans | **fixed** | 32 markdown links to `https://github.com/Sarkar22/ascon-glitch-leakage/{blob,tree}/main/...`. Every target exists and is not ignored. All but one are already on the public `main`. The exception is `notebook/tests/colab_live.sh`, which is untracked, so its link gives 404 until the push. The shipped files (`data/`, `media/`, the helpers, `LICENSE`) stay plain |
| N6, author items | **partly done; the rest is left for the author** | The acknowledgments marker is gone from the notebook, and `test_todo_markers` asserts that "Acknowledgments" is absent. Still open: the e-mail (three places), the attendance sentence and the CI-run link |
| N7, small items | **partly fixed** | "How to run" now gives the live time from one run ("about 3 min"). The two E128 warnings in `nbfigs.py` (lines 298 and 330) remain. CI does not check them |

## Items of the jury-perspective review

| Item | Status | New text or evidence |
|---|---|---|
| Claim wording | **fixed** | "**A first-order masked Ascon S-box in which a zero-delay model finds no leak does leak at first order in transistor-level SPICE on sky130, before and after place and route**" |
| Cost on the first screen | **fixed** | "The fix costs 59 % more cell area, 39 % more energy per evaluation before layout (60 % after layout, clock tree included), 2 cycles of latency instead of 1 (+13 % in time) and no extra randomness (§7)." Every number is filled in from the data |
| D and DA share their maximum | **fixed** | Under the claim table: "D and DA end at the same max\|t\| (3.08) at the same sample (2.175 ns, in the first cycle's clock-fall region). The likely source is circuitry the two variants share, so the two values are probably one observation, not two (§4.5)." The same point is made in the Figure 1 caption, under the results table of `README.md`, and in the submission README |
| Abstract: what Ascon is | **fixed** | "Ascon is the lightweight cipher that NIST standardized for constrained devices (SP 800-232)." |
| Abstract: the straw man | **fixed** | "A standard digital flow checks a masked netlist only in zero-delay (RTL or functional gate-level) simulation, which cannot see glitches; glitch-aware probing checkers [6-8] exist but are not part of that flow." (See nit 3.) |
| Abstract: where the numbers come from | **fixed** | "Every result number in this text is read from a committed file of the project repository (the result files, the registrations, the reviews and, for the clock tree's insertion delay, `layout/README.md`). The run times in "How to run" and the ngspice-36 comparison in the version line are wall-clock and live-path measurements, not results." |
| Tool versions | **fixed** | "**Versions.** ngspice-42 for every SPICE campaign; live mode installs Ubuntu 22.04's ngspice-36 from apt, which matched the ngspice-42 reference within 5e-5 µA ... sky130A at open_pdks `0fe599b2...`, installed with ciel 3.0.0. OpenLane v1 at commit `ff5509f`. Icarus Verilog 11 or 12. Python 3.10 to 3.12 with NumPy and Matplotlib." |
| Live-mode times from one run | **fixed** | "about 3 min: fetch 2 s; installs 38 s (apt 14 s, pip install ciel 3 s, PDK 20 s); then the notebook 139 s, of which the SPICE demo takes 93 s and the animation 40 s. Measured in one run in an Ubuntu 22.04 container with 2 CPUs". These match `runs/colab_live_final.out` (1.8 / 14.4 / 3.1 / 20.1 / 37.9 s; notebook wall time 139 s; cell 18 93.0 s, cell 25 39.5 s). The same log gives ngspice-36, a largest current difference of 5.0e-05 uA and max\|t\| 6.57 against the reference's 6.57. "typically similar" appears nowhere |
| §1: novelty of the design rule | **fixed** | "The design rule that comes out of it, DOM's register barrier after Ascon's input affine layer, follows from DOM's condition that the two inputs of each masked AND be independent [5] (§2.3); the contribution here is to show its consequence in transistor-level simulation, before and after layout, on an open PDK." |
| §3.3: how the probing check was validated | **fixed** | "Its unit tests (`model/tests/test_probing.py`) hold it to verdicts derived by hand: ... D fails at exactly the cross-domain terms (`m01`, `p01`, `m10`, `p10`) of $t_1$, $t_3$ and $t_4$, and DA fails nowhere; an independent re-implementation that parses the SPICE netlists finds the same failing nets in N, D and DA (`docs/reviews/sca-method.md`, check 1). It was not cross-checked against SILVER [7] or PROLEAD [8]." Checked against the tests: `test_barrier_leaves_only_dependent_and_inputs` asserts exactly those 12 nets for D, `test_affine_first_passes_both` asserts an empty set for DA, and `test_naive_fails_glitch_model_at_integration` asserts 39 nets for N. Check 1 of `sca-method.md` reports N 39, D 12 and DA 0, identical to `results/probing/*.json` |
| §4.2: the animation on Colab | **fixed** | The code cell adds `if 'google.colab' in sys.modules:` ... `display(Image(filename=GIF))`, and the text says "on Colab, where the image link above may not load, it also plays the animation". The saved outputs contain no `image/gif`, which `test_gif_plays_on_colab_only` asserts |
| §5 heading | **fixed** | "**D and DA: no first-order key recovery, and what that rules out.**" The contents row was changed to match |
| §7: area in gate equivalents; the utilisation target | **fixed** | "In gate equivalents (GE; one `sky130_fd_sc_hd__nand2_1` is 3.7536 µm²) ... 90 GE for U, 269 GE for N and 429 GE for D and DA. After place and route with a 40 % core-utilisation target (`FP_CORE_UTIL`) ...". 3.7536 µm² = 1.38 × 2.72 µm (`SIZE` in the PDK's `sky130_fd_sc_hd.lef`). 337.824 / 1009.718 / 1610.294 µm² from `cost.csv` give 90.0 / 269.0 / 429.0 GE |
| Disclosure statement | **fixed** | The same sentence appears once in each of four places: the notebook's closing cell, `README.md`, `docs/PR_BODY.md` and the generated submission README. In the last three it stands alone under its heading, with no bold label. A test in `notebook/test_notebook.py` and `tools/test_make_submission.py::test_readme` pin it |
| §3.6: how the reviews are described | **left for the author** | "Adversarial reviews ([`docs/reviews/`], one file each) tried to refute the results." is unchanged |

## Scans

| Scan | Result |
|---|---|
| Wording about how the work was produced | There are two hits, and neither is such a statement. Line 73 of `docs/KILL_TEST.md` is registered text, which must stay byte-identical. Line 177 of `docs/reviews/repro-code.md` lists the search terms of a privacy scan (the account name among them). Neither is attribution wording. The scrubbed reviews (`repro-code.md`, `stage3-key-recovery.md`, `stage3-layout-pex.md`, `stage3b-wording.md`, `stage4-postlayout.md`) keep every technical finding, number and verdict; their diffs change only process wording |
| `TODO` markers | Outside `docs/reviews/` two markers remain. The e-mail marker is in the notebook's author table, in `make_notebook.py`, in the submission README template of `tools/make_submission.py` and in `docs/PR_BODY.md`. The CI-run-link marker is in `docs/PR_BODY.md`. Other hits only describe the markers: `notebook/README.md`, the header comment of `docs/PR_BODY.md`, and the two tests that pin the markers. Inside `docs/reviews/` markers appear only as dated history. There is no FIXME or XXX outside base64 image data |
| Host paths, e-mail addresses, names | `/home/` and `/media/` appear only in three places: the NIST reference URL (`csrc.nist.gov/csrc/media/...`), the regex on line 78 of `tools/test_make_submission.py`, and the list of search terms on line 177 of `repro-code.md`. There is no e-mail address, account name or host name |
| Python bytecode | None among the tracked files or the untracked files that are not ignored. None in the build `runs/submission/ISSCC27/submitted_notebooks/ascon_glitch_leakage/`. After step 4 of the check there is none in the clone's copy either |
| SPDX | Every new file has the line. `README.md`, `docs/KILL_TEST.md` and `docs/POSTLAYOUT.md` have none, as at HEAD; the last two hold registered text |

## Re-runs

| # | Check | Result |
|---|---|---|
| 1 | Notebook unit tests on the host (numpy only, git present) | 42 OK, 1 skipped (figures). `test_repository_links` ran its `git check-ignore` branch and passed |
| 2 | Unit tests in `cac-sca` (`--cpus 2`, numpy 1.26.4, matplotlib 3.6.3, PDK mounted) | notebook 44 OK. tools 8 OK. model/tests 39 OK (1 skipped: needs `$ASCON_REF_DIR`). analysis 44 OK. layout 28 OK. sim 8 OK |
| 3 | `CPUS=2 bash notebook/tests/ci_container.sh` (python:3.10-slim, numpy 2.2.6, matplotlib 3.10.9) | flake8 PASS, has colab-badge PASS, colab-badge is sscs-ose PASS. `pytest --nbmake`: 2 passed in 8.21 s (the main notebook in 6.47 s, `ci_smoke.ipynb` in 1.73 s) |
| 4 | `CPUS=2 bash tools/check_submission.sh` | Exit 0. The build has 45 files (8 at the top level, 33 in `data/`, 4 in `media/`), 4.43 MB. Upstream `main` is at f9370cc. The commands as written exit 1 / 2 / 2 / 4 (no globstar, as for every entry). With globstar they exit 0 / 0 / 0 / 0, and nbmake passes (1 passed in 6.49 s). Hygiene: bytecode deleted from the clone's copy; the clone's copy equals the build; only the folder was added; no host paths or e-mail addresses |
| 5 | Saved outputs of `notebook/ascon_glitch_leakage.ipynb` | 68 cells, 25 of them code, executed in order (counts 1-25). There is no error output, no stderr stream, no `image/gif` and no absolute path. The mode line reads "cached", Python 3.10.21, numpy 2.2.6, matplotlib 3.10.9 |
| 6 | `notebook/data/MANIFEST.csv` | Every SHA-256 matches its file |
| 7 | Registered text | `docs/KILL_TEST.md` lines 1-111, which include the Amendments (the Results start on line 112): sha256 `2f66ec53…` at b4a1159, at HEAD and in the working tree. The Results section changes only on lines 181 and 350 ("the author's", "the author decided"). `docs/POSTLAYOUT.md`, first 3,106 bytes: `bfae37cf…` at 36a8a13, at HEAD and in the working tree |

Not re-run: actionlint on `.github/workflows/ci.yml`, and the live path (`colab_live.sh`). For the live path, the recorded
run in `runs/colab_live_final` was checked against the quoted times.

## Numbers against `results/`

Every value below matches its source. Where a surface quotes the value, it quotes the same number: the claim screen
and abstract, `README.md`, `docs/PR_BODY.md`, and the submission README as built today.

| Quantity | Source | Value |
|---|---|---|
| Zero-delay model, worst of three weightings | `kill_test/summary.json` | N 1.08, D 2.11, DA 2.71 |
| Timing-aware model | same | N 12.1 (cap-weighted), D 15.2 cap-weighted and 16.7 worst, DA 2.96 |
| SPICE | same | N 13.23 at 9,998 (above 4.5 from 1,550, peak 0.945 ns). D 3.08 and DA 3.08 at 19,997 (at most 3.622 and 3.605). DA second order 21.475 |
| Controls | same | U 37.4 at 1,998 (27.7 / 38.4). Masks off 27.5 at 998 (19.2 / 28.1). Random vs random 1.87 at 9,998 (0.60 / 3.12) |
| D and DA maxima | `kill_test/tcurve_{D,DA}_tvla.csv` | both at 2.175 ns, -3.0797 and -3.0798. They differ by at most 0.0036 within 30 ps |
| Probing | `probing/*.json` | 39 of 103, 12 of 133, 0 of 133 |
| Post-layout | `pex/summary_postlayout.json` | N 8.192 at 4,998 (8.074 before, same rows), above 4.5 from 1,902; DA 3.363 at 9,997 (3.347); PL3 0.388; shift 0.69 ns; DA second order 14.96 to 22.29 |
| Detectable fraction | `kill_test` / `pex` summaries | 0.24 before layout, 0.39 after |
| Key recovery | `key_recovery/summary.json` | N at 765 traces per key: per-key-bit POIs SR 0.93 (GE 0.07), default SR 0.62 (GE 0.38). Second order: D SR 0.61 (GE 0.57), DA SR 0.78 (GE 0.27). Injected leak detected from 0.35 (D) and 0.5 (DA) |
| Cost before layout | `cost/cost.csv` | Area 1.59 × N. SPICE energy 1.39 × N (1.46 with CLK pins). 2 cycles against 1. 2.17 against 1.917 ns (1.13; D 1.28). 5 fresh bits |
| Cost after layout | `pex/summary_postlayout.json`, `layout/summary.json` | Energy 6,427 against 4,020 fJ (1.60). Core 3,942.5 against 2,454.9 µm² (1.61). Die 1.44 |
| RC bracket | `pex/rc_check.json` | 4,427 resistors (median 103 Ω, max 511 Ω) on 603 nets. Charge -0.24 % (at most 1.1 %), correlation 0.9998. Current 20 ps later. Last transition +61 ps (22-74), 1.83 to 1.89 ns |
| Negative controls | `layout/negative_controls.json` | LVS counts 96 / 109 and 128 / 141, unchanged under the share swap. Magic 10 and KLayout 3 markers, all on the two defects |

## Left for the author

1. The e-mail, in three places: the notebook's author table (edit `make_notebook.py`, then rebuild and re-execute),
   the README template in `tools/make_submission.py`, and `docs/PR_BODY.md`.
2. The push. Until then, the notebook's link to `notebook/tests/colab_live.sh` gives 404. Optionally, pin
   `REPO_REF` to a tag before the PR (N1). Then run `make_notebook.py`, re-execute and rebuild the folder.
3. After the push:
   - add the link to a green CI run in `docs/PR_BODY.md`;
   - open the "run now" link in real Colab and run all cells.
4. Confirm the attendance sentence in `docs/PR_BODY.md`.
5. Decide on the §3.6 sentence about the reviews.
6. Take the fork's copy from `runs/submission/ISSCC27/submitted_notebooks/ascon_glitch_leakage/`, as the header of
   `docs/PR_BODY.md` says.

## Optional nits

1. §3.3 now says that U fails the value model. The first sentence of the next cell was already there: "No variant
   fails the value model, so all three are secure in the zero-delay sense". It refers to the three masked variants
   of the table. "No masked variant" would avoid the apparent contradiction.
2. The submission README says "the timing-aware model predicts max\|t\| 15.2" without "(cap-weighted)".
   `README.md` and the notebook both give the weighting.
3. In the abstract, "glitch-aware probing checkers [6-8]" includes the robust probing model paper [6], which is a
   model, not a checker. "the glitch-extended probing model [6] and its checkers [7, 8]" would be exact.
4. The two E128 warnings in `nbfigs.py` (hygiene N7).
5. `final-hygiene.md` still lists B1 and B2 as open. It is a dated record, and this file records that both are fixed.
