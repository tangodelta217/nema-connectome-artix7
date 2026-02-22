#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
git_short="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
run_id="${timestamp}_${git_short}"
outdir="build_hw/${run_id}"

mkdir -p "${outdir}"

doctor_json="${outdir}/hw_doctor.json"
python -m nema hw doctor --format json > "${doctor_json}"

if ! python - "${doctor_json}" <<'PY'
import json
import sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)
sys.exit(0 if payload.get("hwToolchainAvailable") else 1)
PY
then
  echo "HW toolchain unavailable: vitis_hls/vivado not detected. See ${doctor_json}" >&2
  exit 1
fi

run_b1_json="${outdir}/b1_hwtest.json"
run_b3_json="${outdir}/b3_hwtest.json"

if python -m nema hwtest --help 2>&1 | grep -q -- "--hw"; then
  python -m nema hwtest example_b1_small_subgraph.json --ticks 2 --outdir "${outdir}" --hw require > "${run_b1_json}"
  python -m nema hwtest example_b3_kernel_302.json --ticks 2 --outdir "${outdir}" --hw require > "${run_b3_json}"
else
  if [[ ! -f programs/b1_small.nema ]]; then
    echo "Missing fallback program: programs/b1_small.nema" >&2
    exit 1
  fi
  if [[ ! -f programs/b3_kernel_302.nema ]]; then
    echo "Missing fallback program: programs/b3_kernel_302.nema" >&2
    exit 1
  fi
  python -m nema dsl hwtest programs/b1_small.nema --ticks 2 --outdir "${outdir}" --hw require --format json --no-color > "${run_b1_json}"
  python -m nema dsl hwtest programs/b3_kernel_302.nema --ticks 2 --outdir "${outdir}" --hw require --format json --no-color > "${run_b3_json}"
fi

extract_bench_report() {
  local json_path="$1"
  python - "${json_path}" <<'PY'
import json
import sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)
for key in ("bench_report", "benchReportPath", "benchReport"):
    value = payload.get(key)
    if isinstance(value, str) and value:
        print(value)
        sys.exit(0)
sys.exit(1)
PY
}

b1_bench_report="$(extract_bench_report "${run_b1_json}")"
b3_bench_report="$(extract_bench_report "${run_b3_json}")"

echo "HW pipeline completed."
echo "B1 bench_report: ${b1_bench_report}"
echo "B3 bench_report: ${b3_bench_report}"
