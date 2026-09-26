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
