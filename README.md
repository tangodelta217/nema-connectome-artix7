# NEMA v0.1

[![Quality](https://github.com/tangodelta217/nema-connectome-artix7/actions/workflows/quality.yml/badge.svg)](https://github.com/tangodelta217/nema-connectome-artix7/actions/workflows/quality.yml)
[![arXiv Build](https://github.com/tangodelta217/nema-connectome-artix7/actions/workflows/arxiv.yml/badge.svg)](https://github.com/tangodelta217/nema-connectome-artix7/actions/workflows/arxiv.yml)
[![Scorecard](https://github.com/tangodelta217/nema-connectome-artix7/actions/workflows/scorecard.yml/badge.svg)](https://github.com/tangodelta217/nema-connectome-artix7/actions/workflows/scorecard.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Release](https://img.shields.io/badge/release-v0.1.0-informational.svg)](https://github.com/tangodelta217/nema-connectome-artix7/releases)

## Overview

NEMA v0.1 is a deterministic toolchain for connectome-oriented workloads: validated IR (`JSON`, schema mirrored in `nema_ir.proto`) -> bit-exact fixed-point golden CPU simulation -> generated HLS C++ kernel -> reproducible reports/artifacts (`bench_report.json`, manifests, checksums).

The normative contract for semantics and schema is defined by `spec.md` and `nema_ir.proto`.

## Key Contributions

- Deterministic fixed-point simulation and contract validation (`nema check`, `nema sim`).
- HLS generation and reproducible hardware-oriented harness (`nema compile`, `nema hwtest`).
- Bench verification and digest-based evidence (`nema bench verify`, `benches/*`).
- Reproducibility-first project structure for paper/reviewer workflows.

## Repository Layout

- `nema/`: CLI, IR validation, lowering/codegen, golden simulator.
- `tests/`: unit/integration fixtures and regression coverage.
- `tools/`: audits, helper scripts, hardware wrappers.
- `benches/`: benchmark manifests and expected digests.
- `docs/`: policies, methods, architecture and reproducibility docs.
- `release/`: release manifests/checksums and reviewer-oriented metadata.

See also: `docs/ARCHITECTURE.md`.

## Quickstart

Prerequisito: Python 3.11 o superior.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
pip install pytest
python -m pytest -q
```

## Calidad y seguridad

Instala dependencias de desarrollo:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Ejecuta checks locales (no requieren Vivado/Vitis):

```bash
make ci
```

Comandos equivalentes:

```bash
ruff check . --config ruff.toml
ruff format --check tools/update_sha256sums.py tools/verify_paper_inputs.py tools/sync_status_docs.py tests/test_status_sync.py tests/test_verify_paper_inputs.py
mypy --config-file mypy.ini
bandit -q -r nema tools/verify_paper_inputs.py tools/update_sha256sums.py -lll
python -m pip_audit -r requirements-dev.txt --skip-editable --progress-spinner off
pytest -q -m "not hw and not integration"
```

Nota: el comando de `pytest` excluye tests marcados como `hw` e `integration`, por lo que no dispara flujos de toolchain de FPGA.

## Supply-chain security

Este repositorio usa dos workflows dedicados en GitHub Actions:

- `dependency-review.yml` (PR): ejecuta `actions/dependency-review-action` y falla si detecta vulnerabilidades nuevas de severidad `high` o `critical` en dependencias introducidas por el cambio.
- `scorecard.yml` (main + schedule): ejecuta OpenSSF Scorecard y publica resultados SARIF para code scanning.
- `codeql.yml` (main + PR + schedule): ejecuta SAST de CodeQL para Python y publica resultados en code scanning.
- `.github/dependabot.yml`: abre PRs automáticas semanales para dependencias Python y GitHub Actions.

Cómo interpretar resultados:

- Dependency Review en rojo: el PR introduce una dependencia con riesgo alto; se debe actualizar, reemplazar o justificar explícitamente antes de merge.
- Scorecard bajo o con checks fallidos: hay debilidades de supply chain (por ejemplo pinning insuficiente, permisos amplios, ramas sin protección); tratarlo como deuda de seguridad prioritaria.
- SARIF en code scanning: cada hallazgo incluye regla y ubicación; usarlo como lista accionable para endurecimiento continuo.

### Gobernanza de merge y scanning

La rama `main` está protegida con controles de calidad y seguridad obligatorios:

- Pull request obligatorio para merge.
- Al menos 1 aprobación humana por PR.
- Aprobación posterior al último push del PR (`require_last_push_approval`).
- Historial lineal y resolución obligatoria de conversaciones.
- Checks obligatorios en `main`: `unit-tests (3.11)`, `unit-tests (3.12)`, `quality (3.11)`, `quality (3.12)`, `CodeQL Analyze (python)`, `Scorecard analysis`.

Estado de referencia (3 de marzo de 2026): no hay alerts abiertos en Code scanning. Los hallazgos históricos de Scorecard puramente de gobernanza temporal (por ejemplo antigüedad <90 días o métricas históricas previas al endurecimiento de branch protection) se cerraron como `won't fix` con justificación explícita en GitHub Security.

## Reproducibility

Core benchmark commands:

```bash
nema check example_b1_small_subgraph.json
nema hwtest example_b1_small_subgraph.json --ticks 32 --outdir build/b1
nema bench verify benches/B1_small/manifest.json

nema check example_b3_kernel_302.json
nema hwtest example_b3_kernel_302.json --ticks 128 --outdir build/b3
nema bench verify benches/B3_kernel_302_7500/manifest.json
```

Hash verification for release assets:

```bash
sha256sum -c release/SHA256SUMS.txt
```

Paper input wiring verification:

```bash
python tools/verify_paper_inputs.py
```

## Artifacts / Releases

- Repository: `https://github.com/tangodelta217/nema-connectome-artix7`
- Releases: `https://github.com/tangodelta217/nema-connectome-artix7/releases`
- v0.1.0 paper asset (release): `https://github.com/tangodelta217/nema-connectome-artix7/releases/download/v0.1.0/paper.pdf`
- Binary/generated Paper A assets: `release/EXTERNAL_ASSETS.md`

Large generated evidence bundles belong in GitHub Releases assets, not git history.

Download and verify release assets locally:

```bash
python tools/fetch_release_assets.py --tag v0.1.0
python tools/fetch_release_assets.py --tag v0.1.0 --check
```

## arXiv Submission

Canonical arXiv paper source in this repo is `paper/paper.tex`.

Build and validate a source-only submission bundle:

```bash
bash tools/build_arxiv_bundle.sh
make arxiv-bundle
```

Two-pass `pdflatex` local validation of the staged bundle:

```bash
make arxiv-pdflatex-2pass
```

### Cómo generar y verificar el bundle arXiv

`tools/build_arxiv_bundle.sh` ejecuta este flujo antes de empaquetar:

1. `python tools/verify_paper_inputs.py` para detectar drift de tablas/artefactos esperados.
2. Resolución y staging determinista de dependencias TeX/Bib/Figures.
3. Preflight estructural con `python tools/arxiv_preflight.py --bundle-dir build/arxiv_bundle_stage --main-rel paper/paper.tex`:
   - valida `\documentclass` en el main TeX;
   - valida `00README.XXX` y `toplevelfile` correcto;
   - valida cierre de dependencias `\input`/`\include` dentro del bundle.
4. Preflight de LaTeX con `bash tools/latex_preflight.sh`:
   - si `latexmk` está disponible, compila en modo no interactivo (`-interaction=nonstopmode -halt-on-error`);
   - si no está disponible, al menos valida `00README.XXX` y `\documentclass` en el main TeX.
5. Empaquetado source-only (`build/arxiv_bundle.tar.gz`) y validación de contenido.

Comando recomendado local:

```bash
bash tools/build_arxiv_bundle.sh
python tools/arxiv_preflight.py --bundle-dir build/arxiv_bundle_stage --main-rel paper/paper.tex
```

Outputs:

- `build/arxiv_bundle.tar.gz`
- `build/arxiv_bundle.required_files.txt`
- `build/arxiv_bundle.contents.txt`

The bundle build fails if it finds stale `release_round10b` references, local absolute paths, missing `\input`/`\include` dependencies, or generated LaTeX byproducts (`.aux`, `.log`, etc.).

### Advertencias AutoTeX

- AutoTeX en arXiv puede usar un entorno TeX distinto al local; evita depender de rutas locales o paquetes no estándar.
- Mantén `00README.XXX` con `toplevelfile` correcto para que arXiv detecte el archivo principal.
- Asegura que el main TeX tenga `\documentclass` y que todas las dependencias estén dentro del tarball.
- El bundle es source-only: no incluir PDFs generados ni subproductos (`.aux`, `.log`, `.fls`, `.fdb_latexmk`, etc.).

## Limitations

Power and energy values in this repository are **ESTIMATED_PRE_BOARD_ONLY** and must not be interpreted as on-board measurements.

## Citation

Citation metadata is provided in `CITATION.cff`.

```bash
cat CITATION.cff
```

Until a permanent arXiv identifier is assigned, placeholder metadata remains explicit and should be updated when available.

## Project Policies

- Contribution process: `CONTRIBUTING.md`
- Security reporting: `SECURITY.md`
- Code of Conduct: `CODE_OF_CONDUCT.md`
- License: `LICENSE`
- Change history: `CHANGELOG.md`
