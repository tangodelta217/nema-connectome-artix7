# NEMA v0.1

[![CI](https://github.com/tangodelta217/nema-connectome-artix7/actions/workflows/ci.yml/badge.svg)](https://github.com/tangodelta217/nema-connectome-artix7/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Release](https://img.shields.io/badge/release-v0.1.0-informational.svg)](https://github.com/tangodelta217/nema-connectome-artix7/releases)

NEMA v0.1 is a deterministic neuro-simulation toolchain: validated IR (`JSON`, schema mirrored in `nema_ir.proto`) -> bit-exact fixed-point CPU golden simulator -> generated HLS C++ kernel -> cosim/harness evidence (`bench_report.json`). The repository is structured for reproducibility, with normative semantics in `spec.md` and benchmark manifests under `benches/`.

## Contributions

- Deterministic fixed-point simulation primitives and CLI scaffold (`nema check/sim/compile/hwtest`).
- Normative contract for v0.1 semantics and schema (`spec.md`, `nema_ir.proto`).
- Benchmark manifests and verification flow (`nema bench verify`, `benches/*`).
- HLS/toolchain wrappers and hardware gate scripts (`tools/hw/*`, `tools/run_hw_gates.sh`).
- Test suite for ISA, LUT policy/checksum, tick semantics, manifests, and reporting (`tests/`).

## Quickstart (Reproducible)

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
pip install pytest
python -m pytest
```

## Reproduce Bench Runs (B1/B3)

```bash
nema check example_b1_small_subgraph.json
nema sim example_b1_small_subgraph.json --ticks 32 --out build/b1/trace.jsonl
nema hwtest example_b1_small_subgraph.json --ticks 32 --outdir build/b1
nema bench verify benches/B1_small/manifest.json

nema check example_b3_kernel_302.json
nema sim example_b3_kernel_302.json --ticks 128 --out build/b3/trace.jsonl
nema hwtest example_b3_kernel_302.json --ticks 128 --outdir build/b3
nema bench verify benches/B3_kernel_302_7500/manifest.json
```

## Reproduce Tables/Figures (Scripts)

Use repository scripts to regenerate paper/evidence outputs (when present in your checkout):

```bash
bash tools/reproduce_paper_a.sh
bash tools/reproduce_paperA_routeA.sh
```

If those scripts are not available in your branch, run the benchmark commands above and collect outputs from `build/` plus `nema bench verify` manifests.

## Verify Artifact Bundle Hashes

```bash
sha256sum -c release/SHA256SUMS.txt
```

Optional single-file check:

```bash
sha256sum release/artifact_bundle_final.tar.gz
cat release/SHA256SUMS.txt
```

## Disclaimer

Power and energy numbers in this repository are **ESTIMATED_PRE_BOARD_ONLY**. They are not board-measured values and must not be presented as physical board measurements.

## Artifacts

- GitHub Releases: `https://github.com/tangodelta217/nema-connectome-artix7/releases`
- Release instructions: `release/RELEASE.md`
- Reviewer guide and release notes remain under `release/`.

## Normative Contract

The normative project contract is versioned at these exact paths:

- `./spec.md`
- `./nema_ir.proto`

These files define v0.1 semantics and the IR schema contract.

## Selected CLI Commands

```bash
nema check <ir.json>
nema sim <ir.json> --ticks N --out trace.jsonl
nema compile <ir.json> --outdir build/
nema hwtest <ir.json> --outdir build/
nema materialize-external <ir.json> --out connectomes/<bundle>.json
python -m nema connectome bundle build --nodes nodes.csv --edges edges.csv --out connectome_bundle/
python -m nema connectome bundle verify connectome_bundle/
python -m nema dsl --help
```

## Hardware Notes

Hardware toolchains (Vitis/Vivado) are optional for software unit testing. CI in this repository runs Python unit tests only.

For local hardware checks:

```bash
bash tools/run_hw_gates.sh
```

## Project Layout

- `nema/`: compiler, IR checks, golden sim, CLI.
- `tools/`: LUT generation, audit gates, hardware wrappers/scripts.
- `tests/`: pytest suite and fixtures.
- `benches/`: benchmark manifests and expected digests.
- `release/`: release metadata, checksums, and reviewer-facing docs.
