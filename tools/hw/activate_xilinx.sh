#!/usr/bin/env bash

# Activate Xilinx toolchain environment (Vivado/Vitis/Vitis_HLS).
#
# Priority order:
# 1) Explicit XILINX_SETTINGS64 override.
# 2) Autodetect new + legacy layouts under common roots.
#
# Usage:
#   source tools/hw/activate_xilinx.sh
#
# Overrides:
#   export XILINX_SETTINGS64=/absolute/path/to/settings64.sh
#   export XILINX_ROOT=/path/to/root
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

_print_post_activation() {
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
}

_source_required() {
  local file="$1"
  local label="$2"
  if [[ ! -f "${file}" ]]; then
    _die "missing ${label} settings file: ${file}" || return 1
  fi
  # shellcheck disable=SC1090
  source "${file}" || {
    _die "failed to source ${label} settings: ${file}" || return 1
  }
  echo "sourced ${label}: ${file}"
}

_source_optional() {
  local file="$1"
  local label="$2"
  if [[ -f "${file}" ]]; then
    # shellcheck disable=SC1090
    source "${file}" || {
      _die "failed to source ${label} settings: ${file}" || return 1
    }
    echo "sourced ${label}: ${file}"
  else
    _warn "${label} settings64.sh not found at ${file}"
  fi
}

_activate_from_settings_override() {
  local settings="${XILINX_SETTINGS64:-}"
  if [[ -z "${settings}" ]]; then
    return 2
  fi
  if [[ ! -f "${settings}" ]]; then
    _die "XILINX_SETTINGS64 is set but file does not exist: ${settings}" || return 1
  fi

  echo "Activated Xilinx environment using explicit override:"
  _source_required "${settings}" "override"
  _print_post_activation
  return 0
}

_collect_candidate_roots() {
  local -n out_roots=$1
  if [[ -n "${XILINX_ROOT:-}" ]]; then
    out_roots+=("${XILINX_ROOT}")
  else
    out_roots+=(
      "/tools"
      "/opt"
      "${HOME}"
      "/usr/local"
      "/data"
      "/mnt"
      "/media"
    )
  fi
}

