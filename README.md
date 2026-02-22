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
python -m nema dsl --help
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

## NEMA-DSL v0.1 (Scaffold)

The textual DSL with braces/`;` is documented at:
- `docs/nema_dsl_v0.1.md`

Current CLI scaffold subcommands exist but are intentionally NYI:
- `python -m nema dsl check <file.dsl>`
- `python -m nema dsl compile <file.dsl> --out <ir.json>`
- `python -m nema dsl hwtest <file.dsl> --ticks N --outdir build/`
- `python -m nema dsl from-ir <ir.json> --out <file.dsl>`

## Testing

```bash
python -m pytest
```

## Audit Gates

For local software development (default gate):

```bash
python tools/audit_min.py --mode software
```

For HW lab environments (requires toolchain/report evidence):

```bash
python tools/audit_min.py --mode hardware
```
