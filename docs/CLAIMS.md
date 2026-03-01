# Claims Ledger (Evidence-Backed)

This file records only claims that are directly backed by artifacts currently present in the repository.

## Claims we can make now

1. **Deterministic digest parity through AMD HLS exists for executed boardless runs.**
   - Evidence: `build/amd_hls/summary.json`
   - Table: `review_pack/tables/artix7_hls_digest_summary.csv`
   - Traces: `artifacts/traces/*.amd_csim.trace.jsonl`, `artifacts/traces/*.amd_cosim.trace.jsonl`
   - Scope caveat: B3 row is currently benchmark-identity aliased (`b3_varshney_exec_expanded_gap_279_7284` executed via baseline B3 assets).

2. **Vivado implementation closure for Artix-7 is not achieved on this host.**
   - Evidence: `build/amd_vivado/summary.json`, `build/amd_vivado/part_probe.json`
   - Table: `review_pack/tables/artix7_qor.csv`
   - Reason: requested part `xc7a200t-1sbg484c` unavailable, implementation runs skipped.

3. **Power numbers are pre-board estimates, not measurements.**
   - Evidence: `build/amd_power/summary.json`
   - Table: `review_pack/tables/artix7_power.csv`
   - Artifacts: `build/amd_power/*/power_vectorless.rpt`, `build/amd_power/*/power_saif.rpt`, `build/amd_power/*/read_saif.log`

## Claims we cannot make yet

1. **Cannot claim G1c closed** for Artix-7 (`xc7a200t-1sbg484c`) until mandatory benchmarks have real post-route reports (WNS/TNS/utilization) for that part.
2. **Cannot claim G1d closed** until activity-guided post-implementation power evidence is complete for required benchmarks under the same Artix-7 part policy.
3. **Cannot claim board measurement** (power/latency on physical board). No `MEASURED_ON_BOARD` evidence is present.
4. **Cannot claim canonical B3 varshney identity closure** while run assets remain aliased.

## Required disclaimer language

- Use “estimated”, “pre-board”, or `ESTIMATED_*` for all power/timing derived values in this state.
- Do not state or imply physical-board validation.
- Do not mix non-Artix runs with Artix-7 closure claims.
