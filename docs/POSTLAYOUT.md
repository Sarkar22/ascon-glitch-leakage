# Post-layout TVLA: registration

Registered 2026-09-25 at about 20:05, while the post-layout campaigns were running: N_pex had 12 of 40 chunks done
(1,500 rows) and DA_pex had not started. The criteria below are not to be edited after the campaigns finish; results
are appended in the "Results" section.

## Disclosed looks at interim data
The queue's progress view (`layout/pex_status.py`) printed a first-order max|t| for N_pex three times before this
registration: 2.55 at 373 traces, 3.00 at 748 and 4.30 at 1,498. DA_pex has not been looked at. The trace counts
below are fixed and do not depend on any interim value, so these looks cannot change when a campaign stops. From
now on the progress view is used without its t-statistic (`--show-t` is off by default) until a campaign is complete.

## Data
- Netlists: `build/N_pex` and `build/DA_pex`, Magic extraction of the DRC/LVS-clean OpenLane layouts (transistors
  with layout W/L and diffusion geometry, all capacitance to substrate and between nets, no resistance). Clock tree,
  taps and decaps are included and draw from the DUT supply. Details and the review: `layout/README.md`,
  `docs/reviews/stage3-layout-pex.md`.
- Stimulus: `runs/kt/stim/M_tvla.npy`, rows 0 to N-1: the same rows as the pre-layout N, D and DA campaigns.
- SPICE: ngspice-42, sky130 `tt`, 27 C, 1.8 V, 4 ns clock, KLU solver (checked against the default solver on 120
  rows: charge within 1.5e-4, data-dependent waveform correlation 0.9999997), 10 ps bins.
- Fixed trace counts: **N_pex 5,000 rows, DA_pex 10,000 rows.** No early stop and no extension under this
  registration.

## Test
Exactly the kill test's first-order TVLA (`analysis/kill_test.py` code path): fixed (x = 0x0B) vs random, Welch t per
10 ps sample over the whole window, first L+1 rows dropped, threshold |t| > 4.5. Reported alongside, not used for
pass/fail: 100 ps bins, charge per window, second order, added noise, and the pre-layout value on the same rows.

## Criteria
| Id | Criterion | Traces |
|---|---|---|
| PL1 | N_pex: max\|t\| > 4.5 (the leak survives place and route) | 5,000 rows |
| PL2 | DA_pex: max\|t\| < 4.5 (the fix survives place and route) | 10,000 rows |
| PL3 | Informational: where the t-peaks sit, by part of the cycle, and the smallest effect TVLA could detect for DA_pex expressed as a fraction of N_pex's measured effect | - |

Cycle parts for PL3 are shifted to the measured post-layout timing (`results/pex/node_timing_N.json`: clock-to-Q
median 0.56 ns, last logic transition up to 2.01 ns): edge and evaluation -0.2 to 2.1 ns, clock fall 2.1 to 2.9 ns,
input edges 2.9 to 3.8 ns after the capturing edge. For DA (latency 2) the same parts are used in each of its two
cycles. The evaluation tail and the clock fall overlap slightly after layout; any peak between 2.0 and 2.2 ns is
reported with that caveat.

If PL1 fails, the result is reported as measured: the leak then does not show within 5,000 post-layout traces, which
says nothing about higher counts.

## Results
(appended after both campaigns finish; each number must come from a file under `results/`)

### Run of 2026-09-25/26

_The registered text above is unchanged; this subsection was appended after both campaigns had finished._

All numbers below come from `results/pex/summary_postlayout.json`, which `analysis/postlayout.py` writes. The
exceptions are the layout figures, which come from `results/layout/summary.json`. Other result files:
- per-sample t-curves: `results/pex/tcurve_<V>_pex.csv`;
- max|t| against the number of traces: `results/pex/maxt_vs_traces_<V>_pex.csv`;
- figures: `results/pex/fig/tvla_pre_vs_post.png` and `maxt_vs_traces_pre_vs_post.png`
  (`analysis/plot_postlayout.py`).

