# NEMA v0.1 Scaffold

This repository contains a clean scaffold for the NEMA v0.1 toolchain:

- IR validation (`nema check`)
- Golden simulator placeholder (`nema sim`)
- HLS C++ generator placeholder (`nema compile`)
- End-to-end harness placeholder (`nema hwtest`)

Semantics are intentionally not implemented yet.

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
```

## Benchmark Repro Commands

### B1 (`example_b1_small_subgraph.json`)

```bash
nema check example_b1_small_subgraph.json
nema sim example_b1_small_subgraph.json --ticks 32 --out build/b1/trace.jsonl
nema compile example_b1_small_subgraph.json --outdir build/b1
nema hwtest example_b1_small_subgraph.json --ticks 32 --outdir build/b1
cat build/b1/bench_report.json
```

### B3 (`example_b3_kernel_302.json`)

```bash
nema check example_b3_kernel_302.json
nema sim example_b3_kernel_302.json --ticks 128 --out build/b3/trace.jsonl
nema compile example_b3_kernel_302.json --outdir build/b3
nema hwtest example_b3_kernel_302.json --ticks 128 --outdir build/b3
cat build/b3/bench_report.json
```

## Testing

```bash
python -m pytest
```
