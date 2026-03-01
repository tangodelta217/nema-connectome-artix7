# Paper A -> GPT-A2 Handoff Index

## Git hash
bb17ac319debc7ee40a28f4502fe4189f0795ac5

## Scope decisions (benchmarks incluidos)
- Core:
  - B1 -> benches/B1_small/manifest.json
  - B3 -> benches/B3_kernel_302_7500/manifest.json
  - B4 -> benches/B4_real_connectome/manifest.json
- Extensión:
  - B2/B5 (QoR diversity) y B6 (delays) como extensión/apéndice

## Tablas generadas
- `papers/paperA/artifacts/tables/gates_summary.csv`
- `papers/paperA/artifacts/tables/gates_summary.md`

## Figuras generadas
- `papers/paperA/artifacts/figures/gates_status.txt`

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

## Warnings / limitaciones
- No warnings/reasons reported by current audit outputs.
