# Kill test: does naive masking leak through glitches on sky130?

Pre-registered on 2026-09-23, before any trace was simulated. The criteria below are not to be edited after results
exist; results are appended in the "Results" section at the end.

## Question
A first-order masked Ascon S-box without a register barrier ("naive") is secure in the zero-delay (value / toggle)
model. Does a transistor-level ngspice simulation on sky130 show first-order leakage from glitches, and does the
DOM version with a register barrier remove it?

## Design under test: one Ascon S-box column (5 bits)
Bit order: `x = x0<<4 | x1<<3 | x2<<2 | x3<<1 | x4` (x0 is the MSB). Bitsliced S-box (NIST SP 800-232):
```
x0 ^= x4;  x4 ^= x3;  x2 ^= x1;
t_i = ~x_i & x_{i+1}          (i = 0..4, indices mod 5)
x_i ^= t_{i+1}                (i = 0..4)
x1 ^= x0;  x0 ^= x4;  x3 ^= x2;  x2 = ~x2;
```
Cross-check the 32-entry table against the author's own Ascon model
(the author's zero-shadow-aead checkout, `$ASCON_REF_DIR/model/ascon.py`, which passes the official KATs) and the RTL
(`.../zero-shadow-aead/rtl/ascon_xof.sv`, lines ~60-71).

### Variants
All variants register their inputs (and randomness) in flip-flops and register their outputs; the power window is
the clock cycle(s) after the input registers capture new values.

| Id | Name | Shares | Structure |
|---|---|---|---|
| U | unmasked | 1 | input regs -> S-box logic -> output regs |
| N | naive DOM (no register barrier) | 2 | input regs (x shares + 5 fresh random bits) -> combinational DOM-indep ANDs and integration -> output regs |
| D | DOM with register barrier | 2 | same, but the four DOM partial products of every AND (p00, p11, p01^r, p10^r) and the linear terms are registered before integration; 2-cycle latency |

2-share masking: linear operations share-wise; NOT only on share 0; each `~a & b` uses DOM-indep with one fresh
random bit r:
```
p00 = a0 b0      p01 = a0 b1 ^ r
p11 = a1 b1      p10 = a1 b0 ^ r
z0  = p00 ^ p01  z1  = p11 ^ p10         (a = ~x_i shares, b = x_{i+1} shares)
```
Netlists are generated structurally from explicit `sky130_fd_sc_hd` cells (no logic synthesis), so no optimizer can
merge shares. One generator emits the structural Verilog, the SPICE subcircuit and the Python gate graph used by the
toggle models, so all three models describe the same netlist.

## Models (the three fidelity levels)
1. **Zero-delay toggle model:** per cycle, settled value of every net; leakage = sum over nets of the Hamming distance to
   the previous cycle's settled value (unweighted, and weighted by an estimated net load capacitance).
2. **Timing-aware gate-level model** (optional in the kill test): event-driven simulation with per-cell delays (transport
   delay), counting every transition including glitches, same weighting.
3. **Transistor-level ngspice** (ground truth for this study): sky130 `tt` corner, 1.8 V, 27 C, the DUT's own supply
   current `i(VPWR)`, resampled to a uniform time grid. Pre-layout: per-net wire capacitance from a fixed estimate,
   documented. (Post-layout parasitics come later, after P&R.)

## Test protocol
- **TVLA, fixed vs random** (non-specific, first order, Welch t per time sample, threshold |t| > 4.5). Classes are
  interleaved randomly cycle by cycle. Fixed unshared input `x_fixed = 0x0B`. Shares and the fresh random bits are
  uniformly random in every cycle for both classes.
- **Controls:** (a) random-vs-random on N (both classes random: must stay below 4.5, false-positive check);
  (b) N with masks forced to zero (share1 = 0, r = 0): must leak strongly (sanity that the harness can see leakage).
- **CPA on U** (sanity that SPICE traces carry data): Ascon initialization context for one column: x0 = IV bit
  (constant), x1, x2 = key bits (secret, fixed; the round constant folds into the guess), x3, x4 = nonce bits (random,
  known). Hypothesis: Hamming weight of the S-box output; 4 key guesses.
- No added noise for the pass/fail decision; results with added Gaussian noise are reported alongside.

## Pass/fail criteria (GO needs K1, K2 and K3)
| Id | Criterion | Traces (cycles) |
|---|---|---|
| K1 | U in SPICE: max\|t\| > 4.5, and CPA ranks the correct key guess first | <= 2,000 |
| K2 | N and D in the zero-delay model: max\|t\| < 4.5 | at the full SPICE trace count, and at 100,000 |
| K3 | N in SPICE: max\|t\| > 4.5 at first order | <= 20,000 |
| K4 | D in SPICE: max\|t\| < 4.5 (informational: if D leaks, that is a finding to explain, not a failure) | same as K3 |
| C  | Controls (a) and (b) behave as stated | (a) 10,000, (b) 1,000 |

If K3 fails at 20,000 traces, the fallback is option B (number formats and data-driven power), decided with the user.

## Amendments (registered 2026-09-24, before any SPICE campaign trace was simulated)
These were added after the level-1/level-2 models and the exact probing checks had run (those are Python models, not
the SPICE ground truth), and before any SPICE campaign. The criteria above are unchanged; these add to them.

**A1: add variant DA.** The probing check and the level-2 model show that D as registered above is not robust to
glitches. Ascon's input affine layer (`x0 ^= x4; x4 ^= x3; x2 ^= x1`) runs between the input registers and the ANDs.
So the two inputs of the ANDs for t1, t3 and t4 share a variable, and their cross-domain terms see both shares of x1,
x3 or x4 before the barrier. The glitch-extended probing model flags exactly 12 nets in D (m01/p01/m10/p10 of t1, t3,
t4). The level-2 model gives max|t| 19.6 at 20,000 traces.

DA is D with the affine layer moved in front of the input registers. It has the same ports, stimulus and latency 2.
In a round-based core, this corresponds to merging the affine layer into the previous round's linear layer, before
the state register. DA passes both probing models (0 failing nets) and stays at max|t| 2.8 at level 2.
- K4 stays as registered for D (informational).
- **K5 (new):** DA in SPICE, max|t| < 4.5 at 20,000 traces.
- **K6 (new, informational):** the SPICE t-peaks for N and D occur on or after the switching of the nets that
  glitch-extended probing flags; report whether they match.

**A2: CPA hypothesis for K1.** The pre-registered HW(S(x)) hypothesis is a poor predictor here. With one column there
are only 4 inputs per key, and guess pairs correlate at |rho| up to 0.93. On the level-1 model it ranks the correct
key first for 1 of the 4 keys. So:
- K1's CPA part is run for **all four keys** (one U campaign of 2,000 traces per key).
- Primary hypothesis: the level-1 zero-delay model's predicted cap-weighted toggle count for each (key guess, nonce).
  This is derived from the netlist only, never fitted to SPICE.
- The pre-registered HW(S(x)) hypothesis is reported alongside for all four keys.
- K1's CPA part passes if the primary hypothesis ranks the correct key first for all four keys.
- K1's TVLA part is unchanged.

**A3: trace budget.**
- N: in 5,000-trace steps, stopping once the leak is stable at two checkpoints, up to 20,000.
- D: at least 10,000 traces.
- DA: 20,000 traces.
- U: TVLA 2,000, plus CPA 4 x 2,000.
- Controls: as registered.

Measured ngspice cost per process: U 0.74, N 2.30, D/DA 4.2 s per cycle.

## Results
(appended after the runs; each number must come from a file under `results/`)

_Edit log: on 2026-09-24, after the runs, the only change to the pre-registered text was on line 20. An absolute local
path to the author's Ascon model was replaced by `$ASCON_REF_DIR` for privacy. No criterion or meaning changed._

### Run of 2026-09-24

_The numbers in this subsection are for the first run (D and DA at 4,997 traces) and are preserved in
`results/kill_test/summary_run1.json`. `summary.json`, the CSVs and the figures now hold the extended data of
2026-09-25 (next subsection)._

All numbers below come from `results/kill_test/summary.json` (written by `analysis/kill_test.py`); the tables are
printed by `analysis/report.py` from that file, except the Criteria table, which is hand-written from it. Per-sample t curves: `results/kill_test/tcurve_<campaign>.csv`;
max|t| against the number of traces: `results/kill_test/maxt_vs_traces_<campaign>.csv`; CPA ranks:
`results/kill_test/cpa_rank_vs_traces.csv`; per-net t of the localization runs:
`results/kill_test/pernet_t_<V>_<source>.csv`; figures: `results/kill_test/fig/`.

**Setup.**
- Netlists from `gen/make_variants.py`: U 27 cells (10 flip-flops), N 88 (25), D 118 (55), DA 118 (55). Before the
  campaigns the generator's checks and the runner's unit tests passed (iverilog on every variant, 39 model tests,
  8 runner tests; the analysis has 8 more in `analysis/test_analysis.py`). No integration fix was needed in either
  codebase.
- SPICE: `sim/spice_campaign.py` with its defaults: ngspice-42, sky130 `tt`, 27 C, 1.8 V, clock period 4 ns,
  trapezoidal integration, maximum step 10 ps, 10 ps bins, DUT supply current only, pre-layout wire caps. ngspice
  and PDK versions, file hashes and the netlist hashes are in `setup` of `summary.json`.
- Stimuli: `model/stimulus.py`, seeded: U TVLA 101, U CPA keys 0-3 110-113, N masks off 201, N random vs random 203,
  fixed vs random for N, D and DA 202 (one file, so the three variants see the same 20,000 input rows), level-1 run
  at 100,000 rows 204. Fixed input 0x0B, classes interleaved at random, fresh masks and random bits every row.
- Every campaign drops its first L+1 rows (L = latency), in SPICE and in the models alike, because the models
  start from the reset state. So "1,998 traces" means a 2,000-row campaign of U.
- Every SPICE row's registered output was compared with the S-box of its input (`--save-outputs`): 0 mismatches
  in every campaign.
- Models on the same rows: level 1 (zero-delay toggles) and level 2 (transport-delay event model, Liberty delays)
  from `model/`, on the SPICE runner's time grid, including the same tail rows.

**Criteria.** Values from `results/kill_test/summary.json` (key given in the last column; "traces" are after the
dropped first rows).

| Id | Criterion | Measured | Traces | Result | Source (`summary.json`) |
|---|---|---|---|---|---|
| K1 | U in SPICE: max\|t\| > 4.5, and CPA ranks the correct key first | TVLA: max\|t\| 37.4, above 4.5 from 20 traces on. CPA, primary hypothesis (A2), rank of the correct key for keys 0/1/2/3: **1 / 3 / 4 / 2**; HW(S(x)): 2 / 2 / 1 / 1 | TVLA 1,998; CPA 4 x 1,998 | TVLA pass, CPA **FAIL**, so **K1 FAIL** | `criteria.K1`, `campaigns.U_tvla`, `cpa` |
| K2 | N and D in the zero-delay model: max\|t\| < 4.5 | worst of the 3 weightings: N 1.08, D 1.21 at the SPICE trace counts; N 1.06, D 2.48 (DA 2.23) at 100,000 | 9,998 (N), 4,997 (D), 100,000 | **pass** | `criteria.K2` |
| K3 | N in SPICE: max\|t\| > 4.5 at first order | max\|t\| 13.2 at 0.945 ns after the edge; above 4.5 from 1,550 traces on (8.1 at 5,000; 13.2 at 9,998) | 9,998 | **pass** | `criteria.K3`, `campaigns.N_tvla.spice` |
| K4 | D in SPICE: max\|t\| < 4.5 (informational) | max\|t\| 1.97; never above 4.5 | 4,997 (A3 asks >= 10,000) | below 4.5 at this count | `criteria.K4` |
| K5 | DA in SPICE: max\|t\| < 4.5 at 20,000 (A1) | max\|t\| 2.34; never above 4.5 | 4,997 of 20,000 | below 4.5 so far; **incomplete** | `criteria.K5` |
| K6 | SPICE t-peaks of N and D on or after the switching of the flagged nets (informational) | N: peak at 0.945 ns; the flagged nets switch at 0.33-0.99 ns; the 7 nets whose own transitions leak are all flagged. D: no supply-current t-peak within 4,997 traces, but its flagged nets' own transitions do leak | node re-runs: N 1,998, D 997 | N **match**; D not applicable | `criteria.K6`, `localization` |
| C | (a) N random vs random < 4.5; (b) N with masks off leaks strongly | (a) max\|t\| 1.87 (at most 2.90 at any checkpoint); (b) max\|t\| 27.5, above 4.5 from 40 traces on | (a) 9,998; (b) 998 | **pass** | `criteria.C` |

Every campaign's registered outputs matched the S-box (0 mismatches). SPICE time in total: 23,447 s = 6.5 h of
wall clock (`spice_wall_clock_s`).

**GO / NO-GO.** By the letter of the pre-registered rule this is **NO-GO**: GO needs K1, K2 and K3, and K1 fails
on its CPA part. The registered question has two parts. The first, whether naive masking leaks through the timing
of its unregistered logic while the zero-delay model calls it secure, is answered **yes**. N is secure in the
zero-delay model (max|t| 1.08 on the same 9,998 rows, 1.06 at 100,000). In transistor-level SPICE it leaks at first
order: max|t| 13.2, above 4.5 from 1,550 traces on. The leak sits in the evaluation phase, about 0.95 ns after the
clock edge. The nets whose own transitions carry it are nets flagged by glitch-extended probing. Both controls
behave as stated. The second part, whether a register barrier removes the leak, is **still open**: D cannot answer
it (its barrier sits after the affine layer, A1, and its net-level leak is confirmed), and DA has 4,997 of the 20,000
traces K5 needs. At 4,997 traces, TVLA can only exclude a leak at least half as strong as N's; at 20,000, about a
quarter. The CPA failure does not show that the SPICE traces
lack data; U's TVLA reaches |t| 37 within 1,998 traces. It shows that a one-column CPA with two key bits and four
nonce values cannot separate the keys with these hypotheses. The key-independent activity (input registers,
input-port edges, flip-flop clock current) dominates each trace. The four guesses' level-1 hypotheses therefore
correlate at 0.97-0.99 with one another (`cpa.*.guess_hypothesis_corr_level1_model`), and the model's own
error decides the ranking. Amendment A2 named this risk. The level-2 model, run on the same stimulus before the
SPICE CPA traces existed, already ranked keys 0 and 1 wrongly. My recommendation is to go ahead with option A on
the strength of K2, K3, C and the localization. K1 stays reported as failed, and the CPA sanity check needs a
redesign (e.g. more key bits or several columns) before the notebook relies on it. The decision is the user's; the
fallback to option B written above is tied to K3, which passed.

**What the runs show.**
- *N's leak is concentrated in the timing of the evaluation; the total charge also depends on x, but more weakly.*
  Per 10 ps sample, N reaches max|t| 13.2. Per 100 ps it reaches 12.7. On the charge per window the fixed-vs-random
  |t| is only 3.2, but an ANOVA over x on the same charge is significant (permutation p < 5e-4;
  `docs/reviews/sca-method.md`). The leak survives a bandwidth-limited probe: a first-order 1 GHz low-pass gives
  max|t| 9.5 and 250 MHz gives 5.5 (noiseless, 9,998 traces; `docs/reviews/spice-circuit.md`). The fixed-minus-random mean current is a bump of up to 27 uA (at 0.925 ns)
  between 0.6 and 1.1 ns (`tcurve_N_tvla.csv`, `fig/tvla_N_tvla.png`). The clock-fall and input-edge parts of
  the cycle stay below 4.5 (3.1 and 1.9), and so does the quiet end of evaluation, 1.3-1.8 ns (3.97), so the leak
  is switching activity during evaluation. "Glitch" here is meant broadly: the leak comes from the timing of the
  unregistered cross-domain logic, both glitch pulses and data-dependent arrival times of transitions that do not
  glitch. The glitch-extended probing model captures both; the zero-delay model captures neither.
- *Localization (K6).* The SPICE re-run recorded every net's voltage (`analysis/spice_nodes.py`,
  `fig/localization_N.png`). The nets whose own transition counts depend on the class are m01_1, m10_1, ts1_1,
  m01_3, p01_3, m10_3 and ts1_3, and all of them are flagged by glitch-extended probing. The cross-domain products
  (m01/m10) leak first, at 0.57-0.69 ns. Their downstream integration nets (ts, bs) follow up to about 1 ns, which is
  where the supply-current t peaks. Level 2 on 19,997 rows gives the same picture: 38 nets leak and every one is
  flagged. Re-simulating the same rows with the node voltages saved reproduced the campaign's current, with
  correlation 1.000000.
