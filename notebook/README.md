<!-- SPDX-License-Identifier: Apache-2.0 -->
# The submission notebook

`ascon_glitch_leakage.ipynb` is the Code-a-Chip notebook. It is written as a guided tour, in the style of a paper.
In its default *cached* mode it reads only the notebook's own data set in `data/` (CSV files and a few JSON
summaries), so it runs in under a minute with numpy and matplotlib. It needs no ngspice and no PDK, which is also how
the organizers' CI runs it (`pytest --nbmake`).

| File | Role |
|---|---|
| `ascon_glitch_leakage.ipynb` | The notebook, with saved outputs, so that it reads on GitHub without running it |
| `make_notebook.py` | Holds the narrative and builds the notebook's cells. The numbers quoted from the result files are filled in from the data (`<<key>>` placeholders); a few numbers from the reviews in `docs/reviews/` are fixed text (for example 7.20 against 9.20, 2.30 against 2.29, 28 % against 8.7 %). Project files that the text names and the pull-request folder does not ship (for example `docs/KILL_TEST.md`, `colab_check.py`) become links to the public repository at `REPO_REF`; `LIVE` holds the measured live-path times |
| `nbdata.py` | Reads the data: `data/` first, else the repository's `results/`. `headline()` holds the quoted numbers |
| `nbfigs.py` | The figures and tables (matplotlib; same colors as `analysis/plots.py`) |
| `nbanim.py` | The animation of one input change in N and DA (level-2 events). `python3 notebook/nbanim.py` rewrites `media/glitch_events.json` from `build/` |
| `nbexplorer.py` | The TVLA explorer (ipywidgets, with a static fallback), from `data/tvla_t_checkpoints_*.csv` and `data/class_stats_*.csv` |
| `media/` | The cached animation (`glitch_N_vs_DA.gif`) and its events (`glitch_events.json`), and small copies of the N and DA layout renders for §6 (`layout_<V>.png`) |
| `make_layout_media.py` | Writes the layout copies in `media/` from `results/layout/*_layout.png` (matplotlib and Pillow; run it in the cac-sca image) |
| `test_notebook.py` | Unit tests: the text matches the data, `data/` is current, lint-friendly code cells, badge, SPDX, no private paths, figures and tables |
| `setup_env.py`, `make_cached_data.py`, `colab_check.py`, `data/` | The environment helper, the export of `data/` and the live-path check (see their docstrings) |
| `tests/` | `ci_container.sh`: the organizers' two CI jobs in clean `python:3.10-slim` containers. `colab_live.sh` (with `colab_live.py`): the live path as Colab runs it, timed, in a clean `ubuntu:22.04` container that fetches everything from GitHub; its times are the ones in "How to run". `colab_container.sh`: the older live-path check on a copy of the repository |

## Rebuild after the results change

```
python3 notebook/make_cached_data.py   # data/ from results/ and runs/kt/ (host python3 + numpy)
python3 notebook/nbanim.py             # only if the netlists changed (needs build/)
bash sim/docker_run.sh python3 notebook/make_layout_media.py   # only if the layout renders changed
python3 notebook/make_notebook.py      # rewrites the cells (the saved outputs are dropped)
jupyter nbconvert --to notebook --execute --inplace notebook/ascon_glitch_leakage.ipynb
python3 -m unittest discover -s notebook -p 'test_*.py'
```

The organizers' checks are `nbqa flake8 --ignore=E402,E226` on the notebook, a `colab-badge` line that points to
`sscs-ose`, and `pytest --nbmake`. All three pass in a Python 3.10 environment with only
`pytest nbmake pandas graphviz matplotlib` installed, which is the organizers' CI. Execute the notebook without
ipywidgets installed when saving its outputs, so that GitHub shows the static explorer views instead of an
unrendered widget.

## Colab before and after the merge

The organizers' badge opens the notebook in `sscs-ose`, which exists only after they merge the entry. The line under
the badge opens the same notebook from the author's public repository. On Colab the setup cell fetches the notebook's
folder: the `sscs-ose` copy when it is there, else the public repository at `REPO_REF`. Live mode clones the public
repository at the same ref when the code is missing.

`REPO_REF` is `setup_env.DEFAULT_REPO_REF` (now `main`). To pin a release, push a tag, set `DEFAULT_REPO_REF` to it, run
`make_notebook.py` (which writes the ref into the setup cell and the "run now" link) and execute the notebook again.
At run time `$ASCON_REPO_REF` overrides the ref (in the setup cell and in `setup_env`), and `$ASCON_REPO_URL` the
repository that `setup_env` clones in live mode.

Measure the live path (the numbers in "How to run", the version line and `LIVE` in `make_notebook.py`, all taken
from one run; the comment above `LIVE` says which file each number comes from):
```
CPUS=2 bash notebook/tests/colab_live.sh                     # the notebook as pushed, at REPO_REF
LOCAL_NOTEBOOK=1 CPUS=2 bash notebook/tests/colab_live.sh    # this working tree's notebook/ over the clone
```

## Open items in the text

No `TODO` markers remain; the author table carries the contact e-mail. §5 (key recovery), §6
(layout and post-layout) and §7 (cost) are filled from `data/key_recovery__summary.json`, `data/layout__summary.json`,
`data/layout__placement_<V>.csv`, `data/pex__summary_postlayout.json`, `data/pex__*.csv` and `data/cost__cost.csv`;
§6.3 (the post-hoc negative controls and RC bracket) from `data/layout__negative_controls.json` and
`data/pex__rc_check.json`. After `analysis/key_recovery.py`, `analysis/postlayout.py`, `analysis/cost_table.py`,
`layout/neg_controls.py` or `layout/rc_check.py` change them, re-run the commands above (`make_cached_data.py` without
`--optional`, so that every later step is copied).
