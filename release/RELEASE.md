# Release Packaging Guide

## What Goes to GitHub Release Assets

Publish binary-heavy or generated evidence as release assets (not git history), for example:

- `artifact_bundle_final.tar.gz` (evidence bundle)
- hardware/cosim logs and large generated reports
- large simulation dumps (`.wdb`, `.vcd`, `.saif`) when needed for review

Keep small, reviewable metadata in git:

- `release/SHA256SUMS.txt`
- `release/DATASET_SHA256.txt`
- `release/FINAL_STATUS.json`
- `release/FINAL_STATUS.md`
- `release/EXTERNAL_ASSETS_SHA256SUMS.txt`
- benchmark manifests/tables in JSON/CSV

## Verify SHA256SUMS

Before running `sha256sum -c`, make sure large generated artifacts referenced by
`release/SHA256SUMS.txt` are present locally (for example by downloading/extracting
the evidence bundle from GitHub Releases).

```bash
sha256sum -c release/SHA256SUMS.txt
python tools/check_release_integrity.py
```

If release assets are hosted externally, fetch them first:

```bash
python tools/fetch_release_assets.py --tag v0.1.0
python tools/fetch_release_assets.py --tag v0.1.0 --check
```

To hash a new bundle before publishing:

```bash
sha256sum release/artifact_bundle_final.tar.gz
```

Append the output to `release/SHA256SUMS.txt` and verify again.

## Source vs Evidence Bundle

- **Source**: repository code, scripts, specs, docs, manifests, and small tables needed to reproduce runs.
- **Evidence bundle**: generated outputs from expensive runs (tool logs, reports, traces, packaged artifacts) published as GitHub Release assets.

This separation keeps clone size manageable while preserving reproducibility.

## External Asset Retrieval

For large generated Paper A artifacts stored as release assets:

```bash
python tools/fetch_release_assets.py --tag v0.1.0
python tools/fetch_release_assets.py --tag v0.1.0 --check
```

Reference list: `release/EXTERNAL_ASSETS.md`.
