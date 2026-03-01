# Artifacts Index

## Claim Support Map

- C1 (bit-exactness core benches): `papers/paperA/artifacts/evidence/audit_software.json`, `papers/paperA/artifacts/tables/gates_summary.*`.
- C2 (hardware evidence pipeline): `papers/paperA/artifacts/evidence/audit_hardware.json`, `papers/paperA/artifacts/figures/gates_status.*`.
- C3 (artifact reproducibility contract): `papers/paperA/artifacts/artifact_manifest.json`, `papers/paperA/artifacts/ARTIFACT_README.md`.

## Tables

- `papers/paperA/artifacts/tables/gates_summary.csv`

```text
mode,ok,decision,toolchainHwAvailable,software_ok,hardware_ok,all_ok
software,true,GO,True,True,True,True
hardware,true,GO,True,True,True,True
```

- `papers/paperA/artifacts/tables/gates_summary.md`

```text
| mode | ok | decision | toolchainHwAvailable | software_ok | hardware_ok | all_ok |
|---|---|---|---|---|---|---|
| software | true | GO | True | True | True | True |
| hardware | true | GO | True | True | True | True |
```

## Figures

- `papers/paperA/artifacts/figures/gates_status.png` -> caption: Gate status snapshot rendered from papers/paperA/artifacts/figures/gates\_status.txt
- `papers/paperA/artifacts/figures/gates_status.txt` -> caption: MISSING

## audit_min decisions

- software: decision=GO ok=True
  - criteria.digestMatchAll=True
  - criteria.benchVerifyOk=True
  - criteria.b3Evidence302_7500=True
  - criteria.graphCountsNormalized=True
  - criteria.hardwareToolchainAvailable=True
- hardware: decision=GO ok=True
  - criteria.digestMatchAll=True
  - criteria.benchVerifyOk=True
  - criteria.b3Evidence302_7500=True
  - criteria.graphCountsNormalized=True
  - criteria.hardwareToolchainAvailable=True

## artifact_manifest sha256

- `719232ab0de3d1c8fe699055768a60d975d80d20a613900e0eb4b5fe989ac403` (`papers/paperA/artifacts/artifact_manifest.json`)