**Interim looks and trace counts.** As disclosed in the registration, the progress view printed N_pex's first-order
max|t| three times before the criteria were written down: 2.55 at 373 traces, 3.00 at 748 and 4.30 at 1,498. DA_pex
was not looked at. The trace counts were fixed in the registration: N_pex 5,000 rows and DA_pex 10,000 rows. Both
campaigns ran to exactly these counts, with no early stop and no extension. The interim looks therefore could not
change where either campaign stopped.

**Setup, as registered.**
- The netlists are `build/N_pex/dut.sp` (sha256 `b1999858…`) and `build/DA_pex/dut.sp` (`8517658f…`). These are the
  current files, and they are the hashes in the campaign manifests.
- The stimulus is rows 0-4,999 and 0-9,999 of `runs/kt/stim/M_tvla.npy`. Its hash equals the pre-layout
  campaigns' hash.
- SPICE: ngspice-42, sky130 `tt`, 27 °C, 1.8 V, 4 ns clock, KLU, 10 ps bins. Each campaign ran as 6 processes in one
  container capped at 6 CPUs, in 125-row chunks (`runs/pex/queue.log`: N_pex 19:24-23:25, DA_pex 23:25-04:19).
- The first L+1 rows were dropped, leaving 4,998 traces for N_pex (2,511 fixed, 2,487 random) and 9,997 for DA_pex
  (5,009 fixed, 4,988 random).
- Function: every registered output matches the S-box (0 mismatches in 5,000 and 10,000 rows). Every output is also
  bit-identical to the pre-layout campaign's output for the same row (`campaigns.<V>_pex.function_check`).
- The test is the kill test's code path. `analysis/postlayout.py` calls `analysis/kill_test.py`'s own functions
  (`checkpoints`, `tvla_block`, `noise_sigma`, `curve_stats`, and `model/tvla.py` behind them). As a check, the same
  wrapper was run on the full pre-layout N_tvla (9,998 traces) and DA_tvla (19,997) campaigns. It reproduces their
  `spice` blocks in `results/kill_test/summary.json` exactly (`reproduces_kill_test.all_identical`: true).
- "First above 4.5" is read on the kill test's checkpoint grid for the given trace count: 41 log-spaced counts plus
  every multiple of 500. That is why pre-layout N on the first 4,998 traces crosses at 1,657 here, against 1,550 in
  the kill test at 9,998 traces.

**Criteria.** "Traces" is the count after the dropped rows.

| Id | Criterion | Measured | Traces | Result | Source (`summary_postlayout.json`) |
|---|---|---|---|---|---|
| PL1 | N_pex: max\|t\| > 4.5 (the leak survives place and route) | max\|t\| **8.19** at 1.655 ns after the edge; above 4.5 from 1,902 traces on and at every later checkpoint. Pre-layout on the same rows: 8.07 | 4,998 (5,000 rows, as registered) | **pass** | `criteria.PL1`, `campaigns.N_pex.spice` |
| PL2 | DA_pex: max\|t\| < 4.5 (the fix survives place and route) | max\|t\| **3.36**; never above 4.5 (at most 3.62 at any checkpoint). Pre-layout on the same rows: 3.35 | 9,997 (10,000 rows, as registered) | **pass** | `criteria.PL2`, `campaigns.DA_pex.spice` |
| PL3 | Where the t-peaks sit, by part of the cycle (post-layout parts: edge and evaluation -0.2 to 2.1 ns, clock fall 2.1 to 2.9, input edges 2.9 to 3.8, per cycle), and DA_pex's detectable effect as a fraction of N_pex's measured effect (informational) | **N_pex:** all 39 samples above 4.5 lie between 1.415 and 1.795 ns, in the edge-and-evaluation part (8.19). The clock fall reaches 1.13 and the input edges 1.13. **DA_pex:** no sample above 4.5. By part: cycle 1 2.42 / 3.33 / 3.36, cycle 2 2.46 / 0.89 / 1.04 (evaluation / clock fall / input edges). The largest \|t\|, 3.36, falls at 2.945 ns in cycle 1's input-edges part, 45 ps after the boundary. Neither peak lies in the 2.0-2.2 ns overlap. **Detectable effect:** at 9,997 traces TVLA reaches 4.5 on average for a standardized effect of 0.090, which is **0.39** of N_pex's measured 0.232 | - | informational | `criteria.PL3`, `campaigns.<V>_pex.peaks` |

