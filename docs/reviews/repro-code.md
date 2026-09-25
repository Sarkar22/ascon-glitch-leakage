<!-- SPDX-License-Identifier: Apache-2.0 -->
# Review: reproducibility and code (kill test, run of 2026-09-24)

Lens: can the results in `docs/KILL_TEST.md` be regenerated from the documented commands, does every number in
its Results section trace to `results/kill_test/`, was the pre-registered text left alone, is the file set clean
to commit, and is there a code bug that would change a result. Nothing in the repository was changed by this
review except this file. Every re-run was done in a scratch copy of the working tree, outside the repository and
without `.git`, `runs/`, `build/` and `results/`. The campaign's raw data in `runs/kt/` was only read. Paths below
are relative to the repository root.

Reviewed state: `docs/KILL_TEST.md` as it stood at 19:17 local on 2026-09-24, right after the absolute path on
line 20 was replaced (sha256 `39c8dd25…`). This review supersedes the earlier `repro-code.md`
(10:35 the same day). The one blocking item in that review (B1, the absolute path) is now fixed.

**Verdict: issues, one blocking item, and it is wording only.** The results reproduce: regenerated netlists,
probing output and stimuli are byte-identical, and re-simulated SPICE chunks of U, N and D are bit-identical to
the campaign. Re-running the analysis gives a byte-identical `summary.json`, every CSV and every figure. I
checked each number in the Results section against the data. Three sentences state something the data
contradicts (B1 below). None of them changes a criterion or the GO/NO-GO reading. I found no code bug that
changes a reported number.

## What I re-ran

