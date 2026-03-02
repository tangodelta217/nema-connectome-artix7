# Architecture Overview

## Pipeline

NEMA v0.1 follows a deterministic, evidence-driven pipeline:

1. DSL/authoring inputs (optional) -> IR JSON.
2. IR validation against semantic invariants (`spec.md`) and schema contract (`nema_ir.proto`).
3. Golden CPU simulation with fixed-point numerics.
4. HLS C++ generation for accelerator flow.
5. hwtest/cosim integration and bench report generation.
6. Manifest/digest verification and audit gates.

## Core Components

- `nema/ir_validate.py`: structural and semantic contract checks.
- `nema/sim.py`: fixed-point golden reference execution.
- `nema/codegen/hls_gen.py`: HLS-oriented code emission.
- `nema/hwtest.py`: orchestrates software/hardware evidence paths.
- `tools/audit_min.py`: software/hardware gate decisions.

## Determinism and Evidence

Determinism is enforced through explicit validation and digest-based checks:

- Canonical graph references and manifest verification.
- Stable output artifacts (`bench_report.json`, traces, digest files).
- Reproducible command-line workflows for benchmark families.

## CI Scope

GitHub Actions CI intentionally covers software checks only:

- Python matrix tests (3.10 / 3.11)
- `pip` dependency installation
- `pytest -q`

Vivado/Vitis toolchains are not required in CI due licensing/environment constraints.

## Artifact Separation

- **Git history**: source code, docs, small fixtures/manifests, final small tables.
- **Release assets**: heavy generated bundles and large run evidence.

This separation keeps the repository lightweight while preserving reproducibility.