**Pre-layout against post-layout on the same rows.** The same test is applied to the same rows. Pre-layout uses the
kill-test netlists, the default solver and ideal-clock traces. Post-layout uses the extracted netlists and KLU.

| | N pre | N post | DA pre | DA post |
|---|---|---|---|---|
| traces | 4,998 | 4,998 | 9,997 | 9,997 |
| max\|t\|, 10 ps bins | 8.07 | 8.19 | 3.35 | 3.36 |
| first above 4.5 / stays above from | 1,657 / 1,657 | 1,902 / 1,902 | never | never |
| t-peak (ns after the edge) | 0.945 | 1.655 | 2.415 | 2.945 |
| samples above 4.5, span (ns) | 33, 0.765-1.115 | 39, 1.415-1.795 | 0 | 0 |
| max\|t\|, 100 ps bins | 7.79 | 7.97 | 3.32 | 3.30 |
| \|t\| of the charge per window | 2.48 | 2.34 | 2.00 | 1.81 |
| second-order max\|t\| | 10.6 | 10.6 | 15.0 | 22.3 |
| largest mean fixed-minus-random current (uA, at ns) | 23.2 at 0.935 | 25.5 at 1.485 | -18.8 at 0.175 | -19.9 at 4.565 |
| noise unit, 1x (uA) | 340 | 346 | 504 | 510 |
| added noise 0.5x / 1x / 2x: final max\|t\| | 5.05 / 4.24 / 3.79 | 5.34 / 3.84 / 4.35 | 3.12 / 3.20 / 3.78 | 2.99 / 3.17 / 3.79 |
| added noise, stays above 4.5 from | 2,500 / - / - | 2,500 / - / - | - | - |
| mean charge per window (fC) | 954 | 2,240 | 2,640 | 7,145 |

Sources: `campaigns.<V>_pex.pre_layout_same_rows`, `campaigns.<V>_pex.spice`, `campaigns.<V>_pex.pre_vs_post` and
the two CSV files. The DA peak times count from the first edge; the second edge is at 4 ns.

**What this shows.**
- *N's leak survives place and route under C-only extraction at tt.* On the same 4,998 rows it is as strong as before
  layout: 8.19 against 8.07. It crosses 4.5 a little later, at 1,902 against 1,657 traces. The t-curve keeps its shape
  but moves 0.69 ns later: the correlation of the two signed curves is 0.88 at that shift and 0.16 without it
  (`pre_vs_post.t_curve`).
- *The shift is consistent with the node timing measured before the campaigns* (`results/pex/node_timing_N.json`).
  The clock tree adds about 0.33 ns of insertion delay. The flip-flops' median clock-to-Q grows from 0.20 to 0.56 ns,
  and the median last logic transition from 1.06 to 1.83 ns.
- *The whole post-layout leak lies inside the registered evaluation part.* Every sample above 4.5 falls between 1.415
  and 1.795 ns. The clock-fall and input-edge parts stay at 1.13.
- *The leak is still in the timing of the evaluation, not in the total charge.* The \|t\| of the charge per window is
  2.34, below 4.5, as it was before layout (2.48). In 100 ps bins the leak stays at 7.97.
