# Gate Status (Canonical)

This file is generated from `release/FINAL_STATUS.json`.
Do not edit manually. Regenerate with `python tools/sync_status_docs.py`.

## Canonical Source

- File: `release/FINAL_STATUS.json`
- Canonical generated-at: `2026-03-01T14:33:57.632936+00:00`
- Synced-at (UTC): `2026-03-02T11:28:31+00:00`
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

- `b3CanonicalStatus`: `build/codex_handoff/B3_CANONICAL_STATUS.json`
- `gateStatusDoc`: `docs/GATE_STATUS.md`
- `metricsCsv`: `review_pack/tables/artix7_metrics_v1.csv`
- `postRouteTimingReports`: `build/amd_vivado_artix7_v5/b1_small/post_route_timing.rpt`, `build/amd_vivado_artix7_v5/b3_varshney_exec_expanded_gap_300_5824/post_route_timing.rpt`
- `postRouteUtilReports`: `build/amd_vivado_artix7_v5/b1_small/post_route_utilization.rpt`, `build/amd_vivado_artix7_v5/b3_varshney_exec_expanded_gap_300_5824/post_route_utilization.rpt`
- `powerCsv`: `review_pack/tables/artix7_power_v6.csv`
- `powerMethodologyDoc`: `docs/POWER_METHODOLOGY.md`
- `powerSaif100usReports`: `build/amd_power_artix7_v6/b1_small/power_saif_100us.rpt`, `build/amd_power_artix7_v6/b3_varshney_exec_expanded_gap_300_5824/power_saif_100us.rpt`
- `powerSummary`: `build/amd_power_artix7_v6/summary.json`
- `qorCsv`: `review_pack/tables/artix7_qor_v6.csv`
- `saif100us`: `build/amd_power_artix7_v6/b1_small/activity_100us.saif`, `build/amd_power_artix7_v6/b3_varshney_exec_expanded_gap_300_5824/activity_100us.saif`
- `vivadoSummary`: `build/amd_vivado_artix7_v5/summary.json`

## Limits

- No board measurement is claimed.
- Power/energy remain ESTIMATED_PRE_BOARD_ONLY.
- SAIF activity uses synthetic harness (clock-only) and is not board traffic.
