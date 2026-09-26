# SPDX-License-Identifier: Apache-2.0
# Magic: transistor-level SPICE netlist with parasitic R and C from a final GDS (the RC bracket of
# the C-only extraction in extract.tcl; everything else is the same as there).
# Run by layout/run_pex_rc.sh inside the OpenLane image:
#   magic -dnull -noconsole -rcfile $PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc extract_rc.tcl
# Env: PEX_GDS (final GDS), PEX_TOP (top cell, e.g. dut_N), PEX_DIR (output directory),
#      PEX_RTOL (extresist tolerance, default 10: a larger value merges fewer resistors),
#      PEX_RIGNORE (nets left without resistance, default "VPWR VGND": the supply stays one
#      ideal node per rail, as in the C-only netlist and the testbench; set it to "" to extract
#      the rails too).
# Output: $PEX_DIR/<top>_flat.spice, one flat .subckt <top>_flat with
#   - every transistor, capacitance to substrate and coupling capacitance, as in extract.tcl,
#   - resistance from Magic's extresist on every net except PEX_RIGNORE: each net becomes a
#     resistor network through its routing, vias and contacts and through the cells' own poly,
#     li1 and local-interconnect geometry, with its capacitance distributed over the network's
#     nodes (small series resistors merged within the tolerance PEX_RTOL).
# Method (Magic manual, "extresist"): extract with lumped resistance, write the .sim/.nodes files
# with ext2sim, run "extresist all", then ext2spice with "extresist on", which splices the
# resistor networks of <top>.res.ext into the netlist. Magic 8.3.413 looks for the .res.ext file
# only on ext2spice's -p search path, so the -p argument below is required (without it the
# output silently has no resistors).

crashbackups stop
drc off
set top $::env(PEX_TOP)
set outdir $::env(PEX_DIR)
set rtol [expr {[info exists ::env(PEX_RTOL)] ? $::env(PEX_RTOL) : 10}]
set rignore [expr {[info exists ::env(PEX_RIGNORE)] ? $::env(PEX_RIGNORE) : "VPWR VGND"}]
file mkdir $outdir

gds readonly true
gds read $::env(PEX_GDS)
load $top -dereference
select top cell
flatten -dotoplabels ${top}_flat
load ${top}_flat
select top cell

cd $outdir
extract path $outdir
extract do local
extract do capacitance
extract do coupling
extract do adjust
extract do resistance
extract unique
extract all

ext2sim labels on
ext2sim
extresist tolerance $rtol
foreach net $rignore {
    extresist ignore $net
}
extresist all

ext2spice format ngspice
ext2spice cthresh 0
ext2spice rthresh 0
ext2spice hierarchy off
ext2spice subcircuit on
ext2spice subcircuit top on
ext2spice scale off
ext2spice extresist on
ext2spice -p $outdir -o $outdir/${top}_flat.spice ${top}_flat
puts "PEX RC done: $outdir/${top}_flat.spice (extresist tolerance $rtol, no R on: $rignore)"
quit -noprompt
