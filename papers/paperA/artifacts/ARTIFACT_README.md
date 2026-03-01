# Paper A Artifact Reproduction

## Prerequisites
- Python environment with project deps installed (`pip install -e .` + test deps).
- Repo root available with `tools/audit_min.py`.
- Optional for HW checks: `vivado` and `vitis_hls` in `PATH` (or wrapper setup already configured).

## One-Command Boardless Rebuild
From repo root:

```bash
bash tools/reproduce_paper_a.sh
```

This is the single reproducible boardless entrypoint for Paper A. It performs:
1. Safe cleanup of `build/paperA_*` and `papers/paperA/artifacts/tables/results_*.csv`.
2. `python -m pytest -q`.
3. `python tools/independent_check.py --paperA`.
4. Regeneration of Paper A tables/figure snapshots + `review_pack_v3`.
5. `make -C papers/paperA clean paper`.
6. SHA-256 emission for key outputs.

Generated logs and outputs:
- `build/reproduce_paper_a.log`
- `build/paperA_reproduce.sha256`
- `papers/paperA/text/paper.pdf`
- `papers/paperA/artifacts/review_pack_v3.md`
- `papers/paperA/artifacts/tables/results_bitexact.csv`
- `papers/paperA/artifacts/tables/results_qor.csv`
- `papers/paperA/artifacts/tables/results_throughput.csv`

Verify checksums:

```bash
sha256sum -c build/paperA_reproduce.sha256
```

## Regenerate Artifacts
From repo root:

```bash
make -C papers/paperA artifacts
```

This executes:
- `papers/paperA/artifacts/scripts/regenerate_artifacts.sh`
- `python tools/audit_min.py --mode software`
- `python tools/audit_min.py --mode hardware`
- `papers/paperA/artifacts/scripts/build_tables.py`
- `papers/paperA/artifacts/scripts/make_table_bitexact.py`
- `papers/paperA/artifacts/scripts/make_table_qor.py`

## Recompute Checks
From repo root:

```bash
make -C papers/paperA check
```

`check` runs:
1. `python -m pytest -q`
2. `python tools/audit_min.py --mode software`
3. `python tools/audit_min.py --mode hardware`
4. artifact regeneration
5. artifact validation script

## Expected Outputs
- Evidence JSON:
  - `papers/paperA/artifacts/evidence/audit_software.json`
  - `papers/paperA/artifacts/evidence/audit_hardware.json`
- Tables:
  - `papers/paperA/artifacts/tables/gates_summary.csv`
  - `papers/paperA/artifacts/tables/gates_summary.md`
  - `papers/paperA/artifacts/tables/results_bitexact.csv`
  - `papers/paperA/artifacts/tables/results_bitexact.tex`
  - `papers/paperA/artifacts/tables/results_qor.csv`
  - `papers/paperA/artifacts/tables/results_qor.tex`
- Figures (text artifact source):
  - `papers/paperA/artifacts/figures/gates_status.txt`

## Paper Result Tables
From repo root:

```bash
python papers/paperA/artifacts/scripts/make_table_bitexact.py
python papers/paperA/artifacts/scripts/make_table_qor.py
```

## Paper Build
From repo root:

```bash
make -C papers/paperA paper
```

If `latexmk` is unavailable, the target prints exact manual compile instructions.
