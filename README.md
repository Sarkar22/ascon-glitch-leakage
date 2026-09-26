# Safe on paper, leaky in SPICE: glitch leakage of a masked Ascon S-box on sky130

A first-order masked Ascon S-box that a zero-delay model calls secure leaks at first order in transistor-level SPICE
on the open sky130 PDK. This repository contains the whole study: one generated netlist per design, three leakage
models of increasing fidelity, an exact probing check, SPICE campaigns with first-order TVLA, a profiled key-recovery
attack, DRC/LVS-clean layouts with parasitic extraction, and the post-layout re-test. It is the code behind an
IEEE SSCS Code-a-Chip notebook for ISSCC 2027 (`notebook/ascon_glitch_leakage.ipynb`).

No chip was fabricated. SPICE with the foundry's device models is the reference, and the limits of that are stated
in the documents below.

## Results

One Ascon S-box column (5 bits), sky130 `tt`, 1.8 V, 4 ns clock; first-order fixed-vs-random TVLA, threshold
|t| = 4.5.

| Design | Zero-delay model | Glitch-extended probing | SPICE, pre-layout | SPICE, post-layout |
|---|---|---|---|---|
| N: masked, no register barrier | 1.08 (secure) | 39 of 103 nets leak | **13.2** at 9,998 traces (leaks) | **8.19** at 4,998 (leaks) |
| D: DOM, affine layer between the input registers and the ANDs | secure | 12 nets leak | 3.08 at 19,997 | not laid out |
| DA: DOM, affine layer before the registers | secure | 0 nets leak | 3.08 at 19,997 | 3.36 at 9,997 |

D and DA end at the same max|t| (3.08) at the same sample (2.175 ns, in the first cycle's clock-fall region),
probably from circuitry the two variants share: one observation, not two (notebook §4.5).

- **N leaks.** The leak sits in the timing of the unregistered cross-domain logic (glitch pulses and data-dependent
  arrival times). The nets that carry it in SPICE are nets the glitch-extended probing check flags. A profiled
  template attack recovers N's key at first order (success rate 0.93 at 765 traces per key, with points of interest
  chosen per key bit after the default attack missed one bit).
- **D and DA show no first-order leak** within 19,997 traces. For D this is not a proof: its net-level leak is real
  in SPICE and the timing-aware model predicts max|t| 15.2 (cap-weighted), but it does not reach the supply current at
  that count. At 19,997 traces TVLA reaches 4.5 on average for a leak about a quarter as strong as N's.
- **After place and route** (OpenLane, every generator cell kept; Magic, KLayout and netgen clean; Magic extraction
  with parasitic capacitances), N still leaks and DA still shows no first-order leak on the same stimulus rows (DA at
  half the pre-layout traces).
- **Checks of the checks** (post hoc, outside the registrations): netgen LVS fails on a netlist with one AND input
  moved from share 0 to share 1 (every device and net count unchanged), on a changed gate type and on a missing
  flip-flop, and Magic and KLayout flag exactly two injected DRC defects. A 120-row RC bracket of N (Magic
  `extresist`) delays its evaluation by about 61 ps and changes little else; it is a sanity check, not a TVLA.
- **Cost of the fix (DA against N):** about 1.6x cell area, +39 % energy per evaluation before layout (+60 % after
  layout, where the clock tree is included), 2 cycles of latency instead of 1, the same 5 fresh random bits.

The kill test and the post-layout test were registered with fixed criteria before their data existed; deviations,
amendments and the one failed sanity criterion (a one-column CPA, K1) are reported in place:
[`docs/KILL_TEST.md`](docs/KILL_TEST.md), [`docs/POSTLAYOUT.md`](docs/POSTLAYOUT.md). Adversarial reviews of each
stage are in [`docs/reviews/`](docs/reviews/). The negative controls and the RC bracket are in
[`layout/README.md`](layout/README.md) and the post-hoc note at the end of `docs/POSTLAYOUT.md`.

## Repository

| Path | Contents |
|---|---|
| `gen/` | netlist generator: structural sky130 Verilog, SPICE and a Python gate graph from one description |
| `model/` | Ascon S-box, stimulus, zero-delay and timing-aware leakage models, exact probing check, TVLA, CPA |
| `sim/` | parallel ngspice campaign runner and its Docker wrapper |
| `analysis/` | kill-test and post-layout analysis, key recovery, cost table, figures |
| `layout/` | OpenLane flows, extraction into SPICE, sign-off summaries |
| `results/` | small result files (JSON, CSV, figures, final GDS); raw traces are not committed |
| `notebook/` | the Code-a-Chip notebook, its setup helper, cached data and media |
| `docs/` | registrations, results and reviews |

## Reproduce

Quick look, no simulator needed: open `notebook/ascon_glitch_leakage.ipynb`. In cached mode it redraws every figure
from the CSV files in `notebook/data/`. In live mode (Colab or Linux with `ngspice` and the sky130 PDK) its setup cell
installs the tools and runs a short SPICE demo.

Full runs use the Docker image in `docker/` (ngspice-42, yosys, iverilog, Python):
```
docker build -t cac-sca:0.1 docker/
python3 gen/make_variants.py && python3 tb/run_iverilog.py && python3 model/probing.py
python3 -m unittest discover -s model/tests
```
The exact campaign and analysis commands are in the "Reproduce" sections of `docs/KILL_TEST.md`,
`docs/POSTLAYOUT.md`, `layout/README.md` and `notebook/README.md`. The sky130 PDK is pinned by ciel hash
`0fe599b2afb6708d281543108caf8310912f54af`.

## Limits

Pre-layout netlists carry estimated wiring only, and the stock sky130 cell netlists have no diffusion capacitance;
the post-layout campaigns use capacitance-only extraction (the RC bracket covers 120 rows of N and no power grid). One
process corner (`tt`), one temperature, an ideal supply, ideal clock and input sources, no package, board or
measurement chain. The results are statements about transistor-level simulation, not about silicon.

## AI use

AI coding assistants were used in this project. All results come from open-source tools (ngspice, the sky130 PDK,
OpenLane, Magic, KLayout, netgen, Python), and the author is responsible for all content.

## License

Apache License 2.0 (`LICENSE`). Author: Emon Sarkar, University of Waterloo.
