<!-- SPDX-License-Identifier: Apache-2.0 -->
# Layout and post-layout SPICE model

Question: does N's first-order leak survive place and route with extracted parasitics, and does DA
stay clean? This directory takes the generator's structural netlists (`build/<V>/dut.v`) through
OpenLane v1 to DRC/LVS-clean layouts, extracts them with Magic into transistor-level SPICE netlists
with parasitic capacitance, and wraps them for the unchanged SPICE runner (`sim/spice_campaign.py`).
The post-layout TVLA campaigns ran from `runs/pex/queue.sh`; their registration and results are in
`docs/POSTLAYOUT.md`.

## Steps (from the repository root)

```
bash layout/run_flow.sh N        # OpenLane v1 (then DA, U; one at a time)
bash layout/run_pex.sh N         # Magic extraction -> build/N_pex/{dut.sp,ports.json,graph.json}
bash layout/run_klayout.sh N     # KLayout DRC (PDK deck) + results/layout/N_{layout,routing}.png
bash sim/docker_run.sh python3 layout/plot_placement.py N DA U   # results/layout/<V>_placement.png, placement_<V>.csv
python3 layout/summarize.py      # results/layout/summary.json and table.md (the table below)
python3 -m unittest layout/test_layout.py layout/test_controls.py
bash layout/run_controls.sh N DA   # LVS/DRC negative controls (section below)
bash layout/run_pex_rc.sh N        # RC bracket netlist runs/pex/rc/N_rc (section below)
```

The scripts find the OpenLane checkout (`OPENLANE_DIR`, default `~/rtl2gds/OpenLane`, commit ff5509f),
the PDK (`PDK_ROOT`, default `~/.ciel`, sky130A via ciel) and the OpenLane image (`OL_IMAGE`) at run time,
and apply the CPU cap in `runs/docker_opts`. The OpenLane design directory is assembled under
`runs/pex/ol/<V>/` (git-ignored) from `layout/<V>/config.json`, `layout/pin_order.cfg` and a copy of
`build/<V>/dut.v`.

## OpenLane configuration: keep the generator's netlist

- `SYNTH_ELABORATE_ONLY` with the Liberty cells read as black boxes: yosys only elaborates the
  structural netlist, no ABC mapping. `layout/summarize.py` checks the result: every instance of
  `build/<V>/dut.v` is in the synthesized and in the final netlist with the same cell type and the
  same net on every pin (N 88, DA 118, U 27 instances).
- All resizer steps off (`PL_RESIZER_*_OPTIMIZATIONS`, `GLB_RESIZER_*_OPTIMIZATIONS`, port
  buffering): no buffer insertion, no sizing, no timing or hold repair.
- Clock tree kept (`RUN_CTS`); the only cells OpenLane adds are the clock buffers, tap cells,
  decap cells and fill. Clock period 4 ns, as in SPICE. No antenna diodes were needed
  (`GRT_REPAIR_ANTENNAS` on; it inserted none).
- Relative floorplan at 40 % core utilisation, placement density 0.5; inputs on the west edge,
  outputs on the east edge, clock on the north edge; met4 power straps every 20 um (`DESIGN_IS_CORE`
  off, a block, not a chip); the GDS for LVS is extracted from the final GDS (`MAGIC_EXT_USE_GDS`).
- OpenLane's own KLayout DRC step is skipped for this PDK (no `KLAYOUT_DRC_TECH_SCRIPT`), so
  `run_klayout.sh` runs the PDK's `sky130A_mr.drc` deck (FEOL, BEOL and off-grid rules) directly.

## Result

| | N | DA | U |
|---|---|---|---|
| die (um) | 61.28 x 72.00 | 74.49 x 85.21 | 40.10 x 50.82 |
| core area (um^2) | 2455 | 3942 | 788 |
| placement utilisation | 44.2 % | 43.4 % | 48.4 % |
| logic cells: generator / synthesized / final | 88 / 88 / 88 | 118 / 118 / 118 | 27 / 27 / 27 |
| logic netlist unchanged (types, pins) | yes | yes | yes |
| CTS buffers added | 3 x clkbuf_16 | 5 x clkbuf_16 | 3 x clkbuf_16 |
| other buffers added | 0 | 0 | 0 |
| tap / decap / fill cells | 30 / 148 / 54 | 50 / 224 / 72 | 12 / 52 / 14 |
| antenna diodes | 0 | 0 | 0 |
| clock skew (ns) | 0.01 | 0.02 | 0.01 |
| setup / hold worst slack at 4 ns (ns) | 1.78 / 0.25 | 2.05 / 0.13 | 2.12 / 0.29 |
| wire length (um) / vias | 1537 / 524 | 2162 / 708 | 487 / 173 |
| DRC: router / Magic / KLayout | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| LVS (netgen) | clean | clean | clean |
| antenna violations (pins / nets) | 0 / 0 | 0 / 0 | 0 / 0 |
| extracted transistors (of them decap) | 1578 (296) | 2530 (448) | 616 (104) |
| extracted capacitors | 7105 | 12120 | 2466 |
| logic-net cap, pre-layout estimate / extracted (fF) | 178 / 392 | 223 / 498 | 54 / 118 |
| coupling share 0 - share 1 nets (fF, capacitors) | 7.0 (112) | 7.8 (106) | - |

