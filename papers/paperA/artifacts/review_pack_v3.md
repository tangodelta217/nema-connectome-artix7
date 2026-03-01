# Paper A Review Pack v3

## Executive Bullets

- Preflight `make -C papers/paperA clean paper`: exit `MISSING` (`build/paperA_preflight_out/make_clean_paper.stdout.txt`).
- Preflight `python -m pytest -q`: exit `MISSING` (`build/paperA_preflight_out/pytest_q.stdout.txt`).
- Preflight `python tools/independent_check.py --paperA`: exit `MISSING`, parsed source `MISSING`.
- Preflight `audit_min --mode software --format json --out ...`: exit `MISSING` (CLI mismatch in this repo; see `build/paperA_preflight_out/audit_software.stderr.txt`).
- Preflight `audit_min --mode hardware --format json --out ...`: exit `MISSING` (CLI mismatch in this repo; see `build/paperA_preflight_out/audit_hardware.stderr.txt`).
- Software gate source: `/home/tangodelta/Escritorio/NEMA/papers/paperA/artifacts/evidence/audit_software.json` decision `GO`.
- Hardware gate source: `/home/tangodelta/Escritorio/NEMA/papers/paperA/artifacts/evidence/audit_hardware.json` decision `GO`.
- Bit-exact table regenerated: `/home/tangodelta/Escritorio/NEMA/papers/paperA/artifacts/tables/results_bitexact.csv`.
- QoR table regenerated: `/home/tangodelta/Escritorio/NEMA/papers/paperA/artifacts/tables/results_qor.csv`.
- Throughput table regenerated: `/home/tangodelta/Escritorio/NEMA/papers/paperA/artifacts/tables/results_throughput.csv`.
- Vivado coverage report regenerated: `/home/tangodelta/Escritorio/NEMA/papers/paperA/artifacts/evidence/vivado_coverage_report.md`.
- Independent checker validates digest consistency from traces + minimal schema + regex cross-checks against HLS/Vivado reports.
- Claims in paper should use table-backed evidence only (no board measurement claims).

## What We Can Claim Safely Today

- C1 bit-exact on core benches is supported when `verify_ok=true`, `mismatches_len=0`, and `digestMatchOk=true` in `results_bitexact.csv`.
- Independent anti-circularity check is supported for Paper A benches when `independent_check_ok=true`.
- Hardware QoR/timing evidence is script-generated and visible in `results_qor.csv` and `vivado_coverage_report.md`.
- Throughput context is present as measured CPU + estimated HW in `results_throughput.csv`.

## What We Cannot Claim (Yet)

- No on-board power/latency measurement claim (expected artifact `build_hw/fpga_measure/power_latency_report.json` not required for Paper A core).
- Do not claim successful Vivado implementation for benches where coverage status is `FAIL` or `SKIPPED`.
- Do not claim preflight audit commands with `--format json` succeeded in this repo; this CLI option is unsupported here.

## Benchmark Table (Canonical CSV)

- Bit-exact: `/home/tangodelta/Escritorio/NEMA/papers/paperA/artifacts/tables/results_bitexact.csv`
- QoR: `/home/tangodelta/Escritorio/NEMA/papers/paperA/artifacts/tables/results_qor.csv`
- Throughput: `/home/tangodelta/Escritorio/NEMA/papers/paperA/artifacts/tables/results_throughput.csv`

### Bit-exact (rows)

| benchId | N | E | ticks | verify_ok | mismatches_len | digestMatchOk | independent_check_ok | trace_present |
|---|---:|---:|---:|---|---:|---|---|---|
| B1 | 2 | 3 | 20 | true | 0 | true | - | true | build/audit_min/bench_verify/b1/example_b1_small_subgraph/bench_report.json |
| B2 | 64 | 1024 | 20 | true | 0 | true | - | true | build/audit_min/bench_verify/b2/B2_mid_64_1024/bench_report.json |
| B3 | 302 | 7500 | 20 | true | 0 | true | - | true | build/audit_min/bench_verify/b3/B3_kernel_302_7500/bench_report.json |
| B4 | 8 | 12 | 2 | true | 0 | true | - | true | build/bench_verify_b4/B4_celegans_external_bundle/bench_report.json |
| B5 | 96 | 1800 | 2 | - | - | true | - | true | build/bench_verify_b5_family/B5_synth_96_1800_s503/bench_report.json |
| B6 | 3 | 2 | 20 | - | - | true | - | true | build/paperA_routeA/B6/B6_delay_small/bench_report.json |

### QoR (rows)

