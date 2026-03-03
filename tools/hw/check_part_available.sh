#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ALLOW_FALLBACK=0
PART=""
if [[ "${1:-}" == "--allow-fallback" ]]; then
  ALLOW_FALLBACK=1
  shift
fi
PART="${1:-${NEMA_VIVADO_PART:-xc7a200tsbg484-1}}"
TCL_SCRIPT="${SCRIPT_DIR}/check_part_available.tcl"

if [[ ! -f "${TCL_SCRIPT}" ]]; then
  echo "ERROR: missing Tcl checker: ${TCL_SCRIPT}" >&2
  exit 2
fi

if ! command -v vivado >/dev/null 2>&1; then
  echo "ERROR: vivado not found in PATH." >&2
  echo "ACTION: source your Xilinx environment, e.g. 'source tools/hw/activate_xilinx.sh'." >&2
  exit 127
fi

set +e
output="$(
  vivado -mode batch -nojournal -nolog -notrace \
    -source "${TCL_SCRIPT}" \
    -tclargs "${PART}" 2>&1
)"
rc=$?
set -e

echo "${output}"

if [[ ${rc} -ne 0 ]]; then
  if [[ ${ALLOW_FALLBACK} -eq 1 ]]; then
    fallback_part="$(printf '%s\n' "${output}" | sed -n 's/^NEMA_PART_CHECK_FALLBACK: first_available=//p' | head -n1)"
    if [[ -n "${fallback_part}" ]]; then
      echo "NEMA_PART_CHECK: requested part '${PART}' not installed; using fallback part '${fallback_part}'." >&2
      echo "ACTION: install device support Artix-7 in Vivado to reproduce on the paper target part." >&2
      exit 0
    fi
  fi
  echo >&2
  echo "NEMA_PART_CHECK: requested part '${PART}' is not available in this Vivado installation." >&2
  echo "ACTION: install device support Artix-7 in Vivado, then rerun this check." >&2
  echo "VERIFY: vivado -mode batch -source tools/hw/check_part_available.tcl -tclargs ${PART}" >&2
  echo "TIP: you can inspect installed Artix-7 parts in Vivado Tcl with: get_parts xc7a*" >&2
  exit "${rc}"
fi

echo "NEMA_PART_CHECK: requested part '${PART}' is available."
