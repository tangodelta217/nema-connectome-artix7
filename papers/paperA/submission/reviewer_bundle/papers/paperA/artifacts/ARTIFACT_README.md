# Paper A Artifact Reproduction

## Prerequisites
- Python environment with project deps installed (`pip install -e .` + test deps).
- Repo root available with `tools/audit_min.py`.
- Optional for HW checks: `vivado` and `vitis_hls` in `PATH` (or wrapper setup already configured).

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