- *Added noise gives the same picture before and after layout.* At 0.5x noise, max\|t\| stays above 4.5 from 2,500
  traces in both. At 1x noise neither stays above 4.5 within 4,998 traces: both end below it (3.84 post-layout, 4.24
  pre-layout). The only crossings are small-sample false alarms at 20-105 traces, as explained in the kill test. The kill
  test needed 6,273 traces for N at 1x, so this count cannot say more.
- *DA shows no first-order leak after layout within 9,997 traces* (3.36, at most 3.62 at any checkpoint). The same
  rows before layout give 3.35. This rules out only leaks at least 0.39 times as strong as N_pex's measured effect.
  DA_pex has half the traces of the pre-layout DA campaign, so its bound is weaker than the kill test's "about a
  quarter" (0.24 at 19,997 traces).
- *DA's largest \|t\| is not a peak in the TVLA sense.* It lies at the end of a flat stretch of the t-curve
  (about 2.6 to 2.95 ns). There the mean current has decayed from 761 to 7 uA, just before the next row's input
  edges. The pre-layout D/DA maximum of the kill test (2.175 ns, clock fall) sits on a similar stretch. No
  conclusion is drawn from its position.
- *DA's second-order t grows after layout,* from 15.0 to 22.3 on the same rows. That is expected for two-share,
  first-order masking and is informational only.
- *Charge.* The charge per window is 2.35x (N) and 2.71x (DA) the pre-layout value on the same rows. The per-row
  charges correlate at 0.988 (N) and 0.987 (DA) (`pre_vs_post`).

**Solver: KLU against Sparse.** The post-layout campaigns use KLU (`--options klu`); the pre-layout campaigns used
ngspice's default Sparse solver. The two solvers were run on the same post-layout netlists and the same 120 rows
(`solver_check_klu_vs_sparse`):

| | N | DA |
|---|---|---|
| largest per-bin difference (uA) | 4.95 | 11.0 |
| supply-current peak (uA) | 2,721 | 5,889 |
| largest relative difference of the charge per window | 1.31e-4 | 1.47e-4 |
| correlation of the data-dependent parts | 0.9999999 | 0.9999997 |

The solvers differ by the same amount whatever the data. So the choice of solver cannot create or hide a class
difference of the size TVLA measures here: a mean fixed-minus-random difference of up to 25.5 uA in N.

**The netlist text behind the sanity and benchmark files (review note N2).** Three result files were made from an
earlier text of the same Magic extraction: `results/pex/sanity_N.json`, `sanity_DA.json` and `bench.json`. The
earlier hashes are N `672d8809` and DA `f2984d22`. The campaigns ran the current text, N `b1999858` and DA `8517658f`,
which is what `build/<V>_pex/dut.sp` holds now. The two texts are element-for-element rewrites of one extraction
(review check 8). They now also agree in simulation for both variants. On rows 0-119, the campaign (current text,
125-row chunks) was compared with the KLU benchmark (earlier text, 20-row chunks) (`netlist_text_check`):

| | N | DA |
|---|---|---|
| largest per-bin difference (uA) | 4.2 | 4.5 |
| rms per-bin difference (uA) | 0.061 | 0.103 |
| correlation of the data-dependent parts | 0.9999999 | 0.9999997 |
| largest relative difference of the charge per window | 1.3e-4 | 1.1e-4 |

So the sanity numbers in `layout/README.md` (charge ratios, timing) and the solver benchmark describe the netlists
the campaigns ran, to within these differences.

**Capacitance: two views (review note N1).** The pre-layout wire-capacitance estimate was right for the routed
wiring. What the pre-layout model lacked is the cells' own parasitics (`capacitance_views`):
- OpenROAD's extraction of the routed wiring alone (OpenRCX SPEF, coupling included) gives 178.6 fF on N's 103 named
  logic nets. The pre-layout estimate was 178.0 fF. For DA the figures are 233.3 against 223.0 fF.
