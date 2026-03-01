# Artix-7 Execution (Boardless, Reproducible)

## Contract target

- FPGA part: `xc7a200t-1sbg484c`
- This document is boardless only.
- No claim in this flow is `MEASURED_ON_BOARD`.

## Canonical scripts

- HLS parity attempt: `tools/amd_hls_g1b_attempt.py`
- Vivado implementation attempt: `tools/amd_vivado_g1c_attempt.py`
- Power estimation attempt: `tools/amd_power_g1d_attempt.py`

## Execution sequence

```bash
python tools/amd_hls_g1b_attempt.py
python tools/amd_vivado_g1c_attempt.py
python tools/amd_power_g1d_attempt.py
```

## Produced artifacts

- HLS:
  - `build/amd_hls/summary.json`
  - `build/amd_hls/<bench>/csim.log`
  - `build/amd_hls/<bench>/csynth.log`
  - `build/amd_hls/<bench>/cosim.log`
  - `build/amd_hls/<bench>/digest_compare.json`
- Vivado:
  - `build/amd_vivado/summary.json`
  - `build/amd_vivado/part_probe.json`
  - `build/amd_vivado/logs/*`
- Power (estimated):
  - `build/amd_power/summary.json`
  - `build/amd_power/<bench>/power_vectorless.rpt`
  - `build/amd_power/<bench>/power_saif.rpt` (when SAIF available)
  - `build/amd_power/<bench>/read_saif.log`
- Review tables:
  - `review_pack/tables/artix7_hls_digest_summary.csv`
  - `review_pack/tables/artix7_qor.csv`
  - `review_pack/tables/artix7_power.csv`

## Interpretation rules

1. If `build/amd_vivado/summary.json` reports `requested_part_unavailable:xc7a200t-1sbg484c`, G1c remains OPEN.
2. If B3 varshney benchmark is executed via alias assets, treat G1b as partial evidence, not full benchmark-identity closure.
3. Power outputs are estimation-only (`ESTIMATED_*`) until board protocol artifacts exist.

## Current known blockers

- Artix-7 part availability on this host (Vivado part probe).
- Canonical, non-aliased assets for `b3_varshney_exec_expanded_gap_279_7284`.
- SAIF-guided power flow availability for required B3 benchmark path.
