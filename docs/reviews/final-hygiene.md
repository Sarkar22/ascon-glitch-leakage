<!-- SPDX-License-Identifier: Apache-2.0 -->
# Review: technical and hygiene check of the submission (final, 2026-09-26)

**Scope.** This review covers the working tree as it will be pushed (tracked files plus new files that are not
ignored: 279 files, 16 MB) and the pull-request folder that `tools/make_submission.py` builds from it. It checks:
- the folder's contents, LICENSE and README;
- the notebook in cached mode at its PR location, inside a clone of the organizers' repository, and their CI
  commands there;
- the Colab badge, the "run now" link and the Colab fallback;
- `.github/workflows/ci.yml`: actionlint, and each job's commands in a fresh container;
- host paths, e-mail addresses, host and user names, and markers other than `TODO(user)`;
- the numbers in `README.md`, the notebook's claim screen, the submission README and `docs/PR_BODY.md` against
  `results/`.

**What I changed.** Nothing except this file. The folder was built from a clean export of the files to be committed,
which was mounted read-only. Every container ran at `--cpus 2` or less. The spice job's emulation ran the 60-row
SPICE demo only, and no campaign was started.

## Verdict

**The submission is technically ready.** The folder, the organizers' checks, the workflow and all three of its
jobs pass. The folder contains only what the notebook uses, and it has no host paths or e-mail addresses. Two items
must be fixed before the PR is opened:
- one sentence in `docs/PR_BODY.md` (B1);
- a trap in how the PR copy is taken (B2).

## What I checked or re-ran

