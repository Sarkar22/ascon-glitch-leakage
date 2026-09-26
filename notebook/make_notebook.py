# SPDX-License-Identifier: Apache-2.0
"""Build notebook/ascon_glitch_leakage.ipynb (cells without outputs) from the text below.

The narrative lives here so that the numbers it quotes from the committed result files are filled
in from them: a placeholder <<key>> in a markdown cell is replaced by nbdata.fmt_headline()[key]
(read from results/kill_test/summary.json, results/probing/*.json, results/key_recovery/,
results/cost/, results/layout/ and results/pex/). A few numbers from the reviews in docs/reviews/ are fixed text. Re-run this script
whenever the results change, then execute the notebook to refresh its saved outputs:

  python3 notebook/make_notebook.py
  jupyter nbconvert --to notebook --execute --inplace notebook/ascon_glitch_leakage.ipynb

Markers for work that is not done yet: "TODO(user)" (the author must fill it in) and
"TODO(setup)" (the measured live-mode run time). Section 6 (layout and post-layout) is filled
from results/layout/summary.json and results/pex/summary_postlayout.json (data/layout__*, pex__*).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nbdata                                         # noqa: E402

OUT = os.path.join(HERE, "ascon_glitch_leakage.ipynb")
COLAB = ("https://colab.research.google.com/github/sscs-ose/sscs-ose-code-a-chip.github.io/blob/main/"
         "ISSCC27/submitted_notebooks/ascon_glitch_leakage/ascon_glitch_leakage.ipynb")

CELLS = []


def md(text):
    CELLS.append(("markdown", text.strip("\n")))


def code(text):
    CELLS.append(("code", text.strip("\n")))


# ================================================================= title and first screen
md(r"""
<!-- SPDX-License-Identifier: Apache-2.0 -->
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](""" + COLAB + r""")

# Safe on Paper, Leaky in SPICE
### Pre-silicon glitch-leakage assessment of a masked Ascon S-box on SkyWater sky130, at three fidelity levels

**IEEE SSCS Code-a-Chip, ISSCC 2027** &nbsp;|&nbsp; License: Apache-2.0 (see `LICENSE`) &nbsp;|&nbsp;
Tools: <<ngspice>>, sky130A (open_pdks `<<pdk_commit>>`), Icarus Verilog, OpenLane v1 (Yosys, OpenROAD, Magic,
KLayout, Netgen), Python, NumPy, Matplotlib

| Name | Affiliation | Role | IEEE member | SSCS member | Contact |
|---|---|---|---|---|---|
| Emon Sarkar | University of Waterloo, Electrical and Computer Engineering | author | yes | no | TODO(user): e-mail |
""")

md(r"""
## The claim, on one screen

**A first-order masked Ascon S-box that the zero-delay model certifies as secure leaks at first order in
transistor-level simulation on sky130.** The leak comes from the *timing* of the unregistered logic: glitches
and data-dependent arrival times. An exact glitch-extended probing check, which runs in seconds, names the nets
that carry it. With DOM's register barrier moved *behind Ascon's input affine layer*, no first-order leak shows
up within the <<DA_n>> traces we simulated.

| Variant (same cells, same stimulus rows) | zero-delay model | glitch-extended probing (exact) | transistor-level SPICE, sky130 tt | after place and route (extracted layout, SPICE) |
|---|---|---|---|---|
| **N**, naive DOM, no register barrier | secure: max\|t\| <<N_l1>> on the same <<N_n>> rows, below 4.5 up to <<l1_100k_n>> rows | <<N_probe_fail>> of <<N_nets>> nets insecure | **leaks**: max\|t\| **<<N_t>>** at <<N_n>> traces, above 4.5 from <<N_first>> on | **still leaks**: <<pl_N_t>> at <<pl_N_n>> traces (<<pl_N_pre_t>> before layout on the same rows) |
| **D**, DOM with the barrier in the textbook place | secure (<<D_l1>>) | <<D_probe_fail>> nets insecure | leak confirmed on <<D_leaky_count>> nets; in the supply current <<D_t>> at <<D_n>> traces, although the timing-aware model predicts <<D_l2cap>> (cap-weighted; <<D_l2>> with the worst weighting): **not seen** | not laid out |
| **DA**, DOM with the barrier after the affine layer | secure (<<DA_l1>>) | <<DA_probe_fail>> nets insecure | **no first-order leak detected**: <<DA_t>> at <<DA_n>> traces | **none detected**: <<pl_DA_t>> at <<pl_DA_n>> traces |

The threshold is \|t\| > 4.5 (fixed-vs-random TVLA). At <<DA_n>> traces, a leak <<DA_detect_frac_words>> as strong as N's would
reach 4.5 on average, so DA's result rules out leaks of that size and larger, not every leak. A profiled attack on the same
traces (§5, post hoc) reaches a success rate of <<kr_N_bits_sr>> on N's two key bits at <<kr_N_n>> traces per key, with one
point of interest per key bit, chosen after the default attack had missed key bit $x_2$ (default: success rate <<kr_N_sr>>).
It finds no key in DA at first order: at <<kr_DA_n>> traces per key it would find a leak <<kr_DA_alpha_words>> as strong as N's, so
TVLA is more sensitive. **After place and route** (OpenLane; DRC, LVS and antenna clean) and capacitance-only
extraction, a registered test on the same stimulus rows gives the same verdicts (§6). N still leaks, as strongly as
before layout and <<pl_N_shift_ns>> ns later in the cycle. DA shows no first-order leak at <<pl_DA_n>> traces, where TVLA
would reach 4.5 on average for a leak <<pl_DA_detect_frac>> times as strong as N's post-layout one. The fix costs
<<cost_DA_area_vs_N_pct>> % more cell area and <<cost_DA_energy_vs_N_pct>> % more energy per evaluation in the simulated
supply current than N (<<cost_DA_total_vs_N_pct>> % with an estimate of the flip-flops' clock-pin charge; both for pipelined
use), and no extra randomness (§7). After layout, where the clock tree also draws from the simulated supply, DA's
core is <<lay_core_DA_vs_N_pct>> % larger and its energy per evaluation <<pl_energy_DA_vs_N_pct>> % higher. **Limits:** this is
simulation of the pre-layout netlists and of the extracted (capacitance-only) layouts at one corner (tt, 27 °C,
1.8 V), with an ideal supply and no measurement noise. It is not silicon. Section 8 lists every limit. Figure 1
shows the three SPICE t-curves.
""")

code(r"""
# SPDX-License-Identifier: Apache-2.0
# Setup: locate the project files, choose the run mode, load the helpers.
# On Colab the submission folder is fetched first. setup_env.setup() finds
# (on Colab: installs) ngspice and the sky130 PDK and picks the mode: 'live'
# when every tool is there, else 'cached' (plots the data/ folder only).
import os
import subprocess
import sys

UPSTREAM = 'https://github.com/sscs-ose/sscs-ose-code-a-chip.github.io'
FOLDER = 'ISSCC27/submitted_notebooks/ascon_glitch_leakage'
if 'google.colab' in sys.modules and not os.path.exists('nbdata.py'):
    subprocess.run(['git', 'clone', '--depth', '1', '--filter=blob:none',
                    '--sparse', UPSTREAM, 'code-a-chip'], check=True)
    subprocess.run(['git', '-C', 'code-a-chip', 'sparse-checkout', 'set',
                    FOLDER], check=True)
    os.chdir(os.path.join('code-a-chip', FOLDER))
sys.path.insert(0, os.getcwd())

try:
    import setup_env          # environment helper in this folder
except ImportError:
    setup_env = None
ENV = setup_env.setup() if setup_env else None      # prints what it found
MODE = getattr(ENV, 'mode', 'cached')

import nbanim
import nbdata
import nbexplorer
import nbfigs

H = nbdata.fmt_headline()
print('run mode:', MODE, '| data from', nbdata.source() + '/',
      '| results dated', H['generated'])
""")

md(r"""
**Figure 1.** Welch \|t\| of the DUT's supply current against time, for the three masked variants, from the
per-sample t-curves in `data/tcurve_*.csv` (copies of `results/kill_test/`). The zero-delay model has no time axis: it gives
one value per row (green line). N's window is one 4 ns clock cycle; D and DA take two cycles (second edge at 4 ns).
""")

code(r"""
nbfigs.show(nbfigs.headline())
""")

md(r"""
## Abstract

