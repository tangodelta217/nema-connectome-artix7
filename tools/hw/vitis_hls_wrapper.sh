#!/usr/bin/env bash

set -euo pipefail

XILINX_BASE="${XILINX_BASE:-/tools/Xilinx/2025.2}"
VITIS_ROOT="${XILINX_BASE}/Vitis"
SETTINGS="${VITIS_ROOT}/settings64.sh"
UNWRAPPED_BIN="${VITIS_ROOT}/bin/unwrapped/lnx64.o/vitis_hls"
VITIS_RUN_BIN="${VITIS_ROOT}/bin/vitis-run"

export LANG=C.UTF-8
export LC_ALL=C.UTF-8

if [[ ! -f "${SETTINGS}" ]]; then
  echo "vitis_hls_wrapper: missing settings64.sh: ${SETTINGS}" >&2
  exit 1
fi

if [[ ! -x "${UNWRAPPED_BIN}" ]]; then
  echo "vitis_hls_wrapper: missing vitis_hls unwrapped binary: ${UNWRAPPED_BIN}" >&2
  exit 1
fi

if [[ ! -x "${VITIS_RUN_BIN}" ]]; then
  echo "vitis_hls_wrapper: missing vitis-run binary: ${VITIS_RUN_BIN}" >&2
  exit 1
fi

# Prevent failure if settings64.sh references undefined vars.
set +u
# shellcheck disable=SC1090
source "${SETTINGS}"
set -u

export PATH="${VITIS_ROOT}/bin/unwrapped/lnx64.o:${PATH}"
export LD_LIBRARY_PATH="${VITIS_ROOT}/lib/lnx64.o:${LD_LIBRARY_PATH:-}"
export RDI_DATADIR="${XILINX_BASE}/Vivado/data"
export TCL_LIBRARY="${XILINX_BASE}/tps/tcl/tcl8.6"
if [[ -d "${XILINX_BASE}/tps/tcl/tk8.6" ]]; then
  export TK_LIBRARY="${XILINX_BASE}/tps/tcl/tk8.6"
fi

if [[ "${1-}" == "-version" || "${1-}" == "--version" ]]; then
  # Keep legacy version output semantics.
  cd "${VITIS_ROOT}"
  exec "${UNWRAPPED_BIN}" "$@"
fi

# Backward-compatible mode for callers expecting `vitis_hls -f <script.tcl>`.
if [[ "${1-}" == "-f" && -n "${2-}" ]]; then
  tcl_script="$2"
  work_dir="$(pwd)"
  exec "${VITIS_RUN_BIN}" --mode hls --tcl --input_file "${tcl_script}" --work_dir "${work_dir}"
fi

# Fallback: pass-through to unwrapped binary from Vitis root.
cd "${VITIS_ROOT}"
exec "${UNWRAPPED_BIN}" "$@"
