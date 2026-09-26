#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Negative controls of the layout sign-off (see layout/neg_controls.py for the cases):
#   LVS  netgen of the layout netlist that Magic extracts from results/layout/gds/dut_<V>.gds
#        against the correct final netlist and three wrong ones (share swap, gate type, missing
#        flip-flop), for each variant given (default N DA);
#   DRC  Magic (OpenLane's signoff commands) and KLayout (sky130A_mr.drc) on the clean GDS of the
#        first variant and on a copy with a met1 spacing and a via1 enclosure violation added.
#   bash layout/run_controls.sh [N DA]
# Needs runs/pex/ol/<V>/ from layout/run_flow.sh (the final netlist) and build/<V>/graph.json.
# Writes runs/controls/ (git-ignored) and results/layout/negative_controls.json. About 30 s.
# Env: PDK_ROOT [~/.ciel], OL_IMAGE [OpenLane v1 image], DOCKER_OPTS [runs/docker_opts].
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PDK_ROOT=${PDK_ROOT:-$HOME/.ciel}
OL_IMAGE=${OL_IMAGE:-ghcr.io/the-openroad-project/openlane:ff5509f65b17bfa4068d5336495ab1718987ff69-amd64}
DOCKER_OPTS=${DOCKER_OPTS:-$(cat "$REPO/runs/docker_opts" 2>/dev/null || true)}
VARIANTS=${*:-N DA}
FIRST=${VARIANTS%% *}
CTL=$REPO/runs/controls
PDK=$PDK_ROOT/sky130A
MAGICRC=$PDK/libs.tech/magic/sky130A.magicrc
KL=$PDK/libs.tech/klayout

for V in $VARIANTS; do
  [ -f "$REPO/results/layout/gds/dut_$V.gds" ] || { echo "missing results/layout/gds/dut_$V.gds"; exit 1; }
  rm -rf "${CTL:?}/$V"; mkdir -p "$CTL/$V"
  python3 "$REPO/layout/neg_controls.py" mutants --variant "$V"
  for c in correct share_swap gate_type missing_ff; do
    cat > "$CTL/$V/lvs_$c.tcl" <<EOF
readnet spice $PDK/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice 1
lvs {$CTL/$V/layout.spice dut_$V} {$CTL/$V/$c.v dut_$V} $PDK/libs.tech/netgen/sky130A_setup.tcl $CTL/$V/lvs_$c.log -json
EOF
  done
done
rm -rf "$CTL/drc"; mkdir -p "$CTL/drc"

# shellcheck disable=SC2086
docker run --rm --init $DOCKER_OPTS -u "$(id -u):$(id -g)" -e HOME=/tmp -e QT_QPA_PLATFORM=offscreen \
  -v "$PDK_ROOT:$PDK_ROOT" -v "$REPO:$REPO" -w "$CTL" -e PDK_ROOT="$PDK_ROOT" -e PDK=sky130A \
  "$OL_IMAGE" bash -c "
    set -e
    for V in $VARIANTS; do
      CTL_GDS=$REPO/results/layout/gds/dut_\$V.gds CTL_TOP=dut_\$V CTL_OUT=$CTL/\$V/layout.spice \
        CTL_DIR=$CTL/\$V/ext magic -dnull -noconsole -rcfile $MAGICRC \
        $REPO/layout/controls/lvs_extract.tcl > $CTL/\$V/lvs_extract.log 2>&1 < /dev/null
      for c in correct share_swap gate_type missing_ff; do
        netgen -batch source $CTL/\$V/lvs_\$c.tcl > $CTL/\$V/lvs_\$c.out 2>&1 < /dev/null
      done
    done
    klayout -b -r $REPO/layout/controls/inject_drc.py -rd gds_in=$REPO/results/layout/gds/dut_$FIRST.gds \
      -rd gds_out=$CTL/drc/dut_${FIRST}_injected.gds -rd json_out=$CTL/drc/injected.json
    for g in clean injected; do
      f=$REPO/results/layout/gds/dut_$FIRST.gds; [ \$g = injected ] && f=$CTL/drc/dut_${FIRST}_injected.gds
      CTL_GDS=\$f CTL_TOP=dut_$FIRST CTL_OUT=$CTL/drc/magic_\$g.rpt magic -dnull -noconsole \
        -rcfile $MAGICRC $REPO/layout/controls/magic_drc.tcl > $CTL/drc/magic_\$g.log 2>&1 < /dev/null
      klayout -b -r $KL/drc/sky130A_mr.drc -rd input=\$f -rd top_cell=dut_$FIRST \
        -rd report=$CTL/drc/klayout_\$g.lyrdb -rd feol=1 -rd beol=1 -rd offgrid=1 -rd thr=2 \
        > $CTL/drc/klayout_\$g.log 2>&1
    done"
# shellcheck disable=SC2086
python3 "$REPO/layout/neg_controls.py" summarize $VARIANTS
