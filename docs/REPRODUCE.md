# Reproduce v0.1 (Evidence vs HW)

This document separates two workflows:

1. Evidence verification (hashes + paper table alignment), no HLS/Vivado rerun.
2. Hardware end-to-end rerun (HLS/Vivado), requiring Artix-7 device support.

Canonical release/profile in this repo: `v0.1.0` + `release/profiles/round10b_funcsaif/profile.json`.
Canonical paper source: `paper/paper.tex`.
Legacy/alternative paper tree (non-canonical): `papers/paperA/`.
Canonical handoff path naming: `build/handoff/`.

Benchmark identities used in this release:

- `B3_kernel_302_7500`: synthetic/kernel benchmark for quick regression and G0 closure.
- `B3_varshney_exec_expanded_gap_300_5824`: canonical structural benchmark used by the paper and evidence tables (G1 closure path).

## 1) Evidence Verification (No HW rerun)

```bash
sha256sum -c release/SHA256SUMS.txt
python tools/check_release_integrity.py
python tools/verify_paper_inputs.py

nema bench verify benches/B1_small/manifest.json --hw off
nema bench verify benches/B3_kernel_302_7500/manifest.json --hw off
nema bench verify benches/B3_varshney_exec_expanded_gap_300_5824/manifest.json --hw off
```

Reference docs:

- Gate status: `docs/GATE_STATUS.md`
- Power methodology: `docs/POWER_METHODOLOGY.md`
- Reviewer guide: `docs/REVIEWER_GUIDE.md` (release evidence index: `release/REVIEWER_GUIDE.md`)

## 2) HW End-to-End Reproduction (HLS/Vivado rerun)

### Prerequisites

- Vivado 2025.2 and Vitis HLS 2025.2 available in PATH.
- Device support for Artix-7 installed in Vivado.
- Target part available: `xc7a200tsbg484-1`.

### Preflight

```bash
bash tools/hw/preflight_ubuntu24.sh
bash tools/hw/check_part_available.sh xc7a200tsbg484-1
```

Strict target-part preflight:

```bash
NEMA_PREFLIGHT_ALLOW_PART_FALLBACK=0 bash tools/hw/preflight_ubuntu24.sh
```

### Core rerun commands

```bash
nema check example_b1_small_subgraph.json
nema hwtest example_b1_small_subgraph.json --ticks 32 --outdir build/b1
nema bench verify benches/B1_small/manifest.json --hw require --strict-part

nema check example_b3_kernel_302.json
nema hwtest example_b3_kernel_302.json --ticks 128 --outdir build/b3
nema bench verify benches/B3_kernel_302_7500/manifest.json --hw require --strict-part

# Canonical paper benchmark (structural B3 used in review_pack tables):
nema bench verify benches/B3_varshney_exec_expanded_gap_300_5824/manifest.json --hw require --strict-part
```

If `requested_part_unavailable` appears, install Artix-7 device support in Vivado and rerun:

```bash
bash tools/hw/check_part_available.sh xc7a200tsbg484-1
```

For host-only fallback reruns on a non-target installed part:

```bash
nema bench verify benches/B1_small/manifest.json --hw require
```