| # | Check | Result |
|---|---|---|
| 1 | Folder build from a clean, read-only export (`make_submission.py` in cac-sca) | 45 files: 8 at the top level, 33 in `data/`, 4 in `media/`; 4.42 MB, of which the notebook is 1.93 MB. It is byte-identical to `runs/submission/ISSCC27/...`, and the build wrote nothing into the export. The notebook, the five helpers and every `data/` and `media/` file equal their `notebook/` sources. The trimmed `MANIFEST.csv` lists exactly the 32 shipped data files, with matching hashes |
| 2 | Only what the notebook needs | The helpers are the five modules the code cells import (`setup_env`, `nbdata`, `nbfigs`, `nbanim`, `nbexplorer`). The data are the files a traced cached run opens, plus the explorer's other variants and the live demo's reference. There is no `make_*`, no test file, no `ci_smoke.ipynb` and no `__pycache__` |
| 3 | LICENSE | The full Apache License 2.0 text (201 lines, appendix included). It equals apache.org's `LICENSE-2.0.txt` except for indentation |
| 4 | Submission README | Badge, author table (affiliation, IEEE yes, SSCS no, `TODO(user): e-mail`), claim, headline table, how to run, pinned versions, file table, AI use, license. Every `{}` placeholder is filled |
| 5 | Organizers' CI at the PR location: a sparse clone of their `main` at f9370cc, the folder copied in, `python:3.10-slim` with only their packages (numpy 2.2.6, matplotlib 3.10.9) | Commands as written: flake8 exit 1, the greps exit 2 and nbmake exit 4, because `**/*.ipynb` without globstar finds no notebook. This happens for every entry, not only ours. With globstar: flake8 0, has colab-badge 0, colab-badge is sscs-ose 0, and `pytest --nbmake` passes in 7.2 s. Nothing outside the folder changed |
| 6 | Saved outputs | 25 of 25 code cells executed in order, with no error output and no stderr stream. No absolute path appears in any output (the helper prints `repository ..` and `~/.ciel/...`). The embedded PNGs carry only Matplotlib's "Software" tag |
| 7 | Badge and "run now" link | The badge points to `sscs-ose/sscs-ose-code-a-chip.github.io/blob/main/ISSCC27/submitted_notebooks/ascon_glitch_leakage/ascon_glitch_leakage.ipynb`: the right path, and 404 until the merge, as designed. The "run now" link `Sarkar22/ascon-glitch-leakage/blob/main/notebook/ascon_glitch_leakage.ipynb` resolves (raw file: HTTP 200). The only line with `colab-badge` is the sscs-ose badge |
| 8 | Colab fallback, emulated (`google.colab` injected, empty working directory, python:3.10-slim with git) | The sparse sscs-ose clone succeeds and has no folder yet. The cell then clones the public repository at `main`, changes into `notebook/`, and the helpers import and pick cached mode. Against the public `main` as it is now (7a544e9), the new setup cell stops at `H['results_dated']` (KeyError), because that `nbdata.py` predates the key. This goes away with the push; see N2 |
| 9 | `ci.yml`, static | actionlint 1.7.12 (with shellcheck and pyflakes): 0 errors. The tags exist upstream: `actions/checkout@v7`, `setup-python@v7`, `cache@v6`, `upload-artifact@v7`. The cache exclusion `~/.ciel/ciel/sky130/versions/*/sky130B` matches ciel's layout |
| 10 | Unit job (`python:3.12-slim`, numpy 2.5.3, matplotlib 3.11.2, non-root, clean export) | model/tests OK, analysis 44 OK (1 skipped), notebook 41 OK, layout 28 OK, sim 8 OK (1 skipped), tools 7 OK |
| 11 | Notebook job (`python:3.10-slim`, graphviz from apt, the organizers' packages only, non-root) | flake8 0 on `notebook/*.ipynb`, both badge steps 0, `pytest --nbmake` 2 passed (11 s). `make_submission.py` in `$RUNNER_TEMP` gives 45 files. The globstar block on that folder passes (nbmake 1 passed, 7.2 s) |
| 12 | Spice job (`ubuntu:24.04`, ngspice `42+ds-3build1` and iverilog 12 from apt, Python 3.12.3, non-root). The PDK at the pinned hash was mounted read-only instead of downloaded; ciel's download was exercised earlier by `colab_live.sh` | `setup_env.py --install --mode live`: live, apt skipped, PDK found. Unit tests with ngspice: model OK, sim 8 OK with none skipped. `colab_check.py --jobs 2`: every step ok. The netlists and stimuli are identical to the campaigns', iverilog ALL PASS, and probing flags N 39, D 12, DA 0. SPICE demo: ngspice-42, 60 rows, \|dI\| ≤ 5e-5 uA, max\|t\| 6.57 (reference 6.57), outputs equal. The report step's asserts pass. Live-mode nbmake: 1 passed in 131 s. The job took 245 s |
| 13 | Paths, e-mails, names (export, folder, and every commit in `git rev-list --all`) | No home or mount path. The only matches are the test regex and a sentence in an older review. No e-mail address (commits use the GitHub noreply address). No host name and no user name. The GDS files and PNG text chunks carry no paths |
| 14 | Markers | Outside `docs/reviews/` the only markers are `TODO(user)`: the e-mail in the notebook, the submission README and the PR body; the acknowledgments in the notebook; the green CI run link in the PR body |
| 15 | SPDX | Every new `.py`, `.sh`, `.tcl`, `.yml` and `.md` file starts with the SPDX line |
| 16 | Registered text | The first 3,106 bytes of `docs/POSTLAYOUT.md` are byte-identical to 36a8a13 |
| 17 | Numbers against `results/`: `kill_test/summary.json`, `probing/*.json`, `key_recovery/summary.json`, `cost/cost.csv`, `pex/summary_postlayout.json`, `pex/rc_check.json`, `layout/negative_controls.json`, `layout/summary.json` | Claim table: zero-delay 1.08 / 2.11 / 2.71, timing-aware 12.1 / 16.7 / 2.96, SPICE 13.2 at 9,998 / 3.08 / 3.08 at 19,997; post-layout 8.19 at 4,998 (8.07 before) and 3.36 at 9,997 (3.35). Controls: 27.7 / 38.4 / 37.4 at 1,998, then 19.2 / 28.1 / 27.5 at 998, then 0.60 / 3.12 / 1.87 at 9,998. Other figures: probing 39/103, 12/133, 0/133; D's 5 nets and 15.2 cap-weighted; bounds 0.24 and 0.39; SR 0.93 at 765 (per-key-bit POIs) against 0.62 by default; cost +59 % area, +39 % energy (+60 % post-layout, 61 % core area), 2 cycles against 1, 5 bits. Negative controls: 96/109 and 128/141 unchanged under the share swap, Magic 10 and KLayout 3 markers only on the defects. RC bracket: 4,427 R, median 103 ohm, max 511 ohm, 603 nets; charge -0.24 % (1.1 %), 0.9998; 20 ps; 0.98 / 0.94 and 0.98 / 0.95; +25 ps (23-27); +61 ps (22-74), 1.83 -> 1.89 ns (2.08); 2,065 -> 2,057; 0.9 uA. All match in README.md, the notebook, the submission README and PR_BODY.md. Two exceptions are wording, not numbers: B1 and N4 |

## Blocking

**B1. `docs/PR_BODY.md`, summary point 3, overstates the attack.** It reads: "A profiled attack recovers the naive
design's key (success rate 0.93 at 765 traces per key) and no key from DA."
- DA does give up its key at second order: GE 0.27, SR 0.78 (notebook §5, "Second order", from
  `key_recovery/summary.json`). That is expected for first-order masking, but "no key from DA" without "first
  order" is false.
- The 0.93 needs the per-key-bit points of interest, which were chosen post hoc; the default attack gives 0.62.
  README.md, the abstract, §5, §9 and the submission README all say so. The PR body, which the jury reads first,
  is the only place that drops both qualifiers.

Suggested text: "A profiled first-order attack recovers the naive design's key (success rate 0.93 at 765 traces
per key, with points of interest chosen per key bit after the default attack missed one bit) and finds no
first-order key in DA."

