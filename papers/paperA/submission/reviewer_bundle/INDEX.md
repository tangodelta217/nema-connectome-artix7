# Reviewer Bundle Index

This bundle is assembled to include all evidence paths referenced by Paper A and artifact scripts.

## Evidence Map

| Evidence | File |
|---|---|
| Final paper PDF | `paperA.pdf` |
| Artifact README | `papers/paperA/artifacts/ARTIFACT_README.md` |
| Artifact manifest | `papers/paperA/artifacts/artifact_manifest.json` |
| Software audit JSON | `papers/paperA/artifacts/evidence/audit_software.json` |
| Hardware audit JSON | `papers/paperA/artifacts/evidence/audit_hardware.json` |
| Gate summary tables | `papers/paperA/artifacts/tables/gates_summary.csv`, `papers/paperA/artifacts/tables/gates_summary.md` |
| Bit-exact result tables | `papers/paperA/artifacts/tables/results_bitexact.csv`, `papers/paperA/artifacts/tables/results_bitexact.tex` |
| QoR result tables | `papers/paperA/artifacts/tables/results_qor.csv`, `papers/paperA/artifacts/tables/results_qor.tex` |
| Figure (pipeline + gates) | `papers/paperA/artifacts/figures/fig_pipeline_gates.png` |
| Legacy status snapshot artifact | `papers/paperA/artifacts/figures/gates_status.txt` |
| Normative spec | `spec.md` |
| Artifact regeneration scripts | `papers/paperA/artifacts/scripts/` |
| Bench manifests used in paper | `benches/B1_small/manifest.json`, `benches/B2_mid/manifest.json`, `benches/B3_kernel_302_7500/manifest.json`, `benches/B4_real_connectome/manifest.json`, `benches/B6_delay_small/manifest.json` |
| Review traceability | `papers/paperA/reviews/review_round1.md`, `papers/paperA/reviews/patchlist_round1.md`, `papers/paperA/reviews/REVIEW_RESOLUTION.md` |

## Included Bench Reports (B1/B2/B3/B4/B6)

- B1: `build/audit_min/bench_verify/b1/example_b1_small_subgraph/bench_report.json` (ok=True, digestMatchOk=True, ticks=20, irSha256=31b5a208c287eaec92e2e39f4f19442a7c080a2ff000c0f667cd984b7e1e8286)
- B2: `build/audit_min/bench_verify/b2/B2_mid_64_1024/bench_report.json` (ok=True, digestMatchOk=True, ticks=20, irSha256=61d1c9b1b97d3d8509c59349445472ed8cf76bf0205e560a1cacffd21509e98b)
- B3: `build/audit_min/bench_verify/b3/B3_kernel_302_7500/bench_report.json` (ok=True, digestMatchOk=True, ticks=20, irSha256=05ce6de59b1518129c3d690c5fca81e507dd8c109193fd83b2ae1301e8447080)
- B4: `build/bench_verify_eqlozbf7/B4_celegans_external_bundle/bench_report.json` (ok=True, digestMatchOk=True, ticks=2, irSha256=5b21d1db4975db16c02802eaba409f4ac194535880a15b215f7bd02d01071473)
- B6: `build_hw/b6/B6_delay_small/bench_report.json` (ok=True, digestMatchOk=True, ticks=2, irSha256=ab9f80fb981df0f73b1bcd925a962c71feece6fb4d0f731479024997be935c34)

## Reproduction Commands (from repo root)

1. `python tools/audit_min.py --mode software > papers/paperA/artifacts/evidence/audit_software.json`
2. `python tools/audit_min.py --mode hardware > papers/paperA/artifacts/evidence/audit_hardware.json`
3. `python papers/paperA/artifacts/scripts/make_table_bitexact.py`
4. `python papers/paperA/artifacts/scripts/make_table_qor.py`
5. `make -C papers/paperA paper`

## Notes

- Paths in this bundle preserve the same relative structure used in the paper text.
- If hardware toolchain is unavailable, hardware audit/generation may not reproduce GO in another environment.