| benchId | ii | latencyCycles | lut | ff | bram | dsp | wns | fmax_est | hls_csim_ok | hls_csynth_ok | vivado_impl_ok |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| B1 | 32 | 31 | 1148 | 355 | 0 | 0 | 1.129 | 258.331181 | true | true | true | build/audit_min/bench_verify/b1/example_b1_small_subgraph/bench_report.json |
| B2 | 614 | 613 | 4818 | 4738 | 1 | 1 | 0.957 | 247.341083 | true | true | true | build/audit_min/bench_verify/b2/B2_mid_64_1024/bench_report.json |
| B3 | 2746 | 2745 | 3172 | 3110 | 7 | 1 | 0.988 | 249.252243 | true | true | true | build/pre_board_20260228T132542Z/runs/b3_hw/B3_kernel_302_7500/bench_report.json |
| B4 | 100 | 99 | 2584 | 2633 | 0 | 0 | 1.032 | 252.016129 | true | true | true | build/bench_verify_b4/B4_celegans_external_bundle/bench_report.json |
| B5 | 892 | 891 | 4561 | 5148 | 6 | 1 | - | 200 | true | true | false | build/bench_verify_b5_family/B5_synth_96_1800_s503/bench_report.json |
| B6 | 67 | 66 | 1928 | 1098 | 1 | 0 | 0.894 | 243.54603 | true | true | true | build/paperA_routeA/B6/B6_delay_small/bench_report.json |

## Semantics Summary (from spec.md)

- Fixed-point rounding/overflow: L23: Overflow behavior: | L24: - `SATURATE` only. | L26: Rounding behavior: | L27: - `RNE` (round to nearest, ties to even) only.
- Tick semantics: L141: ## 5. Tick Semantics (`nema.tick.v0.1`) | L149: 1. snapshot all node voltages: `V_snapshot` | L163: 4. Euler update with snapshot rule: | L170: - simulation node iteration is index-ordered | L171: - snapshot rule guarantees order-independent results for update ordering
- Bit-exact definition: L177: Two executions are bit-exact equal when all per-tick digests match. | L179: Digest computation: | L180: - collect `V` in node index order | L181: - pack each raw voltage as signed int16 little-endian | L182: - compute SHA-256 over packed byte array

## Pipeline Summary

- DSL -> IR: `python -m nema dsl check programs/*.nema` (or manifest-driven lower/check).
- Golden + C++ ref: `python -m nema bench verify <manifest>` emits `bench_report.json`, `golden/digest.json`, `golden/trace.jsonl`.
- HLS/Vivado path: `python -m nema hwtest <ir>` / `bash tools/run_hw_gates.sh` emits `hw_reports/*.rpt|*.xml|*.log` and hardware fields in bench report.
- Independent checker: `python tools/independent_check.py --paperA`.

## Vivado Implementation Coverage

- Detailed table: `/home/tangodelta/Escritorio/NEMA/papers/paperA/artifacts/evidence/vivado_coverage_report.md`

| benchId | status | reason | log_path |
|---|---|---|---|
| B1 | OK | - | build/audit_min/bench_verify/b1/example_b1_small_subgraph/hw_reports/vivado_batch/run_vivado.log |
| B2 | OK | - | build/audit_min/bench_verify/b2/B2_mid_64_1024/hw_reports/vivado_batch/run_vivado.log |
| B3 | OK | - | build/pre_board_20260228T132542Z/runs/b3_hw/B3_kernel_302_7500/hw_reports/vivado_batch/run_vivado.log |
| B4 | OK | - | build/bench_verify_b4/B4_celegans_external_bundle/hw_reports/vivado_batch/run_vivado.log |
| B5 | FAIL | vivado impl failed | build/bench_verify_b5_family/B5_synth_96_1800_s503/hw_reports/vivado_batch/run_vivado.log |
| B6 | OK | - | build/paperA_routeA/B6/B6_delay_small/hw_reports/vivado_batch/run_vivado.log |

## Roadmap (Measured-on-Board, No Fabrication)

- Measurement runbook: `docs/FPGA_MEASUREMENT.md`.
- Latency collector placeholder: `tools/fpga_measure/collect_latency.py`.
- Power collector placeholder: `tools/fpga_measure/collect_power.py`.
- JSON schema target: `tools/fpga_measure/schema_power_latency_report.json`.
- Expected real artifact path: `build_hw/fpga_measure/power_latency_report.json` with `method=MEASURED_ON_BOARD`.

## Reproduction Commands

```bash
make -C papers/paperA clean paper
python -m pytest -q
python tools/independent_check.py --paperA
python tools/paperA/build_review_pack_v3.py
make -C papers/paperA paper
```
