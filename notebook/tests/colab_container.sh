#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Test the Colab path in a clean ubuntu:22.04 container (Colab's OS), from the repository root:
#   bash notebook/tests/colab_container.sh [OUTDIR]        (default OUTDIR: runs/colab_test)
# 1. baseline that mimics a Colab runtime (not part of the recipe): Python 3.12 (uv), numpy 2.0.2,
#    scipy, matplotlib, pandas, git, curl
# 2. the recipe, as the notebook runs it: python3 notebook/setup_env.py --install
#    (apt: ngspice iverilog; pip: ciel; ciel: sky130A at the pinned hash)
# 3. python3 notebook/colab_check.py: netlists, iverilog, probing, stimuli, level-1/2 models and
#    the live SPICE demo, each timed and compared with notebook/data/
# The repository is copied in (no clone) without .git, build/ and runs/. Results: OUTDIR/
# colab_check.json and colab_container.log. Env: CPUS (default 4), MEMORY (default 4g).
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
OUT=$(mkdir -p "${1:-$REPO/runs/colab_test}" && cd "${1:-$REPO/runs/colab_test}" && pwd)
CPUS=${CPUS:-4}
MEMORY=${MEMORY:-4g}
docker run --rm --cpus "$CPUS" --memory "$MEMORY" -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -v "$REPO:/src:ro" -v "$OUT:/out" ubuntu:22.04 bash -c '
set -euo pipefail
exec > >(tee /out/colab_container.log) 2>&1
trap "chown -R $HOST_UID:$HOST_GID /out" EXIT
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
pip install -q numpy==2.0.2 scipy matplotlib pandas 2>&1 | grep -v "^WARNING" || true
python3 -c "import sys, numpy; print(\"python\", sys.version.split()[0], \"numpy\", numpy.__version__)"
rm -rf /var/lib/apt/lists/*        # Colab starts with stale lists, so the recipe runs apt-get update
mkdir -p /content/ascon-glitch-leakage
(cd /src && tar --exclude=./.git --exclude=./build --exclude=./runs --exclude="*/__pycache__" -cf - .) \
  | tar -xf - -C /content/ascon-glitch-leakage
cd /content/ascon-glitch-leakage
stamp "recipe: python3 notebook/setup_env.py --install"
python3 notebook/setup_env.py --install
ngspice -v | grep -m1 ngspice
du -sh "$(readlink -f ~/.ciel/sky130A)"
stamp "check: python3 notebook/colab_check.py"
python3 notebook/colab_check.py --out /out/colab_check.json
stamp "done"
'
