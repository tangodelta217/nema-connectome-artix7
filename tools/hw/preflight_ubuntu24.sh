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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PART_CHECK_SCRIPT="${REPO_ROOT}/tools/hw/check_part_available.sh"
TARGET_PART="${NEMA_VIVADO_PART:-xc7a200tsbg484-1}"
ALLOW_PART_FALLBACK="${NEMA_PREFLIGHT_ALLOW_PART_FALLBACK:-1}"

detect_os_release_value() {
  local key="$1"
  if [[ -f /etc/os-release ]]; then
    grep -E "^${key}=" /etc/os-release | head -n1 | cut -d= -f2- | tr -d '"'
  fi
}

print_header "OS (/etc/os-release)"
if [[ -f /etc/os-release ]]; then
  print_kv "source" "/etc/os-release"
  os_pretty_name="$(detect_os_release_value PRETTY_NAME)"
  os_name="$(detect_os_release_value NAME)"
  os_version="$(detect_os_release_value VERSION)"
  os_id="$(detect_os_release_value ID)"
  os_version_id="$(detect_os_release_value VERSION_ID)"
  print_kv "PRETTY_NAME" "${os_pretty_name:-UNKNOWN}"
  print_kv "NAME" "${os_name:-UNKNOWN}"
  print_kv "VERSION" "${os_version:-UNKNOWN}"
  print_kv "ID" "${os_id:-UNKNOWN}"
  print_kv "VERSION_ID" "${os_version_id:-UNKNOWN}"
else
  print_kv "source" "MISSING (/etc/os-release not found)"
fi

kernel_release="$(uname -r 2>/dev/null || echo UNKNOWN)"
echo
print_header "Kernel"
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

part_available="false"
part_fallback_active="false"
if [[ -n "${vivado_path}" ]]; then
  echo
  print_header "Target Part Availability"
  print_kv "targetPart" "${TARGET_PART}"
  if [[ -x "${PART_CHECK_SCRIPT}" ]]; then
    if [[ "${ALLOW_PART_FALLBACK}" == "1" ]]; then
      check_output="$("${PART_CHECK_SCRIPT}" --allow-fallback "${TARGET_PART}" 2>&1)" || true
      echo "${check_output}"
      if printf '%s\n' "${check_output}" | grep -q "NEMA_PART_CHECK_OK:"; then
        part_available="true"
      elif printf '%s\n' "${check_output}" | grep -q "using fallback part"; then
        part_available="false"
        part_fallback_active="true"
      else
        part_available="false"
      fi
    elif "${PART_CHECK_SCRIPT}" "${TARGET_PART}"; then
      part_available="true"
    else
      part_available="false"
    fi
  else
    print_kv "part check script" "NOT_EXECUTABLE (${PART_CHECK_SCRIPT})"
    part_available="false"
  fi
else
  part_available="false"
fi

echo
print_header "Licensing env"
license_printed="false"
if [[ -n "${XILINXD_LICENSE_FILE:-}" ]]; then
  print_kv "XILINXD_LICENSE_FILE" "${XILINXD_LICENSE_FILE}"
  license_printed="true"
fi
if [[ -n "${LM_LICENSE_FILE:-}" ]]; then
  print_kv "LM_LICENSE_FILE" "${LM_LICENSE_FILE}"
  license_printed="true"
fi
if [[ "${license_printed}" != "true" ]]; then
  echo "No license env vars set (XILINXD_LICENSE_FILE / LM_LICENSE_FILE)."
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
hw_toolchain_detected="false"
if [[ -n "${vitis_path}" || -n "${vivado_path}" ]]; then
  hw_toolchain_detected="true"
fi
hw_available="false"
if [[ "${hw_toolchain_detected}" == "true" && ( "${part_available}" == "true" || "${part_fallback_active}" == "true" ) ]]; then
  hw_available="true"
fi
print_kv "hwToolchainDetected" "${hw_toolchain_detected}"
print_kv "targetPart" "${TARGET_PART}"
print_kv "partAvailable" "${part_available}"
print_kv "partFallbackActive" "${part_fallback_active}"
print_kv "hwToolchainAvailable" "${hw_available}"

if [[ "${hw_available}" != "true" ]]; then
  echo
  echo "Preflight failed: hardware toolchain is not ready for target part '${TARGET_PART}'." >&2
  if [[ "${part_available}" != "true" ]]; then
    echo "Reason: requested part is not installed in Vivado." >&2
    echo "Action: install device support Artix-7 in Vivado and re-run preflight." >&2
    echo "Verify: bash tools/hw/check_part_available.sh ${TARGET_PART}" >&2
  fi
  exit 1
fi

if [[ "${part_fallback_active}" == "true" ]]; then
  echo
  echo "Warning: target part '${TARGET_PART}' is unavailable; fallback part is available for non-target reruns." >&2
  echo "For strict target-part runs, install Artix-7 device support and verify with:" >&2
  echo "  bash tools/hw/check_part_available.sh ${TARGET_PART}" >&2
fi
