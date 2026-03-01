# FPGA Measurement (Power + Latency)

This document defines the reproducible process for real on-board measurements.

## Scope

The milestone for real FPGA measurements is satisfied only by a measured artifact:

- `build_hw/fpga_measure/power_latency_report.json`
- `method` must be `"MEASURED_ON_BOARD"`

Estimated HLS/Vivado reports are not accepted as real measurement evidence.

## Prerequisites

- Supported FPGA board connected and powered.
- Programming/debug cable connected.
- Linux permissions for cable drivers configured.
- Vivado available in PATH (`vivado -version`).
- Bitstream already built for the target benchmark/part.

## Generate Bitstream

Use the existing flow with bitstream enabled. Example:

```bash
python -m nema hwtest example_b1_small_subgraph.json --outdir build_hw/b1 --ticks 2 --hw require --write-bitstream
```

Alternative helper:

```bash
python -m nema vivado bitstream example_b1_small_subgraph.json --outdir build_hw/b1 --ticks 2
```

## Program Board

Use the deploy helper:

```bash
bash tools/fpga/deploy_bitstream.sh --bit build_hw/<modelId>/hw_reports/<name>.bit
```

## Latency Measurement

Use both methods when possible and document both:

1. Internal counter method (preferred): hardware cycle counter around kernel start/end.
2. Host timestamp method: host-side start/end timestamps with enough samples.

Write raw latency samples to CSV and aggregate to p50/p95/max.

## Power Measurement

Preferred order:

1. Board sensors/PMBus/INA monitors if available.
2. External power meter in the board supply path.

Record sample frequency, units, and measurement window. Keep raw CSV files.

## Final Artifact

Produce:

- `build_hw/fpga_measure/power_latency_report.json`

Required fields:

- `method`: `"MEASURED_ON_BOARD"`
- `board`: non-empty string
- `part`: string
- `bitstreamSha256`: string
- `latency`: object with `unit`, `samples`, `p50`, `p95`, `max`
- `power`: object with `unit`, `samples`, `avg`, `max`
- `rawFiles`: list of raw CSV paths (if present)

Validate against:

- `tools/fpga_measure/schema_power_latency_report.json`

