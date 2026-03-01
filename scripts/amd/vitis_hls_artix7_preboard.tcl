# Deterministic Vitis HLS pre-board flow for Artix-7 runs.
# Usage (from run_artix7_hls.py):
#   vitis_hls -f scripts/amd/vitis_hls_artix7_preboard.tcl \
#     --benchmark <id> --top nema_kernel --tb <tb.cpp> \
#     --kernel-cpp <nema_kernel.cpp> --kernel-h <nema_kernel.h> \
#     --clock-ns 5.0 --part xc7a200t-1sbg484c --outdir <dir> --cosim off

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

proc _arg_or_env {argv key env_key default} {
  set from_arg [_arg_value $argv $key "__NEMA_ARG_MISSING__"]
  if {$from_arg ne "__NEMA_ARG_MISSING__"} {
    return $from_arg
  }
  if {[info exists ::env($env_key)]} {
    return $::env($env_key)
  }
  return $default
}

proc _require_nonempty {name value} {
  if {$value eq ""} {
    error "required argument is empty: $name"
  }
}

set benchmark [_arg_or_env $argv "--benchmark" "NEMA_BENCHMARK" ""]
set top_name [_arg_or_env $argv "--top" "NEMA_TOP" "nema_kernel"]
set tb_path [_arg_or_env $argv "--tb" "NEMA_TB" ""]
set kernel_cpp [_arg_or_env $argv "--kernel-cpp" "NEMA_KERNEL_CPP" ""]
set kernel_h [_arg_or_env $argv "--kernel-h" "NEMA_KERNEL_H" ""]
set clock_ns [_arg_or_env $argv "--clock-ns" "NEMA_CLOCK_NS" "5.0"]
set requested_part [_arg_or_env $argv "--part" "NEMA_PART" "xc7a200t-1sbg484c"]
set outdir [_arg_or_env $argv "--outdir" "NEMA_OUTDIR" ""]
set cosim_mode [_arg_or_env $argv "--cosim" "NEMA_COSIM" "off"]

_require_nonempty "--benchmark" $benchmark
_require_nonempty "--tb" $tb_path
_require_nonempty "--kernel-cpp" $kernel_cpp
_require_nonempty "--kernel-h" $kernel_h
_require_nonempty "--outdir" $outdir

file mkdir $outdir
set hls_proj_dir [file normalize [file join $outdir "hls_proj"]]
set hls_logs_dir [file normalize [file join $outdir "logs"]]
file mkdir $hls_logs_dir
set status_file [file normalize [file join $outdir "hls_status.json"]]
set part_file [file normalize [file join $outdir "hls_selected_part.txt"]]

if {![file exists $kernel_cpp]} {
  error "kernel cpp not found: $kernel_cpp"
}
if {![file exists $kernel_h]} {
  error "kernel header not found: $kernel_h"
}
if {![file exists $tb_path]} {
  error "tb source not found: $tb_path"
}

open_project -reset [file join $hls_proj_dir "nema_hls_prj"]
set_top $top_name
add_files $kernel_cpp
add_files $kernel_h
set kernel_inc [file dirname [file normalize $kernel_h]]
add_files -tb $tb_path -cflags "-std=c++17 -I$kernel_inc"
open_solution -reset sol1

# Force requested part (no fallback). If this fails, abort deterministically.
if {[catch {set_part $requested_part} part_err]} {
  error "NEMA_HLS_ERROR: set_part_failed requested=$requested_part msg=$part_err"
}
set selected_part $requested_part
set fp [open $part_file w]
puts $fp $selected_part
close $fp

create_clock -period $clock_ns

set csim_ok 0
set csynth_ok 0
set cosim_ok -1

if {[catch {csim_design} err]} {
  puts "NEMA_HLS_ERROR: csim_design failed: $err"
  set sf [open $status_file w]
  puts $sf "{"
  puts $sf "  \"benchmark\": \"$benchmark\","
  puts $sf "  \"ok\": false,"
  puts $sf "  \"reason\": \"csim failed\","
  puts $sf "  \"part\": \"$selected_part\","
  puts $sf "  \"csim_ok\": false,"
  puts $sf "  \"csynth_ok\": false,"
  puts $sf "  \"cosim_ok\": null"
  puts $sf "}"
  close $sf
  error $err
}
set csim_ok 1

if {[catch {csynth_design} err]} {
  puts "NEMA_HLS_ERROR: csynth_design failed: $err"
  set sf [open $status_file w]
  puts $sf "{"
  puts $sf "  \"benchmark\": \"$benchmark\","
  puts $sf "  \"ok\": false,"
  puts $sf "  \"reason\": \"csynth failed\","
  puts $sf "  \"part\": \"$selected_part\","
  puts $sf "  \"csim_ok\": true,"
  puts $sf "  \"csynth_ok\": false,"
  puts $sf "  \"cosim_ok\": null"
  puts $sf "}"
  close $sf
  error $err
}
set csynth_ok 1

export_design -rtl verilog

if {$cosim_mode eq "on"} {
  if {[catch {cosim_design -rtl verilog} err]} {
    set cosim_ok 0
    puts "NEMA_HLS_ERROR: cosim_design failed: $err"
  } else {
    set cosim_ok 1
  }
} elseif {$cosim_mode eq "off"} {
  set cosim_ok -1
} else {
  error "invalid --cosim value: $cosim_mode (expected on|off)"
}

set sf [open $status_file w]
puts $sf "{"
puts $sf "  \"benchmark\": \"$benchmark\","
puts $sf "  \"ok\": [expr {$csim_ok && $csynth_ok}],"
puts $sf "  \"part\": \"$selected_part\","
if {$csim_ok} {
  set csim_json "true"
} else {
  set csim_json "false"
}
if {$csynth_ok} {
  set csynth_json "true"
} else {
  set csynth_json "false"
}
puts $sf "  \"csim_ok\": $csim_json,"
puts $sf "  \"csynth_ok\": $csynth_json,"
if {$cosim_ok < 0} {
  puts $sf "  \"cosim_ok\": null,"
} else {
  if {$cosim_ok} {
    set cosim_json "true"
  } else {
    set cosim_json "false"
  }
  puts $sf "  \"cosim_ok\": $cosim_json,"
}
puts $sf "  \"hls_proj_dir\": \"$hls_proj_dir\""
puts $sf "}"
close $sf

exit
