# Paper A Artifact Index

## Tables (paths)
- `papers/paperA/artifacts/tables/gates_summary.csv`
- `papers/paperA/artifacts/tables/gates_summary.md`

## Table sample rows (3)
| mode | ok | decision | toolchainHwAvailable | software_ok | hardware_ok | all_ok |
| software | true | GO | True | True | True | True |
| hardware | true | GO | True | True | True | True |

## Figures (paths + current captions)
- `papers/paperA/artifacts/figures/gates_status.txt` -> caption: Gate status snapshot

## audit_min summary
- software.decision: `GO`
  - software.criteria.dslReady: `True`
  - software.criteria.digestMatchAll: `True`
  - software.criteria.benchVerifyOk: `True`
  - software.criteria.b3Evidence302_7500: `True`
  - software.criteria.graphCountsNormalized: `True`
- hardware.decision: `GO`
  - hardware.criteria.hardwareToolchainAvailable: `True`
  - hardware.criteria.hardwareEvidenceG0b: `True`
  - hardware.criteria.hardwareEvidenceG2: `True`
  - hardware.criteria.hardwareEvidenceG3: `True`
  - hardware.criteria.digestMatchAll: `True`

## Benchmarks summary (present + latest status found)
| Bench | manifest_present | manifest_path | latest_status | latest_report |
|---|---:|---|---|---|
| B1 | true | `benches/B1_small/manifest.json` | report_ok=True, digestMatch_ok=True | `build/audit_min/bench_verify/b1/example_b1_small_subgraph/bench_report.json` |
| B3 | true | `benches/B3_kernel_302_7500/manifest.json` | report_ok=True, digestMatch_ok=True | `build/audit_min/bench_verify/b3/B3_kernel_302_7500/bench_report.json` |
| B4 | true | `benches/B4_real_connectome/manifest.json` | report_ok=True, digestMatch_ok=True | `build/bench_verify_eqlozbf7/B4_celegans_external_bundle/bench_report.json` |
| B6 | true | `benches/B6_delay_small/manifest.json` | report_ok=True, digestMatch_ok=True | `build_hw/b6/B6_delay_small/bench_report.json` |
| B2 | true | `benches/B2_mid/manifest.json` | report_ok=True, digestMatch_ok=True | `build/audit_min/bench_verify/b2/B2_mid_64_1024/bench_report.json` |
| B5 | false | `benches/B5_synthetic_family/manifest.json` | report_ok=True, digestMatch_ok=True | `build/bench_verify_b5_family/B5_synth_96_1800_s503/bench_report.json` |