Masking is the standard countermeasure against power side-channel attacks. Ascon, standardized by NIST in
SP 800-232 for constrained devices, is the cipher it will protect most often at the edge. Whether a masked
netlist is secure is usually checked in a zero-delay model, which cannot see glitches. We build one masked Ascon
S-box column from explicit `sky130_fd_sc_hd` cells in four variants: unmasked (U), naive domain-oriented masking
without a register barrier (N), DOM with its register barrier in the textbook place (D), and DOM with the barrier
after Ascon's input affine layer (DA). We assess the *same* netlists at three fidelity levels: a zero-delay
toggle model, a timing-aware gate-level model with Liberty delays, and transistor-level ngspice simulation with
the sky130 foundry models. An exact probing check (value and glitch-extended models) runs alongside. The test protocol
was written down before any SPICE trace existed (pre-registered): fixed-vs-random TVLA with fresh masks in every
row. N is secure in the zero-delay model (max\|t\| <<N_l1>>) but leaks in SPICE (<<N_t>> at <<N_n>> traces). The leak
sits in the evaluation, <<N_peak_ns>> ns after the clock edge. The nets whose own transitions carry it are nets
that glitch-extended probing flags. Textbook DOM (D) still fails the probing check, because Ascon's affine layer
sits between its input registers and its AND gates. Its net-level leak is visible in SPICE node voltages, but it
does not show in the supply current at <<D_n>> traces, where the timing-aware model predicts max\|t\| <<D_l2cap>>
(cap-weighted; <<D_l2>> with the worst of three weightings). DA passes the probing check and shows no first-order leak at
<<DA_n>> traces. N and DA were then placed and routed with OpenLane (DRC, LVS and antenna clean; the generator's cells
unchanged) and extracted with Magic (capacitance only). A post-layout test, registered with fixed trace counts while
the campaigns were running, gives the same verdicts on the same stimulus rows: N still leaks (<<pl_N_t>> at <<pl_N_n>> traces; <<pl_N_pre_t>> before
layout), <<pl_N_shift_ns>> ns later, and DA shows no first-order leak at <<pl_DA_n>> traces (<<pl_DA_t>>). A profiled template attack on the same traces, run after the kill test, recovers N's two key bits at
first order (success rate <<kr_N_bits_sr>> at <<kr_N_n>> attack traces per key) once one point of interest is chosen per
key bit; that choice was made after the default attack had missed one key bit (default success rate <<kr_N_sr>>). It
finds no first-order key in D or DA, where it would detect a leak <<kr_alpha_range>> times as strong as N's (TVLA: about
<<DA_detect_frac_of_N>>). The fix costs <<cost_DA_area_vs_N_pct>> % more cell area and <<cost_DA_energy_vs_N_pct>> % more energy per
evaluation in the simulated supply current than N (<<cost_DA_total_vs_N_pct>> % with an estimate of the flip-flops' clock-pin
charge; both for pipelined use), and no extra randomness; after layout, <<lay_core_DA_vs_N_pct>> % more core area and
<<pl_energy_DA_vs_N_pct>> % more energy per evaluation with the clock tree in the simulated supply. Every step uses open
tools and an open PDK, and every number in this text is read from a committed result file or review.
""")

md(r"""
## Contents

| § | Section | What it answers |
|---|---|---|
| 1 | Motivation | Why masked Ascon, why at the edge, why pre-silicon |
| 2 | Background | Ascon S-box, Boolean masking, DOM, glitches, probing models, TVLA |
| 3 | Method | Four variants, one netlist, three models, the protocol and its pre-registration |
| 4 | Results | N leaks; one clock cycle animated; which nets; D; DA; how far the cheap models go; noise; an explorer |
| 5 | Key recovery | What a profiled attacker gets from N, D and DA, and what "no key recovery" rules out |
| 6 | Layout and post-layout | N and DA through OpenLane, extraction and SPICE: does the leak survive place and route, and does the fix? |
| 7 | Cost of the fix | Area, energy, latency and randomness of U, N, D and DA (pre-layout), and N and DA after layout |
| 8 | Limitations | What these numbers do and do not show |
| 9 | Conclusion | Summary and next steps |
| 10 | References | With DOIs |
""")

md(r"""
## How to run

| Path | What runs | Time (estimate) |
|---|---|---|
| **Cached** (default; also what CI runs) | Reads the notebook's data set (`data/`, CSV files and a few JSON summaries, listed with hashes in `data/MANIFEST.csv`) and draws every figure, table and the explorer | under 1 min |
| **Live** (Colab or any Linux with the setup helper) | Also installs ngspice and the sky130 PDK, regenerates the netlists, re-runs the probing check and the level-1/2 models, re-derives the animation, and simulates a few clock cycles of N in ngspice | TODO(setup): measure; target 10 min |
| **Full reproduction** (outside the notebook) | All SPICE campaigns of §4, with the commands in `docs/KILL_TEST.md` ("Reproduce"); then the key recovery of §5 (`analysis/key_recovery.py`), the layouts and post-layout campaigns of §6 (`layout/README.md`, `docs/POSTLAYOUT.md`) and the cost table of §7 (`analysis/cost_table.py`) | <<spice_wall_h>> h of wall clock for the first run (10 ngspice processes on one laptop), plus about 18 h on 6 CPUs to extend DA and D to 20,000 rows; the key recovery about 25 min with 3 processes; the two post-layout campaigns <<pl_wall_h>> h of wall clock on 6 CPUs, including a pause while the laptop was suspended |

Run the cells top to bottom. The first code cell chooses the mode and prints what it found. Every figure is drawn
from `data/`, which `make_cached_data.py` exports from `results/` and the SPICE runs. A review re-ran the kill
test's reproduction and got its `results/` bit for bit (`docs/reviews/repro-code.md`); the layout and post-layout
steps of §6 were not re-run that way.
""")

# ================================================================= 1 motivation
md(r"""
## 1. Motivation

**Edge devices need cryptography that survives physical access.** A sensor node, a medical patch or a
car's control unit runs its cipher where an attacker can put a probe on the supply pin. The attacker then
correlates the current with the data. This is differential power analysis. Masking is the standard answer: every
secret-dependent value is split into random shares, so that no single wire carries information about the secret.
The ISSCC 2027 theme, *Trusted Sustainable Silicon Intelligence from Edge to Cloud*, asks for exactly this kind
of trust at the edge.

**Ascon is now the lightweight standard.** NIST standardized the Ascon family in SP 800-232 [2] for constrained
devices. Its 5-bit S-box has algebraic degree 2, so a masked Ascon needs only five masked AND gates per S-box
column. That is why Ascon is the textbook case for low-cost masking [1, 11].

**The gap is between the model and the circuit.** Masking is proven secure in a model where every wire
settles once per cycle. Real CMOS gates see their inputs arrive at different times: an output can switch
briefly before it settles (a *glitch*), and *when* it switches can depend on the data. Mangard et al. showed in
2005 that glitches break masked gates [3]. The fixes are threshold implementations [4] and
domain-oriented masking (DOM) with a register barrier [5], and the checks are the robust (glitch-extended) probing
model [6] and tools such as SILVER [7] and PROLEAD [8]. A zero-delay or RTL simulation, the check that a
standard digital flow provides, cannot see any of these effects. Unprotected Ascon hardware is known to fall to
power analysis [14].

**What this notebook adds.** On an open PDK and with open tools only, we take *one* netlist per variant through
four views: an exact probing check, a zero-delay model, a timing-aware model and transistor-level SPICE. We then
ask three things. Does the leak that theory predicts appear in the foundry transistor models? Which cheap model
predicts it? And what does the fix need, and cost, in a real Ascon datapath? The test protocol was fixed before
the first SPICE trace (§3.6), and the negative results are reported as they came out.
""")

# ================================================================= 2 background
md(r"""
## 2. Background

### 2.1 The Ascon S-box

Ascon's state is five 64-bit words; the S-box acts on one bit column $x = (x_0, x_1, x_2, x_3, x_4)$, with
$x_0$ the most significant bit. In the bitsliced form of SP 800-232 [2]:

$$
\begin{aligned}
&x_0 \mathrel{\oplus}= x_4,\quad x_4 \mathrel{\oplus}= x_3,\quad x_2 \mathrel{\oplus}= x_1 &&\text{(input affine layer)}\\
&t_i = \overline{x_i}\, x_{i+1}\quad (i = 0..4,\ \text{indices mod } 5) &&\text{(the only nonlinear part: 5 ANDs)}\\
&x_i \mathrel{\oplus}= t_{i+1} &&\\
&x_1 \mathrel{\oplus}= x_0,\quad x_0 \mathrel{\oplus}= x_4,\quad x_3 \mathrel{\oplus}= x_2,\quad x_2 = \overline{x_2} &&\text{(output affine layer)}
\end{aligned}
$$

Keep the **input affine layer** in mind. It makes the two inputs of three of the five ANDs share a variable:
$t_1 = \overline{x_1}\,(x_2 \oplus x_1)$, and similarly $t_3$ and $t_4$. That detail decides §4.4.

### 2.2 First-order Boolean masking

Each secret bit is split into two shares, $x = x^{(0)} \oplus x^{(1)}$, with $x^{(1)}$ a fresh uniform random mask.
Linear operations (XOR, NOT) work share by share; NOT acts on share 0 only. A circuit is *first-order probing
secure* [12] if the value of any single wire is statistically independent of the unshared $x$. If every wire
leaked only its own settled value, the *mean* supply current would then not depend on $x$; a first-order leak is a
dependence of the mean. The *variance* can still depend on $x$, which is why second-order tests are expected to
fail.

### 2.3 Domain-oriented masking (DOM) of an AND

Every Ascon AND has the form $z = \overline{a}\,b$ ($a = x_i$, $b = x_{i+1}$ after the affine layer). With shares
$a^{(0)}, a^{(1)}, b^{(0)}, b^{(1)}$, NOT on share 0 only, and one fresh random bit $r$ (DOM-indep [5]):

$$
z^{(0)} = \underbrace{\overline{a^{(0)}}\, b^{(0)}}_{p_{00}} \oplus
\underbrace{\big(\overline{a^{(0)}}\, b^{(1)} \oplus r\big)}_{p_{01}},
\qquad
z^{(1)} = \underbrace{a^{(1)} b^{(1)}}_{p_{11}} \oplus \underbrace{\big(a^{(1)} b^{(0)} \oplus r\big)}_{p_{10}} .
$$