_collect_settings_files() {
  local -n roots_ref=$1
  local -n paths_ref=$2
  local existing_roots=()
  local root
  for root in "${roots_ref[@]}"; do
    [[ -d "${root}" ]] || continue
    existing_roots+=("${root}")
  done

  if [[ ${#existing_roots[@]} -eq 0 ]]; then
    return 0
  fi

  while IFS= read -r p; do
    [[ -n "${p}" ]] || continue
    paths_ref+=("${p}")
  done < <(find "${existing_roots[@]}" -maxdepth 7 -type f -name "settings64.sh" 2>/dev/null | sort -u)
}

_collect_records_from_settings() {
  local -n settings_ref=$1
  local -n records_ref=$2
  local -n discovered_ref=$3
  local trusted_root_mode="$4"

  local path
  local layout
  local xilinx_root
  local version
  local vivado
  local vitis
  local vitis_hls
  local -A seen=()

  shopt -s nocasematch
  for path in "${settings_ref[@]}"; do
    if [[ "${trusted_root_mode}" != "true" && ! "${path}" =~ /xilinx/ ]]; then
      continue
    fi
    discovered_ref+=("${path}")

    # New layout:
    #   <root>/Xilinx/<ver>/Vivado/settings64.sh
    if [[ "${path}" =~ ^(.*/Xilinx)/([^/]+)/Vivado/settings64\.sh$ ]]; then
      layout="new"
      xilinx_root="${BASH_REMATCH[1]}"
      version="${BASH_REMATCH[2]}"
      vivado="${path}"
      vitis="${xilinx_root}/${version}/Vitis/settings64.sh"
      vitis_hls="${xilinx_root}/${version}/Vitis_HLS/settings64.sh"
    # Legacy layout:
    #   <root>/Xilinx/Vivado/<ver>/settings64.sh
    elif [[ "${path}" =~ ^(.*/Xilinx)/Vivado/([^/]+)/settings64\.sh$ ]]; then
      layout="legacy"
      xilinx_root="${BASH_REMATCH[1]}"
      version="${BASH_REMATCH[2]}"
      vivado="${path}"
      vitis="${xilinx_root}/Vitis/${version}/settings64.sh"
      vitis_hls="${xilinx_root}/Vitis_HLS/${version}/settings64.sh"
    else
      continue
    fi

    if [[ -n "${seen["${vivado}"]+x}" ]]; then
      continue
    fi
    seen["${vivado}"]=1
    records_ref+=("${xilinx_root}|${version}|${layout}|${vivado}|${vitis}|${vitis_hls}")
  done
  shopt -u nocasematch
}

_select_record() {
  local -n records_ref=$1
  local selected=""
  local rec
  local rec_root rec_version rec_layout rec_vivado rec_vitis rec_vitis_hls

  if [[ ${#records_ref[@]} -eq 0 ]]; then
    echo ""
    return 0
  fi

  if [[ -n "${XILINX_VERSION:-}" ]]; then
    for rec in "${records_ref[@]}"; do
      IFS="|" read -r rec_root rec_version rec_layout rec_vivado rec_vitis rec_vitis_hls <<<"${rec}"
      if [[ "${rec_version}" == "${XILINX_VERSION}" ]]; then
        selected="${rec}"
        break
      fi
    done
    echo "${selected}"
    return 0
  fi

  local best_version=""
  for rec in "${records_ref[@]}"; do
    IFS="|" read -r rec_root rec_version rec_layout rec_vivado rec_vitis rec_vitis_hls <<<"${rec}"
    if [[ -z "${best_version}" ]]; then
      best_version="${rec_version}"
      selected="${rec}"
      continue
    fi
    if [[ "$(printf '%s\n%s\n' "${best_version}" "${rec_version}" | sort -V | tail -n 1)" == "${rec_version}" ]]; then
      best_version="${rec_version}"
      selected="${rec}"
    fi
  done
  echo "${selected}"
}

_print_not_found_help() {
  local -n roots_ref=$1
  local -n discovered_ref=$2

  {
    echo "no Xilinx installation found."
    echo "inspected roots:"
    local r
    for r in "${roots_ref[@]}"; do
      echo "  - ${r}"
    done
    echo "patterns tried:"
    echo "  - <root>/Xilinx/<ver>/Vivado/settings64.sh"
    echo "  - <root>/Xilinx/Vivado/<ver>/settings64.sh"
    echo "  - and sibling Vitis/Vitis_HLS settings64.sh paths"
    echo "hint:"
    echo "  export XILINX_SETTINGS64=/path/to/settings64.sh"
    echo "  source tools/hw/activate_xilinx.sh"
    if [[ ${#discovered_ref[@]} -gt 0 ]]; then
      echo "settings64.sh files found but not matching expected Vivado patterns:"
      local p
      for p in "${discovered_ref[@]:0:20}"; do
        echo "  - ${p}"
      done
    fi
  } >&2
}

_activate_main() {
  if _activate_from_settings_override; then
    return 0
  else
    local override_rc=$?
    if [[ ${override_rc} -eq 1 ]]; then
      return 1
    fi
  fi

  local roots=()
  _collect_candidate_roots roots

  local settings_paths=()
  _collect_settings_files roots settings_paths

  local records=()
  local discovered_settings=()
  local trusted_root_mode="false"
  if [[ -n "${XILINX_ROOT:-}" ]]; then
    trusted_root_mode="true"
  fi
  _collect_records_from_settings settings_paths records discovered_settings "${trusted_root_mode}"

  local selected_record
  selected_record="$(_select_record records)"
  if [[ -z "${selected_record}" ]]; then
    _print_not_found_help roots discovered_settings
    return 1
  fi

  local sel_root sel_version sel_layout sel_vivado sel_vitis sel_vitis_hls
  IFS="|" read -r sel_root sel_version sel_layout sel_vivado sel_vitis sel_vitis_hls <<<"${selected_record}"
  export XILINX_ROOT="${sel_root}"
  export XILINX_VERSION="${sel_version}"

  echo "Activated Xilinx environment (autodetect):"
  echo "  root: ${XILINX_ROOT}"
  echo "  version: ${XILINX_VERSION}"
  echo "  layout: ${sel_layout}"
  _source_required "${sel_vivado}" "Vivado"
  _source_optional "${sel_vitis}" "Vitis"
  _source_optional "${sel_vitis_hls}" "Vitis_HLS"
  _print_post_activation
  return 0
}

if _is_sourced; then
  _activate_main "$@"
  return $?
fi

_activate_main "$@"
exit $?
