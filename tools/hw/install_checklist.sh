#!/usr/bin/env bash

set -euo pipefail

print_header() {
  echo "== $1 =="
}

print_item() {
  echo "- $1"
}

print_header "AMD/Xilinx Install Checklist (Ubuntu 24.04)"
print_item "Recommended installer: AMD Unified Installer (Vitis), including Vivado + Vitis HLS."
echo

print_header "Recommended Install Paths"
print_item "/tools/Xilinx"
print_item "/opt/Xilinx"
print_item "/usr/local/Xilinx"
echo

print_header "Post-Install Activation Commands"
print_item "New layout: source <install>/2025.2/Vivado/settings64.sh"
print_item "Legacy layout: source <install>/Vivado/2025.2/settings64.sh"
echo

print_header "settings64.sh Discovery Hint"
print_item "Find settings64.sh under your install root and set:"
print_item "export XILINX_SETTINGS64=/absolute/path/to/settings64.sh"
print_item "source tools/hw/activate_xilinx.sh"
echo

print_header "libtinfo.so.5 Check"
lib_candidates=(
  "/usr/lib/x86_64-linux-gnu/libtinfo.so.5"
  "/lib/x86_64-linux-gnu/libtinfo.so.5"
)
lib_found="false"
for p in "${lib_candidates[@]}"; do
  if [[ -e "${p}" ]]; then
    print_item "${p}: FOUND"
    lib_found="true"
  else
    print_item "${p}: MISSING"
  fi
done
if [[ "${lib_found}" != "true" ]]; then
  echo
  print_item "Hint (do not run automatically): install libtinfo5 on Ubuntu 24.04."
  print_item "Example commands:"
  print_item "apt-cache policy libtinfo5"
  print_item "sudo apt update"
  print_item "sudo apt install libtinfo5"
fi
echo

print_header "License Environment (Recommended)"
print_item "export XILINXD_LICENSE_FILE=27000@<license-server-or-path>"
print_item "Optional fallback: export LM_LICENSE_FILE=27000@<license-server-or-path>"
echo

print_header "Reminder"
print_item "This checklist script performs checks and guidance only. It does not install packages."
