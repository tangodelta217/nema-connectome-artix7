# Paper A Submission Gate Report

## Gate Status

| Check | Status | Evidence |
|---|---|---|
| PDF build | PASS | `papers/paperA/submission/paperA.pdf` |
| Artifacts regenerated | PASS | `papers/paperA/artifacts/{tables,figures,evidence}`, `papers/paperA/artifacts/artifact_manifest.json` |
| Software gate | PASS | `papers/paperA/submission/audit_software_final.json` (decision=GO, ok=True) |
| Hardware gate | PASS | `papers/paperA/submission/audit_hardware_final.json` (decision=GO, ok=True) |
| Citation sanity | PASS | undefined citations=0, undefined refs=0 |

## Artifact Manifest Hash

- sha256: `719232ab0de3d1c8fe699055768a60d975d80d20a613900e0eb4b5fe989ac403`
- repeat read: `719232ab0de3d1c8fe699055768a60d975d80d20a613900e0eb4b5fe989ac403`
- stable: yes

## Residual Risks

- LaTeX still reports layout warnings (overfull/underfull boxes) in `papers/paperA/text/paper.log`.
- acmart metadata warnings remain (CCS keywords/ACM keywords missing) in `papers/paperA/text/paper.log`.
- `papers/paperA/submission/citations_report.txt` may still list unused bib entries; this does not block compilation but affects bibliography hygiene.
- Artifact directory was backed up to `papers/paperA/artifacts_backup_20260227T002611Z` before regeneration.

## Reproduction Commands

`make -C papers/paperA artifacts`
`make -C papers/paperA clean`
`make -C papers/paperA paper`
`python tools/audit_min.py --mode software`
`python tools/audit_min.py --mode hardware`
`sha256sum papers/paperA/artifacts/artifact_manifest.json`
