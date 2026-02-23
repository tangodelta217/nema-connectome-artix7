#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

mkdir -p build_hw

timestamp_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
git_hash="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
cat > build_hw/run_meta.json <<EOF
{
  "createdAtUtc": "${timestamp_utc}",
  "gitHash": "${git_hash}",
  "runner": "tools/run_hw_gates.sh"
}
EOF

# Must fail early on machines without an installed Xilinx toolchain, while
# still leaving minimal evidence artifacts under build_hw/.
if ! source tools/hw/activate_xilinx.sh 2> build_hw/activate.stderr.log; then
  cat > build_hw/audit_min_hardware.json <<'EOF'
{
  "ok": false,
  "decision": "NO-GO",
  "mode": "hardware",
  "reasons": [
    "toolchain not found"
  ],
  "toolchainHwAvailable": false
}
EOF
  exit 1
fi

bash tools/hw/preflight_ubuntu24.sh > build_hw/preflight.txt

if python -m nema hw --help >/dev/null 2>&1; then
  python -m nema hw doctor --format json > build_hw/hw_doctor.json
else
  printf '{\n  "ok": false,\n  "error": "nema hw doctor command not available"\n}\n' > build_hw/hw_doctor.json
fi

mkdir -p build_hw/b1 build_hw/b3
python -m nema hwtest example_b1_small_subgraph.json --ticks 2 --outdir build_hw/b1 --hw require > build_hw/b1/hwtest.json
python -m nema hwtest example_b3_kernel_302.json --ticks 2 --outdir build_hw/b3 --hw require > build_hw/b3/hwtest.json

set +e
python tools/audit_min.py --path build_hw --mode hardware > build_hw/audit_min_hardware.json
hardware_rc=$?
python tools/audit_min.py --path build_hw --mode software > build_hw/audit_min_software.json
software_rc=$?
set -e

cat build_hw/audit_min_hardware.json

if [[ ${hardware_rc} -ne 0 || ${software_rc} -ne 0 ]]; then
  echo "run_hw_gates.sh: audit_min returned non-zero (hardware=${hardware_rc}, software=${software_rc})" >&2
  exit 1
fi
