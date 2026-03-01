# Board Measurement Protocol (Normalized Path)

Status: normalized from existing canonical source in this repository.

Canonical source(s):
- `docs/FPGA_MEASUREMENT.md`
- `tools/fpga_measure/schema_power_latency_report.json`

## Contract boundary

- Real board measurement evidence requires `build_hw/fpga_measure/power_latency_report.json`.
- The JSON field `method` MUST be `"MEASURED_ON_BOARD"`.
- Estimated reports (HLS/Vivado/tool reports) MUST NOT be presented as board measurements.

## Execution source of truth

Use `docs/FPGA_MEASUREMENT.md` for full procedure:
- bitstream build
- board programming
- latency measurement methods
- power measurement methods
- required JSON schema fields

## Provenance

This file is a path-normalization adapter requested by contract prompts.
No new semantics were introduced here.
