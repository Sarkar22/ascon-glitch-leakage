#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run a command inside the cac-sca docker image (ngspice-42, python3 + numpy/scipy/matplotlib)
# with this repository and the PDK mounted at their host paths.
#   bash sim/docker_run.sh python3 sim/spice_campaign.py run --dut build/U --stim s.npy --out runs/u
# Env: PDK (default: realpath of ~/.ciel/sky130A), IMAGE (default cac-sca:0.1).
# Output paths must lie inside the repository (runs/ is git-ignored).
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PDK=${PDK:-$(readlink -f ~/.ciel/sky130A)}
IMAGE=${IMAGE:-cac-sca:0.1}
case "$PWD/" in "$REPO"/*) WD=$PWD ;; *) WD=$REPO ;; esac
# Optional extra docker options, e.g. a CPU cap to keep a laptop responsive: DOCKER_OPTS="--cpus 6",
# or put them in runs/docker_opts (git-ignored, machine-local).
DOCKER_OPTS=${DOCKER_OPTS:-$(cat "$REPO/runs/docker_opts" 2>/dev/null || true)}
# shellcheck disable=SC2086
exec docker run --rm --init $DOCKER_OPTS -u "$(id -u):$(id -g)" -e PDK="$PDK" -e HOME=/tmp \
  -v "$PDK:$PDK:ro" -v "$REPO:$REPO" -w "$WD" "$IMAGE" "$@"
