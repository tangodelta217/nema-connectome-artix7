#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"
export PATH="${HOME}/.local/bin:${PATH}"

OUTDIR="build_hw"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --outdir)
      if [[ $# -lt 2 ]]; then
        echo "run_hw_gates.sh: --outdir requires a value" >&2
        exit 2
      fi
      OUTDIR="$2"
      shift 2
      ;;
    *)
      echo "run_hw_gates.sh: unknown argument: $1" >&2
      echo "usage: bash tools/run_hw_gates.sh [--outdir <path>]" >&2
      exit 2
      ;;
  esac
done

mkdir -p "${OUTDIR}"

timestamp_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
git_hash="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
cat > "${OUTDIR}/run_meta.json" <<EOF
{
  "createdAtUtc": "${timestamp_utc}",
  "gitHash": "${git_hash}",
  "runner": "tools/run_hw_gates.sh",
  "outdir": "${OUTDIR}"
}
EOF

# Must fail early on machines without an installed Xilinx toolchain, while
# still leaving minimal evidence artifacts under build_hw/.
if ! source tools/hw/activate_xilinx.sh 2> "${OUTDIR}/activate.stderr.log"; then
  cat > "${OUTDIR}/audit_min_hardware.json" <<'EOF'
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

# Validate command availability from this script context.
if ! command -v vitis_hls >/dev/null 2>&1; then
  echo "run_hw_gates.sh: vitis_hls not found after activation. hint: bash tools/hw/install_wrappers.sh" >&2
  exit 1
fi
if ! command -v vivado >/dev/null 2>&1; then
  echo "run_hw_gates.sh: vivado not found after activation." >&2
  exit 1
fi

if ! { vitis_hls -version 2>&1 | sed -n '1,6p'; } > "${OUTDIR}/vitis_hls.version.txt"; then
  echo "run_hw_gates.sh: failed to execute 'vitis_hls -version'." >&2
  exit 1
fi
if ! { vivado -version 2>&1 | sed -n '1,6p'; } > "${OUTDIR}/vivado.version.txt"; then
  echo "run_hw_gates.sh: failed to execute 'vivado -version'." >&2
  exit 1
fi

bash tools/hw/preflight_ubuntu24.sh > "${OUTDIR}/preflight.txt"

if python -m nema hw --help >/dev/null 2>&1; then
  python -m nema hw doctor --format json > "${OUTDIR}/hw_doctor.json"
else
  printf '{\n  "ok": false,\n  "error": "nema hw doctor command not available"\n}\n' > "${OUTDIR}/hw_doctor.json"
fi

mkdir -p "${OUTDIR}/b1" "${OUTDIR}/b2" "${OUTDIR}/b3"
python -m nema hwtest example_b1_small_subgraph.json --ticks 2 --outdir "${OUTDIR}/b1" --hw require --cosim on > "${OUTDIR}/b1/hwtest.json"
python -m nema hwtest example_b2_mid_scale.json --ticks 2 --outdir "${OUTDIR}/b2" --hw require --cosim off > "${OUTDIR}/b2/hwtest.json"
python -m nema hwtest example_b3_kernel_302.json --ticks 2 --outdir "${OUTDIR}/b3" --hw require --cosim off > "${OUTDIR}/b3/hwtest.json"

set +e
python tools/audit_min.py --path "${OUTDIR}" --mode hardware > "${OUTDIR}/audit_min_hardware.json"
hardware_rc=$?
python tools/audit_min.py --path "${OUTDIR}" --mode software > "${OUTDIR}/audit_min_software.json"
software_rc=$?
set -e

cat "${OUTDIR}/audit_min_hardware.json"

if [[ ${hardware_rc} -ne 0 || ${software_rc} -ne 0 ]]; then
  echo "run_hw_gates.sh: audit_min returned non-zero (hardware=${hardware_rc}, software=${software_rc})" >&2
  exit 1
fi
