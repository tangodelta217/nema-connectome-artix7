#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

mkdir -p build_hw

# Must fail early on machines without an installed Xilinx toolchain.
source tools/hw/activate_xilinx.sh

python -m nema hw doctor --format json > build_hw/hw_doctor.json

if python -m nema hwtest --help 2>&1 | grep -q -- "--hw"; then
  mkdir -p build_hw/b1 build_hw/b3
  python -m nema hwtest example_b1_small_subgraph.json --ticks 2 --outdir build_hw/b1 --hw require > build_hw/b1/hwtest.json
  python -m nema hwtest example_b3_kernel_302.json --ticks 2 --outdir build_hw/b3 --hw require > build_hw/b3/hwtest.json
else
  mkdir -p build_hw/b1 build_hw/b3
  python -m nema dsl hwtest programs/b1_small.nema --ticks 2 --outdir build_hw/b1 --format json --no-color --hw require > build_hw/b1/hwtest.json
  python -m nema dsl hwtest programs/b3_kernel_302.nema --ticks 2 --outdir build_hw/b3 --format json --no-color --hw require > build_hw/b3/hwtest.json
fi

set +e
python tools/audit_min.py --mode hardware > build_hw/audit_min_hardware.json
hardware_rc=$?
python tools/audit_min.py --mode software > build_hw/audit_min_software.json
software_rc=$?
set -e

cat build_hw/audit_min_hardware.json

if [[ ${hardware_rc} -ne 0 || ${software_rc} -ne 0 ]]; then
  echo "run_hw_gates.sh: audit_min returned non-zero (hardware=${hardware_rc}, software=${software_rc})" >&2
  exit 1
fi