The four terms XOR to $(\overline{a^{(0)}} \oplus a^{(1)})(b^{(0)} \oplus b^{(1)}) = \overline{a}\,b$. The
*cross-domain* products $m_{01} = \overline{a^{(0)}}\,b^{(1)}$ and $m_{10} = a^{(1)} b^{(0)}$ combine one share of each input. They are
refreshed with $r$, and DOM registers all four partial products before they are XORed together (integrated). The
register is the *barrier*: it stops glitches of one domain from meeting the other domain's values in the
integration XOR. This is secure only if $a$ and $b$ are independent. If they share a variable, as in $t_1$ above,
then the product $m_{01}$ sees both shares of that variable.

### 2.4 Glitches and the glitch-extended probing model

In CMOS, the supply delivers the charge $C_k V_{DD}$ when net $k$ rises. The supply current is therefore a sum of
pulses at the times $t_k$ when nets switch:
$I_{DD}(t) \approx \sum_k C_k V_{DD}\, h(t - t_k)$, where $h$ is the pulse shape of one transition. A zero-delay model counts one settled toggle per net and
cycle, and loses the times $t_k$ and every extra transition. But a glitch or a late transition happens only for
certain input *orders*, and the order depends on the data. In the **glitch-extended (robust) probing model** [6],
a probe on a combinational net sees every *stable* signal in its combinational fan-in cone (register outputs
and inputs, not crossing a register). A design is first-order secure in this model if the joint distribution of
each cone's stable signals is independent of $x$. This model covers both glitch pulses and data-dependent arrival
times. We use the word *glitch* in this broad sense: any timing effect of unregistered logic.

### 2.5 TVLA: the leakage test

Test vector leakage assessment [9, 10, 13] compares traces of a **fixed** input with traces of **random** inputs.
The two classes are interleaved at random, and the masks are fresh in every trace. At every time sample it
computes Welch's $t$:

$$
t = \frac{\mu_F - \mu_R}{\sqrt{s_F^2/n_F + s_R^2/n_R}},\qquad |t| > 4.5 \ \Rightarrow\ \text{first-order leakage}.
$$

For a true standardized difference $\delta = (\mu_F-\mu_R)/s$ and $n$ traces split evenly, $t \approx \delta\sqrt{n}/2$.
Two consequences are used throughout. First, a real leak grows like $\sqrt{n}$. Second, a run that stays below 4.5 with
$n$ traces rules out only effects with $\delta \gtrsim 9/\sqrt{n}$. For N, $\delta_N = <<dN_sd>>$ standard
deviations.
""")

# ================================================================= 3 method
md(r"""
## 3. Method

### 3.1 Design under test: four variants of one S-box column

All four variants register their inputs, fresh random bits and outputs in `dfxtp_1` flip-flops. They are generated
**structurally from explicit `sky130_fd_sc_hd` cells** (`gen/make_variants.py`). No logic synthesis runs, so no
optimizer can merge shares. Each `~a & b` is DOM-indep with its own fresh bit $r_i$ (§2.3). D registers all 20
partial products and the 10 linear terms before integration. DA is D with the input affine layer moved *in front of*
the input registers. In a round-based core, that corresponds to merging the affine layer into the previous round's
linear layer, before the state register.
""")

code(r"""
nbfigs.show_md(nbfigs.variants_table())
""")

md(r"""
### 3.2 One netlist, three models

One generator writes the structural Verilog (`dut.v`), the SPICE subcircuit (`dut.sp`) and a gate graph
(`graph.json`) for each variant. All models therefore describe the same cells, nets and wire capacitances.
Icarus Verilog checks every variant against the S-box with the PDK's own cell models, exhaustively and on
2,000 random rows.

* **Level 1, zero-delay** (`model/toggle.py`): per clock cycle, the number of nets whose settled value
  changed, optionally weighted by the net's load capacitance. This is what an RTL or zero-delay flow can see.
* **Level 2, timing-aware** (`model/glitch.py`): an event-driven simulation with per-arc delays from the sky130
  `tt` Liberty file at each net's load. Transport delay keeps every glitch, and every transition is binned in
  time on the SPICE runner's 10 ps grid.
* **Level 3, transistor level** (`sim/spice_campaign.py`): ngspice [17] with the sky130 [16] `tt` models, 27 °C, 1.8 V, a
  4 ns clock and trapezoidal integration (maximum step 10 ps). The trace is the DUT's own supply current $i(V_{PWR})$
  in 10 ps bins. It is the ground truth of this study; §8 says what it leaves out.

**Figure 2.** The workflow.
""")

code(r"""
nbfigs.show(nbfigs.workflow())
""")

md(r"""
### 3.3 The exact probing check

`model/probing.py` enumerates all $32^3 = 32{,}768$ combinations of unshared input, mask and fresh bits, with
the flip-flops transparent. For every net it compares the exact distributions, with no sampling and no threshold:
the net's value (value model), and the joint value of all stable signals in its combinational cone
(glitch-extended model). It runs in seconds and needs no SPICE. The table is read from `data/probing_nets.csv`.
""")

code(r"""
nbfigs.show_md(nbfigs.probing_table())
""")

md(r"""
No variant fails the value model, so all three are secure in the zero-delay sense (§4.1 shows why that is
exact). In the glitch-extended model N fails on <<N_probe_fail>> nets and D on <<D_probe_fail>>. D's failing nets are
the cross-domain products of $t_1$, $t_3$ and $t_4$ (`m01`, `p01`, `m10`, `p10`), the three ANDs whose inputs share a
variable through the input affine layer. DA fails on none.

### 3.4 SPICE ground truth

Each campaign simulates thousands of consecutive clock cycles per ngspice process, in parallel chunks. Four
warm-up rows are replayed before each chunk. Inputs change 1 ns before the capturing edge, far outside the
flip-flops' setup and hold windows. Every net carries an estimated wire capacitance of 1 fF plus 0.5 fF per fanout
pin, and every output port a 2 fF load. **Every simulated row's registered output was checked against the S-box:
0 mismatches in every campaign.** The runner's settings, the PDK and ngspice versions and the netlist hashes are
recorded in the kill-test summary (`data/kill_test_summary.json`). In live mode the next cell simulates a few
clock cycles in ngspice.
""")

code(r"""
demo = getattr(setup_env, 'spice_demo', None)
if MODE == 'live' and demo is not None:
    demo()        # wire-up point: a few clock cycles in ngspice
else:
    print('cached mode: the SPICE results are read from data/')
""")

md(r"""
### 3.5 Stimulus and TVLA protocol

* **Fixed vs random** (non-specific, first order): fixed input $x = \mathtt{0x0B}$ against uniform random $x$.
  The class of each row is drawn at random, and masks and fresh bits are uniform and fresh in every row for both
  classes (`model/stimulus.py`, seeded).
* N, D and DA read **the same stimulus file** (20,000 rows), so the three variants are compared on identical
  rows. Levels 1 and 2 are run on exactly the rows SPICE simulated.
* The models start from the reset state, so the first $L+1$ rows ($L$ = latency) are dropped at every level.
* **Controls:** N random-vs-random (both classes random: must stay below 4.5; <<Nrvr_t>> at <<Nrvr_n>> traces), and N
  with the masks forced to zero (must leak: <<Nmo_t>> at <<Nmo_n>> traces, above 4.5 from <<Nmo_first>> on).
* **Sanity:** U (unmasked) reaches <<U_t>> at <<U_n>> traces, so the SPICE traces carry data-dependent current.
* Pass/fail uses noiseless traces at the runner's 10 ps resolution. Coarser bins, the charge per cycle and
  added noise are reported alongside (§4.7).

### 3.6 Pre-registration, amendments and what failed

The question, the variants U/N/D, the protocol and the pass/fail criteria were written into `docs/KILL_TEST.md`
before any trace was simulated. Three amendments were added after the Python models and the probing check had run,
and before the first SPICE campaign:
**A1** adds DA, because the probing check showed that D, as registered, is not robust to glitches.
**A2** fixes the CPA hypothesis of K1. **A3** sets the trace budgets. The order of events is reconstructed in
`docs/reviews/repro-code.md` from the file history and the SPICE job log. The repository's first commit came after
the campaigns, so git alone does not timestamp the pre-registration. Adversarial reviews (`docs/reviews/`, one file
each) tried to refute the results. Their corrections are applied in this text.

By the letter of the registered rule the outcome was **NO-GO**. **K1 failed on its CPA part:** a one-column CPA with two
key bits and four nonce values cannot separate the key guesses (ranks <<K1_cpa_ranks>>). The unmasked traces do
carry data (TVLA <<U_t>>); the design of the check could not separate the keys. §5 answers K1's question post hoc with
a profiled attack, but K1 stays failed as registered. The author chose to continue on the strength of K2, K3, the
controls (C) and the localization of §4.3. K5 was still incomplete at that point; it passed later, at <<DA_n>> traces. The
table is generated from `summary.json`.
""")

code(r"""
nbfigs.show_md(nbfigs.criteria_table())
""")

# ================================================================= 4 results
md(r"""
## 4. Results

### 4.1 N leaks in SPICE while the zero-delay model calls it secure

