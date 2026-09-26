#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Measure the notebook's live path as Colab runs it, in a clean ubuntu:22.04 container (Colab's OS),
# with everything fetched from GitHub. From the repository root:
#   bash notebook/tests/colab_live.sh [OUTDIR]          (default OUTDIR: runs/colab_live)
# 1. baseline that mimics a Colab runtime, not timed as part of the recipe: Python 3.12 (uv), numpy
#    2.0.2, scipy, matplotlib, pandas, nbconvert, ipykernel, git
# 2. colab_live.py: the notebook's setup cell with google.colab stubbed and an empty /content, so its
#    bootstrap clones the folder from GitHub (sscs-ose first, then the public repository at REPO_REF);
#    then setup_env.setup() (apt, pip, ciel), the SPICE demo and the live animation, each timed
# 3. the whole notebook, executed in live mode (jupyter nbconvert, google.colab stubbed), timed
# The setup cell comes from the notebook on GitHub at REPO_REF (what the Colab links open), or with
# LOCAL_NOTEBOOK=1 from this working tree, whose notebook/ folder is then also copied over the clone
# before step 3 (to test changes before they are pushed; the rest of the code still comes from GitHub).
# Results: OUTDIR/colab_live.json, colab_live.log, executed_live.ipynb, cell_times.json.
# Env: CPUS (default 2), MEMORY (default 8g), REPO_REF (default: setup_env.DEFAULT_REPO_REF),
#      LOCAL_NOTEBOOK (default 0).
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUT=$(mkdir -p "${1:-$REPO/runs/colab_live}" && cd "${1:-$REPO/runs/colab_live}" && pwd)
REF=${REPO_REF:-$(cd "$REPO/notebook" && python3 -c "import setup_env; print(setup_env.DEFAULT_REPO_REF)")}
URL=$(cd "$REPO/notebook" && python3 -c "import setup_env; print(setup_env.DEFAULT_REPO_URL)")
SCRIPT=$(cat <<'CONTAINER'
set -euo pipefail
exec > >(tee /out/colab_live.log) 2>&1
trap 'chown -R $HOST_UID:$HOST_GID /out' EXIT
T0=$(date +%s)
stamp() { echo "== $(( $(date +%s) - T0 )) s: $*"; }
stamp "baseline (Colab mimic, not part of the recipe)"
export DEBIAN_FRONTEND=noninteractive
apt-get -qq update >/dev/null
apt-get -qq install -y --no-install-recommends ca-certificates curl git python3 python3-pip >/dev/null
pip3 install -q uv 2>/dev/null
uv python install -q 3.12
uv venv -q --seed -p 3.12 /usr/local/colab
export PATH=/usr/local/colab/bin:$PATH
pip install -q numpy==2.0.2 scipy matplotlib pandas nbconvert ipykernel 2>&1 | grep -v "^WARNING" || true
python3 -c "import sys, numpy; print('python', sys.version.split()[0], 'numpy', numpy.__version__)"
git --version
cat /sys/fs/cgroup/cpu.max 2>/dev/null || nproc      # CPU quota (docker --cpus)
rm -rf /var/lib/apt/lists/*        # Colab starts with stale lists, so the recipe runs apt-get update
mkdir -p /root/.ipython/profile_default/startup
printf '%s\n' 'import sys, types' 'sys.modules.setdefault("google", types.ModuleType("google"))' \
  'sys.modules["google.colab"] = types.ModuleType("google.colab")' \
  > /root/.ipython/profile_default/startup/00-colab-stub.py
if [ "$LOCAL" = 1 ]; then NB=/nbsrc/ascon_glitch_leakage.ipynb
else NB=${URL/github.com/raw.githubusercontent.com}/$REF/notebook/ascon_glitch_leakage.ipynb; fi
stamp "setup cell and live steps (colab_live.py), notebook from $NB"
python3 /nbsrc/tests/colab_live.py --notebook "$NB" --out /out/colab_live.json
DIR=/content/$(python3 -c "import json; print(json.load(open('/out/colab_live.json'))['notebook_folder'])")
if [ "$LOCAL" = 1 ]; then
  (cd /nbsrc && tar --exclude=./__pycache__ -cf - .) | tar -xf - -C "$DIR"
fi
stamp "whole notebook in live mode: jupyter nbconvert --execute ($DIR)"
S=$(date +%s)
jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=1800 \
  --output-dir /out --output executed_live "$DIR/ascon_glitch_leakage.ipynb"
echo "notebook wall time $(( $(date +%s) - S )) s"
python3 - <<'PY'
import datetime, json
nb = json.load(open("/out/executed_live.ipynb"))
def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
cells = []
for k, c in enumerate(nb["cells"]):
    e = c.get("metadata", {}).get("execution", {})
    if c["cell_type"] == "code" and "iopub.execute_input" in e:
        dt = (ts(e["shell.execute_reply"]) - ts(e["iopub.execute_input"])).total_seconds()
        cells.append({"cell": k, "seconds": round(dt, 1), "first_line": c["source"][0].strip()[:60]})
text = ["".join(o.get("text", "")) for c in nb["cells"] for o in c.get("outputs", [])]
out = [t.strip() for t in text if "run mode" in t]
res = {"cells_seconds_total": round(sum(c["seconds"] for c in cells), 1), "mode_line": out, "cells": cells}
json.dump(res, open("/out/cell_times.json", "w"), indent=1)
print("code cells: %.1f s in total; mode line: %s" % (res["cells_seconds_total"], out))
for c in sorted(cells, key=lambda c: -c["seconds"])[:6]:
    print("  cell %2d %7.1f s  %s" % (c["cell"], c["seconds"], c["first_line"]))
PY
stamp done
CONTAINER
)
docker run --rm --cpus "${CPUS:-2}" --memory "${MEMORY:-8g}" -e HOST_UID="$(id -u)" \
  -e HOST_GID="$(id -g)" -e REF="$REF" -e URL="$URL" -e LOCAL="${LOCAL_NOTEBOOK:-0}" \
  -v "$REPO/notebook:/nbsrc:ro" -v "$OUT:/out" ubuntu:22.04 bash -c "$SCRIPT"
