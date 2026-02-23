#!/usr/bin/env bash

set -euo pipefail

export PATH="${HOME}/.local/bin:${PATH}"
source tools/hw/activate_xilinx.sh
vitis_hls -version | head
