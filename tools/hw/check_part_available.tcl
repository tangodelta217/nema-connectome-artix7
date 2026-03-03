set requested_part "xc7a200tsbg484-1"
if {[llength $argv] >= 1} {
  set requested_part [string trim [lindex $argv 0]]
}

if {$requested_part eq ""} {
  puts stderr "NEMA_PART_CHECK_ERROR: empty requested part"
  puts stderr "usage: vivado -mode batch -source tools/hw/check_part_available.tcl -tclargs <part>"
  exit 2
}

set exact_match [lsort [get_parts $requested_part]]
if {[llength $exact_match] > 0} {
  puts "NEMA_PART_CHECK_OK: requested=$requested_part available=[join $exact_match ,]"
  exit 0
}

set all_parts [lsort [get_parts *]]
set fallback_part ""
if {[llength $all_parts] > 0} {
  set fallback_part [lindex $all_parts 0]
}

set artix_candidates [lsort [get_parts xc7a*]]
puts stderr "NEMA_PART_CHECK_FAIL: requested_part_unavailable requested=$requested_part"
if {[llength $artix_candidates] > 0} {
  puts stderr "NEMA_PART_CHECK_HINT: installed_xc7a_parts=[join $artix_candidates ,]"
} else {
  puts stderr "NEMA_PART_CHECK_HINT: no xc7a* parts listed by this Vivado installation."
}
if {$fallback_part ne ""} {
  puts stderr "NEMA_PART_CHECK_FALLBACK: first_available=$fallback_part"
}
puts stderr "ACTION: install device support Artix-7 in Vivado (target part: $requested_part)."
puts stderr "VERIFY: vivado -mode batch -source tools/hw/check_part_available.tcl -tclargs $requested_part"
exit 3