**B2. Take the PR copy from the build, not from the check's clone.** Running the notebook writes
`__pycache__/*.pyc` next to the helpers. After `tools/check_submission.sh`, `runs/submission/upstream/ISSCC27/
submitted_notebooks/ascon_glitch_leakage/` holds 50 files, the 45 plus five `.pyc`. The upstream `.gitignore` does
not ignore them, so a `git add` of that folder in that clone would commit them. Committed `__pycache__` is one of
the hygiene faults listed against other entries.

The check's hygiene step does not see this: its "files: 45" counts the build folder, not the clone the notebook
ran in. Fix both:
- make the fork commit from a fresh copy of `runs/submission/ISSCC27/submitted_notebooks/ascon_glitch_leakage/`,
  and write that down in the header comment of `PR_BODY.md`;
- in `check_submission.sh`, after step 3, delete `__pycache__` from the clone's folder, or count and grep that copy
  and fail when it differs from the build.

`sys.dont_write_bytecode = True` in the setup cell, before the helper imports, would also stop it at the source,
but that changes the notebook and needs a re-execution.

## Notes (non-blocking)

**N1. Pin `REPO_REF` to a tag before the PR.** The merged notebook's live mode clones the public repository for
`gen/`, `model/` and `sim/` at `REPO_REF` (now `main`). A later push to `main` can break the merged copy's live path
while judging runs. Push a tag (for example `v1.0`), set `setup_env.DEFAULT_REPO_REF`, run `make_notebook.py`,
re-execute, and rebuild the folder. `notebook/README.md` already describes these steps.

**N2. Push before anyone uses the "run now" link.** Check 8 shows that the fallback works, but the public `main`
still has the old helpers. After the push, open the link once in real Colab.

**N3. `notebook/ci_smoke.ipynb` has a dead badge.** Its badge points to
`ISSCC27/submitted_notebooks/ascon_glitch_leakage/ci_smoke.ipynb` on sscs-ose. That path will never exist, because
the folder does not ship the file. The notebook is in the public repository only, so the badge check still passes.
Point the badge at the public repository, drop it, or retire the notebook: the main notebook's nbmake run covers it.

**N4. The controls table's DA column says "not run" for both DRC rows.** DA's final GDS is DRC clean in the sign-off
table of §6. Only the negative control was not repeated on DA. "Not repeated (sign-off: 0, §6)" would avoid a
reader thinking that DA's DRC was not run.

**N5. Some references in the notebook point to files that are not in the PR folder.** The notebook names
`layout/README.md`, `docs/POSTLAYOUT.md`, `tests/colab_live.sh`, `make_cached_data.py`, `colab_check.py` and
`make_layout_media.py` as plain code spans. In the PR folder they do not exist. The reading guide and the closing
cell say that they are in the project repository, but links to the public repository (at the pinned tag, N1) would
make them one click away.

**N6. Items for the author:**
- the e-mail (three places) and the acknowledgments;
- the attendance sentence in the PR body;
- the green CI run link after the push.

**N7. Small items.** `nbfigs.py` has two E128 warnings; CI does not check them. The "How to run" live time (about
5 minutes) still fits the latest measurement: setup 48 s plus the notebook 138 s.
