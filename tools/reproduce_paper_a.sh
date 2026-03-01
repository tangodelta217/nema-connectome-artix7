#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${REPO_ROOT}/build"
LOG_PATH="${BUILD_DIR}/reproduce_paper_a.log"
TMP_TABLE_DIR="${BUILD_DIR}/paperA_tmp_tables"

ARTIFACTS_DIR="${REPO_ROOT}/papers/paperA/artifacts"
ARTIFACTS_TABLES_DIR="${ARTIFACTS_DIR}/tables"
ARTIFACTS_FIGURES_DIR="${ARTIFACTS_DIR}/figures"
ARTIFACTS_EVIDENCE_DIR="${ARTIFACTS_DIR}/evidence"

mkdir -p "${BUILD_DIR}" "${ARTIFACTS_TABLES_DIR}" "${ARTIFACTS_FIGURES_DIR}" "${ARTIFACTS_EVIDENCE_DIR}"
: > "${LOG_PATH}"
exec > >(tee -a "${LOG_PATH}") 2>&1

timestamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

step() {
  local msg="$1"
  printf '\n[%s] %s\n' "$(timestamp)" "${msg}"
}

require_file() {
  local path="$1"
  if [[ ! -f "${path}" ]]; then
    echo "ERROR: required file not found: ${path}" >&2
    exit 1
  fi
}

safe_cleanup() {
  step "Safe cleanup: build/paperA_* and papers/paperA/artifacts/tables/results_*.csv"
  shopt -s nullglob

  local target=""
  for target in "${REPO_ROOT}"/build/paperA_*; do
    if [[ ! -e "${target}" ]]; then
      continue
    fi
    case "${target}" in
      "${REPO_ROOT}/build/paperA_"*)
        rm -rf -- "${target}"
        echo "removed: ${target}"
        ;;
      *)
        echo "skip (unsafe): ${target}"
        ;;
    esac
  done

  local csv=""
  for csv in "${REPO_ROOT}"/papers/paperA/artifacts/tables/results_*.csv; do
    if [[ ! -f "${csv}" ]]; then
      continue
    fi
    case "${csv}" in
      "${REPO_ROOT}/papers/paperA/artifacts/tables/results_"*.csv)
        rm -f -- "${csv}"
        echo "removed: ${csv}"
        ;;
      *)
        echo "skip (unsafe): ${csv}"
        ;;
    esac
  done

  shopt -u nullglob
}

run_or_fail() {
  local label="$1"
  shift
  step "Run: ${label}"
  "$@"
}

run_independent_check_scoped() {
  step "Run: python tools/independent_check.py (scoped Paper A reports)"

  local -a reports=(
    "${REPO_ROOT}/build/audit_min/bench_verify/b1/example_b1_small_subgraph/bench_report.json"
    "${REPO_ROOT}/build/audit_min/bench_verify/b2/B2_mid_64_1024/bench_report.json"
    "${REPO_ROOT}/build/audit_min/bench_verify/b3/B3_kernel_302_7500/bench_report.json"
    "${REPO_ROOT}/build/bench_verify_b4/B4_celegans_external_bundle/bench_report.json"
    "${REPO_ROOT}/build_hw/b6/B6_delay_small/bench_report.json"
  )

  local -a cmd=(python tools/independent_check.py)
  local report=""
  local found=0
  for report in "${reports[@]}"; do
    if [[ -f "${report}" ]]; then
      cmd+=(--bench-report "${report}")
      found=1
    fi
  done

  if [[ "${found}" -eq 0 ]]; then
    cmd+=(--paperA)
  fi

  "${cmd[@]}"
}

