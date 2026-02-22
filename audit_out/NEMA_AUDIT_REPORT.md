# NEMA Audit Report (Post-fixes)

_Generated at_: 2026-02-22T03:37:40Z

## Executive Summary
- **GO** para iniciar DSL/compiler NEMA v0.1 sobre la base actual (contratos normativos presentes + evidencia B1/B3 software bit-exact).
- B1 evidencia completa: `digestMatch.ok=True`, `nodeCount=2`, `chemicalEdgeCount=1`.
- B3 evidencia completa y resuelta: `nodeCount=302`, `chemicalEdgeCount=7500`, `digestMatch.ok=True`.
- Toolchain HW: **NO HW TOOLCHAIN AVAILABLE** (`vitis_hls=NOT_FOUND`, `vivado=NOT_FOUND`).
- Contratos normativos presentes en raíz: `spec.md=True`, `nema_ir.proto=True`.

## Repo Fingerprint
- `git rev-parse HEAD`: `75e2352335fb3e1fec746fbbb27b6236719e548b`
- `git log -1 --decorate --oneline`: `75e2352 (HEAD -> master) Bench report normalization + schema + audit_min`
- `git status --porcelain=v1`: `?? audit_out/`
- Evidencias:
  - `audit_out/evidence/step1_git_rev_parse_HEAD.txt`
  - `audit_out/evidence/step1_git_status_porcelain_v1.txt`
  - `audit_out/evidence/step1_git_log_1.txt`
  - `audit_out/evidence/step1_ls_la.txt`
  - `audit_out/evidence/step1_find_outputs.txt`

## Benchmarks: B1 Summary
- IR: `example_b1_small_subgraph.json`
- Bench report: `build/example_b1_small_subgraph/bench_report.json`
- `modelId`: `example_b1_small_subgraph` ; `bench.targetId`: `example_b1_small_subgraph/CE/2-1`
- Conteos resueltos (`config.graph`): `nodeCount=2`, `chemicalEdgeCount=1`, `gapEdgeCount=1`, `edgeCountTotal=3`
- Integrador/schedule: `dt=1.0`, `dtNanoseconds=1000000000`, `snapshotRule=True`
- Correctness: `ok=True`, `digestMatch.ok=True`, `ticks=20`
- Performance CPU: `goldenTicksPerSecond=4167.635641438592`, `cppRefTicksPerSecond=19857.147687235556`
- Artefactos clave presentes: `digest=True`, `trace=True`, `hls_cpp=True`, `cpp_main=True`

## Benchmarks: B3 Summary
- IR: `example_b3_kernel_302.json`
- Bench report: `build/B3_kernel_302_7500/bench_report.json`
- `modelId`: `B3_kernel_302_7500` ; `bench.targetId`: `B3_kernel_302_7500/CE/302-7500`
- Conteos resueltos (`config.graph`): `nodeCount=302`, `chemicalEdgeCount=7500`, `gapEdgeCount=0`, `edgeCountTotal=7500`
- Provenance: `syntheticUsed=True`, `externalVerified=False`
- Integrador/schedule: `dt=1.0`, `dtNanoseconds=1000000000`, `snapshotRule=True`
- Correctness: `ok=True`, `digestMatch.ok=True`, `ticks=20`
- Performance CPU: `goldenTicksPerSecond=99.25147268687874`, `cppRefTicksPerSecond=9963.215804583126`
- Artefactos clave presentes: `digest=True`, `trace=True`, `hls_cpp=True`, `cpp_main=True`

## Determinism/Correctness Evidence
- B1 `correctness.digestMatch.ok`: `True`
- B3 `correctness.digestMatch.ok`: `True`
- Suite unitaria/integración: `python -m pytest -q` => `...............................................                          [100%]`
- Bench report schema validado en runtime por `nema hwtest` (`tools/bench_report_schema.json`).
- Evidencias:
  - `audit_out/evidence/step2_b1_bench_report.json.txt`
  - `audit_out/evidence/step2_b3_bench_report.json.txt`
  - `audit_out/evidence/step3_pytest_full_run.txt`

