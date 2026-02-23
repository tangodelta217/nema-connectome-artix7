#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

export PATH="${HOME}/.local/bin:${PATH}"
source tools/hw/activate_xilinx.sh

{ vivado -version 2>&1 | sed -n '1,6p'; }
{ vitis_hls -version 2>&1 | sed -n '1,6p'; }
