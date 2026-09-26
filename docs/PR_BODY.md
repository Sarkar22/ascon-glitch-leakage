<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
Draft of the pull request to github.com/sscs-ose/sscs-ose-code-a-chip.github.io.
Title: [ISSCC27] Safe on paper, leaky in SPICE: glitch leakage of a masked Ascon S-box on SKY130
The description is everything below this comment. The folder is built by tools/make_submission.py and
checked with tools/check_submission.sh. Before opening the PR: replace the CI-run TODO with the latest green run.
The fork's commit must come from the pristine build: a fresh copy of
runs/submission/ISSCC27/submitted_notebooks/ascon_glitch_leakage/ into the fork's
ISSCC27/submitted_notebooks/ascon_glitch_leakage/, never from runs/submission/upstream/, where
check_submission.sh executed the notebook and Python wrote __pycache__/*.pyc next to the helpers
(upstream's .gitignore does not ignore them). The folder must hold no __pycache__ and no *.pyc.
-->

Adds `ISSCC27/submitted_notebooks/ascon_glitch_leakage/`: the notebook, its helper modules, the cached data it
reads, an Apache-2.0 `LICENSE` and a `README.md` (45 files, 4.4 MB). Nothing outside this folder is changed.

| Name | Affiliation | IEEE member | SSCS member | E-mail |
|---|---|---|---|---|
| Emon Sarkar ([@Sarkar22](https://github.com/Sarkar22)) | University of Waterloo, Electrical and Computer Engineering | yes | no | esarkar@uwaterloo.ca |

### Summary

1. A first-order masked Ascon S-box (NIST SP 800-232) that a zero-delay leakage model calls secure (max|t| 1.08)
   leaks at first order in transistor-level ngspice simulation on sky130: max|t| 13.2 at 9,998 traces (TVLA
   threshold 4.5).
2. An exact glitch-extended probing check, which runs in seconds, flags 39 of the design's 103 nets; the nets that
   carry the leak in SPICE are among them.
3. With DOM's register barrier moved behind Ascon's input affine layer (DA), no first-order leak shows up within
   19,997 traces (max|t| 3.08). A profiled first-order attack recovers the naive design's key (success rate 0.93 at
   765 traces per key, with points of interest chosen per key bit after the default attack missed one bit; 0.62
   with the default ones) and finds no first-order key in DA (a second-order template partly does, as expected for
   two-share masking).
4. After OpenLane place and route (DRC, LVS and antenna clean) and Magic extraction (capacitance only), the verdicts
   hold: the naive design 8.19 at 4,998 traces, DA 3.36 at 9,997 (half the pre-layout traces). LVS and DRC fail on
   injected faults, including one swapped share input, and a 120-row RC bracket delays the evaluation by about
   61 ps.
5. The fix costs 59 % more cell area, 39 % more energy per evaluation (60 % after layout, clock tree
   included), one more cycle of latency and no extra randomness. All results are simulations at one corner
   (tt, 27 °C, 1.8 V); no chip was fabricated.

### What the notebook shows

- Background: the Ascon S-box, Boolean masking, domain-oriented masking (DOM), glitches and the glitch-extended
  probing model, TVLA.
- Four variants of one S-box column, generated as sky130 standard-cell netlists from one description, and three
  leakage models of increasing fidelity on the same netlist: zero-delay toggles, a timing-aware model with Liberty
  delays, and transistor-level ngspice-42. An exact probing check runs alongside them.
- The pre-registered test with fixed trace counts, its amendments, and the one criterion that failed.
- Where the leak sits (per-net t-values, an animation of one input change); why textbook DOM has a real net-level
  leak that does not show in the supply current; robustness to noise and bandwidth; an interactive TVLA explorer.
- A profiled key-recovery attack, the layouts with their sign-off and its negative controls, the registered
  post-layout TVLA, an RC bracket of the extraction, the cost of the fix, and the limitations.

### How to run

- Colab, from this folder (once merged):
  [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/sscs-ose/sscs-ose-code-a-chip.github.io/blob/main/ISSCC27/submitted_notebooks/ascon_glitch_leakage/ascon_glitch_leakage.ipynb)
- Colab, before the merge: [the same notebook from the project repository](https://colab.research.google.com/github/Sarkar22/ascon-glitch-leakage/blob/main/notebook/ascon_glitch_leakage.ipynb)
- Project repository (full flow, registrations, reviews): <https://github.com/Sarkar22/ascon-glitch-leakage>
- CI of the project repository: <https://github.com/Sarkar22/ascon-glitch-leakage/actions/workflows/ci.yml>;
  green run: TODO(user): link after the push. It runs the organizers' lint and `pytest --nbmake` checks on
  this folder, and on a fresh Ubuntu machine installs ngspice-42 and the pinned PDK and compares a live SPICE
  run with the shipped results.
- Cached mode (the default, and what `pytest --nbmake` runs) needs only numpy and matplotlib and takes under a
  minute. Live mode installs ngspice, Icarus Verilog and the sky130 PDK (open_pdks
  `0fe599b2afb6708d281543108caf8310912f54af`) and simulates 60 clock cycles in ngspice.
- The workflows in `.github/workflows/` use `**/*.ipynb` without `shopt -s globstar`, which does not reach
  `ISSCC27/submitted_notebooks/*/`. With globstar on, all their steps pass on this folder.

### License

Apache License 2.0 (`LICENSE` in the folder).

### AI use

AI coding assistants were used in this project. All results come from open-source tools (ngspice, the sky130 PDK,
OpenLane, Magic, KLayout, netgen, Python), and the author is responsible for all content.