## Toolchain/HW Readiness
- `vitis_hls` en PATH: `NOT_FOUND`
- `vivado` en PATH: `NOT_FOUND`
- Estado: **NO HW TOOLCHAIN AVAILABLE** (solo flujo software: golden + C++ ref + codegen HLS C++).
- Reportes HW (`*.rpt`, `*.xml`) encontrados: ninguno en `build/` para esta corrida.
- Evidencias:
  - `audit_out/evidence/step4_which_vitis_hls.txt`
  - `audit_out/evidence/step4_which_vivado.txt`
  - `audit_out/evidence/step4_vitis_version.txt`
  - `audit_out/evidence/step4_vivado_version.txt`
  - `audit_out/evidence/step4_find_hw_reports.txt`

## Placeholder/Blockers Table
| Archivo | Línea | Placeholder | Severidad | Acción recomendada |
|---|---:|---|---|---|
| `./example_b3_kernel_302.json` | 22 | `"sha256": "sha256:REPLACE"` | MAJOR | Reemplazar placeholder por SHA-256 real del artifact external y activar verificación externalVerified=true. |

## IR & Semantics Readiness
- `spec.md` presente: `True` ; `nema_ir.proto` presente: `True`.
- Tick semantics, fixed-point y LUT policy documentados en `spec.md` y usados por tests/hwtest actuales.
- IR B3 incluye `modelId`, `graph.stats` y `graph.external`; loader resuelve conteos a `302/7500` en `bench_report.config.graph`.
- Hay evidencia de compatibilidad de contrato en CI local (`pytest`) y bench reports normalizados.

## GO/NO-GO Decision + Criteria
**Decision (DSL start)**: **GO**

| Criterio | Booleano | Evidencia |
|---|---|---|
| `contract.spec_md_present` | `True` | `audit_out/evidence/step2_structured_benchmark_summary.json` / bench reports |
| `contract.nema_ir_proto_present` | `True` | `audit_out/evidence/step2_structured_benchmark_summary.json` / bench reports |
| `tests.pytest_pass` | `True` | `audit_out/evidence/step2_structured_benchmark_summary.json` / bench reports |
| `b1.bench_report_exists` | `True` | `audit_out/evidence/step2_structured_benchmark_summary.json` / bench reports |
| `b1.digest_match_ok` | `True` | `audit_out/evidence/step2_structured_benchmark_summary.json` / bench reports |
| `b3.bench_report_exists` | `True` | `audit_out/evidence/step2_structured_benchmark_summary.json` / bench reports |
| `b3.digest_match_ok` | `True` | `audit_out/evidence/step2_structured_benchmark_summary.json` / bench reports |
| `b3.resolved_nodeCount_is_302` | `True` | `audit_out/evidence/step2_structured_benchmark_summary.json` / bench reports |
| `b3.resolved_chemicalEdgeCount_is_7500` | `True` | `audit_out/evidence/step2_structured_benchmark_summary.json` / bench reports |
| `toolchain.hw_available` | `False` | `audit_out/evidence/step2_structured_benchmark_summary.json` / bench reports |

Interpretación:
- DSL/compiler puede iniciar con respaldo de evidencia software bit-exact (B1 + B3).
- Cierre HW (csim/cosim/synth real) sigue bloqueado por ausencia de toolchain en entorno actual.

## Next Steps (prioritized, <=15)
1. Publicar artifact externo real de B3 (`artifacts/graphs/b3_kernel_302_7500.json`) y reemplazar `sha256:REPLACE` por digest real.
2. Re-ejecutar `nema hwtest` B3 con external verificado y confirmar `provenance.externalVerified=true`.
3. Instalar `vitis_hls`/`vivado` en entorno de auditoría para habilitar csim/cosim/synth.
4. Ejecutar `nema hwtest` con HW toolchain y archivar `*.rpt`/`*.xml` en `build/<modelId>/vitis_hls/...`.
5. Agregar job CI que ejecute `tools/audit_min.py` sobre outputs de benchmark y falle en NO-GO.
6. Versionar manifests de benchmark (B1/B3) con ticks objetivo y digests esperados.
7. Eliminar o archivar `build/302/` legacy para evitar confusión con `build/B3_kernel_302_7500/`.
