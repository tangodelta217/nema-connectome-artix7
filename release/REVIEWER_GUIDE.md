# Reviewer Guide (Final)

## One command (integrity check)

```bash
sha256sum -c release/SHA256SUMS.txt
```

## Where to look

- Gate closure rationale: `docs/GATE_STATUS.md`
- Power assumptions/limits: `docs/POWER_METHODOLOGY.md`
- HLS digest evidence (Table 1): `review_pack/tables/artix7_hls_digest_summary_strict_v2.csv`
- QoR evidence (Table 2): `review_pack/tables/artix7_qor_v6.csv`
- Power evidence (Table 3): `review_pack/tables/artix7_power_v7_funcsaif.csv`
- Derived throughput/energy (Table 4): `review_pack/tables/artix7_metrics_final.csv`
- Vivado raw reports: `build/amd_vivado_artix7_v5/*/post_route_{timing,utilization}.rpt`
- SAIF raw reports: `build/amd_power_artix7_v7_funcsaif/*/activity_func.saif` and `power_saif_func.rpt`
- Canonical B3 identity: `build/handoff/B3_CANONICAL_STATUS.json`
- Release manifest: `release/FINAL_STATUS.json`

- no AI-agent artifacts included
