#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run the organizers' two CI jobs (sscs-ose-code-a-chip .github/workflows/lint.yaml and run.yaml)
# on this notebook folder, each in its own clean python:3.10-slim container, from the repo root:
#   bash notebook/tests/ci_container.sh [OUTDIR]           (default OUTDIR: runs/ci_test)
# The folder is copied to ISSCC27/submitted_notebooks/ascon_glitch_leakage/ as in the PR.
#   lint: pip install flake8 nbQA; nbqa flake8 --ignore=E402,E226; colab-badge greps
#   run:  apt-get install graphviz; pip install pytest nbmake pandas graphviz matplotlib;
#         pytest --nbmake
# The workflows write `**/*.ipynb` in a bash without globstar, where `**` matches one directory
# level only; this script runs each command with globstar on, so every notebook is included.
# Env: CPUS (default 2), NOTEBOOKS (default: all *.ipynb of the folder).
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUT=$(mkdir -p "${1:-$REPO/runs/ci_test}" && cd "${1:-$REPO/runs/ci_test}" && pwd)
CPUS=${CPUS:-2}
DEST=ISSCC27/submitted_notebooks/ascon_glitch_leakage
PREP='set -euo pipefail; shopt -s globstar
trap "chown -R $HOST_UID:$HOST_GID /out" EXIT
mkdir -p /w/'$DEST' && cd /src && tar --exclude="./__pycache__" --exclude="./.ipynb_checkpoints" \
  -cf - . | tar -xf - -C /w/'$DEST' && cd /w
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
NB=${NOTEBOOKS:-$(ls **/*.ipynb)}
stamp "nbqa flake8 --ignore=E402,E226 $NB"
nbqa flake8 --ignore=E402,E226 $NB && echo "flake8: PASS"
grep -l colab-badge $NB && echo "has colab-badge: PASS"
grep colab-badge $NB | (! grep -v "sscs-ose") && echo "colab-badge is sscs-ose: PASS"
stamp done'
run nbmake '
stamp "apt-get install graphviz; pip install pytest nbmake pandas graphviz matplotlib"
apt-get -qq update >/dev/null && apt-get -qq install -y graphviz >/dev/null
pip install -q --root-user-action=ignore pytest nbmake pandas graphviz matplotlib
python --version; pip list 2>/dev/null | grep -i -E "^(pytest|nbmake|pandas|numpy|matplotlib|graphviz|scipy|ipywidgets|ngspice) "
NB=${NOTEBOOKS:-$(ls **/*.ipynb)}
stamp "pytest --nbmake $NB"
pytest --nbmake --durations=0 $NB && echo "nbmake: PASS"
stamp done'