- *D's leak is real at the net level but is not resolved in the supply current within 4,997 noiseless traces*
  (TVLA at this count only excludes effects at least half as strong as N's). Glitch-extended probing flags 12 nets of D. The SPICE node
  run confirms that 5 of them switch in a class-dependent way (m01_1 |t| 6.0 at 0.53 ns, m10_1 5.6, p10_1 4.9,
  m10_3 4.9, m01_3 4.6, with 997 traces). But the supply current stays at max|t| 1.97. Level 2 predicted a leak on
  the same rows: 7.9, first above 4.5 at 831 traces and above from 1,095 on, in the first cycle. That prediction exists only at 10 ps
  resolution; binned to 100 ps, level 2 gives 1.37 for D. The small pre-barrier glitches of D are real at the net
  level, but at this trace count they do not stand out in the total current. Whether they do at A3's 10,000 or
  beyond is open. At circuit level, D's cross-domain nets glitch as often as N's (2.30 vs 2.29 pulses per row), but
  the glitches stop at the barrier flip-flops' D pins while the master latch is closed; in N they run on through the
  integration and output logic (`docs/reviews/spice-circuit.md`). D's and DA's peak times in the tables are
  measured from the first edge: 0.885 and 0.845 ns after the second edge.
- *DA* stays at max|t| 2.34 (second order 9.3, as expected for first-order masking); level 2 agrees (2.97).
- *How far the cheap models can be trusted* (table "Models vs SPICE" below). Level 1 gets the energy right: per
  trace, its charge correlates with SPICE at 0.87-0.98, better than level 2 (0.73-0.89). But it misses the leak in
  N entirely. Level 2 flags N and names the right nets. It does not reproduce the leak's waveform, sign or timing,
  and its per-sample |t| is not a prediction of SPICE's |t|: the similar max|t| (12.1 vs 13.2) is a coincidence,
  and the two t-curves are uncorrelated at every shift. Level 2 and the pre-layout SPICE also disagree by about
  200 ps (best waveform shift +190 to +250 ps; N t-peak 1.455 vs 0.945 ns). A large part of that comes from the SPICE
  cell netlists, which have no parasitics and switch faster than their Liberty characterization (clock-to-Q
  0.18-0.29 ns in SPICE vs 0.31-0.41 ns in Liberty). It
  overstates D: at 10 ps resolution it flags a leak that neither SPICE nor its own 100 ps view shows. So level 2
  is a good screening tool that is pessimistic for D, and SPICE remains the reference.
- *Added noise* (table "Noise"): N stays detectable within 10,000 traces at 0.5x and 1x noise (stable from 2,470
  and 6,273 traces) but not at 2x. U stays detectable at all three levels. For D and DA the noisy max|t| of 3.4-4.0
  is the null distribution of 800 now-independent samples, still below 4.5. With noise, a single checkpoint below
  about 50 traces can touch 4.5 (D at 1x, `fig/noise.png`) and fall back; the table therefore gives the count
  from which max|t| stays above 4.5.
- *CPA details* (table "CPA", `fig/cpa_U.png`): on its own level-1 traces the primary hypothesis ranks every key
  first. On level-2 traces it ranks keys 0 and 1 wrongly; on SPICE traces keys 1, 2 and 3. Every guess reaches
  |rho| 0.88-0.98 on SPICE, and for the three failing keys the correct guess scores 0.0001-0.034 below the best
  wrong guess (`cpa.*.level1_model.final_scores`). So model error decides the ranking. More traces would not
  help: a noiseless U trace is a function of four consecutive nonces (256 shapes per key); weighting them equally,
  i.e. the large-trace limit, the primary hypothesis ranks the keys 1 / 2 / 4 / 2.

**Figures** (`results/kill_test/fig/`): `tvla_<campaign>.png` (mean current, fixed minus random, and t against
time for SPICE and level 2), `maxt_vs_traces.png` (all levels), `noise.png`, `cpa_U.png`, `localization_N.png`,
`localization_D.png` (supply-current t above, per-net t of the SPICE node re-run below).

**Campaigns** (level 1 and level 2 on the same rows as SPICE; "unw / cap / rise" = unweighted, cap-weighted,
rising-only weighting):

| Campaign | Traces | SPICE max\|t\| | first > 4.5 | peak (ns after edge) | level 2 max\|t\| (unw / cap / rise) | level 1 max\|t\| (unw / cap / rise) | function check |
|---|---|---|---|---|---|---|---|
| U_tvla | 1998 | 37.4 | 20 | 0.235 | 38.4 / 37.3 / 31.4 | 27.72 / 27.01 / 10.24 | 0 mismatches |
| N_masksoff | 998 | 27.5 | 40 | 0.235 | 28.1 / 26.8 / 24.1 | 19.17 / 19.16 / 7.67 | 0 mismatches |
| N_rvr | 9998 | 1.9 | - | 0.555 | 2.9 / 3.1 / 2.9 | 0.17 / 0.15 / 0.60 | 0 mismatches |
| N_tvla | 9998 | 13.2 | 1550 | 0.945 | 8.4 / 12.1 / 11.6 | 0.95 / 1.06 / 1.08 | 0 mismatches |
| D_tvla | 4997 | 2.0 | - | 4.885 | 7.1 / 7.9 / 8.9 | 1.20 / 1.21 / 0.56 | 0 mismatches |
| DA_tvla | 4997 | 2.3 | - | 4.845 | 3.0 / 3.0 / 3.4 | 1.42 / 1.62 / 0.99 | 0 mismatches |

**SPICE max|t| by part of the clock cycle** (ns after each capturing edge: edge and evaluation -0.2 to 1.8, clock
fall 1.8 to 2.8, input edges 2.8 to 3.8, and the quiet end of evaluation 1.3 to 1.8):

| Campaign | SPICE max\|t\| by part of the cycle | level 2 (cap-weighted) |
|---|---|---|
| U_tvla | edge_and_evaluation 37.4, clock_fall 25.3, input_edges 26.2, settled_1.3_to_1.8 11.8 | edge_and_evaluation 37.3, clock_fall 0.0, input_edges 23.2, settled_1.3_to_1.8 0.0 |
| N_masksoff | edge_and_evaluation 27.5, clock_fall 18.0, input_edges 18.8, settled_1.3_to_1.8 10.5 | edge_and_evaluation 26.8, clock_fall 0.0, input_edges 13.2, settled_1.3_to_1.8 11.2 |
| N_rvr | edge_and_evaluation 1.9, clock_fall 1.1, input_edges 1.4, settled_1.3_to_1.8 1.0 | edge_and_evaluation 3.1, clock_fall 0.0, input_edges 0.6, settled_1.3_to_1.8 2.6 |
| N_tvla | edge_and_evaluation 13.2, clock_fall 3.1, input_edges 1.9, settled_1.3_to_1.8 4.0 | edge_and_evaluation 12.1, clock_fall 0.0, input_edges 0.4, settled_1.3_to_1.8 12.1 |
| D_tvla | cycle1_edge_and_evaluation 1.5, cycle1_clock_fall 1.6, cycle1_input_edges 1.3, cycle1_settled_1.3_to_1.8 1.3, cycle2_edge_and_evaluation 2.0, cycle2_clock_fall 0.7, cycle2_input_edges 0.7, cycle2_settled_1.3_to_1.8 0.5 | cycle1_edge_and_evaluation 7.9, cycle1_clock_fall 0.0, cycle1_input_edges 0.2, cycle1_settled_1.3_to_1.8 0.0, cycle2_edge_and_evaluation 3.0, cycle2_clock_fall 0.0, cycle2_input_edges 0.3, cycle2_settled_1.3_to_1.8 0.0 |
| DA_tvla | cycle1_edge_and_evaluation 1.4, cycle1_clock_fall 1.7, cycle1_input_edges 1.9, cycle1_settled_1.3_to_1.8 1.3, cycle2_edge_and_evaluation 2.3, cycle2_clock_fall 1.1, cycle2_input_edges 1.2, cycle2_settled_1.3_to_1.8 0.9 | cycle1_edge_and_evaluation 2.3, cycle1_clock_fall 0.0, cycle1_input_edges 1.5, cycle1_settled_1.3_to_1.8 0.0, cycle2_edge_and_evaluation 3.0, cycle2_clock_fall 0.0, cycle2_input_edges 1.0, cycle2_settled_1.3_to_1.8 0.0 |

**Noise** (max|t| at the full trace count, and in brackets the count from which it stays above 4.5; noise std in
units of the largest per-sample std of the noiseless traces):

| Campaign | noise unit (uA) | no noise | 0.5x | 1x | 2x |
|---|---|---|---|---|---|
| U_tvla | 260.9 | 37.4 (20) | 26.6 (40) | 17.0 (56) | 9.5 (317) |
| N_masksoff | 251.4 | 27.5 (40) | 19.5 (48) | 12.2 (141) | 8.1 (209) |
| N_rvr | 316.1 | 1.9 (-) | 2.7 (-) | 3.0 (-) | 3.7 (-) |
| N_tvla | 341.3 | 13.2 (1550) | 7.6 (2470) | 5.6 (6273) | 3.9 (-) |
| D_tvla | 513.3 | 2.0 (-) | 4.0 (-) | 3.4 (-) | 3.5 (-) |
| DA_tvla | 507.3 | 2.3 (-) | 4.0 (-) | 3.4 (-) | 3.5 (-) |

**Models vs SPICE** (same rows; waveform correlation of the data-dependent parts at 100 ps resolution; a
positive shift means level-2 events come later):

| Campaign | corr. charge per trace, SPICE vs level 2 | vs level 1 | waveform corr. SPICE vs level 2, 100 ps (no shift) | level-2 shift (ps) | corr. at that shift | t-peak SPICE / level 2 (ns) |
|---|---|---|---|---|---|---|
| U_tvla | 0.894 | 0.982 | 0.388 | +190 | 0.672 | 0.235 / 0.325 |
| N_masksoff | 0.852 | 0.978 | 0.427 | +250 | 0.622 | 0.235 / 0.325 |
| N_rvr | 0.734 | 0.873 | 0.287 | +220 | 0.484 | 0.555 / 1.095 |
| N_tvla | 0.769 | 0.879 | 0.297 | +190 | 0.517 | 0.945 / 1.455 |
| D_tvla | 0.866 | 0.970 | 0.186 | +200 | 0.603 | 4.885 / 0.815 |
| DA_tvla | 0.894 | 0.955 | 0.189 | +200 | 0.612 | 4.845 / 4.835 |

**CPA on U** (final rank of the correct key at 1,998 traces; "signed" scores by the largest positive
correlation; model columns: the same CPA on the level-1 and level-2 traces of the same rows):

| Key | Traces | primary (level-1 model): rank, rank 1 from | HW(S(x)): rank | primary, signed | HW, signed | primary on level-1 / level-2 traces | HW on level-1 / level-2 traces | primary with noise 0.5x / 1x / 2x |
|---|---|---|---|---|---|---|---|---|
| 0 | 1998 | 1, 20 | 2 | 1 | 2 | 1 / 4 | 3 / 1 | 1 / 1 / 2 |
| 1 | 1998 | 3, - | 2 | 3 | 1 | 1 / 3 | 2 / 3 | 2 / 2 / 1 |
| 2 | 1998 | 4, - | 1 | 4 | 1 | 1 / 1 | 4 / 3 | 1 / 1 / 1 |
| 3 | 1998 | 2, - | 1 | 2 | 1 | 1 / 1 | 1 / 2 | 3 / 1 / 3 |


**Deviations from the registered protocol** (none changes a criterion):
1. Trace counts for D and DA. A3 asks for D >= 10,000 and DA 20,000. Both were run to 5,000 rows (4,997 traces
   after the dropped rows). The step had a budget of about 4 h of SPICE time; the measured throughput with 10
   processes was 2.0 simulated cycles/s for N and 1.0 for D and DA (the per-process costs in A3 do not scale to
   10 processes: this CPU is power-limited, and one D process slows from about 4 s to about 10 s per cycle).
   D and DA at the A3 counts would have needed about 5.4 h more; the task's rule was to reduce D first. D and DA ran on
   the same 5,000 input rows, so they are compared at equal trace counts. **K5 was therefore incomplete** (5,000 of
   20,000) in the first run, and K4 ran on half of A3's minimum. Both were completed on 2026-09-25 (see the
   extension subsection).
