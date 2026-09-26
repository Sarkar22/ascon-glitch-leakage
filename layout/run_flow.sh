#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Place and route one variant with OpenLane v1, from its structural netlist build/<V>/dut.v.
#   bash layout/run_flow.sh N            (then DA, U; run one at a time)
# The design directory is assembled under runs/pex/ol/<V>/ (git-ignored): src/dut.v (a copy of
# build/<V>/dut.v), config.json (layout/<V>/config.json) and pin_order.cfg; the OpenLane run is
# runs/pex/ol/<V>/runs/pex/. Host paths are resolved here, at run time; nothing absolute is committed.
# Env (defaults in brackets):
#   OPENLANE_DIR  OpenLane v1 checkout with flow.tcl        [~/rtl2gds/OpenLane]
#   PDK_ROOT      directory holding sky130A (ciel)          [~/.ciel]
#   OL_IMAGE      OpenLane image                            [ghcr.io/the-openroad-project/openlane:ff5509f...-amd64]
#   DOCKER_OPTS   extra docker options, e.g. a CPU cap       [contents of runs/docker_opts]
set -euo pipefail
V=${1:?usage: layout/run_flow.sh <variant>}
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OPENLANE_DIR=${OPENLANE_DIR:-$HOME/rtl2gds/OpenLane}
PDK_ROOT=${PDK_ROOT:-$HOME/.ciel}
OL_IMAGE=${OL_IMAGE:-ghcr.io/the-openroad-project/openlane:ff5509f65b17bfa4068d5336495ab1718987ff69-amd64}
DOCKER_OPTS=${DOCKER_OPTS:-$(cat "$REPO/runs/docker_opts" 2>/dev/null || true)}

[ -f "$REPO/build/$V/dut.v" ] || { echo "missing build/$V/dut.v (run gen/make_variants.py)"; exit 1; }
[ -f "$REPO/layout/$V/config.json" ] || { echo "missing layout/$V/config.json"; exit 1; }
D=$REPO/runs/pex/ol/$V
mkdir -p "$D/src"
cp "$REPO/build/$V/dut.v" "$D/src/dut.v"
cp "$REPO/layout/$V/config.json" "$D/config.json"
cp "$REPO/layout/pin_order.cfg" "$D/pin_order.cfg"

# shellcheck disable=SC2086
docker run --rm --init $DOCKER_OPTS -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$OPENLANE_DIR:/openlane" -v "$PDK_ROOT:$PDK_ROOT" -v "$REPO:$REPO" \
  -e PDK_ROOT="$PDK_ROOT" -e PDK=sky130A -e STD_CELL_LIBRARY=sky130_fd_sc_hd \
  -w /openlane "$OL_IMAGE" ./flow.tcl -design "$D" -tag pex -overwrite -pdk sky130A
echo "run directory: runs/pex/ol/$V/runs/pex"