**Figure 3** plots max\|t\| over the window against the number of traces, for all three model levels. The dotted
line is the growth that an effect as strong as N's would follow ($t = \delta_N \sqrt{n}/2$). In N the SPICE curve
crosses 4.5 at <<N_first>> traces, stays above from there on, and grows like $\sqrt{n}$ to <<N_t>> at <<N_n>> traces,
as a real effect must. The zero-delay model ends at <<N_l1>> on the same rows (worst of three weightings) and stays
below 4.5 at every checkpoint up to <<l1_100k_n>> rows (at most <<N_l1_100k_cp>>).
""")

code(r"""
nbfigs.show(nbfigs.maxt_vs_traces())
""")

md(r"""
The zero-delay model is not just unlucky here: it **cannot** see this leak. The value-model probing check (§3.3)
shows that every net's settled value, and every cell's settled input tuple, is independent of $x$
(`docs/reviews/sca-method.md`, check 1). With fresh masks in every row, the expected toggle count is therefore the
same for both classes, under any weighting. So the leak is not in *what* N computes but in *how* it gets there.

What makes the SPICE result trustworthy (details and re-runs in `docs/reviews/`):
* **Where:** the leak sits in the evaluation, 0.6 to 1.3 ns after the capturing edge, with its peak at
  <<N_peak_ns>> ns. The other parts of the cycle stay below 4.5: the clock edge (\|t\| 1.94), the flip-flops'
  clock-to-Q (0.87), the clock's falling edge (3.1) and the input edges (1.9). The fixed-minus-random mean current
  is a bump of up to 27 µA.
* **Replication:** each half of the data shows it at the same sample with the same sign. It also appears
  *without a fixed class*: an ANOVA of the supply current over $x$ in the random-vs-random campaign gives
  $F = 21.8$ at the same 0.945 ns.
* **Not numerics:** re-simulating 240 rows (600 in a second check) with a 1 ps (2 ps) step and much tighter
  tolerances reproduces the bump (27.4 against 27.7 µA; 31.73 against 31.69 µA), and the numerical error does not
  depend on the class.
* **Energy as well as timing:** on the total charge per cycle the fixed-vs-random \|t\| is only <<N_tq>>, but an ANOVA over
  $x$ on the same charge is significant. N's leak is concentrated in the timing of the evaluation; its total
  energy also depends on $x$, more weakly.
""")

md(r"""
### 4.2 One input change, animated

What happens inside one clock cycle? The animation follows AND $t_1 = \overline{x_1}\,(x_2 \oplus x_1)$ along
share 0 of its output, in N (top) and DA (bottom), for one stimulus row. It uses the level-2 event model. Every
transition is drawn at its Liberty delay; glitch pulses are shaded.

![Glitch propagation in N and DA, one input change](media/glitch_N_vs_DA.gif)

* **In N**, $b^{(1)} = x_2^{(1)} \oplus x_1^{(1)}$ is computed *after* the input registers, so it arrives late
  and glitches. The cross-domain product $m_{01} = \overline{a^{(0)}}\, b^{(1)}$ then switches while it
  sees both shares of $x_1$. From there the glitch runs through three more XOR levels (the integration
  $p_{00} \oplus p_{01}$, the S-box XOR and the output layer) to the output register's D pin.
* **In DA**, $b^{(1)}$ comes straight from a register, so no cone of the AND holds a variable twice. The
  products can still glitch (here $p_{01}$, from the skew between $r_1$ and $m_{01}$), but those glitches end at
  the barrier flip-flops' D pins. In the next cycle the integration starts from registered values.

The next cell rebuilds the animation (live mode) or reads the cached events, and draws the last frame (Figure 4).
The row shown was chosen because its glitch runs the whole path. Other rows differ, and the statistics are in
§4.3. SPICE adds a second effect that one row cannot show: the cross-domain ANDs that leak first rarely glitch in
SPICE. Their leak comes mostly from *when* their single transition happens (`docs/reviews/spice-circuit.md`, F2).
""")

code(r"""
EV = nbanim.events(MODE)
GIF = os.path.join('media', 'glitch_N_vs_DA.gif')
if MODE == 'live' or not os.path.exists(GIF):
    nbanim.save_gif(EV, GIF)
nbfigs.show(nbanim.draw(EV, t_now=5.8))
""")

md(r"""
### 4.3 Which nets carry N's leak

A second SPICE run on the first <<N_nodes_rows>> traces saved every net's voltage. For each net it counts VDD/2
crossings in 20 ps bins and runs the same fixed-vs-random t-test on those counts. The re-run reproduces the
campaign's supply current with correlation 1.000000. **Figure 5:** <<N_leaky_count>> nets exceed 4.5:
<<N_leaky_list>>. **All of them are flagged by glitch-extended probing.** The cross-domain
products (`m01`, `m10`) leak first, at 0.57–0.69 ns. Their integration nets (`ts`, `bs`) follow up to about 1 ns,
which is where the supply-current t peaks. Cross-domain nets that probing does *not* flag (the ANDs $t_0$ and
$t_2$, the same cell types) stay at \|t\| ≤ 3.3. On a permutation null over every net and bin, the maximum is about
4.2. Level 2 on <<N_l2_nets_rows>> rows gives the same picture: <<N_l2_nets>> nets leak, and every one is flagged.
""")

code(r"""
nbfigs.show(nbfigs.localization('N'))
""")

md(r"""
**Two structural causes, two fixes.** The flagged nets of N fall into two groups, and the node data show both
(`docs/reviews/spice-circuit.md`, F6).
1. *ANDs whose inputs share a variable* through the input affine layer ($t_1$, $t_3$, $t_4$). Their cross-domain
   products see both shares of $x_1$, $x_3$ or $x_4$ before any register. A barrier after the products does
   not help, because the product itself already leaks. D keeps this cause; DA removes it.
2. *Integration without a barrier*, even for the ANDs with independent inputs ($t_0$, $t_2$; for example `ts0_0`).
   When $a^{(0)}$ switches, $p_{00} = \overline{a^{(0)}} b^{(0)}$ switches if $b^{(0)} = 1$, and
   $p_{01} = \overline{a^{(0)}} b^{(1)} \oplus r$ switches if $b^{(1)} = 1$. If both switch, their skew makes a
   glitch on $p_{00} \oplus p_{01}$. Both switching needs $b^{(0)} = b^{(1)} = 1$, which happens only when the
   unshared $b = 0$, so whether the XOR glitches depends on $b$. DOM's register barrier removes this cause.
""")

md(r"""
### 4.4 Textbook DOM (D): a real net-level leak, not seen in the supply current

D has the register barrier that DOM prescribes, but it registers the partial products *after* Ascon's input affine
layer. The ANDs $t_1, t_3, t_4$ get inputs that share a variable, so their cross-domain products see both shares of
$x_1$, $x_3$ or $x_4$ before the barrier. Probing flags <<D_probe_fail>> nets. In SPICE, <<D_leaky_count>> of them switch in a
class-dependent way (<<D_leaky_list>>; <<D_nodes_rows>> traces, Figure 6). **But the supply current stays at max\|t\|
<<D_t>> at <<D_n>> traces** (at most <<D_tmax_cp>> at any checkpoint), while the timing-aware model (level 2) predicts
<<D_l2cap>> on the same rows (cap-weighted; <<D_l2>> with the worst weighting). The pre-registered minimum for D was 10,000
traces; the run to <<D_n>> was exploratory, beyond it (`docs/KILL_TEST.md`, addendum). At this count TVLA would reach
4.5 on average for a leak <<D_detect_frac_words>> as strong as N's. So the leak that level 2 predicts for D does not show in the
supply current at <<D_n>> noiseless traces: if it is there, it is smaller than that. This is not a proof that D is
secure. The glitch-extended probing model, which is conservative by design, still flags it.

A circuit-level reason why it is small: D's cross-domain nets glitch as often as N's (2.30 vs 2.29 pulses per row).
But in D each glitch ends at one flip-flop D pin. In N it travels through three more XOR levels: glitches are 28 % of
N's switching charge and 8.7 % of D's (`docs/reviews/spice-circuit.md`, F5). Level 2 overstates D at 10 ps
resolution: in 100 ps bins it gives <<D_l2cap100>>.
""")

code(r"""
nbfigs.show(nbfigs.localization('D'))
""")

md(r"""
### 4.5 The fix: DA

