# Paper A Artifact Requirements

## Benchmarks incluidos
- Core (mínimo): `B1`, `B3`, `B4`
  - `benches/B1_small/manifest.json`
  - `benches/B3_kernel_302_7500/manifest.json`
  - `benches/B4_real_connectome/manifest.json`
- Extensión (si aplica): `B2/B5` (diversidad QoR), `B6` (delays)

## Tablas/Figuras requeridas
- Figura: pipeline completo NEMA (DSL/IR -> verify -> HLS/Vivado -> bench_report).
- Tabla: failure modes y gate que los detecta.
- Figura: arquitectura por capas (DSL, IR, validator, sim, codegen, hwtest/audit).
- Figura: semántica de tick + snapshotRule.
- Tabla: contrato IR usado en v0.1 (campos/checks).
- Figura: estrategia de bit-exactness (golden vs C++, digest pipeline).
- Figura: etapas HW (csim/csynth/cosim + Vivado impl + parse a bench_report).
- Tabla: suite de benches y metodología (N, E, ticks, métricas).
- Tabla: resultados de correctitud/reproducibilidad (mismatch=0, digestMatchOK).
- Tabla: evidencia HW (ii/latency/util + WNS por bench/part).
- Figura: mapa de artefactos y salidas reproducibles.
- Tabla: comandos exactos y checks esperados (exit code + keys JSON).
- Tabla: limitaciones/no-claims explícitos.

## Métricas exactas (machine-checkable)
- Correctitud:
  - `ok == true` (bench verify JSON)
  - `mismatches == []`
  - `digestMatchOk == true` (o equivalente de schema)
  - `bench_report.ok == true`
- HW/QoR:
  - `hardware.qor.ii`
  - `hardware.qor.latencyCycles`
  - `hardware.qor.utilization.{lut,ff,bram,dsp}`
  - `hardware.vivado.wns` (cuando haya implementación Vivado)
- Gates:
  - `python tools/audit_min.py --mode software` => `decision=GO`
  - `python tools/audit_min.py --mode hardware` => `decision=GO`

## Comandos de verificación base
```bash
python -m nema bench verify benches/B1_small/manifest.json --outdir build/paper_verify/b1
python -m nema bench verify benches/B3_kernel_302_7500/manifest.json --outdir build/paper_verify/b3
python -m nema bench verify benches/B4_real_connectome/manifest.json --outdir build/paper_verify/b4
python -m pytest -q
python tools/audit_min.py --mode software
python tools/audit_min.py --mode hardware
```