2. The N stop rule of A3 was applied: max|t| was above 4.5 at the 5,000 and the 10,000 checkpoints, so N stopped
   at 10,000.
3. The first L+1 rows of every campaign are dropped (see Setup).
4. A2's primary hypothesis says "for each (key guess, nonce)". It was implemented, before any SPICE CPA trace
   existed, as the level-1 cap-weighted toggle count of each row's window simulated with the guessed key and the
   known nonce sequence (so it also depends on the neighbouring nonces, which are known). Read literally, as one
   value per (guess, nonce) averaged over the neighbouring nonces, the four guesses' tables are affine images of
   each other, so every guess gets exactly the same correlation (summary.json `cpa.*.literal_guess_nonce_table`)
   and that reading cannot rank keys at all.
5. Pass/fail uses the runner's native 10 ps bins. The same test on 100 ps bins and on the charge per window is
   reported alongside.
6. Added noise: white Gaussian noise per 10 ps sample, standard deviation 0.5, 1 or 2 times the largest
   per-sample standard deviation of the noiseless traces (for N: 341 uA). Not used for pass/fail.

### Extension of 2026-09-25: A3 trace counts reached

DA was extended to 20,000 rows and D to 10,000 rows (`runs/kt/ext.sh`, same stimulus file `M_tvla.npy`, so the
first 5,000 rows are the ones above), with the SPICE container capped at 6 CPUs. `analysis/kill_test.py` was re-run;
all numbers below are from `results/kill_test/summary.json`. Every SPICE row's output still matched the S-box.

