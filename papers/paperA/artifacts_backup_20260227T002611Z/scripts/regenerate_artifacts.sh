#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ART_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PAPER_DIR="$(cd "${ART_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${PAPER_DIR}/../.." && pwd)"

mkdir -p "${ART_DIR}/evidence" "${ART_DIR}/tables" "${ART_DIR}/figures"

cd "${REPO_ROOT}"
python tools/audit_min.py --mode software > "${ART_DIR}/evidence/audit_software.json"
python tools/audit_min.py --mode hardware > "${ART_DIR}/evidence/audit_hardware.json"

python "${SCRIPT_DIR}/build_tables.py" \
  --software "${ART_DIR}/evidence/audit_software.json" \
  --hardware "${ART_DIR}/evidence/audit_hardware.json" \
  --csv "${ART_DIR}/tables/gates_summary.csv" \
  --md "${ART_DIR}/tables/gates_summary.md" \
  --figure "${ART_DIR}/figures/gates_status.txt"
