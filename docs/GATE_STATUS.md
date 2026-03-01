# Gate Status (Evidence-Aligned)

Last reconciled: 2026-03-01T14:17:55.860093+00:00

## Current status

| Gate | Status | Evidence | Notes |
|---|---|---|---|
| G1b (AMD HLS digest parity) | `CLOSED` | `build/amd_hls_strict_v2/summary.json`, `review_pack/tables/artix7_hls_digest_summary_strict_v2.csv`, `artifacts/traces/*.amd_{csim,cosim}.trace.jsonl` | Strict v2 canonical run closes digest parity for B1 and canonical B3. |
| G1c (Vivado synth+impl on Artix-7) | `CLOSED` | `build/amd_vivado_artix7_v5/summary.json`, `build/amd_vivado_artix7_v5/*/post_route_utilization.rpt`, `build/amd_vivado_artix7_v5/*/post_route_timing.rpt`, `review_pack/tables/artix7_qor_v6.csv` | Both required benches (`b1_small`, `b3_varshney_exec_expanded_gap_300_5824`) have Artix-7 post-route evidence. |
| G1d (post-implementation power with activity) | `CLOSED` | `build/amd_power_artix7_v6/summary.json`, `build/amd_power_artix7_v6/*/activity_100us.saif`, `build/amd_power_artix7_v6/*/read_saif_100us.log`, `build/amd_power_artix7_v6/*/power_saif_100us.rpt`, `review_pack/tables/artix7_power_v6.csv` | SAIF 100us + read_saif PASS + power_saif present for B1 and B3. |

## Hard boundaries

- All power evidence is `ESTIMATED_PRE_BOARD_ONLY`.
- No claim in this repo state is `MEASURED_ON_BOARD`.
- QoR parser refresh in Round9 used existing reports only (no synth/impl rerun).

## Round9 artifacts

- QoR summary refreshed in place: `build/amd_vivado_artix7_v5/summary.json`
- QoR table: `review_pack/tables/artix7_qor_v6.csv`
- Power summary: `build/amd_power_artix7_v6/summary.json`
- Power table: `review_pack/tables/artix7_power_v6.csv`
- Derived metrics: `review_pack/tables/artix7_metrics_v1.csv`
