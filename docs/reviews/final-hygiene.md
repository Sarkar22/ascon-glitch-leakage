<!-- SPDX-License-Identifier: Apache-2.0 -->
# Review: technical and hygiene check (final, 2026-09-26)

**Scope.** This review covers the working tree as it will be pushed (tracked files plus new files that are not
ignored: 279 files, 16 MB). It checks:
- LICENSE and the notebook's saved outputs;
- the Colab path;
- `.github/workflows/ci.yml`: actionlint, and each job's commands in a fresh container;
- host paths, e-mail addresses, host and user names, and markers other than `TODO(user)`;
- the numbers in `README.md` and the notebook's claim screen against `results/`.

**What I changed.** Nothing except this file. Every container ran at `--cpus 2` or less. The spice job's emulation
ran the 60-row SPICE demo only, and no campaign was started.

## Verdict

**Technically sound.** The workflow and all three of its jobs pass, and the working tree has no host paths or
e-mail addresses. Nothing is blocking; three small notes follow.

## What I checked or re-ran

| # | Check | Result |
|---|---|---|
| 1 | LICENSE | The full Apache License 2.0 text (201 lines, appendix included). It equals apache.org's `LICENSE-2.0.txt` except for indentation |
| 2 | Saved outputs | 25 of 25 code cells executed in order, with no error output and no stderr stream. No absolute path appears in any output (the helper prints `repository ..` and `~/.ciel/...`). The embedded PNGs carry only Matplotlib's "Software" tag |
| 3 | Colab path, emulated (`google.colab` injected, empty working directory, python:3.10-slim with git) | The setup cell clones the public repository at `main`, changes into `notebook/`, and the helpers import and pick cached mode. Against the public `main` as it is now (7a544e9), the new setup cell stops at `H['results_dated']` (KeyError), because that `nbdata.py` predates the key. This goes away with the push |
| 4 | `ci.yml`, static | actionlint 1.7.12 (with shellcheck and pyflakes): 0 errors. The tags exist upstream: `actions/checkout@v7`, `setup-python@v7`, `cache@v6`, `upload-artifact@v7`. The cache exclusion `~/.ciel/ciel/sky130/versions/*/sky130B` matches ciel's layout |
| 5 | Unit job (`python:3.12-slim`, numpy 2.5.3, matplotlib 3.11.2, non-root, clean export) | model/tests OK, analysis 44 OK (1 skipped), notebook 41 OK, layout 28 OK, sim 8 OK (1 skipped) |
| 6 | Notebook job (`python:3.10-slim`, graphviz from apt, the job's packages only, non-root) | flake8 0 on `notebook/*.ipynb`, has colab-badge 0, `pytest --nbmake` 2 passed (11 s) |
| 7 | Spice job (`ubuntu:24.04`, ngspice `42+ds-3build1` and iverilog 12 from apt, Python 3.12.3, non-root). The PDK at the pinned hash was mounted read-only instead of downloaded; ciel's download was exercised earlier by `colab_live.sh` | `setup_env.py --install --mode live`: live, apt skipped, PDK found. Unit tests with ngspice: model OK, sim 8 OK with none skipped. `colab_check.py --jobs 2`: every step ok. The netlists and stimuli are identical to the campaigns', iverilog ALL PASS, and probing flags N 39, D 12, DA 0. SPICE demo: ngspice-42, 60 rows, \|dI\| ≤ 5e-5 uA, max\|t\| 6.57 (reference 6.57), outputs equal. The report step's asserts pass. Live-mode nbmake: 1 passed in 131 s. The job took 245 s |
| 8 | Paths, e-mails, names (export and every commit in `git rev-list --all`) | No home or mount path. The only matches are the test regex and a sentence in an older review. No e-mail address (commits use the GitHub noreply address). No host name and no user name. The GDS files and PNG text chunks carry no paths |
| 9 | Markers | Outside `docs/reviews/` the only markers are `TODO(user)`: the e-mail and the acknowledgments in the notebook |
| 10 | SPDX | Every new `.py`, `.sh`, `.tcl`, `.yml` and `.md` file starts with the SPDX line |
| 11 | Registered text | The first 3,106 bytes of `docs/POSTLAYOUT.md` are byte-identical to 36a8a13 |
| 12 | Numbers against `results/`: `kill_test/summary.json`, `probing/*.json`, `key_recovery/summary.json`, `cost/cost.csv`, `pex/summary_postlayout.json`, `pex/rc_check.json`, `layout/negative_controls.json`, `layout/summary.json` | Claim table: zero-delay 1.08 / 2.11 / 2.71, timing-aware 12.1 / 16.7 / 2.96, SPICE 13.2 at 9,998 / 3.08 / 3.08 at 19,997; post-layout 8.19 at 4,998 (8.07 before) and 3.36 at 9,997 (3.35). Controls: 27.7 / 38.4 / 37.4 at 1,998, then 19.2 / 28.1 / 27.5 at 998, then 0.60 / 3.12 / 1.87 at 9,998. Other figures: probing 39/103, 12/133, 0/133; D's 5 nets and 15.2 cap-weighted; bounds 0.24 and 0.39; SR 0.93 at 765 (per-key-bit POIs) against 0.62 by default; cost +59 % area, +39 % energy (+60 % post-layout, 61 % core area), 2 cycles against 1, 5 bits. Negative controls: 96/109 and 128/141 unchanged under the share swap, Magic 10 and KLayout 3 markers only on the defects. RC bracket: 4,427 R, median 103 ohm, max 511 ohm, 603 nets; charge -0.24 % (1.1 %), 0.9998; 20 ps; 0.98 / 0.94 and 0.98 / 0.95; +25 ps (23-27); +61 ps (22-74), 1.83 -> 1.89 ns (2.08); 2,065 -> 2,057; 0.9 uA. All match in README.md and the notebook. One exception is wording, not a number: N1 |

## Notes (non-blocking)

**N1. The controls table's DA column says "not run" for both DRC rows.** DA's final GDS is DRC clean in the sign-off
table of §6. Only the negative control was not repeated on DA. "Not repeated (sign-off: 0, §6)" would avoid a
reader thinking that DA's DRC was not run.

**N2. Some references in the notebook are plain code spans.** The notebook names `layout/README.md`,
`docs/POSTLAYOUT.md`, `tests/colab_live.sh`, `make_cached_data.py`, `colab_check.py` and `make_layout_media.py` as
plain code spans. The reading guide and the closing cell say that they are in the project repository, but links to
the public repository (at `REPO_REF`) would make them one click away.

**N3. Small items.** `nbfigs.py` has two E128 warnings; CI does not check them. The "How to run" live time (about
5 minutes) still fits the latest measurement: setup 48 s plus the notebook 138 s.
