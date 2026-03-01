#!/usr/bin/env bash

set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

OUTDIR="build_ckpt_full"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --outdir)
      if [[ $# -lt 2 ]]; then
        echo "checkpoint_full.sh: --outdir requires a value" >&2
        exit 2
      fi
      OUTDIR="$2"
      shift 2
      ;;
    *)
      echo "checkpoint_full.sh: unknown argument: $1" >&2
      echo "usage: bash tools/checkpoint_full.sh [--outdir <path>]" >&2
      exit 2
      ;;
  esac
done

rm -rf "${OUTDIR}"
mkdir -p "${OUTDIR}" "${OUTDIR}/build_hw"

run_step() {
  local name="$1"
  shift
  local stdout_file="${OUTDIR}/${name}.stdout.txt"
  local stderr_file="${OUTDIR}/${name}.stderr.txt"
  local rc_file="${OUTDIR}/${name}.exitcode.txt"
  "$@" >"${stdout_file}" 2>"${stderr_file}"
  local rc=$?
  printf "%s\n" "${rc}" > "${rc_file}"
  return "${rc}"
}

json_get() {
  local json_path="$1"
  local key_path="$2"
  python - "$json_path" "$key_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
key_path = sys.argv[2].split(".")
if not path.exists():
    print("MISSING")
    raise SystemExit(0)
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("INVALID")
    raise SystemExit(0)
cur = data
for key in key_path:
    if isinstance(cur, dict) and key in cur:
        cur = cur[key]
    else:
        print("MISSING")
        raise SystemExit(0)
if isinstance(cur, bool):
    print("true" if cur else "false")
elif cur is None:
    print("null")
else:
    print(str(cur))
PY
}

# 1) pytest
set +e
run_step "pytest" python -m pytest -q
pytest_rc=$?
set -e
cat "${OUTDIR}/pytest.stdout.txt" "${OUTDIR}/pytest.stderr.txt" > "${OUTDIR}/pytest.txt"

# 2) audit software
set +e
run_step "audit_software_cmd" python tools/audit_min.py --mode software --out "${OUTDIR}/audit_software.json"
audit_sw_rc=$?
set -e

# 3) run HW gates (with isolated outdir)
set +e
run_step "run_hw_gates" bash tools/run_hw_gates.sh --outdir "${OUTDIR}/build_hw"
run_hw_rc=$?
set -e

# 4) audit hardware scanning that outdir
set +e
run_step "audit_hardware_cmd" python tools/audit_min.py --mode hardware --scan "${OUTDIR}/build_hw" --out "${OUTDIR}/audit_hardware.json"
audit_hw_rc=$?
set -e

# Toolchain probe in clean shell
set +e
run_step "toolchain_check" bash -lc 'export PATH="$HOME/.local/bin:$PATH"; echo "vitis_hls=$(which vitis_hls || echo NOT_FOUND)"; echo "vivado=$(which vivado || echo NOT_FOUND)"; (vitis_hls -version | head -n 6 || true); (vivado -version | head -n 6 || true)'
toolchain_rc=$?
set -e
cat "${OUTDIR}/toolchain_check.stdout.txt" "${OUTDIR}/toolchain_check.stderr.txt" > "${OUTDIR}/toolchain_check.txt"

# Artifact listings
find "${OUTDIR}/build_hw" -name bench_report.json -print | sort > "${OUTDIR}/build_hw_bench_reports.txt" || true
find "${OUTDIR}/build_hw" -type f \( -name "*.rpt" -o -name "*.xml" -o -name "*.log" \) -print | sort > "${OUTDIR}/build_hw_reports.txt" || true

bench_count="$(wc -l < "${OUTDIR}/build_hw_bench_reports.txt" | tr -d ' ')"
hw_reports_count="$(wc -l < "${OUTDIR}/build_hw_reports.txt" | tr -d ' ')"

audit_sw_decision="$(json_get "${OUTDIR}/audit_software.json" "decision")"
audit_sw_toolchain="$(json_get "${OUTDIR}/audit_software.json" "toolchainHwAvailable")"
audit_hw_decision="$(json_get "${OUTDIR}/audit_hardware.json" "decision")"
audit_hw_toolchain="$(json_get "${OUTDIR}/audit_hardware.json" "toolchainHwAvailable")"
audit_hw_reasons="$(python - "${OUTDIR}/audit_hardware.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.exists():
    print("-")
    raise SystemExit(0)
try:
    data = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    print("INVALID_JSON")
    raise SystemExit(0)
reasons = data.get("reasons")
if isinstance(reasons, list) and reasons:
    print("; ".join(str(r) for r in reasons))
else:
    print("-")
PY
)"

vitis_line="$(grep -m1 '^vitis_hls=' "${OUTDIR}/toolchain_check.stdout.txt" || echo 'vitis_hls=NOT_FOUND')"
vivado_line="$(grep -m1 '^vivado=' "${OUTDIR}/toolchain_check.stdout.txt" || echo 'vivado=NOT_FOUND')"

pytest_status="FAIL"
[[ "${pytest_rc}" -eq 0 ]] && pytest_status="PASS"
audit_sw_status="FAIL"
[[ "${audit_sw_rc}" -eq 0 && "${audit_sw_decision}" == "GO" ]] && audit_sw_status="PASS"
toolchain_status="FAIL"
[[ "${toolchain_rc}" -eq 0 ]] && toolchain_status="PASS"
hw_artifacts_status="FAIL"
if [[ "${run_hw_rc}" -eq 0 && "${bench_count}" -ge 2 ]]; then
  hw_artifacts_status="PASS"
fi
audit_hw_status="FAIL"
[[ "${audit_hw_rc}" -eq 0 && "${audit_hw_decision}" == "GO" ]] && audit_hw_status="PASS"

cat > "${OUTDIR}/SUMMARY.md" <<EOF
# CHECKPOINT FULL SUMMARY

| Check | Result | Details |
|---|---|---|
| pytest | ${pytest_status} | exit=${pytest_rc} |
| audit software | ${audit_sw_status} | exit=${audit_sw_rc}, decision=${audit_sw_decision}, toolchainHwAvailable=${audit_sw_toolchain} |
| toolchain (clean shell) | ${toolchain_status} | ${vitis_line}; ${vivado_line} |
| run_hw_gates artifacts | ${hw_artifacts_status} | exit=${run_hw_rc}, bench_reports=${bench_count}, hw_reports=${hw_reports_count} |
| audit hardware | ${audit_hw_status} | exit=${audit_hw_rc}, decision=${audit_hw_decision}, toolchainHwAvailable=${audit_hw_toolchain}, reasons=${audit_hw_reasons} |

## Evidence Files
- \`${OUTDIR}/pytest.txt\`
- \`${OUTDIR}/audit_software.json\`
- \`${OUTDIR}/audit_hardware.json\`
- \`${OUTDIR}/toolchain_check.txt\`
- \`${OUTDIR}/build_hw_bench_reports.txt\`
- \`${OUTDIR}/build_hw_reports.txt\`
- \`${OUTDIR}/run_hw_gates.stdout.txt\`
- \`${OUTDIR}/run_hw_gates.stderr.txt\`
EOF

# Required gates: pytest + software gate + run_hw_gates + hardware gate.
if [[ "${pytest_rc}" -eq 0 && "${audit_sw_rc}" -eq 0 && "${audit_sw_decision}" == "GO" && "${run_hw_rc}" -eq 0 && "${audit_hw_rc}" -eq 0 && "${audit_hw_decision}" == "GO" ]]; then
  exit 0
fi
exit 1
