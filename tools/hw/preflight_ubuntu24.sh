#!/usr/bin/env bash

set -euo pipefail

print_header() {
  echo "== $1 =="
}

print_kv() {
  local key="$1"
  local value="$2"
  printf "%-28s %s\n" "${key}:" "${value}"
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

detect_os_release_value() {
  local key="$1"
  if [[ -f /etc/os-release ]]; then
    grep -E "^${key}=" /etc/os-release | head -n1 | cut -d= -f2- | tr -d '"'
  fi
}

print_header "System"
if command_exists lsb_release; then
  lsb_release -a 2>/dev/null || true
else
  os_name="$(detect_os_release_value NAME)"
  os_version="$(detect_os_release_value VERSION)"
  os_id="$(detect_os_release_value ID)"
  os_version_id="$(detect_os_release_value VERSION_ID)"
  print_kv "OS name" "${os_name:-UNKNOWN}"
  print_kv "OS version" "${os_version:-UNKNOWN}"
  print_kv "OS id" "${os_id:-UNKNOWN}"
  print_kv "OS version id" "${os_version_id:-UNKNOWN}"
fi

kernel_release="$(uname -r 2>/dev/null || echo UNKNOWN)"
print_kv "Kernel release" "${kernel_release}"

echo
print_header "Resources"
if command_exists free; then
  free -h || true
else
  echo "free command not found"
fi
echo
if command_exists df; then
  df -h || true
else
  echo "df command not found"
fi

echo
print_header "libtinfo.so.5"
lib_candidates=(
  "/usr/lib/x86_64-linux-gnu/libtinfo.so.5"
  "/lib/x86_64-linux-gnu/libtinfo.so.5"
)
lib_found="false"
for lib_path in "${lib_candidates[@]}"; do
  if [[ -e "${lib_path}" ]]; then
    print_kv "${lib_path}" "FOUND"
    lib_found="true"
  else
    print_kv "${lib_path}" "MISSING"
  fi
done

if [[ "${lib_found}" != "true" ]]; then
  echo
  echo "libtinfo.so.5 is missing. Suggested Ubuntu 24.04 remediation (commands not executed):"
  if command_exists apt-cache; then
    echo "  apt-cache policy libtinfo5"
    apt-cache policy libtinfo5 || true
    echo "  sudo apt update"
    echo "  sudo apt install libtinfo5"
  else
    echo "  apt-cache is not available on this machine."
  fi
  echo "  If libtinfo5 is unavailable in apt, use a compatible .deb from security.ubuntu.com:"
  echo "  wget http://security.ubuntu.com/ubuntu/pool/universe/n/ncurses/libtinfo5_<version>_amd64.deb"
  echo "  sudo apt install ./libtinfo5_<version>_amd64.deb"
fi

echo
print_header "Toolchain in PATH"
vitis_path="$(command -v vitis_hls 2>/dev/null || true)"
vivado_path="$(command -v vivado 2>/dev/null || true)"
if [[ -n "${vitis_path}" ]]; then
  print_kv "vitis_hls" "${vitis_path}"
else
  print_kv "vitis_hls" "NOT_FOUND"
fi
if [[ -n "${vivado_path}" ]]; then
  print_kv "vivado" "${vivado_path}"
else
  print_kv "vivado" "NOT_FOUND"
fi

echo
print_header "Licensing env"
if [[ -n "${XILINXD_LICENSE_FILE:-}" ]]; then
  print_kv "XILINXD_LICENSE_FILE" "${XILINXD_LICENSE_FILE}"
else
  print_kv "XILINXD_LICENSE_FILE" "NOT_SET"
fi
if [[ -n "${LM_LICENSE_FILE:-}" ]]; then
  print_kv "LM_LICENSE_FILE" "${LM_LICENSE_FILE}"
else
  print_kv "LM_LICENSE_FILE" "NOT_SET"
fi

echo
print_header "Kernel compatibility hint"
os_id="$(detect_os_release_value ID)"
os_version_id="$(detect_os_release_value VERSION_ID)"
if [[ "${os_id}" == "ubuntu" && "${os_version_id}" == "24.04" ]]; then
  if [[ "${kernel_release}" != 6.8.* ]]; then
    echo "WARNING: Ubuntu 24.04 detected but kernel is '${kernel_release}', not 6.8.*."
    echo "AMD publishes tested kernel lists for Ubuntu 24.04 in release notes/docs."
    echo "This is a warning only (non-blocking)."
  else
    echo "Kernel '${kernel_release}' matches 6.8.* pattern for Ubuntu 24.04."
  fi
else
  echo "Host is not Ubuntu 24.04 (ID='${os_id:-UNKNOWN}', VERSION_ID='${os_version_id:-UNKNOWN}')."
  echo "Kernel compatibility hint is informational only."
fi

echo
print_header "Summary"
hw_available="false"
if [[ -n "${vitis_path}" || -n "${vivado_path}" ]]; then
  hw_available="true"
fi
print_kv "hwToolchainAvailable" "${hw_available}"
