# READINESS AUDIT (Industria + Academia/arXiv)

Fecha de auditoria: 2026-03-03  
Repositorio: `NEMA v0.1`  
Paper principal canonico: `paper/paper.tex`

## 0) Dictamen ejecutivo

- **Industria: GO condicionado**
  - **GO por defecto** para verificacion de evidencia (`--hw off`): hashes, integridad de release, alineacion paper-tablas y verificacion de manifests.
  - **GO condicionado** para rerun HW (`--hw require`): requiere toolchain Vivado/Vitis disponible y prerequisitos HW; para reproducir exactamente el part del paper (`xc7a200tsbg484-1`) se necesita soporte Artix-7 instalado en Vivado.
  - El flujo falla temprano con mensaje accionable cuando el part objetivo no esta disponible (no falla tardia opaca).
- **Academia/arXiv: GO**
  - `paper/paper.tex` pasa preflight canonico de bundle arXiv y compilacion local 2-pass.
  - Coherencia paper↔tablas↔artefactos verificada sin cambios de resultados/tablas.

## 1) Alcance y reglas aplicadas

- Sin cambios de producto, sin refactors grandes.
- Sin cambios de resultados ni tablas del paper.
- Sin commits/push.
- Cambios solo en documentacion/referencias de rutas y reporte de readiness.

## 2) Inventario (A)

### Entrypoints y flujos

- `README.md`
- `docs/REPRODUCE.md`
- `docs/REVIEWER_GUIDE.md`
- `release/REVIEWER_GUIDE.md`
- `tools/build_arxiv_bundle.sh`
- `tools/arxiv_preflight.py`
- `tools/verify_paper_inputs.py`
- `tools/check_release_integrity.py`
- `tools/hw/preflight_ubuntu24.sh`
- `tools/hw/check_part_available.sh`

### Canonicalidad paper

- Canonico para claims/arXiv: `paper/paper.tex`
- Alternativo/legacy (no canonico): `papers/paperA/`

### Nomenclatura handoff

- Canonico: `build/handoff/`
- Referencia clave: `build/handoff/B3_CANONICAL_STATUS.json`

## 3) Coherencia paper↔tablas↔artefactos (B)

Resultado: **PASS**

Evidencia valida:

- `python3 tools/verify_paper_inputs.py` -> PASS  
  Verifica inputs canonicos en `paper/paper.tex`:
  - `review_pack/tables/artix7_hls_digest_summary_strict_v2.tex`
  - `review_pack/tables/artix7_qor_v6.tex`
  - `review_pack/tables/artix7_power_v7_funcsaif.tex`
  - `review_pack/tables/artix7_metrics_final.tex`
- `sha256sum -c release/SHA256SUMS.txt` -> PASS
- `python3 tools/check_release_integrity.py` -> PASS

## 4) Reproducibilidad (C)

Resultado: **PASS para evidencia** y **PASS condicionado para HW rerun**.

### Ruta 1: evidencia (default recomendado)

Comandos:

- `nema bench verify benches/B1_small/manifest.json --hw off`
- `nema bench verify benches/B3_kernel_302_7500/manifest.json --hw off`

Estado: validacion reproducible sin rerun HLS/Vivado.

### Ruta 2: rerun HW

Comandos de prerequisito:

- `bash tools/hw/preflight_ubuntu24.sh`
- `bash tools/hw/check_part_available.sh xc7a200tsbg484-1`

Comandos de rerun:

- `nema bench verify benches/B1_small/manifest.json --hw require`
- `nema bench verify benches/B3_kernel_302_7500/manifest.json --hw require`

Condicion de strict target-part:

- `nema bench verify ... --hw require --strict-part`
- Si falta `xc7a200tsbg484-1`, instalar soporte Artix-7 en Vivado y reintentar.

## 5) ArXiv preflight (D)

Resultado: **PASS**

Comandos:

- `bash tools/build_arxiv_bundle.sh`
- `python3 tools/arxiv_preflight.py --bundle-dir build/arxiv_bundle_stage --main-rel paper/paper.tex`
- `make arxiv-pdflatex-2pass`

## 6) Calidad profesional (E)

Estado: **adecuado para industria + academia** en el alcance de esta auditoria.

- Estructura repo clara y rutas canonicas explicitas.
- Documentacion separa evidencia vs rerun HW.
- Canonicalidad paper resuelta (`paper/` canonico, `papers/paperA` legacy).
- Nomenclatura handoff normalizada (`build/handoff/`).

## 7) Checklist P0/P1/P2

## P0

- [x] P0-1 Eliminar ambiguedad de paper canonico (`paper/paper.tex`).
- [x] P0-2 Definir `papers/paperA` como legacy/alternativo (no canonico para claims/arXiv).
- [x] P0-3 Separar ruta de verificacion de evidencia (`--hw off`) de rerun HW (`--hw require`).
- [x] P0-4 Normalizar nomenclatura handoff en docs (`build/handoff`).
- [x] P0-5 Actualizar readiness con evidencia ejecutada y dictamen actual.

## P1

- [ ] P1-1 Ejecutar rerun estricto del part del paper (`--strict-part`) en host con Artix-7 instalado.
- [ ] P1-2 Consolidar notas legacy de `papers/paperA` en su propia guia interna si se mantiene a largo plazo.

## P2

- [ ] P2-1 Reducir warnings tipograficos (overfull boxes) en compilacion arXiv para pulido editorial.

## 8) Mapa paper -> artefactos -> rutas

| Claim/Seccion paper | Artefacto | Ruta canonica |
|---|---|---|
| Paridad digest HLS/CPU | Tabla HLS strict v2 | `paper/paper.tex` -> `review_pack/tables/artix7_hls_digest_summary_strict_v2.tex` |
| QoR Artix-7 | Tabla QoR v6 + reportes post-route | `paper/paper.tex` -> `review_pack/tables/artix7_qor_v6.tex`, `build/amd_vivado_artix7_v5/*/post_route_{timing,utilization}.rpt` |
| Potencia SAIF funcional | Tabla power v7 + SAIF/rpt | `paper/paper.tex` -> `review_pack/tables/artix7_power_v7_funcsaif.tex`, `build/amd_power_artix7_v7_funcsaif/*` |
| Throughput/energia derivada | Tabla metrics final | `paper/paper.tex` -> `review_pack/tables/artix7_metrics_final.tex` |
| Identidad canonica B3 | Estado canonico de handoff | `build/handoff/B3_CANONICAL_STATUS.json` |
| Bundle arXiv | Tar + preflight | `build/arxiv_bundle.tar.gz`, `build/arxiv_bundle_stage/` |

## 9) Comandos ejecutados en esta auditoria

- `pytest -q -m "not hw and not integration"` -> PASS
- `python3 tools/verify_paper_inputs.py` -> PASS
- `sha256sum -c release/SHA256SUMS.txt` -> PASS
- `python3 tools/check_release_integrity.py` -> PASS
- `nema check example_b1_small_subgraph.json` -> PASS
- `nema check example_b3_kernel_302.json` -> PASS
- `bash tools/hw/preflight_ubuntu24.sh` -> PASS (`hwToolchainAvailable=true`, `partFallbackActive=true`)
- `nema bench verify benches/B1_small/manifest.json --hw off` -> PASS
- `nema bench verify benches/B3_kernel_302_7500/manifest.json --hw off` -> PASS
- `nema bench verify benches/B1_small/manifest.json --hw require` -> PASS
- `nema bench verify benches/B3_kernel_302_7500/manifest.json --hw require` -> PASS
- `bash tools/build_arxiv_bundle.sh` -> PASS
- `python3 tools/arxiv_preflight.py --bundle-dir build/arxiv_bundle_stage --main-rel paper/paper.tex` -> PASS
- `make arxiv-pdflatex-2pass` -> PASS