| Variant | Traces | SPICE max\|t\| (final) | max over all checkpoints | first > 4.5 | peak (ns after first edge) | 2nd order | charge per window \|t\| | SPICE, 1x noise | level 2 (worst weighting) | level 1 (worst weighting) |
|---|---|---|---|---|---|---|---|---|---|---|
| D | 9,997 | 3.35 | 3.69 | never | 2.405 | 13.1 | 1.21 | 3.20 | 12.2 | 2.26 |
| DA | 19,997 | 3.08 | 3.60 | never | 2.175 | 21.5 | 2.61 | 3.04 | 3.0 | 2.71 |

| Id | Measured | Traces | Result |
|---|---|---|---|
| K4 | D max\|t\| 3.35; never above 4.5 | 9,997 (A3 minimum met) | below 4.5 (informational) |
| K5 | DA max\|t\| 3.08; never above 4.5 | 19,997 of 20,000 | **pass, complete** |

**What this adds.**
- *The second part of the registered question is answered for DA.* With the register barrier placed after
  Ascon's affine layer (DA, amendment A1), the supply current shows no first-order leak within 19,997
  noiseless traces; TVLA at this count excludes a leak about a quarter as strong as N's or stronger. Second-order
  t is large (21.5), as expected for two-share (first-order)
  masking.
