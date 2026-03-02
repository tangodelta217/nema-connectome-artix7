# NEMA v0.1

[![CI](https://github.com/tangodelta217/nema-connectome-artix7/actions/workflows/ci.yml/badge.svg)](https://github.com/tangodelta217/nema-connectome-artix7/actions/workflows/ci.yml)
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

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
pip install pytest
python -m pytest -q
```

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

## Artifacts / Releases

- Repository: `https://github.com/tangodelta217/nema-connectome-artix7`
- Releases: `https://github.com/tangodelta217/nema-connectome-artix7/releases`
- v0.1.0 paper asset (release): `https://github.com/tangodelta217/nema-connectome-artix7/releases/download/v0.1.0/paper.pdf`

Large generated evidence bundles belong in GitHub Releases assets, not git history.

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