Timing is the tt corner from OpenROAD with the extracted SPEF. The only max-fanout warnings are
the CTS leaf buffers (clkbuf_16 driving 12-13 flip-flops against a limit of 10), which is harmless
for a clkbuf_16. KLayout's XOR of the Magic and KLayout GDS streams shows no difference.

Images in `results/layout/`: `<V>_layout.png` (all drawn layers, PDK colours),
`<V>_routing.png` (li1 and metals, vias and pins only), `<V>_placement.png` (each cell coloured by
the share domain of the net it drives; hatched = output net flagged by glitch-extended probing;
N's cross-domain ANDs sit between the share-0 and share-1 halves). The same placement as data is
in `placement_<V>.csv`, which the notebook draws; the notebook shows small copies of the layout
renders (`notebook/make_layout_media.py`).

## Extraction (`layout/pex/extract.tcl`, `layout/make_pex.py`)

- Magic reads the final GDS, flattens it (keeping the top-level labels, so ports and routed nets
  keep their names) and extracts every transistor with its drawn W, L and drain/source diffusion
  areas and perimeters (`ad/as/pd/ps`), every capacitance to substrate and every coupling
  capacitance between nets, with no threshold (`ext2spice cthresh 0`).
- **No resistance** (C-only). The blocks are under 90 um across; a 100 um met1 or met2 route at
  minimum width has about 90 ohm (0.125 ohm/square), which with 20 fF of load is under 2 ps, well
  below the 10 ps bins. Via and in-cell li1 resistance are left out as well. That estimate is too
  low: the RC bracket below, which includes the cells' poly and li1 and the clock tree's wiring,
  finds N's evaluation about 60 ps later (flip-flop clock-to-Q +25 ps) with little else changed.
- n-well and substrate come out merged with VPWR and VGND through the tap cells, so the extracted
  subckt has exactly the pre-layout ports; `make_pex.py` writes it as `.subckt dut_<V>` with the port
  order of `build/<V>/ports.json` (the runner's deck is unchanged) and makes node names ngspice-safe.
  Routed nets keep their names, so node tools can probe `xdut.<net>` as before
  (`analysis/spice_nodes.py` works on `build/<V>_pex`, whose `graph.json` is a copy of the logical
  netlist).
- The extracted netlist uses `sky130_fd_pr` devices directly; the runner's
  `.lib sky130.lib.spice tt` defines them (with `.option scale=1.0u`, matching Magic's micron units).
- What changes against the pre-layout netlist: the routed wiring alone (OpenRCX SPEF) totals
  179 fF on N's logic nets, the same as the 178 fF estimate; with the cells' own pin geometry,
  which the stock cell netlists lack, Magic extracts 392 fF (2.2x; DA: estimate 223, routed 233, Magic 498 fF;
  `results/pex/summary_postlayout.json` `capacitance_views`). The layouts add coupling between
  nets, and the clock tree (3-5 clkbuf_16) now draws its current from the DUT supply.
  Decap MOS capacitors sit between VPWR and VGND; with the testbench's ideal supply they carry
  only a constant current (dropping them changed the traces by < 0.001 uA, `--drop-supply-devices`),
  but they are kept.
- Regenerating `build/<V>_pex` is deterministic. Do not change the text `make_pex.py` writes while
  a campaign is running or meant to be resumed: the runner keys finished chunks on `dut.sp`'s hash.

## Validation (`layout/validate_pex.py`, `results/pex/sanity_<V>.json`)

First 120 rows of `runs/kt/stim/M_tvla.npy`, compared with the pre-layout campaigns on the same rows.
These sanity files and `results/pex/bench.json` were made from an earlier text of the same
extraction (N `672d8809`, DA `f2984d22`); the campaigns ran the current text (N `b1999858`, DA
`8517658f`). On rows 0-119 the two give the same traces to within 4.5 uA per bin and a
data-dependent correlation of 0.9999997 or better (`docs/POSTLAYOUT.md`, Results):

| | N | DA |
|---|---|---|
| registered outputs vs S-box | 0 mismatches | 0 mismatches |
| charge per window, post / pre (mean) | 2.35 | 2.69 |
| correlation of the data-dependent charge, post vs pre | 0.988 | 0.989 |
| supply-current peak after the edge (ns), post / pre | 0.315 / 0.055 | 0.335 / 0.055 |
| 90 % / 99 % of the evaluation charge flowed by (ns), post | 1.30 / 1.69 | 0.81 / 1.10 |
| same, pre-layout | 0.77 / 1.08 | 0.40 / 0.62 |
| best alignment of the mean current, post later by (ns) | 0.16 | 0.20 |
| data-dependent waveform correlation at that shift | 0.35 | 0.27 |

The charge columns stop at 1.8 ns after the edge, before the clock's falling edge; the post-layout
evaluation runs a little past that, so its net-level timing is the better measure. Node runs of the
same 40 rows for N (`analysis/spice_nodes.py` on `build/N` and `build/N_pex`, then
`layout/node_timing.py` -> `results/pex/node_timing_N.json`; times after the ideal clock edge at the
block's CLK pin, so post-layout includes the clock tree's insertion delay of about 0.33 ns):

| N, 38 cycles | pre-layout | post-layout |
|---|---|---|
| flip-flop clock-to-Q, median (max) (ns) | 0.20 (0.29) | 0.56 (0.74) |
| last logic-net transition per cycle, median (max) (ns) | 1.06 (1.20) | 1.83 (2.01) |
| setup margin at the output flip-flops, min (ns) | 2.80 | 1.99 |
| logic-net transitions per cycle, median | 51 | 55 |
| glitch transitions per cycle (beyond one per net), median | 21 | 22 |

So the evaluation after layout starts about 0.36 ns later and takes about 0.4 ns longer, with the
same amount of glitching; it still ends 2 ns before the capturing edge (every output matched the
S-box; STA setup slack 1.8-2.1 ns). The per-window charge keeps its data dependence (correlation
0.99), but the data-dependent waveform changes shape, so the post-layout t-curves have to be
measured, not inferred from the pre-layout ones.

## Cost and the campaigns

`layout/bench_summary.py` -> `results/pex/bench.json` (6 ngspice processes x 1 thread in one
container capped at 6 CPUs):

| netlist | solver | s per simulated cycle per process | peak RSS per process | rows/s |
|---|---|---|---|---|
| N post-layout | Sparse (runner default) | 10.4 | 204 MB | 0.42 |
| N post-layout | KLU | 6.6 | 207 MB | 0.67 |
| DA post-layout | Sparse | 25.7 | 352 MB | 0.17 |
| DA post-layout | KLU | 12.0 | 358 MB | 0.36 |
| DA pre-layout (kill test, 10 x 2 threads) | Sparse | 19.7 | 309 MB | 0.50 |

KLU (`--options klu`) gives the same traces as the default solver (on 120 rows: charge within
1.5e-4, data-dependent correlation 0.9999997) and is 1.6x (N) to 2.2x (DA) faster, so the campaigns
use it. The projection before the runs, at 125-row chunks, was N 5,000 rows 1.7 h and DA 10,000 rows
6.2 h. The campaigns took 4.0 h (N_pex, including a suspend of the host) and 4.9 h (DA_pex) of wall
clock, with median chunk times of 843 s and 1,286 s (`results/pex/summary_postlayout.json`,
`spice_wall_clock`).

`runs/pex/queue.sh` (git-ignored) runs N_pex 5,000 rows, then DA_pex 10,000 rows, on the kill test's
stimulus `runs/kt/stim/M_tvla.npy` (same rows as pre-layout), resumable, with `--save-outputs`. It waits
while another SPICE or OpenLane container runs and logs START/END/DONE to `runs/pex/queue.log`.

```
nohup setsid bash runs/pex/queue.sh > runs/pex/queue.out 2>&1 &    # start or resume
tail runs/pex/queue.log                                           # START / END / DONE lines
python3 layout/pex_status.py     # chunks done, hours left, function check (TVLA look only with --show-t)
pkill -f 'bash runs/pex/queue.sh'; docker ps -q --filter ancestor=cac-sca:0.1 | xargs -r docker kill   # stop
```

## Negative controls and an RC bracket

**Negative controls of the sign-off** (`bash layout/run_controls.sh N DA`, about 10 s;
`layout/neg_controls.py`, `layout/controls/`; `results/layout/negative_controls.json`). A DRC count
of 0 and an LVS match only mean something if the same checks fail on a broken input. Magic
extracts the layout netlist from `results/layout/gds/dut_<V>.gds` with OpenLane's signoff commands
(identical to OpenLane's own extraction), and netgen, with the PDK's setup file, compares it with
OpenLane's final netlist (the file its LVS step read) and with three edits of that netlist:

| netlist given to netgen | N | DA |
|---|---|---|
| correct | match (96 / 96 devices) | match (128 / 128) |
| share swap: the first cross-domain AND's share-0 input moved to the share-1 net of the same name (N `g_m01_0.A_N`: `as0_0` -> `as1_0`) | fails | fails |
| gate type: the first `and2_1` made an `or2_1` (same pins) | fails | fails |
| missing flip-flop: the first `dfxtp_1` deleted | fails | fails |

The share swap changes one pin and keeps every device and net count (96 / 109 in N); netgen still
reports "Netlists do not match", so the LVS match does pin down the share-domain wiring the leakage
argument rests on. For DRC, `layout/controls/inject_drc.py` (KLayout) copies N's GDS and adds two
defects inside the cell rows, away from other metal: two met1 rectangles 0.07 um apart (m1.2:
0.14 um) and a via1 with 0.03 um of met1 past two opposite sides of the cut (via.4a: 0.055 um),
each shape otherwise legal. Magic (OpenLane's signoff DRC commands, `layout/controls/magic_drc.tcl`)
and KLayout (`sky130A_mr.drc`, as `run_klayout.sh` runs it) report 0 on the final GDS and, on the
copy, only the two defects: Magic 2 met1.2 boxes and 8 via1-overlap boxes, KLayout one m1.2 and two
via.4a markers, nothing elsewhere. (Magic's via1 contact type already includes the 0.055 um
enclosure, so its message counts the missing surround from that edge.)

**RC bracket of the C-only extraction** (`bash layout/run_pex_rc.sh N`, then the SPICE runs in the
header of `layout/rc_check.py`; `results/pex/rc_check.json`). A sanity check on 120 rows, not a
TVLA: it cannot show or rule out a leak, only whether resistance changes the current or the timing
enough to question the C-only campaigns.
- *Extraction.* Magic `extresist` on every net except VPWR/VGND (`layout/pex/extract_rc.tcl`):
  4,427 resistors (median 103 ohm, max 511 ohm) on 603 nets, through the routing, vias, contacts
  and the cells' own poly and li1. The rails stay one ideal node each, as in the testbench. Magic
  8.3.413 needs `ext2spice -p <dir>` to find the `.res.ext` file (without it the netlist silently
  has no resistors), and its output is not byte-reproducible (4,425-4,429 resistors in five runs,
  total within 0.005 %), so the simulated netlist is identified by its hash.
- *Capacitance.* The extresist netlist keeps only 745 of the C-only netlist's 1,032 fF (coupling to
  resistor-extracted nodes is dropped). `layout/make_pex_rc.py` therefore takes its transistors and
  resistors and puts the C-only capacitors back: the 399 fF to the rails spread evenly over each
  net's network nodes, the 237 fF of coupling between signal nets at one node of each net (spreading
  it too made each KLU factorization about 300 times slower, 355 ms instead of 1.1 ms; the
  placement error is about R x C = 0.01 ps).
  The capacitance per pair of nets and the transistors equal the C-only netlist's.
- *Result* (rows 0-119 of `runs/kt/stim/M_tvla.npy`, KLU, the C-only run equal to the N_pex
  campaign's first 120 rows within 0.9 uA per bin):

| RC against C-only | |
|---|---|
| registered outputs | 0 mismatches in both; identical bit for bit |
| charge per window | -0.24 % on average (-1.1 % to +0.7 %); data-dependent part correlated at 0.9998 |
| supply current | RC 20 ps later; after that shift the mean trace correlates at 0.995 and the data-dependent part at 0.98 (0.94 unshifted) |
| fixed-minus-random mean current (the TVLA numerator on these rows) | correlation 0.95, 0.98 after the 20 ps shift |
| flip-flop clock-to-Q after the ideal edge at the CLK pin (node runs, 38 cycles) | +25 ps (23-27 ps; resistance along the clock path) |
| last logic transition per cycle | +61 ps median (22-74 ps): 1.83 -> 1.89 ns median, 2.01 -> 2.08 ns max |
| logic-net transitions incl. glitches | 2,065 -> 2,057 |

  So resistance delays N's evaluation by about 60 ps and leaves its charge, its glitches and the
  data-dependent shape of its current nearly unchanged. That is a tenth of the 0.69 ns shift that
  place and route caused, and the evaluation still ends 1.9 ns before the next edge. The C-only
  campaigns' verdicts are not re-tested by this; the bracket says the C-only model's timing is
  within about 60 ps of the RC one.

## Limits

C-only extraction for the campaigns (no wire or via resistance; the RC bracket above, on 120 rows
of N, moves the evaluation about 60 ps later and changes little else), tt corner at 27 C, one
layout per variant (one placement seed), an ideal 1.8 V supply at the block's power pins (no
power-grid resistance, package or on-chip decoupling effect), ideal clock and input sources at the
block's pins. The layouts are blocks, not a chip: no pads, no seal ring, no density fill.
