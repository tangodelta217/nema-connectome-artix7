# Patchlist Round 1

| Área | Cambio aplicado | Archivos |
|---|---|---|
| Tablas de resultados | Generación automática de tabla bit-exact (CSV + LaTeX tabular) desde artefactos y bench reports, con deduplicación determinista por benchmark/model más reciente. | `papers/paperA/artifacts/scripts/make_table_bitexact.py`, `papers/paperA/artifacts/tables/results_bitexact.csv`, `papers/paperA/artifacts/tables/results_bitexact.tex` |
| Tablas de resultados | Generación automática de tabla QoR (CSV + LaTeX tabular) desde bench reports, incluyendo ii/latency/utilización/wns y flags csim/csynth/cosim/vivado. | `papers/paperA/artifacts/scripts/make_table_qor.py`, `papers/paperA/artifacts/tables/results_qor.csv`, `papers/paperA/artifacts/tables/results_qor.tex` |
| Paper (Evaluation) | Inserción de tablas “Bit-exact summary” y “QoR summary (boardless)” con `\input{...}` y referencias en texto. | `papers/paperA/text/sections/04_eval.tex` |
| Figura principal | Reemplazo de snapshot por figura pipeline real + mini matriz gates→evidence. Se mantiene `gates_status.txt` como artefacto secundario. | `papers/paperA/artifacts/figures/fig_pipeline_gates.png`, `papers/paperA/text/sections/06_appendix_artifacts.tex` |
| Bundle reviewer | Bundle autocontenido con PDF, README, manifest, audits, tablas/figuras, scripts, spec, manifests y bench reports B1/B2/B3/B4/B6. | `papers/paperA/submission/reviewer_bundle/`, `papers/paperA/submission/reviewer_bundle.tar.gz`, `papers/paperA/submission/reviewer_bundle/INDEX.md` |
| README artefactos | Documentación de comandos para regenerar `results_bitexact` y `results_qor`. | `papers/paperA/artifacts/ARTIFACT_README.md` |
