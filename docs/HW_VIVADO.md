# NEMA HW Vivado Batch QoR (G3 Optional)

This document describes the optional G3 flow that runs Vivado in batch mode over
RTL exported by Vitis HLS and captures utilization/timing metrics.

## What `nema hwtest` does
When `vitis_hls` is available, `python -m nema hwtest ...` now:

1. Runs Vitis HLS (`csim_design`, `csynth_design`).
2. Exports RTL (`export_design -rtl verilog`).
3. If `vivado` is available, runs a Vivado batch synthesis pass:
   - `synth_design`
   - `report_utilization`
   - `report_timing_summary`
4. Copies HLS/Vivado reports into `build/<modelId>/hw_reports/`.
5. Emits Vivado QoR into `bench_report.json` under:
   - `hardware.vivado.utilization`
   - `hardware.vivado.timing`

G3 is optional: software/hardware gates are unchanged unless you explicitly use
`audit_min --mode vivado`.

## Artifacts
- HLS project: `build/<modelId>/hls_proj/`
- Copied reports: `build/<modelId>/hw_reports/`
- Bench report: `build/<modelId>/bench_report.json`

## Audit mode for G3
Run:

```bash
python tools/audit_min.py --mode vivado
```

`GO` requires:
- toolchain available,
- G0b evidence (HLS ran with `csim.ok`),
- Vivado evidence (`hardware.vivado.ok == true` and utilization/timing parsed).