main() {
  step "Paper A boardless reproducible rebuild start"
  cd "${REPO_ROOT}"

  safe_cleanup

  run_or_fail "python -m pytest -q" python -m pytest -q
  run_independent_check_scoped

  local sw_audit="${ARTIFACTS_EVIDENCE_DIR}/audit_software.json"
  local hw_audit="${ARTIFACTS_EVIDENCE_DIR}/audit_hardware.json"
  if [[ ! -f "${sw_audit}" ]]; then
    run_or_fail "python tools/audit_min.py --mode software > ${sw_audit}" bash -lc "python tools/audit_min.py --mode software > \"${sw_audit}\""
  fi
  if [[ ! -f "${hw_audit}" ]]; then
    run_or_fail "python tools/audit_min.py --mode hardware > ${hw_audit}" bash -lc "python tools/audit_min.py --mode hardware > \"${hw_audit}\""
  fi
  require_file "${sw_audit}"
  require_file "${hw_audit}"

  run_or_fail \
    "python papers/paperA/artifacts/scripts/build_tables.py (gates summary + figure snapshot)" \
    python papers/paperA/artifacts/scripts/build_tables.py \
      --software "${sw_audit}" \
      --hardware "${hw_audit}" \
      --csv "${ARTIFACTS_TABLES_DIR}/gates_summary.csv" \
      --md "${ARTIFACTS_TABLES_DIR}/gates_summary.md" \
      --figure "${ARTIFACTS_FIGURES_DIR}/gates_status.txt"

  run_or_fail "python tools/paperA/build_review_pack_v3.py" python tools/paperA/build_review_pack_v3.py

  run_or_fail \
    "python tools/bench_cpu_throughput.py --benchmarks B1,B3 --ticks 1000" \
    python tools/bench_cpu_throughput.py \
      --benchmarks B1,B3 \
      --ticks 1000 \
      --out-csv "${ARTIFACTS_TABLES_DIR}/results_cpu.csv"

  mkdir -p "${TMP_TABLE_DIR}"
  run_or_fail \
    "python papers/paperA/artifacts/scripts/make_table_bitexact.py" \
    python papers/paperA/artifacts/scripts/make_table_bitexact.py \
      --out-csv "${TMP_TABLE_DIR}/results_bitexact.csv" \
      --out-tex "${ARTIFACTS_TABLES_DIR}/results_bitexact.tex"

  run_or_fail \
    "python papers/paperA/artifacts/scripts/make_table_qor.py" \
    python papers/paperA/artifacts/scripts/make_table_qor.py \
      --out-csv "${TMP_TABLE_DIR}/results_qor.csv" \
      --out-tex "${ARTIFACTS_TABLES_DIR}/results_qor.tex"

  run_or_fail \
    "python papers/paperA/artifacts/scripts/make_table_throughput.py" \
    python papers/paperA/artifacts/scripts/make_table_throughput.py \
      --out-csv "${TMP_TABLE_DIR}/results_throughput.csv" \
      --out-tex "${ARTIFACTS_TABLES_DIR}/results_throughput.tex"

  run_or_fail "make -C papers/paperA clean paper" make -C papers/paperA clean paper

  local paper_pdf="${REPO_ROOT}/papers/paperA/text/paper.pdf"
  local review_pack="${REPO_ROOT}/papers/paperA/artifacts/review_pack_v3.md"
  local checksum_file="${BUILD_DIR}/paperA_reproduce.sha256"
  require_file "${paper_pdf}"
  require_file "${review_pack}"
  require_file "${ARTIFACTS_TABLES_DIR}/results_bitexact.csv"
  require_file "${ARTIFACTS_TABLES_DIR}/results_qor.csv"
  require_file "${ARTIFACTS_TABLES_DIR}/results_throughput.csv"
  require_file "${ARTIFACTS_TABLES_DIR}/results_bitexact.tex"
  require_file "${ARTIFACTS_TABLES_DIR}/results_qor.tex"
  require_file "${ARTIFACTS_TABLES_DIR}/results_throughput.tex"

  run_or_fail \
    "sha256sum outputs > ${checksum_file}" \
    bash -lc "sha256sum \
      \"${ARTIFACTS_TABLES_DIR}/results_bitexact.csv\" \
      \"${ARTIFACTS_TABLES_DIR}/results_qor.csv\" \
      \"${ARTIFACTS_TABLES_DIR}/results_throughput.csv\" \
      \"${ARTIFACTS_TABLES_DIR}/results_bitexact.tex\" \
      \"${ARTIFACTS_TABLES_DIR}/results_qor.tex\" \
      \"${ARTIFACTS_TABLES_DIR}/results_throughput.tex\" \
      \"${review_pack}\" \
      \"${paper_pdf}\" > \"${checksum_file}\""

  step "SUCCESS"
  echo "Log: ${LOG_PATH}"
  echo "PDF: ${paper_pdf}"
  echo "Review pack: ${review_pack}"
  echo "Checksums: ${checksum_file}"
}

main "$@"
