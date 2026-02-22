# NEMA v0.1 — AGENTS

## Objective
Implement NEMA v0.1 as a deterministic toolchain:
IR (JSON for debug, later Protobuf) -> golden CPU sim (bit-exact fixed-point) -> HLS C++ kernel (Vitis HLS) -> cosim -> bench_report.json.

## Normative spec
- spec.md is normative for:
  - fixed-point rounding (RNE) + saturation behavior
  - tanh_lut policy and checksum behavior
  - tick semantics (snapshot rule)
  - RefConfig-MVP v1 signal/Q-format table
  - G0 conformance checklist

If any ambiguity arises, follow spec.md and add a regression test.

## Key input artifacts
- example_b1_small_subgraph.json (B1)
- example_b3_kernel_302.json (B3 ref config)

## Definition of Done (per stage)
Stage G0 is DONE only if:
1) ISA fixed-point unit tests pass (A.1)
2) LUT generation + checksum tests pass (A.2)
3) Tick semantics micrograph tests pass (A.3)
4) Bit-exact match between golden sim and HLS/Cosim for B1 (small) and then B3 (302/7500) for N ticks; emit bench_report.json

## Engineering rules
- Every semantic claim must be backed by a test.
- Keep golden sim and HLS kernel numerics aligned (same quantize, same LUT).
- Prefer small, composable modules. Avoid hidden global state.
- All command-line tools must have deterministic outputs given the same inputs + seeds.
- Add a README section with exact commands to reproduce each benchmark.

## Repo layout (target)
- nema/ (compiler + golden sim)
- hls/ (generated and/or template HLS code)
- tests/ (pytest + vectors)
- tools/ (LUT generator, report aggregator)
- benches/ (B1, B3 manifests + expected digests)
