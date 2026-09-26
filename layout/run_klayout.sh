#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# KLayout DRC (the PDK's sky130A_mr.drc deck: FEOL, BEOL and off-grid rules) and layer-coloured
# PNGs of one variant's final GDS, inside the OpenLane v1 image (KLayout 0.28).
#   bash layout/run_klayout.sh N
# Writes runs/pex/klayout/<V>/drc.lyrdb (+ drc.log) and results/layout/<V>_layout.png (all layers),
# results/layout/<V>_routing.png (metals, vias and pins only).
# Env: PDK_ROOT [~/.ciel], OL_IMAGE [OpenLane v1 image], DOCKER_OPTS [runs/docker_opts], WIDTH [1000].
set -euo pipefail
V=${1:?usage: layout/run_klayout.sh <variant>}
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PDK_ROOT=${PDK_ROOT:-$HOME/.ciel}
OL_IMAGE=${OL_IMAGE:-ghcr.io/the-openroad-project/openlane:ff5509f65b17bfa4068d5336495ab1718987ff69-amd64}
DOCKER_OPTS=${DOCKER_OPTS:-$(cat "$REPO/runs/docker_opts" 2>/dev/null || true)}
WIDTH=${WIDTH:-1000}
GDS=$REPO/runs/pex/ol/$V/runs/pex/results/final/gds/dut_$V.gds
OUT=$REPO/runs/pex/klayout/$V
KL=$PDK_ROOT/sky130A/libs.tech/klayout
[ -f "$GDS" ] || { echo "missing $GDS (run layout/run_flow.sh $V)"; exit 1; }
mkdir -p "$OUT" "$REPO/results/layout"

# shellcheck disable=SC2086
docker run --rm --init $DOCKER_OPTS -u "$(id -u):$(id -g)" -e HOME=/tmp -e QT_QPA_PLATFORM=offscreen \
  -v "$PDK_ROOT:$PDK_ROOT" -v "$REPO:$REPO" -w "$REPO" "$OL_IMAGE" bash -c "
    klayout -b -r '$KL/drc/sky130A_mr.drc' -rd input='$GDS' -rd top_cell=dut_$V \
      -rd report='$OUT/drc.lyrdb' -rd feol=1 -rd beol=1 -rd offgrid=1 -rd thr=2 > '$OUT/drc.log' 2>&1
    for m in all routing; do
      name=layout; [ \$m = routing ] && name=routing
      klayout -b -r layout/render.py -rd gds='$GDS' -rd lyp='$KL/tech/sky130A.lyp' \
        -rd out='$REPO/results/layout/${V}_'\$name.png -rd width=$WIDTH -rd layers=\$m
    done"
echo "KLayout DRC items: $(grep -c '<item>' "$OUT/drc.lyrdb" || true)  (runs/pex/klayout/$V/drc.lyrdb)"
