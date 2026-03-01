#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ROUTEA_ROOT="${REPO_ROOT}/build/paperA_routeA"
LOG_DIR="${ROUTEA_ROOT}/logs"
RUN_LOG="${ROUTEA_ROOT}/reproduce_paperA_routeA.log"
BUNDLE_DIR="${REPO_ROOT}/build/paperA_routeA_bundle"
BUNDLE_TAR="${REPO_ROOT}/build/paperA_routeA_bundle.tar.gz"

PAPER_PDF_REL="papers/paperA/text/paper.pdf"
TABLES_DIR_REL="papers/paperA/artifacts/tables"
EVIDENCE_DIR_REL="papers/paperA/artifacts/evidence"

B3_OUT_REL="build/paperA_routeA/B3/B3_kernel_302_7500"
B4_OUT_REL="build/paperA_routeA/B4/B4_celegans_external_bundle"

timestamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log() {
  printf '[%s] %s\n' "$(timestamp)" "$*"
}

require_file() {
  local rel="$1"
  local abs="${REPO_ROOT}/${rel}"
  if [[ ! -f "${abs}" ]]; then
    echo "ERROR: missing required file: ${rel}" >&2
    exit 1
  fi
}

run_step() {
  local name="$1"
  shift
  local out="${LOG_DIR}/${name}.stdout.log"
  local err="${LOG_DIR}/${name}.stderr.log"

  log "STEP ${name}: $*"
  "$@" >"${out}" 2>"${err}"
}

stage_copy_if_exists() {
  local src_rel="$1"
  local dst_rel="$2"
  if [[ -e "${REPO_ROOT}/${src_rel}" ]]; then
    mkdir -p "${BUNDLE_DIR}/$(dirname "${dst_rel}")"
    cp -a "${REPO_ROOT}/${src_rel}" "${BUNDLE_DIR}/${dst_rel}"
  fi
}

