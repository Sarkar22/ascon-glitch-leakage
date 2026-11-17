#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run the notebook job of .github/workflows/ci.yml locally, each half in its own clean
# python:3.10-slim container, from the repo root:
#   bash notebook/tests/ci_container.sh [OUTDIR]           (default OUTDIR: runs/ci_test)
# The containers see only notebook/ (mounted read-only and copied to /w/notebook/), so no helper
# can fall back to the repository's results/.
#   lint: pip install flake8 nbQA; nbqa flake8 --ignore=E402,E226; grep colab-badge
#   run:  apt-get install graphviz; pip install pytest nbmake pandas graphviz matplotlib;
#         pytest --nbmake
# Env: CPUS (default 2), NOTEBOOKS (default: notebook/*.ipynb, paths from the repository root).
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUT=$(mkdir -p "${1:-$REPO/runs/ci_test}" && cd "${1:-$REPO/runs/ci_test}" && pwd)
CPUS=${CPUS:-2}
PREP='set -euo pipefail
trap "chown -R $HOST_UID:$HOST_GID /out" EXIT
mkdir -p /w/notebook && cd /src && tar --exclude="./__pycache__" --exclude="./.ipynb_checkpoints" \
  -cf - . | tar -xf - -C /w/notebook && cd /w
T0=$(date +%s); stamp() { echo "== $(( $(date +%s) - T0 )) s: $*"; }'
run() {   # name, script
  docker run --rm --cpus "$CPUS" --memory 3g -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    -e NOTEBOOKS="${NOTEBOOKS:-}" -v "$REPO/notebook:/src:ro" -v "$OUT:/out" python:3.10-slim \
    bash -c "$PREP
$2" 2>&1 | tee "$OUT/$1.log"
}
run lint '
stamp "pip install flake8 nbQA"
pip install -q --root-user-action=ignore flake8 nbQA
python --version; pip list 2>/dev/null | grep -i -E "^(flake8|nbqa) "
NB=${NOTEBOOKS:-$(ls notebook/*.ipynb)}
stamp "nbqa flake8 --ignore=E402,E226 $NB"
nbqa flake8 --ignore=E402,E226 $NB && echo "flake8: PASS"
grep -l colab-badge $NB && echo "has colab-badge: PASS"
stamp done'
run nbmake '
stamp "apt-get install graphviz; pip install pytest nbmake pandas graphviz matplotlib"
apt-get -qq update >/dev/null && apt-get -qq install -y graphviz >/dev/null
pip install -q --root-user-action=ignore pytest nbmake pandas graphviz matplotlib
python --version; pip list 2>/dev/null | grep -i -E "^(pytest|nbmake|pandas|numpy|matplotlib|graphviz|scipy|ipywidgets|ngspice) "
NB=${NOTEBOOKS:-$(ls notebook/*.ipynb)}
stamp "pytest --nbmake $NB"
pytest --nbmake --durations=0 $NB && echo "nbmake: PASS"
stamp done'
