<!-- SPDX-License-Identifier: Apache-2.0 -->
# Review: layout, extraction and post-layout SPICE model (stage 3, 2026-09-25)

**Scope.** This review covers:
- `layout/`: the OpenLane configs, `run_flow.sh`, `run_pex.sh`, `run_klayout.sh`, `pex/extract.tcl`, `make_pex.py`,
  `validate_pex.py`, `node_timing.py`, `summarize.py`, `pex_status.py`, `bench_summary.py`, the tests and the README;
- the outputs in `results/layout/` and `results/pex/`;
- the generated models in `build/{N,DA,U}_pex/`;
- the OpenLane, Magic and KLayout run directories under `runs/pex/`;
- the running queue `runs/pex/queue.sh`.

None of these files is committed yet.

**Lens.** I tried to refute seven claims:
- the layouts implement exactly the generator's structural netlists, with nothing added beyond clock-tree buffers, taps,
  decaps and fill;
- DRC, LVS and antenna are clean;
- the extracted SPICE carries parasitic capacitance and the drawn diffusion geometry;
- its port order matches `ports.json`, and the unchanged runner uses it correctly;
- the post-layout outputs match the S-box;
- the queue uses the kill test's stimulus rows, stays within the 6-CPU cap and one heavy container, can be resumed, and
  is running;
- nothing that will be committed contains host paths or other personal data.

**What I changed.** Nothing in the repository except this file. I started no container and did not touch the queue, the
running campaign or `build/`. Every check below ran on the host, at low priority, with python3 and numpy, and read the
files in place. My check scripts are scratch files outside the repository. Each check is described well enough to redo.

## Verdict

**Sound. Every claim I tried to refute holds, and several hold more strongly than the report says.**

- **Transistor-level equivalence.** The post-layout netlists are the generator's circuits at transistor level, not
  only cell for cell. I expanded OpenLane's final gate-level netlist with the stock `sky130_fd_sc_hd` cell
  subcircuits and compared the result with `build/<V>_pex/dut.sp`. Every step matches:
  - transistor counts: N 1,578, DA 2,530 and U 616 in both;
  - the multisets of (model, W, L);
  - for each of the 107 / 139 / 36 named nets, the transistors attached to it, with their role, model, W and L;
  - a Weisfeiler-Lehman refinement of the whole transistor graph, including the unnamed nodes inside the cells. It
    gives 605 / 969 / 210 singleton classes and identical label multisets, so the two graphs are isomorphic with every
    named net in its place.
- **Signoff.** DRC, LVS, antenna and XOR are clean in the actual reports.
- **Function.** Every post-layout output matches the pre-layout campaign's output bit for bit: 120 rows each in the
  N and DA benchmarks, and the 750 rows the queue has finished so far. Every one also matches an independent S-box.
- **The queue.** Its decks are identical to decks rebuilt from `runs/kt/stim/M_tvla.npy`. Its finished chunks would be
  skipped on a resume. It is running as 6 ngspice processes in one container capped at `--cpus 6`.

Verdict: **sound**. The notes below are about wording, provenance and the analysis still to come, not about the model.

## What I checked or re-ran

