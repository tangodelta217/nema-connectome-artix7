# Review Resolution (Round 1)

| Issue (review) | Acción aplicada | Evidencia en PDF | Evidencia en bundle |
|---|---|---|---|
| Falta de números mínimos (bit-exact + QoR). | Se añadieron tablas generadas automáticamente desde artefactos: `results_bitexact.*` y `results_qor.*`; se insertaron en Evaluation con `\\input{...}` y referencias en texto. | `papers/paperA/text/sections/04_eval.tex` (tablas `tab:bitexact-summary` y `tab:qor-summary`); `papers/paperA/submission/paperA.pdf` | `papers/paperA/artifacts/tables/results_bitexact.csv`, `papers/paperA/artifacts/tables/results_bitexact.tex`, `papers/paperA/artifacts/tables/results_qor.csv`, `papers/paperA/artifacts/tables/results_qor.tex` |
| Fig 1 era “status light”, no evidencia técnica. | Se reemplazó la figura principal por pipeline real + matriz G0a/G0b/G1/G2/G3→evidence (`fig_pipeline_gates.png`) y se actualizó el caption con mapeo explícito. | `papers/paperA/text/sections/06_appendix_artifacts.tex`; `papers/paperA/submission/paperA.pdf` | `papers/paperA/artifacts/figures/fig_pipeline_gates.png`; se conserva `papers/paperA/artifacts/figures/gates_status.txt` como artefacto secundario |
| Bundle “No evaluable” por faltantes de JSON/manifest/README citados. | Se creó `reviewer_bundle/` autocontenido con PDF, README, manifest, audits, tablas, figuras, scripts, spec, manifests y bench reports B1/B2/B3/B4/B6 seleccionados. | N/A (evidencia de empaquetado) | `papers/paperA/submission/reviewer_bundle/INDEX.md`, `papers/paperA/submission/reviewer_bundle.tar.gz` |

## Comandos ejecutados para resolver

1. `python papers/paperA/artifacts/scripts/make_table_bitexact.py`
2. `python papers/paperA/artifacts/scripts/make_table_qor.py`
3. `make -C papers/paperA paper`
4. Regeneración de `papers/paperA/submission/reviewer_bundle/` y empaquetado `reviewer_bundle.tar.gz`
