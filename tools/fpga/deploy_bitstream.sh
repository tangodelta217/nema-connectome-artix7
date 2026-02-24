#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

BIT_PATH=""
HW_SERVER_URL=""
TARGET_FILTER=""

usage() {
  cat <<'EOF'
Usage:
  bash tools/fpga/deploy_bitstream.sh --bit <path/to/file.bit> [--hw-server <url>] [--target <filter>]

Description:
  Best-effort Vivado Hardware Manager deploy helper.
  Requires: vivado in PATH, connected cable/board, valid hardware target.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bit)
      BIT_PATH="$2"
      shift 2
      ;;
    --hw-server)
      HW_SERVER_URL="$2"
      shift 2
      ;;
    --target)
      TARGET_FILTER="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "deploy_bitstream.sh: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${BIT_PATH}" ]]; then
  echo "deploy_bitstream.sh: --bit is required" >&2
  usage >&2
  exit 2
fi

if [[ ! -f "${BIT_PATH}" ]]; then
  echo "deploy_bitstream.sh: bitstream not found: ${BIT_PATH}" >&2
  exit 1
fi

if ! command -v vivado >/dev/null 2>&1; then
  echo "deploy_bitstream.sh: vivado not found in PATH" >&2
  exit 1
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

TCL_PATH="${WORK_DIR}/deploy_bitstream.tcl"
LOG_PATH="${WORK_DIR}/deploy_bitstream.log"
BIT_ABS="$(python - <<'PY' "${BIT_PATH}"
import pathlib
import sys
print(pathlib.Path(sys.argv[1]).resolve())
PY
)"

cat > "${TCL_PATH}" <<EOF
set bit_path {${BIT_ABS}}
set hw_server_url {${HW_SERVER_URL}}
set target_filter {${TARGET_FILTER}}

open_hw_manager
if {\$hw_server_url ne ""} {
  connect_hw_server -url \$hw_server_url
} else {
  connect_hw_server
}
if {\$target_filter ne ""} {
  open_hw_target -filter \$target_filter
} else {
  open_hw_target
}
set devices [get_hw_devices]
if {[llength \$devices] == 0} {
  error "NEMA_DEPLOY_ERROR: no hardware devices found"
}
set dev [lindex \$devices 0]
current_hw_device \$dev
refresh_hw_device -update_hw_probes false \$dev
set_property PROGRAM.FILE \$bit_path \$dev
program_hw_devices \$dev
puts "NEMA_DEPLOY_OK: programmed \$dev with \$bit_path"
exit
EOF

set +e
vivado -mode batch -source "${TCL_PATH}" > "${LOG_PATH}" 2>&1
rc=$?
set -e

cat "${LOG_PATH}"
if [[ ${rc} -ne 0 ]]; then
  echo "deploy_bitstream.sh: deploy failed (see log above)." >&2
  exit ${rc}
fi

echo "deploy_bitstream.sh: deploy completed successfully."
