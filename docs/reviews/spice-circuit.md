<!-- SPDX-License-Identifier: Apache-2.0 -->
# Review: circuit and SPICE correctness (kill test, run of 2026-09-24)

Reviewer lens: try to refute that N's measured leakage is a real glitch effect of the circuit. The checks
covered five things:
- the ngspice decks: models, supply, body ties, clock, input edges, setup and hold, warm-up, initial state;
- the simulator settings;
- the binning and the window alignment;
- the wire-cap estimate and the missing cell parasitics;
- what the named nets actually do in the waveforms, and whether the netlists match the intended DOM.

I changed no code, result or pre-registered text. The extra SPICE runs went to a scratch copy of the working
tree, outside the repository, and are not committed. Each one is described below well enough to redo it with
`sim/spice_campaign.py` and `analysis/spice_nodes.py`. Their wall times include the machine being suspended,
so they are not throughput data. I did not repeat the checks in `sca-method.md` or `repro-code.md`. Where
one of my runs overlaps theirs (tight tolerances), it is a second, larger sample of the same check, and the
two agree.

## Verdict

**The leak in N is a real effect of the circuit's timing. It is not an artifact of the simulator, the testbench,
the binning or the window placement, and it survives both parasitic brackets I tried.** Every deck element
checks out. The trace holds only the DUT's supply current, and the leak sits in the combinational evaluation
between 0.6 and 1.3 ns after the capturing edge, not at a clock edge or an input edge. The logic nets'
own VDD/2 switching events reproduce the leak's size, so the current is not coming from something invisible at
the net level. Every net that carries the leak is flagged by glitch-extended probing. The netlists match the
intended DOM structure, and D is missing no register.

**Three sentences of the Results need correcting (blocking for the doc, not for the finding):**
1. The mechanism is glitch pulses *and* data-dependent arrival times of transitions that do not glitch. In the
   narrow sense of "spurious pulses", glitches are only part of it (F2).
2. The stock sky130 cell netlists carry no diffusion or junction capacitance. The Limits paragraph does not
   say this, and it does not say how far the headline numbers move with the parasitics: wire cap x4 lowers
   the max|t| by about a fifth at equal traces and moves the peak about 0.44 ns later (F3).
3. The doc says level 2 "gets the timing wrong" (about 200 ps late). The lag does enter at the flip-flops'
   clock-to-Q, as the doc guesses. But there it is the pre-layout SPICE cells that are fast (no parasitics),
   not the Liberty data that is slow (F4).

Verdict: **issues**. These are wording and attribution fixes. There is no defect in the measurement.

## What I checked or re-ran