Moving the input affine layer in front of the input registers (DA) gives the ANDs independent inputs. The same
DOM barrier then does its job. In the probing check, DA has **<<DA_probe_fail>> insecure nets**. In SPICE, **max\|t\| is
<<DA_t>> at <<DA_n>> traces** (at most <<DA_tmax_cp>> at any checkpoint; Figures 1 and 3), and level 2 agrees
(<<DA_l2>>, worst of three weightings). At this count TVLA would reach 4.5 on average for a leak $\delta \ge <<DA_detect_sd>>$ standard deviations. That is
<<DA_detect_frac_words>> of N's $\delta_N = <<dN_sd>>$, so DA rules out leaks of that size and larger. D and DA end at the same
max\|t\| at the same sample (<<DA_peak_ns>> ns, in the first cycle's clock-fall region), and their t-curves differ by at most
<<DDA_tdiff_near_peak>> within 30 ps of it. The likely source is circuitry that D and DA share, driven by the same stimulus rows,
for example the registers of the input bits that the affine layer leaves unchanged; this was not checked at the net
level. If so, the two maxima are one observation, not two. The second-order
t is large (<<DA_t2>>), as expected for two-share masking: first-order masking protects the mean, not the
variance. §7 prices the fix.
""")

md(r"""
### 4.6 How far can the cheap models be trusted?

The next table compares the three levels on the same rows. The charge-per-trace correlation measures how well a
model predicts *energy*. The level-2 lag is the time shift that best aligns its waveform with SPICE's.
""")

code(r"""
nbfigs.show_md(nbfigs.model_table())
""")

md(r"""
* **Level 1 gets the energy right and the security wrong.** Its per-trace charge correlates with SPICE at
  0.87–0.98, better than level 2, yet it misses N's leak entirely (§4.1).
* **Level 2 flags N and names the right nets** (§4.3). **It does not reproduce the leak's waveform, sign or
  timing**, and its per-sample \|t\| is not a prediction of SPICE's: its <<N_l2cap>> (cap-weighted) against SPICE's <<N_t>> is a
  coincidence. Figure 7 shows why. SPICE's t is a smooth positive hump; level 2's alternates in sign.
* **Level 2 and the pre-layout SPICE disagree by about 200 ps.** A large part of that comes from the SPICE cell
  netlists, which have no parasitics and switch faster than their Liberty characterization (clock-to-Q
  0.18–0.29 ns in SPICE against 0.31–0.41 ns in Liberty). Neither model is silicon.
* **Level 2 is pessimistic for D** at 10 ps resolution (§4.4).

So the probing check and level 2 are good *screening* tools, and SPICE remains the reference.
""")

code(r"""
nbfigs.show(nbfigs.model_vs_spice('N'))
""")

md(r"""
### 4.7 Robustness: added noise and limited bandwidth

A real measurement adds noise and low-pass filters the current. **Figure 8** adds white Gaussian noise to the SPICE
traces, at 0.5, 1 and 2 times the largest per-sample standard deviation of the noiseless traces (1x = <<N_noise_unit>> µA
for N). N stays detectable within <<N_n>> traces at 0.5x (above 4.5 from <<N_stable_noise0.5>> on) and at 1x (from
<<N_stable_noise1.0>> on), but not at 2x (<<N_t_noise2.0>>). DA ends below 4.5 at every noise level, and never stays above it:
at 1x it touches <<DA_noise1.0_tmax_cp>> at an early checkpoint (above 4.5 first at <<DA_noise1.0_first>> traces; D reaches
<<D_noise1.0_tmax_cp>>) and falls back. These are the small-sample false alarms that `docs/KILL_TEST.md` explains. Bandwidth, on the
noiseless N traces: <<N_t100>> in 100 ps bins, 10.6 in 1 ns bins, 9.5 after a 1 GHz first-order low-pass and 5.5 after
250 MHz (`docs/reviews/spice-circuit.md`, check 19). So the leak does not depend on a 10 ps probe.
""")

code(r"""
nbfigs.show(nbfigs.noise())
""")

md(r"""
### 4.8 Explore the TVLA yourself

The cached data set holds, for the four fixed-vs-random SPICE campaigns, Welch's t at 25 trace counts and the
per-class statistics (`data/tvla_t_checkpoints_*.csv`, `data/class_stats_*.csv`). That is enough to redo the test
with any amount of added noise. With
ipywidgets installed, move the sliders to choose the variant, the number of traces (checkpoint) and the noise (in
units of the largest noiseless per-sample standard deviation). Without it, the default views below are shown.
The noise is folded in statistically (described in `nbexplorer.py`). The cell also compares five noise draws
for N at 1x with the kill test's exact trace-by-trace result (<<N_t_noise1.0>>).

**Figure 9.** Default views: N without noise, N at 1x noise, and DA without noise.
""")

code(r"""
nbfigs.show(nbexplorer.static_panel())
exact, approx = nbexplorer.check_against_exact('N_tvla', 1.0)
print('N at 1x noise: exact %.2f; from the cached statistics %s'
      % (exact, ', '.join('%.2f' % a for a in approx)))
if not nbexplorer.interactive_panel():
    print('ipywidgets is not installed: the static views above are all.')
""")

# ================================================================= 5 key recovery
md(r"""
## 5. Key recovery: what does an attacker get?

TVLA says whether the current depends on the data; it does not say what an attacker can do with it (§8). This
section runs a profiled attack on the same SPICE traces. It is **post hoc**: it was designed after the kill test,
to answer the question that K1's CPA could not settle (§3.6), and it is not a registered criterion.

**Attack model.** One S-box column in Ascon's initialization: $x_0$ is an IV bit (known), $x_1, x_2$ are two key
bits (secret), and $x_3, x_4$ are two nonce bits (known, varying). Each (IV, key) pair is one scenario with four key
guesses. The attacker first *profiles* an identical device: from traces with known inputs it learns the mean trace
of each of the 32 inputs and the noise covariance (a *template*). It then *attacks* other traces, with known nonces
and an unknown key, and ranks the four guesses by how well each guess's predicted inputs explain those traces. The
traces are the random-class rows of the TVLA campaigns; the fixed 0x0B rows are never used. Profiling and attack
rows come from disjoint 50-row blocks with 3 unused guard rows in between, so no trace of one set depends on an
input of the other. Every number is averaged over <<kr_splits>> random splits and <<kr_trials>> random orderings of the
attack traces (`analysis/key_recovery.py`).

**Metric.** The key rank is the number of wrong guesses that score above the correct one. Its mean is the
*guessing entropy* (GE): 0 means the key is found, 1.5 is random guessing among four. The *success rate* (SR) is
P(rank 0); random is 0.25.

**Distinguishers.**
* The **Gaussian template** is the primary one. It was made primary after a review
  (`docs/reviews/stage2-key-recovery.md`, B2), for the structural reason given in the third point; on D and DA both
  distinguishers are at chance at first order, so no verdict there depends on that choice. Its points of interest
  (POIs) are the samples where the 32 input means differ most (ANOVA F); their number is chosen by cross-validation on
  the profiling rows.
* The same template with **per-key-bit POIs**: the top-F sample plus, for each key bit, the sample where that bit's
  effect *inside every combination of the other four bits* is largest. It was added post hoc, after a review found
  that the default POIs miss one of N's key bits (`docs/reviews/stage2-key-recovery.md`, B1).
* A **correlation** distinguisher is shown as secondary only. It centres the traces over the attack set, and that
  removes exactly the level shift between keys that a key bit's main effect produces.

**Null.** The same pipeline with the profiling labels permuted gives the null distribution (<<kr_perms>> draws per
configuration without added noise). Without added noise, the standard deviation of the null's final GE is
<<kr_null_sd_range>> for the default template and <<kr_null_sd_range_bits>> for the per-key-bit template on U, N, D and DA
(TVLA campaigns), and <<kr_Ucpa_null_sd>> for U on the K1 CPA traces, which have only four keys. A result is better than
chance when its GE falls below the null draws: $p$ = (1 + draws at or below the result) / (draws + 1), so with 20
draws $p$ = 0.048 means below every draw.

**Figure 10.** GE of the Gaussian template against the number of attack traces per key, from
`data/key_recovery__summary.json`. Gray: the null (mean ± 2 SD). The table below the figure lists the final values. Its
null column is the default template's; the per-key-bit template has its own null (N: <<kr_N_bits_null>> ± <<kr_N_bits_null_sd>>).
""")

code(r"""
nbfigs.show(nbfigs.key_recovery())
nbfigs.show_md(nbfigs.key_recovery_table())
""")

md(r"""
**N gives up both key bits at first order.** With the default POIs the template finds key bit $x_1$ (the top guess
has the right $x_1$ with probability <<kr_N_px1>>) but not $x_2$ (<<kr_N_px2>>): GE <<kr_N_ge>>, SR <<kr_N_sr>> at <<kr_N_n>>
attack traces per key. $x_2$ has no main effect at the leak's peak, but it does leak at first order through its
interactions with the other bits, later in the evaluation: the per-key-bit POI for $x_2$ falls at <<kr_N_x2_poi_ns>> ns
after the edge, against the main peak at <<N_peak_ns>> ns. With that POI the template reaches **GE <<kr_N_bits_ge>>, SR
<<kr_N_bits_sr>>** (the right $x_2$ with probability <<kr_N_bits_px2>>; null <<kr_N_bits_null>> ± <<kr_N_bits_null_sd>>,
$p$ = <<kr_N_bits_p>>). On the N_tvla campaign alone, <<kr_Ntvla_n>> traces per key, the per-key-bit POIs give GE
<<kr_Ntvla_bits_ge>> (default POIs <<kr_Ntvla_ge>>). With
added noise of 1x the template's GE rises to <<kr_N_noise1_ge>> (default) and <<kr_N_noise1_bits_ge>> (per-key-bit POIs) at
the same trace count. The correlation distinguisher stays at GE <<kr_N_corr_ge>> on noiseless N: it is blind to the main
effect that carries $x_1$.

**D and DA: no key recovery, and what that rules out.** D gives GE <<kr_D_ge>> at <<kr_D_n>> attack traces per key (null
<<kr_D_null>> ± <<kr_D_null_sd>>, $p$ = <<kr_D_p>>) and DA <<kr_DA_ge>> at <<kr_DA_n>> (null <<kr_DA_null>> ± <<kr_DA_null_sd>>,
$p$ = <<kr_DA_p>>). On its own, "no key recovery" says little. So N's first-order leak, scaled by a factor $\alpha$,
was added to the real D and DA traces at one sample, and the unchanged attack was run again (Figure 11; $\alpha = 1$
is N's own per-sample effect). At this data volume the template detects the injected leak from $\alpha$ =
<<kr_D_alpha>> on D (GE <<kr_D_alpha_ge>>; not at <<kr_D_below>>, GE <<kr_D_below_ge>>) and from $\alpha$ = <<kr_DA_alpha>> on DA
(GE <<kr_DA_alpha_ge>>; not at <<kr_DA_below>>, GE <<kr_DA_below_ge>>). Detected means a GE below all <<kr_perms>> null draws. TVLA on
the same campaigns already reaches 4.5 for a leak <<DA_detect_frac_words>> as strong as N's (§4.5).
So for D and DA the key recovery is a consistency check: it adds no sensitivity beyond the TVLA. The correlation
distinguisher misses the injected leak even at N's full strength (GE <<kr_DA_corr_full_ge>> on DA, <<kr_D_corr_full_ge>> on D),
which is why it is not the primary distinguisher.

**Figure 11.** D and DA: GE at the last checkpoint after adding $\alpha$ times N's first-order leak to the real
traces ($\alpha$ = 0: the real traces). The dotted line marks the leak size at which TVLA on the same campaign reaches
4.5 on average.
""")

code(r"""
nbfigs.show(nbfigs.key_recovery_injection())
""")

md(r"""
**Second order.** First-order masking does not protect the variance, so a univariate second-order template is
expected to work on the masked variants, and it partly does: on DA it reaches GE <<kr_DA_o2_ge>>, SR <<kr_DA_o2_sr>> at
<<kr_DA_n>> traces per key ($p$ = <<kr_DA_o2_p>>), and on D GE <<kr_D_o2_ge>>, SR <<kr_D_o2_sr>> at <<kr_D_n>> ($p$ = <<kr_D_o2_p>>). For N the second-order result (GE <<kr_N_o2_ge>>) is
not independent evidence: the centred square at a sample with a first-order mean shift carries that shift.

**K1, answered post hoc.** Templates from U's TVLA campaign recover U's key from the K1 CPA traces without added
noise (SR ≥ 0.9 from <<kr_Ucpa_from>> traces per key). This answers the question K1 was meant to settle, whether the
traces carry exploitable key information, but **K1 stays failed as registered**. With added noise the outcome
depends on the distinguisher. At 0.5x the template gives GE <<kr_Ucpa_noise0.5_tmpl_ge>> and the correlation
<<kr_Ucpa_noise0.5_corr_ge>> (SR <<kr_Ucpa_noise0.5_corr_sr>>); at 1x, <<kr_Ucpa_noise1_tmpl_ge>> and <<kr_Ucpa_noise1_corr_ge>>
(SR <<kr_Ucpa_noise1_corr_sr>>). All <<kr_Ucpa_n>> traces of a key are used there, so each of the four keys is one
deterministic outcome, and these numbers are coarse. The CPA campaigns keep the IV and key bits fixed from row to
row, so their traces draw <<kr_Ucpa_deficit>> % less charge than the U_tvla templates predict. The template, which
compares absolute levels, suffers from that mismatch between campaigns; the centred correlation does not.

**What the attack assumes.** A profiling device identical to the target (here: the same simulation), noiseless
traces unless noise is added, known nonces, and a two-bit key with four guesses. It is a lower bound on what an
attacker gets from N, not a certificate for D or DA.
""")

# ================================================================= 6 layout and post-layout
md(r"""
## 6. Layout and post-layout: does the leak survive place and route?

§4 simulated the generator's netlists with an estimated wire capacitance and the stock cell netlists, which carry no
parasitics (§8). To see whether its verdicts hold after physical design, N, DA and U were taken through OpenLane v1 on
`sky130_fd_sc_hd`, and N and DA were simulated again from their extracted layouts.

**Keeping the generator's netlist.** The flow must not change the circuit under test:
* Yosys only elaborates the structural netlist; there is no technology mapping.
* All resizer and buffering steps are off.
* The flow adds only the clock tree, tap, decap and fill cells.

`layout/summarize.py` checks the result. Every logic instance of the generator's netlist is in the final layout with
the same cell type and the same net on every pin. The table is read from `data/layout__summary.json`; its
capacitance row comes from `data/pex__summary_postlayout.json`.
""")

code(r"""
nbfigs.show_md(nbfigs.layout_table())
""")

md(r"""
**Figure 12.** Top: the N and DA layouts, rendered by KLayout with all drawn layers in the PDK colours. Each image is
scaled to its own die; the titles give the sizes. Bottom: the placements. Each logic cell is coloured by the share
domain of the net it drives, the cross-domain ANDs are black, and a hatched cell drives a net that glitch-extended
probing flags. In N the cross-domain ANDs sit between the share-0 and share-1 halves. Small copies of
`results/layout/*.png` are in `media/`.
""")

code(r"""
nbfigs.show(nbfigs.layout_figure())
""")

md(r"""
### 6.1 The post-layout SPICE model

Magic extracts every transistor with its drawn W, L and diffusion geometry, every capacitance to substrate and every
coupling capacitance between nets. It extracts no resistance: the blocks are under 90 µm across, and a 100 µm
minimum-width route with 20 fF of load adds under 2 ps (`layout/README.md`). The extracted netlist replaces the
generator's `dut.sp` in the unchanged SPICE runner. Three things change against §4's model:
* **Capacitance.** The routed wiring alone (OpenRCX) totals <<lay_N_cap_rcx>> fF on N's logic nets, the same as the
  pre-layout estimate (<<lay_N_cap_est>> fF). With the cells' own pin geometry, which the stock cell netlists lack,
  Magic extracts <<lay_N_cap_magic>> fF (<<lay_N_cap_ratio>>x). The layouts also add coupling between the share
  domains: <<lay_N_s0s1_fF>> fF between N's share-0 and share-1 nets, <<lay_DA_s0s1_fF>> fF in DA.
* **Timing.** A node run of 38 cycles of N measures the median flip-flop clock-to-Q at <<pl_ckq_post>> ns after the
  ideal clock edge, against <<pl_ckq_pre>> ns before layout. This includes the clock tree's insertion delay of about
  0.33 ns. The median last logic transition moves from <<pl_last_pre>> to <<pl_last_post>> ns (at most
  <<pl_last_post_max>>), still 2 ns before the next edge.
* **The clock tree.** Its buffers (N <<lay_N_cts>>, DA <<lay_DA_cts>> × `clkbuf_16`) and the flip-flops' clock pins
  now draw from the measured supply. This current does not depend on the data.

**Checks.** Every registered output of the post-layout campaigns matches the S-box, and matches the pre-layout output
of the same row: 0 mismatches in <<pl_N_rows>> rows of N and <<pl_DA_rows>> rows of DA. The campaigns use ngspice's KLU
solver. On the same netlists and 120 rows it agrees with the default solver used before layout: the charge differs
by at most <<pl_klu_rel>> (relative), and the data-dependent parts correlate at <<pl_klu_corr>>.

### 6.2 Post-layout TVLA

The criteria were registered in `docs/POSTLAYOUT.md` while the N campaign was running:
* **PL1:** N leaks after layout.
* **PL2:** DA does not.
* **PL3** (informational): where the t-peaks sit, and the smallest leak TVLA could detect in DA.

The trace counts were fixed: the first 5,000 rows for N and the first 10,000 rows for DA, of the stimulus that §4 used.
Before the registration the progress view had printed N's max\|t\| three times (2.55, 3.00 and 4.30 at 373, 748 and
1,498 traces). These looks are disclosed there, and neither trace count depended on them. The test is the kill
test's own code path. As a check, the same analysis run on the pre-layout campaigns reproduces their results exactly.
The table is read from `data/pex__summary_postlayout.json`.
""")

code(r"""
nbfigs.show_md(nbfigs.postlayout_table())
""")

md(r"""
**Figure 13.** Signed Welch t against time after layout (blue) and before layout on the same rows (gray), from
`data/pex__tcurve_*.csv`. Time counts from the ideal clock edge at the block's CLK pin.
""")

code(r"""
nbfigs.show(nbfigs.postlayout_tcurves())
""")

md(r"""
* **N's leak survives place and route under C-only extraction at tt.** On the same rows it is as strong as before
  layout: <<pl_N_t>> against <<pl_N_pre_t>> at <<pl_N_n>> traces. It crosses 4.5 at <<pl_N_first>> against
  <<pl_N_pre_first>> traces.
* **The leak keeps its shape and moves later.** The t-curve is shifted <<pl_N_shift_ns>> ns: the two curves correlate
  at <<pl_N_shift_corr>> at that shift and at <<pl_N_noshift_corr>> without it. The shift fits the slower clock-to-Q and
  evaluation of §6.1.
* **It stays in the evaluation.** All <<pl_N_above>> samples above 4.5 lie in <<pl_N_span>> ns, inside the registered
  evaluation part. The clock-fall and input-edge parts stay at or below <<pl_N_rest>>.
* **It is still a leak of timing, not of total charge.** On the charge per cycle \|t\| is <<pl_N_tq>> (<<pl_N_pre_tq>>
  before layout). In 100 ps bins the leak stays at <<pl_N_t100>>.
* **DA shows no first-order leak after layout** at <<pl_DA_n>> traces: <<pl_DA_t>>, at most <<pl_DA_tmax_cp>> at any
  checkpoint (<<pl_DA_pre_t>> before layout on the same rows).
* **What DA's result rules out.** At this count TVLA reaches 4.5 on average for a leak <<pl_DA_detect_frac>> times as
  strong as N's post-layout one. That is a weaker bound than §4.5's <<DA_detect_frac_of_N>> at <<DA_n>> traces,
  because the registered post-layout campaign is half as long.
* **DA's second order grows after layout,** from <<pl_DA_pre_t2>> to <<pl_DA_t2>>. This is expected for two-share
  masking and is informational only.
* **Added noise.** With noise added in the same way as in §4.7, N stays above 4.5 from <<pl_N_stable_noise0.5>> traces
  at 0.5x, as it does before layout. At 1x neither netlist stays above 4.5 within <<pl_N_n>> traces: both end below it
  (<<pl_N_t_noise1.0>> after layout). The only crossings are small-sample false alarms at 20-105 traces (§4.7); the
  kill test needed 6,273 traces for N at 1x, so this count is too short to say more.

**Figure 14.** max\|t\| against the number of traces, after layout (blue) and before layout on the same rows (gray).
The dotted line is the growth that a leak as strong as N's post-layout one would follow.
""")

code(r"""
nbfigs.show(nbfigs.postlayout_maxt())
""")

md(r"""
**What the post-layout model leaves out** (`layout/README.md`, `docs/POSTLAYOUT.md`):
* resistance: the extraction is capacitance only, with no wire, via or power-grid resistance;
* corners: tt at 27 °C only;
* placement: one layout per variant, from a single placement seed;
* sources: an ideal 1.8 V supply at the block's power pins, and ideal clock and input sources at its pins. There is no
  package and no on-chip decoupling effect;
* the layouts are blocks, not a chip;
* D was not laid out, and U was laid out but not simulated.

The claim these results support is: *under transistor-level simulation of the extracted, capacitance-only layouts at
sky130 tt, N's first-order leak survives place and route, and DA shows no first-order leak within <<pl_DA_n>> traces.*
""")

# ================================================================= 7 cost
md(r"""
## 7. Cost of the fix

The cost of each variant **before layout**, from the netlists, the Liberty file and the SPICE supply charge
(`analysis/cost_table.py`; every column with its definition in `results/cost/cost.md`). The table comes first, then
**Figure 15**: cell area, energy per S-box evaluation (SPICE supply charge plus the estimated charge of the flip-flops'
clock pins) and latency in time, per variant. A second table gives N and DA **after layout** (§6).
""")

code(r"""
COST = nbfigs.cost_table()
if COST:
    nbfigs.show_md(COST)
    nbfigs.show(nbfigs.cost_figure())
else:
    print('cost table not written yet (results/cost/cost.csv)')
""")

md(r"""
**After layout, N and DA.** This table gives the area after place and route (`data/layout__summary.json`) and the
energy per evaluation on the same rows before and after layout (`data/pex__summary_postlayout.json`). Both energies
use the definition of the table above. The post-layout energy also contains the clock tree, the clock pins and the
cells' own parasitics, which the pre-layout supply current leaves out, so the two energy rows are not
interchangeable.
""")

code(r"""
nbfigs.show_md(nbfigs.postlayout_cost_table())
""")

md(r"""
* **Area.** D and DA have the same <<cost_DA_cells>> cells. The <<cost_dff_extra>> extra flip-flops of the barrier make them
  <<cost_DA_area_vs_N_pct>> % larger than N (<<cost_DA_area_um2>> against <<cost_N_area_um2>> µm² of cell area, without
  placement utilization or a clock tree). After place and route at 40 % core utilisation, DA's core is
  <<lay_DA_core>> µm² against N's <<lay_N_core>> µm² (+<<lay_core_DA_vs_N_pct>> %), and its die is +<<lay_die_DA_vs_N_pct>> %.
* **Energy.** In SPICE, DA draws <<cost_DA_e_eval_fJ>> fJ per evaluation against N's <<cost_N_e_eval_fJ>> fJ
  (+<<cost_DA_energy_vs_N_pct>> %). With the flip-flops' clock-pin charge, which the simulated current leaves out
  (ideal clock), it is +<<cost_DA_total_vs_N_pct>> %. These are pipelined figures: a new input enters every cycle, so the
  charge per evaluation is the charge per cycle. A round-based core that cannot interleave two states needs two
  cycles per round with DA and pays about one more cycle of clock and register overhead. The charge is averaged
  over rows whose neighbours are random inputs too. Over all random rows of U's TVLA campaign it is <<cost_U_bias_pct>> %
  lower, because a neighbouring fixed input (0x0B) changes the charge.
* **Energy after layout.** The simulated current now carries the clock tree (DA <<lay_DA_cts>> buffers, N <<lay_N_cts>>),
  the clock pins and the cells' own parasitics. On the same rows DA draws <<pl_DA_e_fJ>> fJ per evaluation against N's
  <<pl_N_e_fJ>> fJ: +<<pl_energy_DA_vs_N_pct>> %, against +<<pl_pre_energy_DA_vs_N_pct>> % before layout.
* **Latency.** Two cycles instead of one, but a shorter cycle, because the barrier cuts the logic depth. In time, DA's
  latency is <<cost_DA_latency_ns>> ns against N's <<cost_N_latency_ns>> ns (+<<cost_DA_latency_vs_N_pct>> %; D
  +<<cost_D_latency_vs_N_pct>> %), not twice as long. DA's affine XORs add <<cost_DA_port_to_reg_ps>> ps in front of the input
  registers; in a round-based core they merge into the previous round's linear layer.
