# Deterministic Vivado implementation + power estimation flow (boardless).
# Usage:
#   vivado -mode batch -source scripts/amd/vivado_artix7_impl_power.tcl -tclargs \
#     --benchmark <id> --top nema_kernel --tb <tb.cpp> --clock-ns 5.0 \
#     --part xc7a200t-1sbg484c --outdir <dir> \
#     --rtl-glob "<sol1>/syn/verilog/*.v" \
#     --xci-glob "<sol1>/impl/ip/hdl/ip/**/*.xci" \
#     --xdc-glob "<sol1>/impl/ip/constraints/*.xdc"

proc _arg_value {argv key default} {
  set idx [lsearch -exact $argv $key]
  if {$idx < 0} {
    return $default
  }
  set next [expr {$idx + 1}]
  if {$next >= [llength $argv]} {
    error "missing value for argument $key"
  }
  return [lindex $argv $next]
}

proc _require_nonempty {name value} {
  if {$value eq ""} {
    error "required argument is empty: $name"
  }
}

set benchmark [_arg_value $argv "--benchmark" ""]
set top_name [_arg_value $argv "--top" "nema_kernel"]
set tb_name [_arg_value $argv "--tb" ""]
set clock_ns [_arg_value $argv "--clock-ns" "5.0"]
set requested_part [_arg_value $argv "--part" "xc7a200t-1sbg484c"]
set outdir [_arg_value $argv "--outdir" ""]
set rtl_glob [_arg_value $argv "--rtl-glob" ""]
set xci_glob [_arg_value $argv "--xci-glob" ""]
set xdc_glob [_arg_value $argv "--xdc-glob" ""]

_require_nonempty "--benchmark" $benchmark
_require_nonempty "--outdir" $outdir
_require_nonempty "--rtl-glob" $rtl_glob

file mkdir $outdir
set logs_dir [file normalize [file join $outdir "logs"]]
file mkdir $logs_dir
set status_file [file normalize [file join $outdir "vivado_status.json"]]

# Required stage artifacts (G1c evidence surface).
set post_synth_dcp [file normalize [file join $outdir "post_synth.dcp"]]
set post_route_dcp [file normalize [file join $outdir "post_route.dcp"]]
set post_synth_util_report [file normalize [file join $outdir "post_synth_utilization.rpt"]]
set post_route_util_report [file normalize [file join $outdir "post_route_utilization.rpt"]]
set post_synth_timing_report [file normalize [file join $outdir "post_synth_timing.rpt"]]
set post_route_timing_report [file normalize [file join $outdir "post_route_timing.rpt"]]
set operating_conditions_report [file normalize [file join $outdir "operating_conditions.rpt"]]

# Legacy compatibility report names.
set util_report [file normalize [file join $outdir "vivado_utilization.rpt"]]
set timing_report [file normalize [file join $outdir "vivado_timing_summary.rpt"]]
set power_report [file normalize [file join $outdir "vivado_power_estimated.rpt"]]
set part_report [file normalize [file join $outdir "vivado_selected_part.txt"]]

set available_parts [get_parts]
if {[lsearch -exact $available_parts $requested_part] >= 0} {
  set selected_part $requested_part
} elseif {[llength $available_parts] > 0} {
  set probe_preview [join [lrange $available_parts 0 9] ","]
  error "NEMA_VIVADO_ERROR: requested_part_unavailable requested=$requested_part sample_available_parts=$probe_preview"
} else {
  error "NEMA_VIVADO_ERROR: no available parts in this Vivado install"
}

create_project -in_memory nema_impl
set_part $selected_part
set_property part $selected_part [current_project]
set fp [open $part_report w]
puts $fp $selected_part
close $fp

set rtl_files [glob -nocomplain -types f $rtl_glob]
if {[llength $rtl_files] == 0} {
  error "NEMA_VIVADO_ERROR: no RTL files found for glob: $rtl_glob"
}

set ip_xci {}
if {$xci_glob ne ""} {
  set ip_xci [glob -nocomplain -types f $xci_glob]
}

set nema_has_ip_inst 0
foreach rtl $rtl_files {
  set fh [open $rtl r]
  set rtl_text [read $fh]
  close $fh
  if {[regexp {\\m[A-Za-z0-9_]+_ip\\M} $rtl_text]} {
    set nema_has_ip_inst 1
    break
  }
}
if {$nema_has_ip_inst && [llength $ip_xci] == 0} {
  error "NEMA_VIVADO_ERROR: detected *_ip instance but no .xci files were found"
}

foreach ip $ip_xci {
  read_ip $ip
}
if {[llength $ip_xci] > 0} {
  generate_target all [get_files -all -quiet *.xci]
  catch {synth_ip [get_ips -all]}
}

foreach rtl $rtl_files {
  read_verilog $rtl
}

if {$xdc_glob ne ""} {
  set xdc_files [glob -nocomplain -types f $xdc_glob]
  foreach xdc $xdc_files {
    read_xdc $xdc
  }
}

synth_design -top $top_name -part $selected_part
if {[llength [get_ports -quiet ap_clk]] > 0} {
  create_clock -name ap_clk -period $clock_ns [get_ports ap_clk]
}

report_utilization -file $post_synth_util_report
report_timing_summary -file $post_synth_timing_report -delay_type max -max_paths 10
write_checkpoint -force $post_synth_dcp

opt_design
place_design
phys_opt_design
route_design

write_checkpoint -force $post_route_dcp
report_utilization -file $post_route_util_report
report_timing_summary -file $post_route_timing_report -delay_type max -max_paths 10
report_power -file $power_report
catch { report_operating_conditions -file $operating_conditions_report }

# Legacy compatibility copies.
file copy -force $post_route_util_report $util_report
file copy -force $post_route_timing_report $timing_report

set sf [open $status_file w]
puts $sf "{"
puts $sf "  \"benchmark\": \"$benchmark\","
puts $sf "  \"top\": \"$top_name\","
puts $sf "  \"tb\": \"$tb_name\","
puts $sf "  \"requested_part\": \"$requested_part\","
puts $sf "  \"part\": \"$selected_part\","
puts $sf "  \"impl_ok\": true,"
puts $sf "  \"post_synth_dcp\": \"$post_synth_dcp\","
puts $sf "  \"post_route_dcp\": \"$post_route_dcp\","
puts $sf "  \"post_synth_utilization\": \"$post_synth_util_report\","
puts $sf "  \"post_route_utilization\": \"$post_route_util_report\","
puts $sf "  \"post_synth_timing\": \"$post_synth_timing_report\","
puts $sf "  \"post_route_timing\": \"$post_route_timing_report\","
puts $sf "  \"operating_conditions_report\": \"$operating_conditions_report\","
puts $sf "  \"timing_report\": \"$timing_report\","
puts $sf "  \"util_report\": \"$util_report\","
puts $sf "  \"power_report\": \"$power_report\","
set part_match_requested "false"
if {$selected_part eq $requested_part} {
  set part_match_requested "true"
}
puts $sf "  \"part_match_requested\": $part_match_requested"
puts $sf "}"
close $sf

exit
