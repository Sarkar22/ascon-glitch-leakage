# SPDX-License-Identifier: Apache-2.0
# Magic DRC of a GDS with the commands of OpenLane v1's signoff check (scripts/magic/drc.tcl with
# MAGIC_DRC_USE_GDS=1): full DRC style, euclidean distances, every error box listed with its rule.
# Run by layout/run_controls.sh inside the OpenLane image:
#   magic -dnull -noconsole -rcfile $PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc magic_drc.tcl
# Env: CTL_GDS (GDS), CTL_TOP (top cell), CTL_OUT (report to write).
# Report: one line per error box, "<llx> <lly> <urx> <ury> um <TAB> <rule text>", then "COUNT <n>".

crashbackups stop
gds read $::env(CTL_GDS)
set oscale [cif scale out]
magic::suspendall
load $::env(CTL_TOP)
select top cell
drc euclidean on
drc style drc(full)
drc check
set result [drc listall why]
set fout [open $::env(CTL_OUT) w]
set count 0
foreach {why boxes} $result {
    foreach b $boxes {
        puts $fout [format "%.3f %.3f %.3f %.3f um\t%s" [expr {$oscale * [lindex $b 0]}] \
            [expr {$oscale * [lindex $b 1]}] [expr {$oscale * [lindex $b 2]}] \
            [expr {$oscale * [lindex $b 3]}] $why]
        incr count
    }
}
puts $fout "COUNT $count"
close $fout
puts "Magic DRC: $count error boxes -> $::env(CTL_OUT)"
quit -noprompt