- Magic's flat extraction, which also contains the cells' own pin geometry and coupling to cell-internal nodes, gives
  391.7 fF on the same nets for N. That is 2.2x the estimate. For DA it gives 498.4 fF (2.2x).
- Per net, Magic's value is 1.3 to 10.3 times OpenRCX's for N (median 2.7), and 1.3 to 15.0 times for DA (median 2.6).
- The stock cell netlists that the pre-layout SPICE used carry none of these cell parasitics
  (`docs/reviews/spice-circuit.md`).

**Energy after layout (informational).** The energy per evaluation uses the cost table's definition: random-class
rows whose whole neighbourhood is random-class, charge x 1.8 V, window charge / L. On the same rows the values are
(`campaigns.<V>_pex.energy_per_evaluation`, `energy_DA_vs_N`):

| | pre-layout | post-layout |
|---|---|---|
| N (fJ, 305 rows) | 1,709 | 4,020 |
| DA (fJ, 179 rows) | 2,374 | 6,427 |
| DA / N | 1.39 | 1.60 |

After layout the supply current also includes what the pre-layout current left out:
- the clock tree (N 3, DA 5 `clkbuf_16`);
- the flip-flops' CLK pins;
- the cells' own parasitics.

So DA's relative cost rises from +39 % to +60 %. From `results/layout/summary.json`, DA's core area is 3,942 µm²
against N's 2,455 µm² (1.61x), and its die is 6,347 µm² against 4,412 µm² (1.44x). Both floorplans use 40 % core
utilisation; the placement utilisation is 43.4 % for DA and 44.2 % for N.

**SPICE cost.** N_pex took 14,431 s of wall clock and DA_pex 17,637 s, 6 processes each (`spice_wall_clock`). N_pex's
time includes a period when the host was suspended: one chunk took 9,422 s, against a median of 843 s. DA_pex's
chunks took 1,286 s (median).

**Limits of these numbers.**
- The extraction is C-only: no wire, via or power-grid resistance.
- One corner: tt at 27 °C.
- One layout per variant, from a single placement seed.
- The supply is an ideal 1.8 V source at the block's power pins, and the clock and inputs come from ideal sources at
  the block's pins. So there is no package, no power-grid IR drop and no on-chip decoupling effect.
- The clock tree now draws its current from the DUT supply, so the measured trace includes it. It is data-independent.
- The layouts are blocks, not a chip.
- The traces are noiseless.
- DA_pex has half the pre-layout DA's trace count.

The claim these results support is: *under transistor-level simulation of the extracted (C-only) layouts on sky130
tt, N's first-order leak survives place and route (max|t| 8.19 at 4,998 traces, above 4.5 from 1,902 on), and DA
shows no first-order leak within 9,997 traces, which rules out only leaks at least 0.39 times as strong as N_pex's
measured effect.* It is not a statement about silicon.

**Reproduce** (from the repository root; here the two campaigns took 8.9 h of wall clock on 6 CPUs, including the
suspend):
```
nohup setsid bash runs/pex/queue.sh > runs/pex/queue.out 2>&1 &      # N_pex 5,000 rows, then DA_pex 10,000 rows
python3 analysis/postlayout.py
bash sim/docker_run.sh python3 analysis/plot_postlayout.py
python3 -m unittest analysis/test_postlayout.py
```
`runs/pex/queue.sh` is git-ignored. It is equivalent to these two commands:
```
bash sim/docker_run.sh python3 sim/spice_campaign.py run --dut build/N_pex --stim runs/kt/stim/M_tvla.npy \
    --out runs/pex/N_pex_tvla --rows 5000 --chunk 125 --jobs 6 --threads 1 --options klu --save-outputs
bash sim/docker_run.sh python3 sim/spice_campaign.py run --dut build/DA_pex --stim runs/kt/stim/M_tvla.npy \
    --out runs/pex/DA_pex_tvla --rows 10000 --chunk 125 --jobs 6 --threads 1 --options klu --save-outputs
```