| # | Check | Result |
|---|---|---|
| 1 | OpenLane completion and warnings, all three variants | `[SUCCESS]: Flow complete`. The only warnings: KLayout DRC tech script missing (the flow's own KLayout DRC skipped), blackboxed tap/fill/decap_12 during STA, no CVC, and max fanout on the CTS leaf buffers (N, DA). The three flows ran one after another (18:36-18:39), each in a `--cpus 6` container |
| 2 | Router, Magic and KLayout DRC | Router: `reports/routing/drt.drc` empty. Magic: `reports/signoff/drc.rpt` COUNT 0. KLayout: `runs/pex/klayout/<V>/drc.lyrdb` has 0 items in 239 rule categories. Its log shows the FEOL, BEOL and OFFGRID-ANGLES sections ran (the deck's "already initialized constant" lines are its own flag handling, not errors) |
| 3 | LVS | netgen log for each variant: "Final result: Circuits match uniquely". Cell-level summary for N: 25 dfxtp_1, 42 xor2_1, 10 and2_1, 10 and2b_1, 1 inv_1, 3 clkbuf_16 and 148 decaps on both sides; 96 devices after parallel merging and 109 nets on each side. DA and U match the same way |
| 4 | Antenna and XOR | OpenROAD `34-arc.log`: "Found 0 net violations", "Found 0 pin violations". The final netlist has no diode cells. `28-xor.rpt`: 0 differences, with real polygons compared (for example 239 flat polygons on a layer), not two empty streams |
| 5 | Generator vs final gate-level netlist (my own parser, independent of `summarize.py`) | 88 / 118 / 27 instances. Each has the same cell type and the same net on every signal pin, and no extra pins. The only change: flip-flop CLK pins move to clock-tree leaves, each reached through exactly 2 clkbuf_16 stages from `CLK`. Added cells are only clkbuf_16 (3/5/3), tapvpwrvgnd_1 (30/50/12), decap_3/4/6/8/12 (148/224/52) and fill_1/2 (54/72/14). Every instance has VNB and VGND on VGND, VPB and VPWR on VPWR |
| 6 | **Transistor-level equivalence of `build/<V>_pex/dut.sp`** with the final gate-level netlist expanded by the stock cell subcircuits (including `sky130_ef_sc_hd__decap_12`) | Transistor count equal (1,578 / 2,530 / 616). The (model, W, L) multisets are equal, including the 100 / 220 / 40 `special_nfet_01v8` of the flip-flops. Every named net is present, with an identical multiset of (gate or source/drain, model, W, L). Six rounds of WL refinement give all-singleton classes and equal label multisets, so the graphs are isomorphic with the names preserved. Every nfet body is on VGND and every pfet body on VPWR. There is no floating well or substrate node, and no node that carries only capacitors |
| 7 | Diffusion geometry and capacitance in the PEX netlist | Every one of the 1,578 FETs of N has nonzero ad/as/pd/ps (logic FETs: ad/W median 0.17 um, range 0.12-0.54). The tech file's ngspice style leaves diffusion area cap to the device models (its `*diff` areacap lines are commented out), so nothing is counted twice. Capacitors: N 7,105 (1,032 fF: 214 to VGND, 186 to VPWR, 395 VPWR-VGND, 237 between signals). Values in plain farads or `f`; W, L, ad and pd in microns. The model library sets `.option scale=1.0u` (`corners/tt.spice` includes `all.spice`) |
| 8 | Is `dut.sp` a faithful rewrite of Magic's output? | Parsed `runs/pex/ext/<V>/dut_<V>_flat.spice` and `build/<V>_pex/dut.sp` element by element. N 8,683, DA 14,650 and U 3,082 elements with 0 mismatches in model or parameters. The node renaming is injective and keeps the port names. The flat file's sha256 equals `ports.json` `pex.flat_spice_sha256`. The source GDS's sha256 equals both the final and the signoff GDS |
| 9 | Port order and runner contract | The `.subckt dut_<V>` line equals `build/<V>/ports.json` `ports` for all three. `ports.json` for `<V>_pex` keeps `subckt`, `ports`, `inputs`, `outputs` and `latency` unchanged. Magic gave exactly 28 (13 for U) ports, with substrate and n-well already merged into VGND and VPWR, so no tie was needed. The runner deck puts VPWR on `vpwr_dut` (the measured source) and VGND on node 0, as before layout |
| 10 | Same stimulus rows | I rebuilt the decks of queue chunks 0, 5 and 11 with `sim/spice_campaign.py` functions from `M_tvla.npy` (chunk 125, `--options klu`, save-outputs). All three are identical to the files on disk. `M_tvla.npy`'s hash equals `stimulus_sha256` of `runs/kt/{N,D,DA}_tvla` and of the benchmark runs |
| 11 | Resumability and the `dut.sp` rewrite at 19:36 | All three `build/*_pex` files were rewritten at 19:36, after the queue started at 19:24:37. The content is identical: the current sha256 `b1999858…` equals the hash in every queue deck. For chunks 0-5, the key recomputed from the rebuilt deck and the post-processing parameters equals `done.json` `key_sha256`, so a re-run skips them |
| 12 | Function, independent S-box (bitsliced formula, table checked against 0x4, 0xb, 0x1f, …) | `bench_N_pex_klu` and `bench_DA_pex_klu`: 120 rows each, 0 mismatches. Queue N_pex rows 0-749: 0 mismatches. Every one of these rows is also bit-identical to the pre-layout campaign's `outputs.npy` for the same row, including the Sparse-solver benchmarks |
| 13 | Sanity numbers (`results/pex/sanity_*.json`) recomputed from `charge.npy` | Charge ratio post/pre: N 2.3515, DA 2.6920. Correlation of the per-row charge: 0.9875 / 0.9893. Both reproduce |
| 14 | KLU vs the default Sparse solver (same netlist, same 120 rows) | Largest per-bin difference: N 4.95 uA against a peak of 2,721 uA; DA 11.0 against 5,889 uA. Largest relative charge difference: 1.31e-4 (N), 1.47e-4 (DA). Correlation of the data-dependent parts: 0.9999999 / 0.9999997. Some KLU chunks need dynamic gmin stepping for the initial operating point only; the 4 warm-up rows wash that out. Dropping the decaps (DA, 10 rows): at most 0.0005 uA |
| 15 | Chunk boundaries and netlist rewrite together | Rows 0-119 of the queue (125-row chunk, current netlist) against the benchmark (20-row chunks, the earlier netlist `672d8809`): largest per-bin difference 4.2 uA, rms 0.06 uA. `check_flat_N` (20 rows, current netlist): bit-identical to the benchmark |
| 16 | STA | `25-rcx_sta.summary.rpt`: worst setup slack 1.78 / 2.05 / 2.12 ns, hold 0.25 / 0.13 / 0.29 ns, tns 0. These are for OpenLane's SDC with its own IO delays. The SPICE testbench's setup is checked by the node run instead: minimum margin 1.99 ns from the ideal edge, and about 2.3 ns from the flip-flop clock pin |
| 17 | Queue state at 19:45 | `queue.sh` (session leader) running. One `cac-sca` container (`--cpus 6`) running 6 ngspice processes at about 99.5 % CPU each, about 212 MB each. Chunks 0-5 done (1,047-1,084 s each); chunks 6-11 started at 19:42. `python3 layout/pex_status.py`: 750/5,000 rows, about 1.8 h left for N; DA_pex 0/80 chunks |
| 18 | Host paths and personal data in what will be committed (`layout/`, `results/layout/`, `results/pex/`) | No home-directory or mount path, user name, hostname or e-mail address in any text file. The PNG text chunks hold only a Matplotlib "Software" tag (placement plots), or the top cell name and view rectangle (KLayout renders). `build/` and `runs/` are git-ignored |
| 19 | SPDX and tests | Every new source and doc file starts with the Apache-2.0 SPDX line, except `layout/<V>/config.json` and `layout/pin_order.cfg` (see N7). `python3 -m unittest layout/test_layout.py`: 8 OK. No tracked file is modified (`git status`), and `sim/`, `analysis/` and `docs/KILL_TEST.md` are untouched |

## Notes (non-blocking)

**N1. The "2.2x capacitance" needs its other half.** The README says the logic nets "carry 2.2x the estimated
capacitance". That is Magic's flat total, 391.7 fF against the 178.0 fF estimate for N. OpenROAD's own extraction of
the routed wiring (`results/final/spef/dut_N.spef`, including coupling, `PIN_CAP NONE`) totals **178.6 fF on the same
nets**, which is essentially the pre-layout estimate. Magic's flat extraction also contains the cells' own geometry on
those nets: input-pin poly over field and li1 pin shapes, plus coupling to cell-internal nodes. Per net, Magic is
1.3-10x the routed-wire value (median 2.7x).

So the pre-layout wire-cap estimate was right in total. What the pre-layout model lacked is the cells' own parasitics.
That fits the stock-cell finding in `spice-circuit.md` (F3), and it is worth saying that way in the README and the
notebook. Suggested wording: "the routed wiring alone (OpenRCX) totals 179 fF, the same as the estimate; with the cells'
own pin geometry, which the stock cell netlists lack, Magic extracts 392 fF (2.2x)".

Also: the drawn diffusion is ad/W ≈ 0.17 um (median). That is smaller than the 0.29 um bracket used in `spice-circuit.md`
check 11, so the diffusion-cap bracket there was on the pessimistic side.

**N2. Provenance of the sanity and benchmark files.** `results/pex/sanity_{N,DA}.json` and `bench.json` were produced
on the earlier netlist text, before the 19:21 restructure: N `672d8809`, DA `f2984d22`. The queue runs N `b1999858` and
DA `8517658f`. For N the two versions were simulated against each other (check 15). For DA they were not. Check 8
shows statically that the current DA file is an element-for-element rewrite of the same Magic output, and N's rewrite
gave bit-identical traces, so I expect DA's to as well.

Say this in the README. A reader who compares `dut_sp_sha256` in the benchmark manifests with the queue's will
otherwise find a mismatch. The first finished DA_pex chunks also serve as the functional check: `pex_status.py`
compares them with the S-box.

**N3. Fix the post-layout reading rule now, before the campaigns finish.** Nothing registers the post-layout
criteria. The progress view has already been looked at: at 373 traces by the layout flow, and at 748 by me (max|t| 3.00 at 1.645 ns,
against 3.41 at 0.945 ns pre-layout on the same rows). The rule should be written down before the full campaign is
read. Suggested:
- the threshold stays 4.5;
- N_pex is read at 5,000 rows, and if it is below 4.5 there, it is extended to 10,000 (the 125-row chunks allow this)
  before anything is concluded;
- DA_pex is read at 10,000 rows.

Also state plainly that DA_pex has **half** of pre-layout DA's 20,000 traces. At 10,000 traces TVLA excludes only a
leak of about a third of N's strength or stronger, not a quarter. The same kind of statement is already in
KILL_TEST.md for 4,997 vs 20,000 traces.

**N4. The cycle-part boundaries of `analysis/kill_test.py` assume pre-layout timing.** Post-layout, the clock reaches
the flip-flops about 0.33 ns after the ideal edge, and logic transitions run to 2.01 ns after it (`node_timing_N.json`).
The pre-layout parts would therefore credit late evaluation current to "clock fall": edge and evaluation -0.2 to 1.8 ns,
clock fall 1.8 to 2.8 ns, quiet end 1.3 to 1.8 ns. The analysis of record should shift these parts by the insertion
delay or redefine them from the post-layout node timing. The first-look peak at 1.645 ns is already in the old
"quiet end" part.

**N5. CPU use of the side runs.** The two 1-CPU node-run containers (`nodes_N_pre` 19:25-19:29, `nodes_N_pex`
19:29-19:39) ran alongside the queue's 6-CPU container, so SPICE used 7 CPUs for about 15 minutes. That is within the
per-container cap but not quite "one heavy container at a time". It is over now, and it is part of the 20 % slowdown of
the first wave that the README attributes to "other jobs".

As disclosed, `queue.sh` checks for other containers only before each campaign starts. A heavy container started by
another stage while DA_pex runs (about 21:30 to about 05:00) would share the machine with it.

**N6. `runs/pex/queue.sh` comment.** It says KLU matches Sparse "to 3e-6 in charge"; the measured maximum is 1.3e-4
(N) and 1.5e-4 (DA), as the README says. The script is git-ignored, so this is cosmetic.

**N7. SPDX exceptions.** `layout/<V>/config.json` (JSON has no comments) and `layout/pin_order.cfg` (OpenLane reads
`#` lines as section headers) have no SPDX line. If the repository wants to be REUSE-clean, add `.license` sidecar files
or a `.reuse/dep5` entry. The nine PNGs total 1.9 MB; `WIDTH=` in `run_klayout.sh` can shrink the two KLayout renders
per variant.

**N8. `pex_status.py` counts every `done.json`.** It does not compare a chunk's key with the current deck, so a stale
chunk from another netlist would be counted in the progress view. The runner itself rejects stale chunks, so final
results are not affected.

**N9. Very small capacitors.** With `cthresh 0` there are capacitors down to 1e-36 F (DA, U). The runs show they cause
no numerical trouble. Dropping those below about 1e-21 F would shorten the decks, but nothing needs to change.

## What remains open (by design)

- There is no TVLA of record for N_pex and DA_pex yet; `pex_status.py` is a progress view. The analysis must state
  that post-layout campaigns use KLU and pre-layout used Sparse, and cite check 14.
- The model is C-only: no wire, via or power-grid resistance. It uses the tt corner, one placement per variant, an
  ideal supply at the block pins, and ideal clock and input sources at the block pins. The clock tree's current is now
  part of the measured trace. All of this is stated in the README's Limits.
- `build/U_pex` is extracted but not simulated. That is optional.
