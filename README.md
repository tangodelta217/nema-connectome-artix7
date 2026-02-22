# NEMA v0.1 Scaffold

This repository contains a clean scaffold for the NEMA v0.1 toolchain:

- IR validation (`nema check`)
- Golden simulator (`nema sim`)
- HLS C++ generator (`nema compile`)
- End-to-end harness (`nema hwtest`)
- Bench manifest verification (`nema bench verify`)
- DSL frontend (`nema dsl ...`)

## Normative Contract

The normative project contract is versioned at these exact paths:
- `./spec.md`
- `./nema_ir.proto`

These two files define the v0.1 semantics and IR schema used by the current implementation.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
pip install pytest
```

## CLI Commands

```bash
nema check <ir.json>
nema sim <ir.json> --ticks N --out trace.jsonl
nema compile <ir.json> --outdir build/
nema hwtest <ir.json> --outdir build/
nema materialize-external <ir.json> --out connectomes/<bundle>.json
nema bench verify benches/<name>/manifest.json
python -m nema dsl check programs/b1_small.nema.toml
python -m nema dsl compile programs/b1_small.nema.toml --out build/b1_from_dsl.ir.json
python -m nema dsl hwtest programs/b1_small.nema.toml --ticks 20 --outdir build/b1_dsl
```

## Benchmark Repro Commands

### B1 (`example_b1_small_subgraph.json`)

```bash
nema check example_b1_small_subgraph.json
nema sim example_b1_small_subgraph.json --ticks 32 --out build/b1/trace.jsonl
nema compile example_b1_small_subgraph.json --outdir build/b1
nema hwtest example_b1_small_subgraph.json --ticks 32 --outdir build/b1
nema bench verify benches/B1_small/manifest.json
cat build/b1/bench_report.json
```

### B3 (`example_b3_kernel_302.json`)

```bash
nema check example_b3_kernel_302.json
nema sim example_b3_kernel_302.json --ticks 128 --out build/b3/trace.jsonl
nema compile example_b3_kernel_302.json --outdir build/b3
nema hwtest example_b3_kernel_302.json --ticks 128 --outdir build/b3
nema bench verify benches/B3_kernel_302_7500/manifest.json
cat build/b3/bench_report.json
```

## DSL Programs (MVP Frontend)

TOML DSL files live under `programs/` with extension `.nema.toml`:

- `programs/b1_small.nema.toml`
- `programs/b3_kernel_302_7500.nema.toml`

Defaults documented for v0.1 runtime compatibility:
- if `graph.dt` is omitted in IR, simulator default is `1.0`
- if `graph.tauM` and per-node `tauM` are omitted, simulator default is `1.0`

Run B1 from DSL:

```bash
python -m nema dsl check programs/b1_small.nema.toml
python -m nema dsl compile programs/b1_small.nema.toml --out build/b1_from_dsl.ir.json
python -m nema dsl hwtest programs/b1_small.nema.toml --ticks 20 --outdir build/b1_dsl
```

Run B3 from DSL:

```bash
python -m nema dsl check programs/b3_kernel_302_7500.nema.toml
python -m nema dsl compile programs/b3_kernel_302_7500.nema.toml --out build/b3_from_dsl.ir.json
python -m nema dsl hwtest programs/b3_kernel_302_7500.nema.toml --ticks 20 --outdir build/b3_dsl
```

## Testing

```bash
python -m pytest
```