main() {
  cd "${REPO_ROOT}"

  rm -rf "${ROUTEA_ROOT}" "${BUNDLE_DIR}" "${BUNDLE_TAR}"
  mkdir -p "${LOG_DIR}"

  : > "${RUN_LOG}"
  exec > >(tee -a "${RUN_LOG}") 2>&1

  log "Starting boardless RouteA reproduction."

  run_step "pytest_q" python -m pytest -q
  run_step "independent_check_paperA" python tools/independent_check.py --paperA

  run_step "hwtest_b3_routeA" \
    python -m nema hwtest example_b3_kernel_302.json --hw require --ticks 20 --outdir build/paperA_routeA/B3
  run_step "hwtest_b4_routeA" \
    python -m nema hwtest example_b4_celegans_external_bundle.json --hw require --ticks 20 --outdir build/paperA_routeA/B4

  run_step "make_table_bitexact" python papers/paperA/artifacts/scripts/make_table_bitexact.py
  run_step "make_table_qor" python papers/paperA/artifacts/scripts/make_table_qor.py
  run_step "bench_cpu_throughput" python tools/bench_cpu_throughput.py --benchmarks B1,B2,B3 --ticks 1000
  run_step "make_table_throughput" python papers/paperA/artifacts/scripts/make_table_throughput.py

  run_step "make_clean_paper" make -C papers/paperA clean paper

  require_file "${PAPER_PDF_REL}"
  require_file "${TABLES_DIR_REL}/results_bitexact.csv"
  require_file "${TABLES_DIR_REL}/results_qor.csv"
  require_file "${TABLES_DIR_REL}/results_throughput.csv"
  require_file "${B3_OUT_REL}/bench_report.json"
  require_file "${B4_OUT_REL}/bench_report.json"
  require_file "${B3_OUT_REL}/hw_reports/vivado_batch/vivado_timing_summary.rpt"
  require_file "${B4_OUT_REL}/hw_reports/vivado_batch/vivado_timing_summary.rpt"

  mkdir -p "${BUNDLE_DIR}/tables" "${BUNDLE_DIR}/logs" "${BUNDLE_DIR}/routeA/B3" "${BUNDLE_DIR}/routeA/B4" "${BUNDLE_DIR}/evidence" "${BUNDLE_DIR}/docs" "${BUNDLE_DIR}/scripts"

  cp -a "${REPO_ROOT}/${PAPER_PDF_REL}" "${BUNDLE_DIR}/paperA.pdf"

  cp -a "${REPO_ROOT}/${TABLES_DIR_REL}/results_bitexact.csv" "${BUNDLE_DIR}/tables/"
  cp -a "${REPO_ROOT}/${TABLES_DIR_REL}/results_qor.csv" "${BUNDLE_DIR}/tables/"
  cp -a "${REPO_ROOT}/${TABLES_DIR_REL}/results_throughput.csv" "${BUNDLE_DIR}/tables/"
  stage_copy_if_exists "${TABLES_DIR_REL}/results_bitexact.tex" "tables/results_bitexact.tex"
  stage_copy_if_exists "${TABLES_DIR_REL}/results_qor.tex" "tables/results_qor.tex"
  stage_copy_if_exists "${TABLES_DIR_REL}/results_throughput.tex" "tables/results_throughput.tex"
  stage_copy_if_exists "${TABLES_DIR_REL}/results_cpu.csv" "tables/results_cpu.csv"

  cp -a "${RUN_LOG}" "${BUNDLE_DIR}/logs/"
  cp -a "${LOG_DIR}/." "${BUNDLE_DIR}/logs/"

  cp -a "${REPO_ROOT}/${B3_OUT_REL}/bench_report.json" "${BUNDLE_DIR}/routeA/B3/"
  cp -a "${REPO_ROOT}/${B4_OUT_REL}/bench_report.json" "${BUNDLE_DIR}/routeA/B4/"
  cp -a "${REPO_ROOT}/${B3_OUT_REL}/hw_reports/vivado_batch" "${BUNDLE_DIR}/routeA/B3/"
  cp -a "${REPO_ROOT}/${B4_OUT_REL}/hw_reports/vivado_batch" "${BUNDLE_DIR}/routeA/B4/"

  stage_copy_if_exists "${EVIDENCE_DIR_REL}/vivado_coverage_report.md" "evidence/vivado_coverage_report.md"
  stage_copy_if_exists "${EVIDENCE_DIR_REL}/routeA_summary.md" "evidence/routeA_summary.md"
  stage_copy_if_exists "build/paperA_routeA/independent_check.out.txt" "evidence/independent_check.out.txt"
  stage_copy_if_exists "build/paperA_routeA/independent_check.err.txt" "evidence/independent_check.err.txt"

  stage_copy_if_exists "papers/paperA/submission/README_SPONSOR.md" "docs/README_SPONSOR.md"
  stage_copy_if_exists "docs/FPGA_MEASUREMENT.md" "docs/FPGA_MEASUREMENT.md"
  stage_copy_if_exists "docs/DEPLOY.md" "docs/DEPLOY.md"
  stage_copy_if_exists "tools/reproduce_paperA_routeA.sh" "scripts/reproduce_paperA_routeA.sh"

  (
    cd "${BUNDLE_DIR}"
    sha256sum \
      paperA.pdf \
      tables/results_bitexact.csv \
      tables/results_qor.csv \
      tables/results_throughput.csv \
      routeA/B3/bench_report.json \
      routeA/B4/bench_report.json \
      routeA/B3/vivado_batch/vivado_timing_summary.rpt \
      routeA/B4/vivado_batch/vivado_timing_summary.rpt \
      > SHA256SUMS.txt
  )

  tar -czf "${BUNDLE_TAR}" -C "${REPO_ROOT}/build" paperA_routeA_bundle

  log "DONE"
  log "Bundle: ${BUNDLE_TAR}"
  log "PDF: ${REPO_ROOT}/${PAPER_PDF_REL}"
}

main "$@"
