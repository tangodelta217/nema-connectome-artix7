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
python -m nema connectome bundle build --nodes nodes.csv --edges edges.csv --out connectome_bundle/
python -m nema connectome bundle verify connectome_bundle/
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

### B4 (`example_b4_celegans_external_bundle.json`)

```bash
nema check example_b4_celegans_external_bundle.json
nema hwtest example_b4_celegans_external_bundle.json --ticks 32 --outdir build/b4
cat build/b4/B4_celegans_external_bundle/bench_report.json
```

External bundle format documentation:
- `docs/CONNECTOME_BUNDLE.md`

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

## HW Lab Quickstart

Use the single runner for hardware-mode pipeline execution:

```bash
tools/run_hw_pipeline.sh
```

What it does:

- creates `build_hw/<timestamp>_<gitshort>/`
- writes `hw_doctor.json`
- runs B1 and B3 in `require` mode (native `nema hwtest --hw require` if supported, otherwise `nema dsl hwtest --hw require`)
- prints final `bench_report.json` paths for B1 and B3

Behavior when toolchain is missing:

- exits with non-zero status
- prints a clear error pointing to `hw_doctor.json`

Gate-oriented HW runner (B1/B3 + audit outputs):

```bash
bash tools/run_hw_gates.sh
```

This runner:
- activates Xilinx env via `tools/hw/activate_xilinx.sh` (fails early if missing)
- runs B1/B3 in HW `require` mode
- writes:
  - `build_hw/hw_doctor.json`
  - `build_hw/audit_min_hardware.json`
  - `build_hw/audit_min_software.json`

## Audit Gates

`tools/audit_min.py` supports three gate modes:

- `software`:
  validates software-readiness gates (DSL ready, digest matches, B3 302/7500 evidence,
  manifest verification, normalized graph counts on relevant B1/B3 reports).
- `hardware`:
  validates hardware-readiness gates (toolchain availability + HW evidence/reports).
- `all`:
  requires both `software` and `hardware` gates to pass.

Recommended commands:

```bash
python tools/audit_min.py --mode software
python tools/audit_min.py --mode hardware
python tools/audit_min.py --mode all
```

Expected exit codes:

- `0` => decision `GO` for the selected mode.
- `1` => decision `NO-GO` for the selected mode.

Typical local development behavior (no Vitis/Vivado in PATH):

- `python tools/audit_min.py --mode software` -> usually exits `0`.
- `python tools/audit_min.py --mode hardware` -> usually exits `1` (missing HW toolchain/evidence).

GitHub Actions hardware gate activation (`CI_HW=1`):

- Set repository variable `CI_HW=1` in GitHub:
  `Settings -> Secrets and variables -> Actions -> Variables`.
- With `CI_HW=1`, CI will run `hardware-gates` even if `vitis_hls`/`vivado`
  are not detected in `PATH`.
- Local equivalent override:
  `CI_HW=1 python tools/audit_min.py --mode hardware`.

`NEMA-DSL2401` interpretation:

- `NEMA-DSL2401` indicates HW toolchain unavailable (`vitis_hls`/`vivado` not found).
- In software-focused flows this is an expected warning and should not block `--mode software`.
- In hardware-focused validation it is expected to contribute to `NO-GO` until HW toolchain/evidence is present.