| # | Check | Result |
|---|---|---|
| 1 | Deck text (`make_deck`) and one deck per campaign | `.lib sky130.lib.spice tt`, stock `sky130_fd_sc_hd.spice`, `.temp 27`, `Vdut vpwr_dut 0 1.8`, VGND = node 0, `.options method=trap`, `.tran 10p ... 0 10p`, 2 fF on every output port. Trace = -i(Vdut): the DUT's VPWR only |
| 2 | Pin order and body ties of every instance, parsed against the stock `.subckt` lines | U 27, N 88, D 118, DA 118 instances: every one has VGND->VGND, VNB->VGND, VPB->VPWR, VPWR->VPWR. All 32/103/133/133 caps go to VGND. No other elements |
| 3 | Clock and input timing | Clock PULSE with its 50 % points at 2.0 + 4c ns, 100 ps edges, 50 % duty. Input PWL edges centred 3.0 ns after each rising edge, i.e. 1.0 ns before the capturing edge. Liberty `dfxtp_1` setup at these slews is 0.05-0.10 ns and hold is negative, so the margins are >= 0.9 ns (setup) and 3 ns (hold). Both PWL corners are written every cycle, so the breakpoints do not depend on the data |
| 4 | Output-register setup, from the node events of the campaign rows | N: last D-pin crossing 1.32 ns after the edge (2,000 rows), a 2.7 ns margin. D: 0.71 ns. Of 110,913 combinational crossings in N, 99.9 % are done by 1.21 ns and 23 fall after 1.3 ns. All four of my re-runs give registered outputs identical to the campaign's |
| 5 | Initial state and warm-up | No `.ic`/`uic`: a DC operating point at t = 0, then 4 replayed warm-up rows, and the first L+1 rows are dropped. Rows 1998-1999 of the x4-cap netlist were simulated twice: mid-deck, and as the 3rd-4th rows of a deck that started from random warm-up rows. The two differ by <= 4.3 uA against a 2,214 uA peak, so a row's current depends only on its real predecessors. Rows 1000-1059 re-simulated as their own deck (same start row as a campaign chunk) are **bit-identical** to the campaign (0.00 uA) |
| 6 | ngspice logs of U_tvla, U_cpa_k0, N_masksoff, N_tvla, N_rvr, D_tvla, DA_tvla, N_nodes, D_nodes (145 logs) | One benign line per log (`m=xx on .subckt line will override multiplier m hierarchy`, from the model library). No timestep-too-small, gmin or source stepping, or convergence messages |
| 7 | Window alignment, from the mean traces | The current before the edge is 0.1-0.6 uA. The clock-edge current starts 15 ps after the edge and peaks at 55 ps (U, N; D at its second edge 4.055 ns). So sample 20 is the capturing edge, as intended |
| 8 | Where N's leak sits (N_tvla, 9,998 traces) | max\|t\| is 1.94 at -0.2-0.15 ns (clock edge), 0.87 at 0.15-0.4 ns (flip-flop clock-to-Q, 0.18-0.29 ns in SPICE), 1.36 at 0.4-0.6 ns (first logic level), **13.23 at 0.6-1.3 ns**, 3.97 at 1.3-1.8 ns; clock fall 3.1, input edges 1.9 |
| 9 | **Tight tolerances**: rows 0-599 re-run with `--tmax 0.002 --options "reltol=1e-4 vntol=1e-7 abstol=1e-13 chgtol=1e-16"` (598 traces, 299 fixed) | Data-dependent correlation 0.99953; per-row correlation >= 0.99929. Charge error per row: mean 0.054 %, max 0.76 %, with no class dependence (t 1.08). The class-dependent error is <= 1.86 uA over 0.4-1.2 ns. Bump at 0.945 ns: 31.73 uA (tight) vs 31.69 uA (campaign); t 3.70 in both; bump waveform correlation 0.998 |
| 10 | **Wire cap x4**: every `Cw` in `dut.sp` multiplied by 4; rows 0-1,999 plus rows 1,996-5,999 (5,998 traces) | Leak persists: **7.20 vs 9.20** for the campaign on the same rows. First checkpoint above 4.5 at 2,500 vs 1,700 (my grid). Peak **1.385 ns vs 0.945 ns**; the t-curve correlates 0.89 with the campaign's at a +380 ps shift. Charge per window x1.29 |
| 11 | **Diffusion caps**: every instance replaced by a copy of its stock subckt with ad = as = W x 0.29 um and pd = ps = 2(W + 0.29 um) per FET; rows 0-1,999 (1,998 traces) | 4.78 at 1.025 ns vs the campaign's 5.17 at 0.955 ns on the same rows. Bump 23.9 vs 23.4 uA; t-curve correlation 0.90 at +100 ps; charge x1.18 |
| 12 | Structure of `dut.sp` (N, D, DA) | See F1. The only cells whose inputs span both share domains are the 10 m01/m10 ANDs. D registers all 20 partial products and all 10 linear terms before integration (55 flip-flops). DA differs only by the affine XORs in front of the input flip-flops |
| 13 | Crossings per net and row split into the settled toggle (parity) and glitch crossings (N_nodes, 1,998 traces) | Settled parity: max\|t\| 2.19 over all 88 nets, i.e. null, as zero-delay security requires. Glitch crossings: bs1_4 4.73, bs0_4 4.68, bs1_2 -4.52, ts0_0 4.44, ts0_2 4.08 |
| 14 | Arrival time of transitions that do not glitch (rows where the net crosses VDD/2 exactly once) | Mean time, fixed minus random: ts1_3 -49 ps (t -6.2), bs1_4 +51 ps (5.6), ts1_0 +48 ps (5.6), bs1_2 -45 ps (-5.1), ts0_2 +43 ps (5.0). For the doc's m01/m10 nets of t1 and t3, the 20 ps-binned count t comes from these single-transition rows (m01_1 8.5, m10_1 6.5, m10_3 5.7, m01_3 4.7) more than from their glitchy rows (3.6, 2.5, 2.0, 4.5). Every net in 13 and 14 is among the 39 that probing flags |
| 15 | Supply-current proxy from the SPICE crossings (each crossing weighted by its net's load C x VDD, 30 ps kernel) | See F2. All crossings: 6.47 (rising) / 5.67 (both edges) against SPICE's 5.17 on the same rows, shape correlation 0.55-0.65 |
| 16 | Raw waveforms of all nets, rows 1000-1059 (deck plus `.save` of every net, rawfile kept) | 618 full glitch pulses and 93 runt pulses (> 0.18 V from a rail, no VDD/2 crossing) in 0-1.8 ns. Worked example in F2 |
| 17 | Timing with and without diffusion caps (rows 1000-1019) | Clock-to-Q median 0.205 -> 0.235 ns; last combinational crossing median 0.545 -> 0.605 ns, max 1.175 -> 1.315 ns; glitch pulses 194 -> 193 |
| 18 | Glitch charge in N vs D (node runs) | Cross-domain m/p nets: 2.29 (N) vs 2.30 (D) pulses per row; all nets: 10.7 vs 4.0; glitch charge 28 % vs 8.7 % of switching charge. See F5 |
| 19 | Bandwidth (N_tvla, 9,998, noiseless) | Bins of 50/100/250/500/1,000 ps: 12.8 / 12.7 / 11.2 / 10.7 / 10.6. First-order RC low-pass at 5/2/1/0.5/0.25 GHz: 12.9 / 11.7 / 9.5 / 7.4 / 5.5 |

## Findings

### F1. Supported: the leak is a real circuit effect, not a simulator or testbench artifact

- **The deck is sound (checks 1-7).** The trace is only the DUT's VPWR current. The ideal supply and ground
  and the ground-only wire caps leave no path between the shares except the logic nets. Body ties and pin
  order are right in every instance. The data changes 1 ns before the capturing edge, far outside the
  flip-flop's setup and hold windows, and every register captures the right value. After the warm-up, a
  row's current depends only on its real predecessors: the same rows simulated from another deck start agree
  to 4.3 uA. The logs show no numerical trouble. The window is placed where the runner says: the capturing
  edge is at sample 20.
- **Not a numerical artifact (check 9).** At 5x smaller steps and tolerances 10x or more tighter, the bump
  under the leak is reproduced to 0.04 uA at its peak, and the class-dependent error stays below 1.9 uA against a
  bump of about 30 uA. This confirms `sca-method.md` check 16 on 2.5x as many rows. The largest per-bin
  differences (rms 13.7 uA) sit at the clock-edge transient, not in the leak region (rms 4.6 uA).
- **In the evaluation, after the capturing edge (check 8).** The input flip-flops switch between 0.18 and 0.29 ns.
  |t| stays below 2 at the edge, during clock-to-Q and at the first logic level. It is 13.2 between 0.6 and
  1.3 ns, where the DOM products, the integration XORs (ts), the S-box XORs (bs) and the output-layer XORs
  switch. The input edges (1.9) and the clock fall (3.1) do not carry it.
- **Explained by the logic nets' own switching (check 15).** A proxy built only from the SPICE nets' VDD/2
  crossings, weighted by their load capacitance, gives |t| 5.7-6.5 on the same 1,998 rows where the SPICE
  supply current gives 5.2, and it follows the same hump (shape correlation 0.55-0.65). So the leak does
  not come from anything invisible at the net level, such as internal cell nodes or static current.
- **The netlists are what the spec says (check 12).**
  - The affine layer is share-wise.
  - Each `~a & b` is `and2b(a0, b0)`, `and2b(a0, b1)`, `and2(a1, b1)` and `and2(a1, b0)`, so the NOT sits on
    share 0 only.
  - Each AND gets its own fresh r_i.
  - The integration and the output linear layer are share-wise, and `~x2` is on share 0 only.
  - In N, the only cells that mix domains are the 10 m01/m10 ANDs.
  - In D, all four products of every AND and all five linear terms of both shares go through a flip-flop
    before any integration XOR.

### F2. The mechanism: glitch pulses *and* data-dependent arrival times (blocking wording)

Glitch-extended probing, which flags all of these nets, treats both effects as one: an unregistered
cross-domain gate lets both shares of one variable shape *when and how often* nets switch. The SPICE nets
show both effects, and they carry comparable parts of the leak:

- **Glitch pulses.** How often a net glitches depends on the class: bs1_4 4.73, bs0_4 4.68, bs1_2 -4.52,
  ts0_0 4.44 at 1,998 traces (check 13). The settled toggle never does (max |t| 2.19 over 88 nets).
  - A typical case is row 1011 (random class). xs0_1 falls at 0.205 ns and xs1_1 rises at 0.275 ns, so
    as1_2 = xs1_2 ^ xs1_1 falls at 0.395 ns.
  - m01_1 = ~xs0_1 & as1_2 therefore pulses high from 0.365 to 0.545 ns. The pulse needs both shares of x1
    to switch.
  - The pulse travels through p01_1 (0.425/0.685 ns), ts0_1 (0.545/0.835 ns) and bs0_0 (0.585/0.605/1.055 ns)
    to ys0_1_d, which settles at 1.175 ns, next to the SPICE t-peak.
- **Arrival times with no glitch.** In rows where a net makes exactly one transition, *when* it switches
  depends on the class by up to +-50 ps on average: ts1_3 -49 ps (t -6.2), bs1_4 +51 ps, ts1_0 +48 ps
  (check 14).
  - The cross-domain ANDs that the doc names first (m01/m10 of t1 and t3) rarely glitch: m10_1 in 0.5 % of
    rows, m10_3 in 0.2 %, m01_1 in 3.7 %.
  - Their 20 ps-binned leak comes mainly from rows with a single transition (m01_1 8.5, m10_1 6.5, m10_3 5.7)
    and much less from their glitchy rows (3.6, 2.5, 2.0; m01_3 is split, 4.7 vs 4.5).
  - Which input triggers the transition, and so when it lands, depends on the class. For example, 33 % of
    m10_1's fixed-class transitions fall in its late mode (about 0.59 ns), against 43 % of the random ones.
- **Neither part reproduces the leak alone (check 15).**
  - Clean single transitions only: |t| 2.5-3.2, shape correlation 0.48.
  - Glitchy nets only: 5.3, shape 0.33-0.47.
  - Glitch crossings removed, settled toggle kept at its final crossing time: 5.1-5.4, shape 0.63.
  - The same with the toggle moved to its first crossing: 2.5-3.2.

**Fix:** wherever the doc or the notebook says N "leaks through glitches", add one sentence. For example: "The
leak comes from the timing of the unregistered cross-domain logic: glitch pulses and data-dependent arrival
times of transitions that do not glitch, both of which the glitch-extended probing model captures and the
zero-delay model misses." The title question can stay as registered.

### F3. The stock cells have no diffusion capacitance, and the headline numbers move with the parasitics (blocking wording)

Every FET in the stock `sky130_fd_sc_hd.spice` has `ad = as = pd = ps = 0` (the model wrapper's defaults). So
the transistor-level reference has no junction capacitance on any drain, source or internal stack node, and
no intra-cell wiring. The only capacitances are the device intrinsics and the generator's net caps (1 fF +
0.5 fF per fanout pin). The Limits paragraph mentions only the "estimated wire capacitance".

The two brackets I ran on the same rows as the campaign:

| Variant | Traces | max\|t\| (campaign, same rows) | Peak (ns after edge) | First checkpoint > 4.5 (campaign) |
|---|---|---|---|---|
| Wire cap x4 | 5,998 | 7.20 (9.20) | 1.385 (0.945) | 2,500 (1,700) |
| Diffusion caps added | 1,998 | 4.78 (5.17) | 1.025 (0.955) | 1,000 (1,700) |

The leak survives both, which strengthens F1. But the sizes that K3 reports do not. The numbers 13.2,
"above 4.5 from 1,550 traces" and "0.945 ns" all belong to the pre-layout estimate. With four times the wire
load, |t| drops by about a fifth at equal traces (about 1.6x the traces for the same t), and the peak moves
0.44 ns later. It then sits inside the "quiet end of evaluation, 1.3-1.8 ns" region, so that region's
boundaries only hold for the nominal caps.

**Fix:** in Limits, say that the cell netlists carry no diffusion or junction capacitance and no intra-cell
wiring, and quote the two rows above. Also say that the trace counts and times in K3 are for this pre-layout
estimate and will move after P&R.

### F4. Level 2's lag is at least as much the SPICE reference's (blocking wording)

Results, "How far the cheap models can be trusted": *"It gets the timing wrong: its events come about 200 ps
late (... its Liberty clock-to-Q delays are the likely cause)"*. The Liberty clock-to-Q of the input flip-flops
at their loads is 306-407 ps (`graph.json`, tt_025C). The Liberty tables come from the characterized cells.
In the pre-layout SPICE the same flip-flops switch in 181-292 ps (median 212 ps), because their netlists
have no parasitics (F3). Adding only the diffusion caps already raises the median to 235 ps and moves the N
t-peak 80 ps later. The clock-to-Q gap alone (about 100 ps) is half of the measured 190-250 ps lag, and
it comes from the SPICE reference being fast, not from Liberty being slow. Neither model is silicon.

**Fix:** "Level 2 and the pre-layout SPICE disagree by about 200 ps. A large part of it comes from the SPICE
cell netlists, which have no parasitics and switch faster than their Liberty characterization (clock-to-Q
0.18-0.29 ns vs 0.31-0.41 ns)." Also soften "It gets the timing wrong" to "its timing differs from SPICE's".
This does not change the shape mismatch that `sca-method.md` F5 reports.

### F5. Why D's supply current stays quiet (supports the doc; non-blocking)

The doc finds D's pre-barrier glitches real at the net level but not visible in the supply current, and
leaves the reason open. The node runs give a circuit-level reason:
- D's cross-domain m/p nets glitch exactly as often as N's: 2.30 vs 2.29 pulses per row.
- In D those nets drive only the barrier flip-flops, and the master latch of `dfxtp_1` is closed while CLK
  is high, 0-2 ns after the edge. So each glitch ends at one D pin.
- In N the same glitches travel through three more XOR levels (ts, bs, ys) with fanout. That gives 10.7 glitch
  pulses per row in total, against 4.0 in D, and 28 % of the switching charge against 8.7 %.
- The class t of the glitch charge is 3.1 for N at 1,998 traces and 0.7 for D at 997.

This supports the doc's wording ("real at the net level ... do not stand out in the total current") and
explains why the effect is small. It does not decide K4 at higher trace counts (see `sca-method.md` F2).

### F6. Non-blocking notes

- **The per-net localization sees only VDD/2 crossings.** In rows 1000-1059 there are 93 runt pulses
  (> 0.18 V, no mid-rail crossing) against 618 full glitch pulses, so about 13 % of the pulses are
  invisible to `spice_nodes.py`. They are still in the supply current. It is worth one sentence where
  K6 is described.
- **What "DUT supply current only" leaves out.** The gate charge of the 10-55 CLK pins comes from the ideal
  clock source, and that of the input flip-flops' D pins (and DA's affine-XOR inputs) comes from the ideal
  PWL sources. Neither is in `i(Vdut)`. The clock part does not depend on the data, and the D-pin part is
  share-wise, so no first-order result changes. On a chip, the clock tree and the input drivers would add
  data-independent and share-wise current to the same supply.