| Check | Result |
|---|---|
| `python3 gen/make_variants.py` | U 27 / N 88 / D 118 / DA 118 cells. `dut.v`, `dut.sp`, `ports.json` and `graph.json` of all four variants are byte-identical to `build/`. `dut.sp` hashes equal every campaign manifest's `dut_sp_sha256`. |
| `python3 tb/run_iverilog.py` | ALL PASS: 4 variants, each with and without `USE_POWER_PINS`, 0 mismatches. Generated vectors and outputs are byte-identical. The compiled `vvp.*` files differ only because they embed the absolute build path. |
| `python3 model/probing.py` | N 39, D 12, DA 0 glitch-extended failures. `results/probing/*.json` byte-identical. |
| `python3 -m unittest discover -s model/tests` | 39 OK (1 skipped). With `ASCON_REF_DIR` set: 39 OK, 0 skipped. |
| `bash sim/docker_run.sh python3 -m unittest discover -s sim -p 'test_*.py'` | 8 OK (includes a real ngspice run), 27 s. |
| `python3 -m unittest discover -s analysis -p 'test_*.py'` | 8 OK. |
| The nine stimulus commands of the Reproduce block (seeds 101, 110-113, 201-204) | Every `.npy` byte-identical to `runs/kt/stim/`, every `.meta.npz` array identical. Each manifest's `stimulus_sha256` matches its file. `stimulus.py` creates the missing `runs/kt/stim/` itself, so the block works on a fresh clone. |
| Protocol in the stimuli | Fixed class is only x = 0x0B. The random class takes all 32 values. Masks and r are uniform (32 values) in both classes. Masks-off has mask = r = 0 everywhere. Random-vs-random draws x at random in both classes. Class shares 0.50 / 0.51 / 0.50 / 0.53. |
| SPICE re-run, U, first chunk (`--chunk 91 --rows 91 --jobs 1 --threads 2`, U_tvla stimulus) | `traces.npy`, `charge.npy` and `outputs.npy` **bit-identical** to `runs/kt/U_tvla/chunks/c00000`; 40,498 timepoints in both. The deck is identical apart from the absolute path of `dut.sp`. |
| SPICE re-run, N, 500 rows (`--chunk 500 --rows 500`, `M_tvla.npy`) | `traces.npy`, `charge.npy` and `outputs.npy` **bit-identical** to `runs/kt/N_tvla/chunks/c00000`; 211,460 timepoints in both; same deck apart from the `dut.sp` path. End to end on the re-run: TVLA on its 498 traces gives max\|t\| 3.8946 at 0.945 ns (identical to the campaign's first 498), and 0 functional mismatches. 1,172 s (2.3 s per cycle, the machine otherwise idle). |
| SPICE re-run, D, 500 rows (`--chunk 500 --rows 500`, `M_tvla.npy`) | **Bit-identical** to `runs/kt/D_tvla/chunks/c00000` in `traces.npy`, `charge.npy` and `outputs.npy`, with 211,878 timepoints in both. This covers latency 2, with the 2-cycle windows and the seeded head and tail rows. TVLA on its 497 traces gives max\|t\| 2.1603, identical to the campaign's; 0 functional mismatches. 2,289 s (4.6 s per cycle). |
| `python3 analysis/kill_test.py` in the copy (regenerated `build/` and stimuli, campaign traces read-only) | `summary.json` **byte-identical** to the committed one, including the `generated` date, which only matches because the re-run fell on the same day. All 18 CSVs byte-identical. 82 s. |
| `python3 analysis/report.py` | Every line of the Campaigns, Regions, Noise, Models-vs-SPICE and CPA tables appears verbatim in the doc. The Criteria table is hand-written (N4). |
| `bash sim/docker_run.sh python3 analysis/plots.py` | All 11 PNGs **byte-identical** to `results/kill_test/fig/`. |

For a fixed chunking, the whole chain is deterministic to the bit: seeded stimulus, generator, deck, ngspice-42,
binning, analysis and figures. The chunk size is part of that: it moves absolute simulation times (the node
re-runs use chunk 100 against the campaign's 500 and differ by at most 4.5 uA). The Reproduce block gives the
chunk size of every campaign, and the queue log confirms those are the sizes used. `--jobs` and `--threads` do
not change the bits (U here, and the earlier review's N run at 1 and 2 threads). numpy is 1.26.4 on the host and
in the image, so the seeded warm-up and tail rows, drawn in docker by the runner and on the host by the models,
agree.

## Independent recomputation
- Plain-numpy Welch t on `runs/kt/<campaign>/traces.npy` and the stimulus labels, first L+1 rows dropped:

  | Campaign | max\|t\| | peak | 100 ps bins | charge |
  |---|---|---|---|---|
  | U_tvla | 37.426 | 0.235 ns | 27.961 | 23.962 |
  | N_masksoff | 27.502 | 0.235 ns | 21.885 | 15.986 |
  | N_rvr | 1.869 | 0.555 ns | 1.711 | 0.435 |
  | N_tvla | 13.230 | 0.945 ns | 12.727 | 3.233 |
  | D_tvla | 1.967 | 4.885 ns | 1.896 | 0.635 |
  | DA_tvla | 2.340 | 4.845 ns | 2.342 | 1.357 |

  These match `summary.json` to the last digit. N_tvla at 1,500 / 1,550 / 5,000 traces gives 4.424 / 4.550 / 8.108.
- CPA: plain Pearson on the SPICE traces, with the primary hypotheses from `model_hypotheses` and HW(S(x)) built
  independently. Ranks 1/3/4/2 (primary) and 2/2/1/1 (HW), with the same scores as `cpa.*.final_scores`.
- Row alignment. Shift the per-row level-1 charge against the SPICE charge by -1 / 0 / +1 rows. The correlation
  peaks at shift 0 for every variant: N 0.08 / **0.88** / 0.11, D 0.61 / **0.97** / 0.68, U 0.40 / **0.98** / 0.49.
  So the CPA failure is not an off-by-one.

## Numbers in the Results section vs the data
I extracted every numeric token in the Results section and matched it against `summary.json` at the printed
precision. The only tokens with no match are parameters (seeds, registered counts), the CPA deficits (which I
recomputed: 0.0164 / 0.0339 / 0.0001) and the "64 shapes" in B1. Checked by hand as well:
- the criteria table (K1-K6, C) and the GO/NO-GO paragraph;
- the 27.17 uA bump at 0.925 ns (`tcurve_N_tvla.csv`);
- the regions, the noise table (it quotes `stable_from`, as its caption says) and 8.1 at 5,000;
- level 2 on D (7.9; 1.37 at 100 ps);
- the localization nets: N's 7 nets; D's 5 nets with |t| 6.0 / 5.6 / 4.9 / 4.9 / 4.6; 38 level-2 nets on
  19,997 rows; flagged-net window 0.33-0.99 ns;
- the charge correlations (0.87-0.98 and 0.73-0.89) and the level-2 shifts (+190 to +250 ps);
- the wall clock: the queue log's job times sum to 23,447 s, and the jobs ran one after another from 02:42 to
  09:14.

The claim that the level-2 CPA already ranked keys 0 and 1 wrongly before any SPICE CPA trace existed has no
record in the repository. The implementation's working record does: a dry run at 02:52 local, while the first CPA
campaign started at 03:36, gave ranks 4 / 3 / 1 / 1.

## Pre-registered text
- The implementation's working record (not in the repository) has the first write of `docs/KILL_TEST.md` at
  00:00:16 local on 2026-09-24 (4,788 bytes) and the one edit that inserted the Amendments at 01:04:48. Its file history keeps the version before
  that edit and the version before the results were appended (08:21).
- Current lines 1-74 are identical to the first version, and lines 1-113 to the pre-results version, **except line
  20**. There, the absolute local path was replaced by `$ASCON_REF_DIR/model/ascon.py` at 19:17 today, and a dated
  "Edit log" line under the Results heading says so. No other pre-registered byte changed.
- The registered values are intact:
  - fixed vs random with `x_fixed = 0x0B` (line 55);
  - threshold 4.5 (lines 54, 67-71);
  - traces K1 <= 2,000, K3 <= 20,000, K2 at the SPICE count and at 100,000, C(a) 10,000, C(b) 1,000 (lines 67-71);
  - K5 20,000 and the A3 budget (lines 89, 104-107).

  The code matches: `X_FIXED = 0x0B` (`model/stimulus.py`), `THRESHOLD = 4.5` (`model/tvla.py`).
- Order of events: the earliest file in `runs/` is from 00:11. The amendments are from 01:04. The first campaign
  job started at 02:42 (`runs/kt/queue.log`).

## Blocking (text fixes before the commit)

**B1. Three sentences in the Results section contradict the data.** Each is a one-line fix. None changes a verdict.

1. *Line 213*: "a noiseless U trace depends only on three consecutive nonces, so it takes at most 64 shapes per
   key." This is false. In window r the output registers switch from S(x_{r-2}) to S(x_{r-1}), so the trace
   depends on four nonces, n_{r-2} to n_{r+1}.
   - Grouped by three nonces, U_cpa traces with the same key differ by up to 284-362 uA within a group, more than
     the largest per-sample std (154-171 uA).
   - Grouped by four nonces, they differ by only 13-24 uA.
   - The level-1 hypothesis is exactly constant over those four nonces.

   So there are 256 shapes per key, each seen 1-18 times in 1,998 traces. The conclusion itself still holds. I
   weighted the 256 shapes equally, which is the large-trace limit. The primary hypothesis then ranks the correct
   key **1 / 2 / 4 / 2** (against 1 / 3 / 4 / 2 at 1,998). More traces would still not pass K1's CPA part, but key
   1's rank does change.

   Suggested text: "a noiseless U trace is a function of four consecutive nonces (256 shapes per key); weighting
   them equally, i.e. the large-trace limit, the primary hypothesis ranks the keys 1 / 2 / 4 / 2, so more traces
   would not help."
2. *Line 192*: "Level 2 predicted a leak on the same rows: 7.9, above 4.5 from 831 traces on". The level-2 curve
   is above 4.5 at 831 but drops back to 4.38 at 954 and 4.31 at 1,000 (`maxt_vs_traces_D_tvla.csv`). It stays
   above only from 1,095 (`campaigns.D_tvla.level2.weighted.stable_from`). The doc uses "from ... on" everywhere
   else for "stays above". Write "first above 4.5 at 831 traces, above from 1,095 on".
3. *Line 283*: "D and DA at the A3 counts would have added about 8 h". Eight hours is the cost of the A3 counts
   *from scratch*. What remains is D +5,000 rows (about 4,700 s = 1.3 h) and DA +15,000 rows (about 14,700 s =
   4.1 h): about 5.4 h more. The implementation's run notes give these same figures. Write "would have needed about
   5.4 h more".

## Non-blocking

- **N1. The D and DA noise columns are one noise draw, not two.** `analyse_tvla` seeds the noise with
  `1000 + 10 f` for every campaign. D and DA have the same labels and shape. Where noise dominates, t does not
  depend on the noise scale. So both columns show exactly 4.0 / 3.4 / 3.5, and the level-2 noise gives
  3.808 / 3.506 for both at 1x / 2x. Say so under the Noise table, or seed per campaign. This does not affect pass/fail.
- **N2. `kill_test.py` does not check that its inputs are the ones SPICE saw.** It reads `build/<V>/graph.json`
  and `runs/kt/stim/*.npy` without comparing them with the manifest's `dut_sp_sha256` and `stimulus_sha256`. Today
  every hash matches (I checked all 10 campaigns). But if someone regenerates `build/` or a stimulus after a
  generator change, the models and labels would silently stop matching the SPICE traces. A two-line assert in
  `load_campaign` would close this.
- **N3. Latency-2 peak times.** The tables give D 4.885 and DA 4.845 ns "after the edge". These times are
  measured from the first capturing edge, so they are 0.885 and 0.845 ns after the second edge. The
  `kill_test.py` docstring says so; the doc does not. (Unchanged from the earlier review.)
- **N4. "The tables are printed by `analysis/report.py`" (line 121).** That holds for five tables. The Criteria
  table is hand-written, in a different layout from `report.py`'s. Its numbers are right. (Unchanged.)
- **N5. `setup.spice_params` in `summary.json`** comes from the last manifest read (U_cpa_k3, `chunk` 91). N, D
  and DA used chunk 500. No number is affected. (Unchanged.)
- **N6. `spice_wall_clock_s`** comes from `runs/kt/queue.log`, which is written by the git-ignored
  `runs/kt/runq.sh`. It cannot be regenerated from the documented commands. It is informational only.
  (Unchanged.)
- **N7. `criteria()` makes GO also require C.** The registered rule is "K1, K2 and K3". This has no effect here.
  (Unchanged.)
- **N8. Resuming depends on the checkout path.** A chunk's reuse key hashes the deck text, and the deck contains
  the absolute paths of the PDK and `dut.sp`. So extending D or DA (`--rows 10000` / `20000`) re-uses the
  finished chunks only when run from the same checkout path, which is the case on this machine. From another
  path, every chunk is re-simulated. Worth one sentence next to the extension commands.
- **N9. Header date.** Line 3 says "Pre-registered on 2026-09-23", but the file was first written 16 s after
  local midnight, on 2026-09-24. It predates every trace either way. The line is pre-registered, so leave it and
  mention it in the edit log if you want the record exact.
- **N10. SPDX and pinning.** `docker/Dockerfile` has no SPDX line and installs unpinned `apt` packages. The
  manifests record `ngspice-42`, which is what matters for the traces. `docs/KILL_TEST.md` has no SPDX comment,
  while `gen/README.md` and the review files do.
- **N11. Tests.** The analysis test `test_rows_match_spice_rows` checks that `model_rows` does not depend on the
  run length. It does not check alignment with SPICE; the evidence for that is the shift test above. No test
  covers chunk-size dependence (the evidence there is the node re-run).
- **N12. Correction to the earlier review's N10.** The `spice_nodes.py` resume crash it described cannot
  happen. `events.npz` is written before the raw file is deleted, so a chunk never has `done.json` and a
  deleted raw file without also having its events. A crash *during* `np.savez` would leave a partial
  `events.npz`, which a resume would accept. That is minor.

## Commit hygiene
- Candidates: 96 untracked files, 3.09 MB in total, including the three review files. The largest are three per-net CSVs (240 kB each) and the PNGs
  (100-175 kB). Nothing large lies outside `runs/`. `.gitignore` covers `build/`, `runs/`, `results/raw/`,
  `*.npz`, `*.raw` and `__pycache__/`.
- I scanned all candidate files for `/home/`, `/media/`, the user name, the host name, the data-disk and
  paper-directory names, e-mail patterns and scratch paths: no hits. The line-20 path is gone. The PNGs carry only
  the "Software: Matplotlib" tag. `summary.json` holds relative run paths and the public PDK commit hash.
- Every `.py`, `.sh`, `.v` and `.sp` file carries the SPDX line (except the Dockerfile, N10).
