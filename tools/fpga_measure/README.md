# FPGA Measurement Harness (On-Board)

This folder contains the measurement harness placeholders and schema for real board evidence.

## Purpose

- Define a strict artifact for real measurements:
  - `build_hw/fpga_measure/power_latency_report.json`
- Prevent confusion between estimated reports and measured-on-board data.

## Commands

Latency collector placeholder:

```bash
python tools/fpga_measure/collect_latency.py --out build_hw/fpga_measure/latency_raw.csv
```

Power collector placeholder:

```bash
python tools/fpga_measure/collect_power.py --out build_hw/fpga_measure/power_raw.csv
```

Both scripts fail with a clear message unless real HW integration is implemented.

## Final Report Schema

- `tools/fpga_measure/schema_power_latency_report.json`

Use the schema to validate `power_latency_report.json` produced in lab runs.