- *D (the registered DOM) stays below 4.5 at 9,997 traces* (3.35; at most
  3.69 at any checkpoint), although its net-level leak is confirmed and
  level 2 predicts 12.2
  on the same rows. D's leak therefore remains unresolved in the supply current at the A3 count; it is not shown to
  be absent. A further D run to 20,000 rows followed (addendum below).
- *Level 2 is pessimistic for D* at 10 ps resolution, which confirms the first run's reading.
- The GO/NO-GO statement above is unchanged: K1 fails on its CPA part, K2, K3, K5 and C pass, and the user decided
  to proceed with option A.

**Addendum (2026-09-25, exploratory, beyond A3): D at 20,000 rows.** The D run was continued to 20,000 rows on the
same stimulus; `analysis/kill_test.py` was re-run, so `summary.json` and the D files now hold 19,997
traces. SPICE max\|t\| 3.08 (at most 3.62 at any checkpoint; never above
4.5; 100 ps bins 3.00; charge per window 1.21; second order
19.0), while level 2 predicts 16.7 on the same rows. D's net-level leak therefore still does not
show in the supply current at 20,000 noiseless traces; at this count TVLA would detect a first-order effect about a
quarter as strong as N's. This is consistent with the circuit-level reading in `docs/reviews/spice-circuit.md`: D's
pre-barrier glitches end at the barrier flip-flops' D pins. It is not a proof that D is secure; the glitch-extended
probing model, which is conservative by design, still flags it.