- **The leak does not depend on a 10 ps probe.** With 1 ns bins, max|t| is still 10.6. Through a 1 GHz
  first-order low-pass it is 9.5, and it only falls to 5.5 at 250 MHz (noiseless, 9,998 traces). The doc
  reports 100 ps bins and the charge per window; one line with the 1 ns / 1 GHz figures would anticipate
  the obvious objection.
- **Accuracy claim of the runner.** The runner's docstring gives a per-window charge error <= 0.14 %
  (tuned on mock DUTs). On N at the campaign settings, the worst of 598 rows is 0.76 % against the tight
  reference (mean 0.054 %). The error does not depend on the class, so no result changes, but the
  docstring's bound does not hold for N.
- **N shows both structural causes.** The first is the ANDs whose two inputs share a variable through the
  affine layer (t1 and t3: m01/m10 and their integration). That is the cause A1 names for D.
  The second is the integration without a register behind the other ANDs (t0 and t2: ts0_0 glitch count
  4.4, ts1_0 and ts0_2 arrival times, t 5.6 and 5.0), where no variable is shared. There, r is not the
  late signal: the r flip-flops switch together with the shares, before m01/m10. Instead, when a0 switches,
  p00 = ~a0 & b0 switches if b0 = 1 and p01 = (~a0 & b1) ^ r switches if b1 = 1. If both switch, their skew
  makes a glitch on ts0. Both switching needs b0 = b1 = 1, which is possible only when b = b0 ^ b1 = 0, so
  whether ts0 glitches depends on the unshared b. Both causes appear in the node data. The notebook can use
  this when it motivates the barrier (the second cause) and DA (the first).
