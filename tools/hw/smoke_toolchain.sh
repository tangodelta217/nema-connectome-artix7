#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

export PATH="${HOME}/.local/bin:${PATH}"
source tools/hw/activate_xilinx.sh

LOG_DIR="${REPO_ROOT}/build/hw_smoke_toolchain"
mkdir -p "${LOG_DIR}"

run_probe() {
  local name="$1"
  shift
  local log_path="${LOG_DIR}/${name}.log"

  echo
  echo "== ${name} =="
  echo "cmd: $*"
  echo "log: ${log_path}"

  set +e
  "$@" >"${log_path}" 2>&1
  local rc=$?
  set -e

  sed -n '1,20p' "${log_path}" || true
  echo "exit_code: ${rc}"

  if [[ ${rc} -eq 139 ]]; then
    echo "DIAGNOSIS: command terminated with SIGSEGV (exit 139)." >&2
    echo "ACTION: verify Xilinx runtime/libraries and wrapper setup, then retry." >&2
  elif [[ ${rc} -ne 0 ]]; then
    echo "DIAGNOSIS: command failed (exit ${rc}). See ${log_path}." >&2
  fi

  return ${rc}
}

status=0
set +e
run_probe "vivado_version" vivado -version
rc=$?
set -e
if [[ ${rc} -ne 0 ]]; then
  status=${rc}
fi

set +e
run_probe "vitis_hls_version" vitis_hls -version
rc=$?
set -e
if [[ ${rc} -ne 0 && ${status} -eq 0 ]]; then
  status=${rc}
fi

if [[ ${status} -ne 0 ]]; then
  echo
  echo "smoke_toolchain: FAIL (exit ${status})" >&2
  exit "${status}"
fi

echo
echo "smoke_toolchain: OK"
