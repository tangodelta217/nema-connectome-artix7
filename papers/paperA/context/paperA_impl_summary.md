# Paper A Implementation Summary

## DSL v0.1 / v0.2
- v0.1 core parser/lowering exists (`nema/dsl/lexer.py`, `nema/dsl/parser.py`, `nema/dsl/lower.py`).
- v0.2 preprocessor features implemented: `include`, `const`, `${NAME}` placeholders (`nema/dsl/preprocess.py`).
- Diagnostics catalog and stable JSON/text rendering (`nema/dsl/catalog.py`, `nema/dsl/diagnostics.py`).
- Current scope is deterministic frontend-to-IR; no learning/plasticity semantics introduced by DSL layer (`docs/nema_dsl_v0.1.md`).

## IR summary (key fields + invariants MUST/SHOULD)
- Normative files: `spec.md`, `nema_ir.proto`.
- Key IR objects: `constraints`, `license`, `graph`, `tanhLut`, optional `compile.schedule`.
- MUST invariants enforced by validator (`nema/ir_validate.py`):
  - unique node IDs and indices; unique edge IDs; canonicalOrderId present
  - edges reference existing nodes
  - CHEMICAL directed; GAP symmetric mirror for directed representation
  - non-negative conductance
  - license.spdxId in constraints.allowedSpdx
  - external artifact exists and sha256 matches when non-placeholder
  - delayTicks <= compile.schedule.delayMax (and delayMax bounded)

## hwtest pipeline summary
- Entry: `nema/hwtest.py::run_hwtest_pipeline`.
- Always runs: IR validation + graph resolution + golden sim + C++ reference + digest comparison.
- If toolchain available/policy allows: runs Vitis HLS stages (csim/csynth, optional cosim) and parses reports/QoR.
- If Vivado available: runs batch implementation, parses utilization/timing and writes into bench report.
- Outputs include:
  - `build*/<modelId>/bench_report.json`
  - `build*/<modelId>/golden/{trace.jsonl,digest.json}`
  - `build*/<modelId>/cpp_ref/*`
  - `build*/<modelId>/hw_reports/**/*.(rpt|xml|log)` when HW flow runs

Bench report schema is validated during hwtest (`tools/bench_report_schema.json`).