* **Randomness.** N, D and DA all use <<cost_DA_fresh_random_bits>> fresh random bits per S-box evaluation. The fix
  costs no extra randomness.
* **What the cost buys** (§4, §5): N leaks at first order and gives up its key (with the post hoc per-key-bit points
  of interest); DA shows no first-order leak at <<DA_n>> traces and no first-order key recovery, down to a leak
  <<kr_DA_alpha_words>> as strong as N's (§5). TVLA on the same traces is more sensitive: it excludes a leak <<DA_detect_frac_words>> as strong (§4.5).
  After place and route N still leaks, and DA still shows no first-order leak at <<pl_DA_n>> traces (§6).
""")

# ================================================================= 8 limitations
md(r"""
## 8. Limitations

* **Simulation, not silicon.** The claim these results support is: *under transistor-level simulation of the
  pre-layout netlist on sky130 `tt`, N leaks at first order within <<N_first>> traces, and DA shows no first-order leak
  within <<DA_n>> traces. After place and route, with capacitance-only extraction, N's leak survives (above 4.5 from
  <<pl_N_first>> traces), and DA shows no first-order leak within <<pl_DA_n>> traces (§6).* It is not a measured result.
* **Pre-layout parasitics.** Wire capacitance is an estimate (1 fF plus 0.5 fF per fanout pin). The stock
  `sky130_fd_sc_hd` SPICE cells carry no diffusion or junction capacitance (every FET has ad = as = pd = ps = 0)
  and no intra-cell wiring, so they switch faster than their Liberty data. N's leak survives both brackets that
  were tried on the same rows. With wire capacitance ×4, max\|t\| is 7.20 against 9.20 at 5,998 traces, and the peak
  moves from 0.945 to 1.385 ns. With diffusion capacitance added, it is 4.78 against 5.17 at 1,998 traces. The trace
  counts and times in §4 belong to this estimate. After place and route (§6), on the same rows, the leak keeps its
  size and sits <<pl_N_shift_ns>> ns later.
