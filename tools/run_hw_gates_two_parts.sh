#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

export PATH="${HOME}/.local/bin:${PATH}"

OUTDIR="build_hw/two_parts"
IR_PATH="example_b1_small_subgraph.json"
TICKS="2"
PART_A=""
PART_B=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --outdir)
      OUTDIR="$2"
      shift 2
      ;;
    --ir)
      IR_PATH="$2"
      shift 2
      ;;
    --ticks)
      TICKS="$2"
      shift 2
      ;;
    --part-a)
      PART_A="$2"
      shift 2
      ;;
    --part-b)
      PART_B="$2"
      shift 2
      ;;
    *)
      echo "run_hw_gates_two_parts.sh: unknown argument: $1" >&2
      echo "usage: bash tools/run_hw_gates_two_parts.sh [--outdir <path>] [--ir <ir.json>] [--ticks <n>] [--part-a <part>] [--part-b <part>]" >&2
      exit 2
      ;;
  esac
done

mkdir -p "${OUTDIR}"

source tools/hw/activate_xilinx.sh

if ! command -v vivado >/dev/null 2>&1; then
  echo "run_hw_gates_two_parts.sh: vivado not found after activation." >&2
  exit 1
fi

if [[ -z "${PART_A}" || -z "${PART_B}" ]]; then
  parts_tcl="${OUTDIR}/list_parts.tcl"
  parts_txt="${OUTDIR}/vivado_parts.txt"
  cat > "${parts_tcl}" <<EOF
set fp [open "${parts_txt}" w]
foreach p [lsort [get_parts]] {
  puts \$fp \$p
}
close \$fp
exit
EOF
  vivado -mode batch -source "${parts_tcl}" -nolog -nojournal > "${OUTDIR}/vivado_list_parts.log" 2>&1

  mapfile -t candidate_parts < <(grep -E '^xc7a' "${parts_txt}" | sed '/^$/d' || true)
  if [[ "${#candidate_parts[@]}" -lt 2 ]]; then
    mapfile -t candidate_parts < <(sed '/^$/d' "${parts_txt}" || true)
  fi

  if [[ "${#candidate_parts[@]}" -lt 2 ]]; then
    echo "run_hw_gates_two_parts.sh: need at least two installed parts; found ${#candidate_parts[@]}." >&2
    echo "parts file: ${parts_txt}" >&2
    exit 1
  fi

  if [[ -z "${PART_A}" ]]; then
    PART_A="${candidate_parts[0]}"
  fi
  if [[ -z "${PART_B}" ]]; then
    PART_B="${candidate_parts[1]}"
  fi
fi

if [[ "${PART_A}" == "${PART_B}" ]]; then
  echo "run_hw_gates_two_parts.sh: PART_A and PART_B must be different." >&2
  exit 1
fi

echo "Running two-part HW gates with PART_A=${PART_A} PART_B=${PART_B}"

mkdir -p "${OUTDIR}/part_a" "${OUTDIR}/part_b"
python -m nema hwtest "${IR_PATH}" --ticks "${TICKS}" --outdir "${OUTDIR}/part_a" --hw require --cosim off --vivado-part "${PART_A}" > "${OUTDIR}/part_a/hwtest.json"
python -m nema hwtest "${IR_PATH}" --ticks "${TICKS}" --outdir "${OUTDIR}/part_b" --hw require --cosim off --vivado-part "${PART_B}" > "${OUTDIR}/part_b/hwtest.json"

bench_a="$(find "${OUTDIR}/part_a" -name bench_report.json -print | sort | head -n 1)"
bench_b="$(find "${OUTDIR}/part_b" -name bench_report.json -print | sort | head -n 1)"
if [[ -z "${bench_a}" || -z "${bench_b}" ]]; then
  echo "run_hw_gates_two_parts.sh: missing bench_report outputs." >&2
  exit 1
fi

python - "${bench_a}" "${bench_b}" "${PART_A}" "${PART_B}" <<'PY'
import json
import sys
from pathlib import Path

bench_a = Path(sys.argv[1])
bench_b = Path(sys.argv[2])
requested_a = sys.argv[3]
requested_b = sys.argv[4]

payload_a = json.loads(bench_a.read_text(encoding="utf-8"))
payload_b = json.loads(bench_b.read_text(encoding="utf-8"))
actual_a = payload_a.get("hardware", {}).get("vivado", {}).get("part")
actual_b = payload_b.get("hardware", {}).get("vivado", {}).get("part")
summary = {
    "ok": bool(actual_a and actual_b and actual_a != actual_b),
    "requested": {"partA": requested_a, "partB": requested_b},
    "actual": {"partA": actual_a, "partB": actual_b},
    "benchReports": {"partA": str(bench_a), "partB": str(bench_b)},
}
out_path = bench_a.parents[1] / "two_parts_summary.json"
out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, sort_keys=True))
if not summary["ok"]:
    raise SystemExit(1)
PY
