#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Post-layout SPICE model of one variant: Magic extraction of the final GDS (transistors with drawn
# diffusion areas/perimeters, parasitic capacitance incl. coupling, no R) wrapped as a subckt with the
# pre-layout port order, so sim/spice_campaign.py can run it unchanged.
#   bash layout/run_flow.sh N && bash layout/run_pex.sh N
# Reads  runs/pex/ol/<V>/runs/pex/results/final/gds/dut_<V>.gds (from layout/run_flow.sh)
# Writes runs/pex/ext/<V>/dut_<V>_flat.spice (raw Magic output, with its .ext files)
#        build/<V>_pex/{dut.sp,ports.json} (via layout/make_pex.py)
# Env: PDK_ROOT [~/.ciel], OL_IMAGE [OpenLane v1 image], DOCKER_OPTS [runs/docker_opts].
set -euo pipefail
V=${1:?usage: layout/run_pex.sh <variant>}
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PDK_ROOT=${PDK_ROOT:-$HOME/.ciel}
OL_IMAGE=${OL_IMAGE:-ghcr.io/the-openroad-project/openlane:ff5509f65b17bfa4068d5336495ab1718987ff69-amd64}
DOCKER_OPTS=${DOCKER_OPTS:-$(cat "$REPO/runs/docker_opts" 2>/dev/null || true)}
GDS=$REPO/runs/pex/ol/$V/runs/pex/results/final/gds/dut_$V.gds
OUT=$REPO/runs/pex/ext/$V
[ -f "$GDS" ] || { echo "missing $GDS (run layout/run_flow.sh $V)"; exit 1; }
rm -rf "$OUT"; mkdir -p "$OUT"

# shellcheck disable=SC2086
docker run --rm --init $DOCKER_OPTS -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PDK_ROOT:$PDK_ROOT" -v "$REPO:$REPO" -w "$OUT" -e PDK_ROOT="$PDK_ROOT" -e PDK=sky130A \
  -e PEX_GDS="$GDS" -e PEX_TOP="dut_$V" -e PEX_DIR="$OUT" \
  "$OL_IMAGE" magic -dnull -noconsole -rcfile "$PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc" \
  "$REPO/layout/pex/extract.tcl" > "$OUT/magic.log" 2>&1 < /dev/null
tail -3 "$OUT/magic.log"
python3 "$REPO/layout/make_pex.py" --variant "$V"