* **Idealized environment.** The supply is an ideal 1.8 V source: no package, power grid, decoupling, probe or
  measurement noise. Before layout, wire capacitances go to ground only, so coupling between nets of different share
  domains [15] is not modelled there. The extracted layouts of §6 include it (<<lay_N_s0s1_fF>> fF between N's share-0
  and share-1 nets), but no resistance. There is one process corner and one temperature, and no mismatch Monte
  Carlo. The measured current is the DUT's VPWR only. Before layout, the gate charge of the clock pins and of the
  input D pins comes from ideal sources; it is data-independent or share-wise, so no first-order result changes.
  After layout, the clock tree drives the clock pins from the DUT supply.
* **The post-layout model** (§6). It is capacitance only, with one placement per variant, an ideal supply, clock and
  inputs at the block's pins, and tt only. D was not laid out. DA's post-layout campaign has half the pre-layout trace
  count, so it rules out only leaks at least <<pl_DA_detect_frac>> times as strong as N's post-layout one.
* **One S-box column, not a cipher.** There is no round structure, no state register feedback and no key
  schedule. The randomness is assumed ideal (fresh and uniform).
* **What TVLA shows.** TVLA detects leakage; it does not measure how exploitable it is (§5 does, for a two-bit key).
  One fixed value is tested, but 0x0B is typical: 18 of the 32 values already exceed 4.5 in an "x = v against the
  rest" test on independent data. An absence claim holds only down to a detectable effect size (§2.5).
* **The key recovery is post hoc.** It was designed after the kill test, profiles on the same simulated device it
  attacks, and recovers a two-bit key with four guesses. Its per-key-bit points of interest were added after a
  review had seen the default attack miss key bit $x_2$. For D and DA it adds no sensitivity beyond TVLA (§5).
* **The models.** Level 2 is a screening model and not a predictor of SPICE's waveform (§4.6). The noiseless SPICE
  traces are deterministic functions of the inputs: N's quiet end of the evaluation (1.3–1.8 ns) reaches
  \|t\| 3.97, which is below 4.5 and comes from sub-threshold tails of the same timing mechanism.
""")

# ================================================================= 9 conclusion
md(r"""
## 9. Conclusion

