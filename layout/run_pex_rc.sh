#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# RC bracket of the post-layout model of one variant: Magic extraction of the final GDS with
# resistance (layout/pex/extract_rc.tcl, extresist on every net), combined with the capacitance of
# the C-only extraction (layout/make_pex_rc.py explains why) and wrapped for the unchanged runner.
#   bash layout/run_pex_rc.sh N
# The supply rails VPWR/VGND get no resistance (one ideal node each, as in build/<V>_pex and the
# testbench's ideal supply at the pins); every other net gets its resistor network.
# Reads  results/layout/gds/dut_<V>.gds (the committed final GDS) and
#        runs/pex/ext/<V>/dut_<V>_flat.spice (the C-only extraction, layout/run_pex.sh)
# Writes runs/pex/rc/ext_<V>_<tag>/ (raw Magic output) and runs/pex/rc/<V>_<tag>/{dut.sp,ports.json,
#        graph.json}, tag rc (via layout/make_pex_rc.py). About 5 s.
# Env: PDK_ROOT [~/.ciel], OL_IMAGE [OpenLane v1 image], DOCKER_OPTS [runs/docker_opts],
#      PEX_RTOL [10].
set -euo pipefail
V=${1:?usage: layout/run_pex_rc.sh <variant>}
TAG=rc
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PDK_ROOT=${PDK_ROOT:-$HOME/.ciel}
OL_IMAGE=${OL_IMAGE:-ghcr.io/the-openroad-project/openlane:ff5509f65b17bfa4068d5336495ab1718987ff69-amd64}
DOCKER_OPTS=${DOCKER_OPTS:-$(cat "$REPO/runs/docker_opts" 2>/dev/null || true)}
GDS=$REPO/results/layout/gds/dut_$V.gds
OUT=$REPO/runs/pex/rc/ext_${V}_$TAG
[ -f "$GDS" ] || { echo "missing $GDS"; exit 1; }
[ -f "$REPO/runs/pex/ext/$V/dut_${V}_flat.spice" ] || { echo "missing the C-only extraction (layout/run_pex.sh $V)"; exit 1; }
rm -rf "$OUT"; mkdir -p "$OUT"

# shellcheck disable=SC2086
docker run --rm --init $DOCKER_OPTS -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PDK_ROOT:$PDK_ROOT" -v "$REPO:$REPO" -w "$OUT" -e PDK_ROOT="$PDK_ROOT" -e PDK=sky130A \
  -e PEX_GDS="$GDS" -e PEX_TOP="dut_$V" -e PEX_DIR="$OUT" -e PEX_RTOL="${PEX_RTOL:-10}" \
  -e PEX_RIGNORE="VPWR VGND" \
  "$OL_IMAGE" magic -dnull -noconsole -rcfile "$PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc" \
  "$REPO/layout/pex/extract_rc.tcl" > "$OUT/magic.log" 2>&1 < /dev/null
tail -1 "$OUT/magic.log"
python3 "$REPO/layout/make_pex_rc.py" --variant "$V" --rc "$OUT/dut_${V}_flat.spice" \
  --out "$REPO/runs/pex/rc/${V}_$TAG"
