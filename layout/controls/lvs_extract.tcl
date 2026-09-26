# SPDX-License-Identifier: Apache-2.0
# Magic: LVS netlist of a final GDS, with the commands of OpenLane v1's signoff extraction
# (scripts/magic/extract_spice.tcl with MAGIC_EXT_USE_GDS=1, LVS_CONNECT_BY_LABEL=0).
# Run by layout/run_controls.sh inside the OpenLane image:
#   magic -dnull -noconsole -rcfile $PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc lvs_extract.tcl
# Env: CTL_GDS (GDS), CTL_TOP (top cell), CTL_OUT (SPICE netlist to write), CTL_DIR (work directory).

crashbackups stop
gds read $::env(CTL_GDS)
load $::env(CTL_TOP) -dereference
file mkdir $::env(CTL_DIR)
cd $::env(CTL_DIR)

extract do local
extract no capacitance
extract no coupling
extract no resistance
extract no adjust
extract unique
extract

ext2spice lvs
ext2spice -o $::env(CTL_OUT) $::env(CTL_TOP).ext
puts "LVS extraction done: $::env(CTL_OUT)"
quit -noprompt