On an open PDK, with open tools, a masked Ascon S-box that a zero-delay flow would sign off leaks at first order
in transistor-level simulation (<<N_t>> at <<N_n>> traces), through the timing of its unregistered cross-domain logic.
An exact glitch-extended probing check that runs in seconds finds the problem in advance and names the nets that
carry it. It also shows that DOM's register barrier must sit *after* Ascon's input affine layer: textbook
placement (D) keeps a net-level leak, and the corrected placement (DA) shows no first-order leak at <<DA_n>>
traces. D's net-level leak does not show in the supply current at <<D_n>> traces, although the timing-aware model
predicts it. The verdicts for N and DA hold after place and route. The OpenLane layouts are DRC and LVS clean, and
the extraction is capacitance only at tt. On the same rows N leaks as strongly as before layout (<<pl_N_t>> at
<<pl_N_n>> traces), <<pl_N_shift_ns>> ns later, and DA shows no first-order leak at <<pl_DA_n>> traces. A profiled attack on the same traces recovers N's two key bits at first order (with points of interest
chosen post hoc) and finds no first-order key in D or DA, where it would detect a leak <<kr_alpha_range>> times as strong as
N's. TVLA on the same traces is more sensitive (about <<DA_detect_frac_of_N>>), so for D and DA the attack adds no evidence
beyond it (§5). The corrected barrier costs <<cost_DA_area_vs_N_pct>> % more cell area, <<cost_DA_energy_vs_N_pct>> % more energy per
evaluation in the simulated supply current (<<cost_DA_total_vs_N_pct>> % with the estimated clock-pin charge; pipelined use)
and <<cost_DA_latency_vs_N_pct>> % more latency in time than N, and no extra randomness. After layout it costs
<<lay_core_DA_vs_N_pct>> % more core area and <<pl_energy_DA_vs_N_pct>> % more energy per evaluation, with the clock tree in the
simulated supply. A designer can take three things from this: a *method* (probing check, then timing-aware
screening, then SPICE on the same netlist, before and after layout), a
concrete *design rule* for masked Ascon datapaths, and an honest account of how far each cheap model can be trusted.

**Next steps:** resistive extraction with a power grid and a package model, process corners, and a full masked
Ascon round.
""")

# ================================================================= 10 references
md(r"""
## 10. References

1. C. Dobraunig, M. Eichlseder, F. Mendel, M. Schläffer, "Ascon v1.2: Lightweight Authenticated Encryption and
   Hashing," *Journal of Cryptology*, vol. 34, art. 33, 2021. doi:[10.1007/s00145-021-09398-9](https://doi.org/10.1007/s00145-021-09398-9)
2. M. Sönmez Turan, K. A. McKay, D. Chang, J. Kang, J. Kelsey, "Ascon-Based Lightweight Cryptography Standards
   for Constrained Devices," NIST SP 800-232, 2025. doi:[10.6028/NIST.SP.800-232](https://doi.org/10.6028/NIST.SP.800-232)
3. S. Mangard, T. Popp, B. M. Gammel, "Side-Channel Leakage of Masked CMOS Gates," *CT-RSA 2005*, LNCS 3376,
   pp. 351–365. doi:[10.1007/978-3-540-30574-3_24](https://doi.org/10.1007/978-3-540-30574-3_24)
4. S. Nikova, C. Rechberger, V. Rijmen, "Threshold Implementations Against Side-Channel Attacks and Glitches,"
   *ICICS 2006*, LNCS 4307, pp. 529–545. doi:[10.1007/11935308_38](https://doi.org/10.1007/11935308_38)
5. H. Gross, S. Mangard, T. Korak, "Domain-Oriented Masking: Compact Masked Hardware Implementations with
   Arbitrary Protection Order," *ACM Workshop on Theory of Implementation Security (TIS)*, 2016.
   doi:[10.1145/2996366.2996426](https://doi.org/10.1145/2996366.2996426)
6. S. Faust, V. Grosso, S. Merino Del Pozo, C. Paglialonga, F.-X. Standaert, "Composable Masking Schemes in the
   Presence of Physical Defaults & the Robust Probing Model," *IACR TCHES*, 2018(3), pp. 89–120.
   doi:[10.13154/tches.v2018.i3.89-120](https://doi.org/10.13154/tches.v2018.i3.89-120)
7. D. Knichel, P. Sasdrich, A. Moradi, "SILVER – Statistical Independence and Leakage Verification,"
   *ASIACRYPT 2020*, LNCS 12491, pp. 787–816. doi:[10.1007/978-3-030-64837-4_26](https://doi.org/10.1007/978-3-030-64837-4_26)
8. N. Müller, A. Moradi, "PROLEAD: A Probing-Based Hardware Leakage Detection Tool," *IACR TCHES*, 2022(4),
   pp. 311–348. doi:[10.46586/tches.v2022.i4.311-348](https://doi.org/10.46586/tches.v2022.i4.311-348)
9. G. Goodwill, B. Jun, J. Jaffe, P. Rohatgi, "A testing methodology for side-channel resistance validation,"
   *NIST Non-Invasive Attack Testing Workshop*, 2011.
   [csrc.nist.gov](https://csrc.nist.gov/csrc/media/events/non-invasive-attack-testing-workshop/documents/08_goodwill.pdf)
10. ISO/IEC 17825:2024, "Testing methods for the mitigation of non-invasive attack classes against cryptographic
    modules," 2nd ed., 2024. See also C. Whitnall, E. Oswald, "A Critical Analysis of ISO 17825," *ASIACRYPT 2019*.
    doi:[10.1007/978-3-030-34618-8_9](https://doi.org/10.1007/978-3-030-34618-8_9)
11. H. Gross, E. Wenger, C. Dobraunig, C. Ehrenhöfer, "Ascon hardware implementations and side-channel
    evaluation," *Microprocessors and Microsystems*, vol. 52, pp. 470–479, 2017.
    doi:[10.1016/j.micpro.2016.10.006](https://doi.org/10.1016/j.micpro.2016.10.006)
12. Y. Ishai, A. Sahai, D. Wagner, "Private Circuits: Securing Hardware against Probing Attacks," *CRYPTO 2003*,
    LNCS 2729, pp. 463–481. doi:[10.1007/978-3-540-45146-4_27](https://doi.org/10.1007/978-3-540-45146-4_27)
13. T. Schneider, A. Moradi, "Leakage Assessment Methodology," *CHES 2015*, LNCS 9293, pp. 495–513.
    doi:[10.1007/978-3-662-48324-4_25](https://doi.org/10.1007/978-3-662-48324-4_25)
14. N. Samwel, J. Daemen, "DPA on hardware implementations of Ascon and Keyak," *ACM Computing Frontiers 2017*,
    pp. 415–424. doi:[10.1145/3075564.3079067](https://doi.org/10.1145/3075564.3079067)
15. T. De Cnudde, B. Bilgin, B. Gierlichs, V. Nikov, S. Nikova, V. Rijmen, "Does Coupling Affect the Security of
    Masked Implementations?," *COSADE 2017*, LNCS 10348, pp. 1–18 (IACR ePrint 2016/1080).
    doi:[10.1007/978-3-319-64647-3_1](https://doi.org/10.1007/978-3-319-64647-3_1)
16. SkyWater Technology and Google, *SKY130 open-source PDK*; open_pdks `sky130A`. https://github.com/google/skywater-pdk
17. ngspice, open-source mixed-signal circuit simulator. https://ngspice.sourceforge.io
""")

md(r"""
---
**Reproducibility and data.** Every file behind the figures is in `data/` (CSV, plus a few JSON summaries), with its size,
SHA-256, source and meaning in `data/MANIFEST.csv`; units are in the column names (µA, ns, fF, fC). The animation's
events are in `media/glitch_events.json`, and the layout images of §6 are small copies of `results/layout/*.png` in
`media/` (`make_layout_media.py`). The netlist generator, models, SPICE runner, layout flow and analysis are in the
project repository (`gen/`, `model/`, `sim/`, `layout/`, `analysis/`), and the pre-registrations
(`docs/KILL_TEST.md`, `docs/POSTLAYOUT.md`) and reviews are in `docs/`.

**AI-use disclosure.** AI coding assistants were used in this project. All results come from open-source tools (ngspice, the sky130 PDK, OpenLane, Magic, KLayout, netgen, Python), and the author is responsible for all content.

**Acknowledgments.** TODO(user).

*Licensed under the Apache License, Version 2.0.*
""")


# ================================================================= build
def fill(text, values):
    missing = []

    def sub(m):
        k = m.group(1)
        if k not in values:
            missing.append(k)
            return m.group(0)
        return str(values[k])
    out = re.sub(r"<<([A-Za-z0-9_.]+)>>", sub, text)
    if missing:
        raise KeyError("no value for placeholders: %s" % ", ".join(sorted(set(missing))))
    return out


def lines(text):
    parts = text.split("\n")
    return [p + "\n" for p in parts[:-1]] + [parts[-1]]


def build(values=None):
    values = values or nbdata.fmt_headline()
    cells = []
    for kind, text in CELLS:
        if kind == "markdown":
            cells.append({"cell_type": "markdown", "metadata": {}, "source": lines(fill(text, values))})
        else:
            cells.append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
                          "source": lines(text)})
    return {"cells": cells, "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
        "colab": {"provenance": []}}, "nbformat": 4, "nbformat_minor": 5}


def main():
    nb = build()
    for k, c in enumerate(nb["cells"]):
        c["id"] = "cell-%02d" % k
    with open(OUT, "w") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("wrote %s (%d cells)" % (os.path.relpath(OUT, nbdata.root()), len(nb["cells"])))


if __name__ == "__main__":
    main()
