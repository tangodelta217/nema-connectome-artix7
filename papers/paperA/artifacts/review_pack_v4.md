# Paper A Review Pack v4 (Build Sheriff)

## Git

- HEAD: `bb17ac319debc7ee40a28f4502fe4189f0795ac5`

## Canonical Entrypoints

- `make -C papers/paperA artifacts` (exists)
- `make -C papers/paperA paper` (exists)

## Commands Executed

1. `make -C papers/paperA artifacts` -> `exit 124` (timed out, terminated while running `audit_min --mode software`).
2. Toolchain check from repo root: `which vivado && vivado -version | head`, `which vitis_hls && vitis_hls -version | head` -> both exit 0.
3. `python tools/audit_min.py --mode software` with timeout -> `exit 143` (terminated).
4. `python tools/audit_min.py --mode hardware` with timeout -> `exit 143` (terminated).
5. `python papers/paperA/artifacts/scripts/make_table_bitexact.py` -> exit 0.
6. `python papers/paperA/artifacts/scripts/make_table_qor.py` -> exit 0.
7. `python tools/bench_cpu_throughput.py --benchmarks B1,B2,B3 --ticks 1000 ...` -> exit 0.
8. `python papers/paperA/artifacts/scripts/make_table_throughput.py ...` -> exit 0.
9. `python tools/paperA/build_review_pack_v3.py` -> exit 0 (refresh coverage/checksums/manifest v3).
10. `make -C papers/paperA paper` -> exit 0.

## Toolchain Evidence (Repo Root)

- `vivado`: `/home/tangodelta/.local/bin/vivado` -> version `v2025.2` (ok).
- `vitis_hls`: `/home/tangodelta/.local/bin/vitis_hls` -> version `v2025.2` (ok).
- CWD-related failure for `vitis_hls`: **not reproduced** in this run.

## Benchmark Summary (B1,B2,B3,B4,B6)

| Bench | verify_ok | digestMatchOk | HLS status | Vivado impl | WNS present | bitexact report | qor report |
|---|---|---|---|---|---|---|---|
| B1 | - | true | OK | true | yes | `build/audit_min/bench_verify/b1/example_b1_small_subgraph/bench_report.json` | `build/audit_min/bench_verify/b1/example_b1_small_subgraph/bench_report.json` |
| B2 | - | true | OK | true | yes | `build/audit_min/bench_verify/b2/B2_mid_64_1024/bench_report.json` | `build/audit_min/bench_verify/b2/B2_mid_64_1024/bench_report.json` |
| B3 | - | true | OK | false | no | `build/audit_min/bench_verify/b3/B3_kernel_302_7500/bench_report.json` | `build/audit_min/bench_verify/b3/B3_kernel_302_7500/bench_report.json` |
| B4 | true | true | OK | false | no | `build/bench_verify_b4/B4_celegans_external_bundle/bench_report.json` | `build/bench_verify_b4/B4_celegans_external_bundle/bench_report.json` |
| B6 | - | true | OK | false | no | `build_hw/b6/B6_delay_small/bench_report.json` | `build_hw/b6/B6_delay_small/bench_report.json` |

## Root Cause Details (Vivado Coverage)

- B3: `FAIL` -> reason: `vivado impl failed`; log: `build/audit_min/bench_verify/b3/B3_kernel_302_7500/hw_reports/vivado_batch/run_vivado.log`; first hard error: `ERROR: [Synth 8-439] module 'nema_kernel_udiv_20ns_3ns_19_13_1_ip' not found`; bench_report: `build/audit_min/bench_verify/b3/B3_kernel_302_7500/bench_report.json`
- B4: `FAIL` -> reason: `vivado impl failed`; log: `build/bench_verify_b4/B4_celegans_external_bundle/hw_reports/vivado_batch/run_vivado.log`; first hard error: `ERROR: [Synth 8-439] module 'nema_kernel_udiv_20ns_3ns_19_13_1_ip' not found`; bench_report: `build/bench_verify_b4/B4_celegans_external_bundle/bench_report.json`
- B6: `FAIL` -> reason: `vivado impl failed`; log: `build_hw/b6/B6_delay_small/hw_reports/vivado_batch/run_vivado.log`; first hard error: `ERROR: [Synth 8-439] module 'nema_kernel_srem_4ns_3ns_4_5_1_ip' not found`; bench_report: `build_hw/b6/B6_delay_small/bench_report.json`

## Audit Artifacts Status

- software audit exit: `143`; json bytes: `0` (`papers/paperA/artifacts/evidence/audit_software.json`).
- hardware audit exit: `143`; json bytes: `0` (`papers/paperA/artifacts/evidence/audit_hardware.json`).

## Generated Outputs

- `papers/paperA/artifacts/tables/results_bitexact.csv`
- `papers/paperA/artifacts/tables/results_qor.csv`
- `papers/paperA/artifacts/tables/results_throughput.csv`
- `papers/paperA/artifacts/evidence/vivado_coverage_report.md`
- `papers/paperA/text/paper.pdf`

## End-of-Run Verification

- `python -m pytest -q` -> `exit 0`
- `python tools/independent_check.py --paperA` -> `exit 0` (2 warnings on B4 legacy lane fields)
- `make -C papers/paperA paper` -> `exit 0`
