# Reviewer Guide (Final)

## One command (integrity check)

```bash
sha256sum -c release/SHA256SUMS.txt
```

## Where to look

- Gate closure rationale: `docs/GATE_STATUS.md`
- Power assumptions/limits: `docs/POWER_METHODOLOGY.md`
- QoR evidence (Round9 table): `review_pack/tables/artix7_qor_v6.csv`
- Power evidence (100us + 200ns): `review_pack/tables/artix7_power_v6.csv`
- Derived throughput/energy: `review_pack/tables/artix7_metrics_v1.csv`
- Vivado raw reports: `build/amd_vivado_artix7_v5/*/post_route_{timing,utilization}.rpt`
- SAIF raw reports: `build/amd_power_artix7_v6/*/activity_100us.saif` and `power_saif_100us.rpt`
- Canonical B3 identity: `build/codex_handoff/B3_CANONICAL_STATUS.json`
- Release manifest: `release/FINAL_STATUS.json`
