# Final Status (Canonical)

- Git HEAD: `bb17ac319debc7ee40a28f4502fe4189f0795ac5`
- Dirty worktree: `True`
- Target part: `xc7a200t-1sbg484c`

## Gate summary

- `G1b`: OPEN. B3 benchmark identity is aliased to B3 baseline assets; canonical varshney identity not demonstrated.
- `G1c`: OPEN. Vivado implementation skipped for requested part: requested_part_unavailable:xc7a200t-1sbg484c.
- `G1d`: OPEN. Power evidence is estimated pre-board only; SAIF coverage incomplete for required B3 benchmark identity.

## Evidence anchors

- HLS digest parity: `build/amd_hls/summary.json`, `review_pack/tables/artix7_hls_digest_summary.csv`
- Vivado implementation status: `build/amd_vivado/summary.json`, `review_pack/tables/artix7_qor.csv`
- Power estimation status: `build/amd_power/summary.json`, `review_pack/tables/artix7_power.csv`
- Contract docs: `docs/GATE_STATUS.md`, `docs/CLAIMS.md`, `docs/ARTIX7_EXECUTION.md`, `docs/POWER_METHODOLOGY.md`
- Snapshot paper: `paper/paper.pdf` (source `paper/paper.tex`)

## Critical open risks

- Artix-7 part unavailable on current host Vivado install, blocking G1c closure.
- B3 varshney benchmark identity remains aliased, blocking strict G1b closure for required benchmark identity.
- G1d remains estimation-only; no board measurement and incomplete SAIF coverage for required B3 identity.

## Principal hashes

- `build/codex_handoff/PRIMARY_HASHES.sha256`