**Limits of these numbers.** Pre-layout netlists with estimated wire capacitance. The stock sky130_fd_sc_hd SPICE
cells carry no diffusion or junction capacitance (every FET has ad = as = pd = ps = 0) and no intra-cell wiring, so
they switch faster than their Liberty data. The N result moves with these parasitics but survives both brackets the
SPICE review ran on the same rows (`docs/reviews/spice-circuit.md`): wire cap x4 gives max|t| 7.20 vs 9.20 (5,998
traces; peak 1.385 vs 0.945 ns; first above 4.5 at 2,500 vs 1,700), and adding diffusion caps gives 4.78 vs 5.17
(1,998 traces; peak 1.025 vs 0.955 ns). K3's trace counts and times belong to this pre-layout estimate and will move
after place and route. The measured current also leaves out the gate charge of the CLK pins (ideal clock, data
independent) and of the input D pins (ideal sources, share-wise), which changes no first-order result. Further: an
ideal 1.8 V supply for the
DUT, no package, power grid, decoupling, probe or measurement noise, one process corner and temperature. The
noiseless SPICE traces are deterministic functions of the inputs, so even the static leakage current depends on
the stored data (U reaches |t| 11.8 between 1.3 and 1.8 ns, after its evaluation has settled). In N that quiet end
of the evaluation part reaches |t| 3.97 at 9,998 traces, below 4.5; whether it is late switching or data-dependent
static current is not resolved here (D and DA: 1.34). The claim
these results support is "under transistor-level simulation of the pre-layout netlist on sky130 tt, N leaks at
first order within 1,550 traces, while D and DA show no first-order leak in the supply current within 4,997 traces
(which excludes only effects at least half as strong as N's)", not a statement about silicon.

**Reproduce** (from the repository root; SPICE and figures in the cac-sca image):
```
python3 gen/make_variants.py && python3 tb/run_iverilog.py && python3 model/probing.py
S=runs/kt/stim
python3 model/stimulus.py --dut build/U --mode tvla --n 2000 --seed 101 --out $S/U_tvla.npy
for k in 0 1 2 3; do python3 model/stimulus.py --dut build/U --mode cpa --n 2000 --seed $((110+k)) --key $k --iv 1 --out $S/U_cpa_k$k.npy; done
python3 model/stimulus.py --dut build/N --mode masks_off --n 1000 --seed 201 --out $S/N_masksoff.npy
python3 model/stimulus.py --dut build/N --mode tvla --n 20000 --seed 202 --out $S/M_tvla.npy
python3 model/stimulus.py --dut build/N --mode rvr --n 10000 --seed 203 --out $S/N_rvr.npy
python3 model/stimulus.py --dut build/N --mode tvla --n 100000 --seed 204 --out $S/M_tvla100k.npy
R="bash sim/docker_run.sh python3 sim/spice_campaign.py run --save-outputs --threads 2"
$R --dut build/U --stim $S/U_tvla.npy --out runs/kt/U_tvla --chunk 91 --jobs 11          # also U_cpa_k0..3
$R --dut build/N --stim $S/N_masksoff.npy --out runs/kt/N_masksoff --chunk 91 --jobs 11
$R --dut build/N --stim $S/M_tvla.npy --out runs/kt/N_tvla --chunk 500 --jobs 10 --rows 10000
$R --dut build/N --stim $S/N_rvr.npy --out runs/kt/N_rvr --chunk 500 --jobs 10
$R --dut build/DA --stim $S/M_tvla.npy --out runs/kt/DA_tvla --chunk 500 --jobs 10 --rows 5000   # --rows 20000 completes K5
$R --dut build/D --stim $S/M_tvla.npy --out runs/kt/D_tvla --chunk 500 --jobs 10 --rows 5000     # --rows 10000 meets A3
bash sim/docker_run.sh python3 analysis/spice_nodes.py --dut build/N --stim $S/M_tvla.npy --rows 2000 --chunk 100 --out runs/kt/N_nodes --jobs 10 --threads 2
bash sim/docker_run.sh python3 analysis/spice_nodes.py --dut build/D --stim $S/M_tvla.npy --rows 1000 --chunk 100 --out runs/kt/D_nodes --jobs 10 --threads 2
python3 analysis/kill_test.py && python3 analysis/report.py && bash sim/docker_run.sh python3 analysis/plots.py
```
Extending a campaign with a larger `--rows` reuses the finished chunks; re-running `analysis/kill_test.py`
then updates every number here.
