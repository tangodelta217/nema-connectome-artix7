#!/usr/bin/env bash

# Activate Xilinx toolchain environment (Vivado/Vitis/Vitis_HLS) using
# autodetection for <version>/Vivado layout (2025.1+ style).
#
# Usage (recommended):
#   source tools/hw/activate_xilinx.sh
#
# Optional overrides:
#   export XILINX_ROOT=/tools/Xilinx
#   export XILINX_VERSION=2025.2

_is_sourced() {
  [[ "${BASH_SOURCE[0]}" != "$0" ]]
}

_die() {
  local msg="$1"
  echo "activate_xilinx.sh: ${msg}" >&2
  return 1
}

_warn() {
  echo "activate_xilinx.sh: WARNING: $1" >&2
}

_best_effort_version() {
  local tool="$1"
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "${tool} -version: NOT_FOUND"
    return 0
  fi

  local cmd_output=""
  local rc=0
  if command -v timeout >/dev/null 2>&1; then
    cmd_output="$(timeout 15s "${tool}" -version 2>&1)"
    rc=$?
    if [[ ${rc} -eq 124 ]]; then
      echo "${tool} -version: TIMEOUT (>15s)"
      return 0
    fi
  else
    cmd_output="$("${tool}" -version 2>&1)"
    rc=$?
  fi

  if [[ ${rc} -ne 0 ]]; then
    echo "${tool} -version: command returned ${rc}"
    echo "${cmd_output}" | head -n 2
    return 0
  fi

  local first_line
  first_line="$(echo "${cmd_output}" | head -n 1)"
  if [[ -z "${first_line}" ]]; then
    echo "${tool} -version: (no output)"
  else
    echo "${tool} -version: ${first_line}"
  fi
}

_activate_main() {
  local candidate_roots=()
  if [[ -n "${XILINX_ROOT:-}" ]]; then
    candidate_roots+=("${XILINX_ROOT}")
  else
    candidate_roots+=("/tools/Xilinx" "/opt/Xilinx" "${HOME}/Xilinx")
  fi

  local records=()
  local root version_dir version vivado_settings vitis_settings vitis_hls_settings
  for root in "${candidate_roots[@]}"; do
    [[ -d "${root}" ]] || continue
    while IFS= read -r version_dir; do
      version="$(basename "${version_dir}")"
      vivado_settings="${version_dir}/Vivado/settings64.sh"
      [[ -f "${vivado_settings}" ]] || continue
      vitis_settings="${version_dir}/Vitis/settings64.sh"
      vitis_hls_settings="${version_dir}/Vitis_HLS/settings64.sh"
      records+=("${root}|${version}|${vivado_settings}|${vitis_settings}|${vitis_hls_settings}")
    done < <(find "${root}" -mindepth 1 -maxdepth 1 -type d | sort -V)
  done

  if [[ ${#records[@]} -eq 0 ]]; then
    _die "no Xilinx installation found. Searched roots: ${candidate_roots[*]}. Expected layout: <root>/<version>/Vivado/settings64.sh" || return 1
  fi

  local selected_record=""
  local record rec_root rec_version rec_vivado rec_vitis rec_vitis_hls
  if [[ -n "${XILINX_VERSION:-}" ]]; then
    for record in "${records[@]}"; do
      IFS="|" read -r rec_root rec_version rec_vivado rec_vitis rec_vitis_hls <<<"${record}"
      if [[ "${rec_version}" == "${XILINX_VERSION}" ]]; then
        selected_record="${record}"
        break
      fi
    done
    if [[ -z "${selected_record}" ]]; then
      _die "requested XILINX_VERSION='${XILINX_VERSION}' not found under roots: ${candidate_roots[*]}" || return 1
    fi
  else
    local best_version=""
    local max_version=""
    for record in "${records[@]}"; do
      IFS="|" read -r rec_root rec_version rec_vivado rec_vitis rec_vitis_hls <<<"${record}"
      if [[ -z "${best_version}" ]]; then
        best_version="${rec_version}"
        continue
      fi
      max_version="$(printf '%s\n%s\n' "${best_version}" "${rec_version}" | sort -V | tail -n 1)"
      best_version="${max_version}"
    done
    for record in "${records[@]}"; do
      IFS="|" read -r rec_root rec_version rec_vivado rec_vitis rec_vitis_hls <<<"${record}"
      if [[ "${rec_version}" == "${best_version}" ]]; then
        selected_record="${record}"
        break
      fi
    done
  fi

  local sel_root sel_version sel_vivado sel_vitis sel_vitis_hls
  IFS="|" read -r sel_root sel_version sel_vivado sel_vitis sel_vitis_hls <<<"${selected_record}"

  if [[ ! -f "${sel_vivado}" ]]; then
    _die "selected Vivado settings script missing: ${sel_vivado}" || return 1
  fi

  export XILINX_ROOT="${sel_root}"
  export XILINX_VERSION="${sel_version}"

  # shellcheck disable=SC1090
  source "${sel_vivado}" || {
    _die "failed to source Vivado settings: ${sel_vivado}" || return 1
  }

  if [[ -f "${sel_vitis}" ]]; then
    # shellcheck disable=SC1090
    source "${sel_vitis}" || {
      _die "failed to source Vitis settings: ${sel_vitis}" || return 1
    }
  fi

  if [[ -f "${sel_vitis_hls}" ]]; then
    # shellcheck disable=SC1090
    source "${sel_vitis_hls}" || {
      _die "failed to source Vitis_HLS settings: ${sel_vitis_hls}" || return 1
    }
  fi

  echo "Activated Xilinx environment:"
  echo "  root: ${XILINX_ROOT}"
  echo "  version: ${XILINX_VERSION}"
  echo "  vivado settings: ${sel_vivado}"
  if [[ -f "${sel_vitis}" ]]; then
    echo "  vitis settings: ${sel_vitis}"
  else
    _warn "Vitis settings64.sh not found at ${sel_vitis}"
  fi
  if [[ -f "${sel_vitis_hls}" ]]; then
    echo "  vitis_hls settings: ${sel_vitis_hls}"
  else
    _warn "Vitis_HLS settings64.sh not found at ${sel_vitis_hls}"
  fi

  echo
  if command -v vivado >/dev/null 2>&1; then
    echo "which vivado: $(command -v vivado)"
  else
    echo "which vivado: NOT_FOUND"
  fi
  if command -v vitis_hls >/dev/null 2>&1; then
    echo "which vitis_hls: $(command -v vitis_hls)"
  else
    echo "which vitis_hls: NOT_FOUND"
  fi

  echo
  _best_effort_version "vivado"
  _best_effort_version "vitis_hls"
  return 0
}

if _is_sourced; then
  _activate_main "$@"
  return $?
fi

_activate_main "$@"
exit $?
