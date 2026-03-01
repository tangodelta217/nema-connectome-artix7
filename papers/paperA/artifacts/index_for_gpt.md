# Paper A -> GPT Handoff Index

## Git hash

bb17ac319debc7ee40a28f4502fe4189f0795ac5

## Scope decisions (benchmarks incluidos)

- B1: `benches/B1_small/manifest.json` (manifest_exists=True)
- B2: `benches/B2_mid/manifest.json` (manifest_exists=True)
- B3: `benches/B3_kernel_302_7500/manifest.json` (manifest_exists=True)
- B4: `benches/B4_real_connectome/manifest.json` (manifest_exists=True)
- B5: `benches/B5_synthetic_family/manifest.json` (manifest_exists=False)
- B6: `benches/B6_delay_small/manifest.json` (manifest_exists=True)

## Tablas generadas

- papers/paperA/artifacts/tables/results_bitexact.csv
- papers/paperA/artifacts/tables/results_bitexact.tex
- papers/paperA/artifacts/tables/results_cpu.csv
- papers/paperA/artifacts/tables/results_qor.csv
- papers/paperA/artifacts/tables/results_qor.tex
- papers/paperA/artifacts/tables/results_throughput.csv
- papers/paperA/artifacts/tables/results_throughput.tex

## Figuras generadas

- papers/paperA/artifacts/figures/fig_pipeline_gates.png
- papers/paperA/artifacts/figures/gates_status.png

## audit_min summary

- software.source: `project_eval_out_v2/evidence/audit_mode_software.json`
- software.decision: GO
    - software.criteria.dslReady: True
    - software.criteria.digestMatchAll: True
    - software.criteria.benchVerifyOk: True
    - software.criteria.b3Evidence302_7500: True
    - software.criteria.graphCountsNormalized: True
- hardware.source: `project_eval_out_v2/evidence/audit_mode_hardware.json`
- hardware.decision: GO
    - hardware.criteria.hardwareToolchainAvailable: True
    - hardware.criteria.hardwareEvidenceG0b: True
    - hardware.criteria.hardwareEvidenceG2: True
    - hardware.criteria.hardwareEvidenceG3: True
    - hardware.criteria.digestMatchAll: True

## Warnings / limitaciones

- Warnings/notes detectadas en auditorías:
    - {"source": "software", "ignoredReports": ["/home/tangodelta/Escritorio/NEMA/build/302/bench_report.json"]}
    - {"source": "hardware", "ignoredReports": ["/home/tangodelta/Escritorio/NEMA/build/302/bench_report.json"]}
