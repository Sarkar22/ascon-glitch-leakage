# SPDX-License-Identifier: Apache-2.0
# Magic: transistor-level SPICE netlist with parasitic capacitances from a final GDS.
# Run by layout/run_pex.sh inside the OpenLane image:
#   magic -dnull -noconsole -rcfile $PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc extract.tcl
# Env: PEX_GDS (final GDS), PEX_TOP (top cell, e.g. dut_N), PEX_DIR (output directory).
# Output: $PEX_DIR/<top>_flat.spice, one flat .subckt <top>_flat with
#   - every transistor from the layout (sky130_fd_pr devices; W, L and the drain/source diffusion
#     area and perimeter ad/as/pd/ps as drawn),
#   - capacitance of every net to substrate and the coupling capacitance between nets (no threshold),
#   - no wire resistance (C-only extraction).
# The layout is flattened before extraction, so the capacitance between the routing and the cell
# geometry underneath it is extracted like any other overlap.

crashbackups stop
drc off
set top $::env(PEX_TOP)
set outdir $::env(PEX_DIR)
file mkdir $outdir

gds readonly true
gds read $::env(PEX_GDS)
load $top -dereference
select top cell
# flat copy of the layout; the top-level labels (ports and the routed nets' names) are kept
flatten -dotoplabels ${top}_flat
load ${top}_flat
select top cell

cd $outdir
extract path $outdir
extract do local
extract do capacitance
extract do coupling
extract do adjust
extract no resistance
extract unique
extract all

ext2spice format ngspice
ext2spice cthresh 0
ext2spice rthresh 0
ext2spice hierarchy off
ext2spice subcircuit on
ext2spice subcircuit top on
ext2spice scale off
ext2spice extresist off
ext2spice -o $outdir/${top}_flat.spice ${top}_flat
puts "PEX done: $outdir/${top}_flat.spice"
quit -noprompt
