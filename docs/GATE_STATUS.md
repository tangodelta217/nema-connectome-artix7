# Gate Status (Canonical)

This file is generated from `release/FINAL_STATUS.json`.
Do not edit manually. Regenerate with `python tools/sync_status_docs.py`.

## Canonical Source

- File: `release/FINAL_STATUS.json`
- Canonical generated-at: `2026-03-02T19:31:22+00:00`
- Synced-at (UTC): `2026-03-02T19:32:24+00:00`
- Target part: `xc7a200tsbg484-1`

## Gate Summary

| Gate | Status |
|---|---|
| G1b | `CLOSED` |
| G1c | `CLOSED` |
| G1d | `CLOSED` |

## Canonical Gate Snapshot

```json
{
  "G1b": "CLOSED",
  "G1c": "CLOSED",
  "G1d": "CLOSED"
}
```

## Evidence Anchors

- `b3CanonicalStatus`: `build/handoff/B3_CANONICAL_STATUS.json`
- `gateStatusDoc`: `docs/GATE_STATUS.md`
- `metricsCsv`: `review_pack/tables/artix7_metrics_final.csv`
- `metricsTex`: `review_pack/tables/artix7_metrics_final.tex`
- `postRouteTimingReports`: `build/amd_vivado_artix7_v5/b1_small/post_route_timing.rpt`, `build/amd_vivado_artix7_v5/b3_varshney_exec_expanded_gap_300_5824/post_route_timing.rpt`
- `postRouteUtilReports`: `build/amd_vivado_artix7_v5/b1_small/post_route_utilization.rpt`, `build/amd_vivado_artix7_v5/b3_varshney_exec_expanded_gap_300_5824/post_route_utilization.rpt`
- `powerCsv`: `review_pack/tables/artix7_power_v7_funcsaif.csv`
- `powerMethodologyDoc`: `docs/POWER_METHODOLOGY.md`
- `powerSaifFunctionalReports`: `build/amd_power_artix7_v7_funcsaif/b1_small/power_saif_func.rpt`, `build/amd_power_artix7_v7_funcsaif/b3_varshney_exec_expanded_gap_300_5824/power_saif_func.rpt`
- `powerSummary`: `build/amd_power_artix7_v7_funcsaif/summary.json`
- `powerTex`: `review_pack/tables/artix7_power_v7_funcsaif.tex`
- `qorCsv`: `review_pack/tables/artix7_qor_v6.csv`
- `saifFunctional`: `build/amd_power_artix7_v7_funcsaif/b1_small/activity_func.saif`, `build/amd_power_artix7_v7_funcsaif/b3_varshney_exec_expanded_gap_300_5824/activity_func.saif`
- `vivadoSummary`: `build/amd_vivado_artix7_v5/summary.json`

## Limits

- No board measurement is claimed.
- Power/energy remain ESTIMATED_PRE_BOARD_ONLY.
- SAIF activity uses functional xsim harness (/tb_tick/dut/*) and is not board traffic.
