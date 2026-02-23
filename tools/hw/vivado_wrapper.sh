#!/usr/bin/env bash

set -euo pipefail

XILINX_BASE="${XILINX_BASE:-/tools/Xilinx/2025.2}"
VIVADO_ROOT="${XILINX_BASE}/Vivado"
SETTINGS="${VIVADO_ROOT}/settings64.sh"
VIVADO_BIN="${VIVADO_ROOT}/bin/vivado"

export LANG=C.UTF-8
export LC_ALL=C.UTF-8

if [[ ! -f "${SETTINGS}" ]]; then
  echo "vivado_wrapper: missing settings64.sh: ${SETTINGS}" >&2
  exit 1
fi

if [[ ! -x "${VIVADO_BIN}" ]]; then
  echo "vivado_wrapper: missing Vivado binary: ${VIVADO_BIN}" >&2
  exit 1
fi

# Prevent failures if settings64.sh references undefined vars.
set +u
# shellcheck disable=SC1090
source "${SETTINGS}"
set -u

# Keep invocation deterministic from any caller working directory.
cd "${VIVADO_ROOT}"
exec "${VIVADO_BIN}" "$@"
