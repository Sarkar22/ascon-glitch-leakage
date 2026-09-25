<!-- SPDX-License-Identifier: Apache-2.0 -->
# Netlist generator and Python models

Regenerate everything and check it (from the repository root; host python3 + numpy, iverilog, sky130A PDK
at `$PDK` or `~/.ciel/sky130A`):

```
python3 gen/make_variants.py && python3 tb/run_iverilog.py && python3 model/probing.py && python3 -m unittest discover -s model/tests
```

1. `gen/make_variants.py` builds the S-box variants into `build/<V>/` (`dut.v`, `dut.sp`, `ports.json`,
   `graph.json`; `build/` is git-ignored). Variants: `U` unmasked, `N` naive DOM, `D` DOM with register barrier
   (the three of `docs/KILL_TEST.md`), and `DA`, a control that is `D` with the S-box input affine layer in front of
   the input registers. `gen/netlist.py` holds the builder, the capacitance estimate and the Liberty timing
   annotation; `gen/pdk.py` reads pin orders from the PDK SPICE/Verilog and delays from the tt Liberty.
2. `tb/run_iverilog.py` simulates every `dut.v` with the PDK's functional Verilog models (exhaustive inputs plus 2,000
   random rows, with and without `USE_POWER_PINS`) and compares with the Python model and the S-box.
3. `model/probing.py` runs the exact first-order probing checks (value and glitch-extended models) and writes
   `results/probing/<V>.json`.
4. The unit tests rebuild the variants in a temporary directory and check the netlists, stimulus, models, TVLA and
   CPA. With `ASCON_REF_DIR` pointing to the zero-shadow-aead checkout they also compare the S-box with the
   author's Python model and RTL (`python3 model/ascon_sbox.py` prints the same checks).

## Contract with the SPICE runner (`sim/`)

- `ports.json`: `ports` = `CLK`, inputs, outputs, `VPWR`, `VGND` (the `.subckt` order); `inputs`/`outputs` with
  `role` (`plain`, `share0`, `share1`, `rand`) and `bit` (x0 is the MSB of a 5-bit value); `latency` 1 or 2.
- Stimulus: `model/stimulus.py` writes a uint8 array (rows, inputs) in `inputs` order plus a `.meta.npz`
  (class label, x, mask, r; for `cpa` also iv, key, nonce). Share 1 is the mask: `xs1 = mask`, `xs0 = x ^ mask`.
- Row k is captured by the input flip-flops at the edge that starts its window; for latency 2 a row's trace spans
  two clock windows, as in the runner.

## Models

- Level 1, `model/toggle.py`: zero-delay toggle count per window (unweighted, load-cap weighted, rising only).
- Level 2, `model/glitch.py`: transport-delay event simulation with per-arc Liberty delays, every transition
  binned in 10 ps steps on the runner's window grid (`params_from_manifest` reads a SPICE run's timing).
- `model/tvla.py` (online Welch t, first and second order), `model/cpa.py` (online Pearson CPA),
  `model/run_models.py` (TVLA/CPA on the level-1/2 models of one variant from the command line).

Estimates are pre-layout and documented where they are made: wire cap 1 fF + 0.5 fF per fanout pin on every net
(written into `dut.sp`); model load cap = wire cap + Liberty pin caps (+ 2 fF on output ports, the runner's load);
delays at the driver's output slew and that load. Clock-tree and flip-flop-internal power are not in the Python
models.
