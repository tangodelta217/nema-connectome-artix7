#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ART_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

required=(
  "${ART_DIR}/evidence/audit_software.json"
  "${ART_DIR}/evidence/audit_hardware.json"
  "${ART_DIR}/tables/gates_summary.csv"
  "${ART_DIR}/tables/gates_summary.md"
  "${ART_DIR}/figures/gates_status.txt"
)

for path in "${required[@]}"; do
  if [[ ! -f "${path}" ]]; then
    echo "missing artifact: ${path}" >&2
    exit 1
  fi
done

python - <<'PY' "${ART_DIR}/evidence/audit_software.json" "${ART_DIR}/evidence/audit_hardware.json"
from __future__ import annotations
import json
import sys
for p in sys.argv[1:]:
    with open(p, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if "decision" not in payload:
        raise SystemExit(f"invalid audit payload (missing decision): {p}")
print("artifact JSON validation: OK")
PY
