# External Release Assets (Binary/Generated)

Large generated artifacts are published as GitHub Release assets (tag `v0.1.0`) instead of being tracked in git history.

Base URL:

`https://github.com/tangodelta217/nema-connectome-artix7/releases/download/v0.1.0/`

Assets covered by checksums in `release/EXTERNAL_ASSETS_SHA256SUMS.txt`:

- `nema_audit_bundle.tar.gz`
- `paperA_review_pack.pdf`
- `paperA_submission.pdf`
- `paperA_submission_bundle.tar.gz`
- `paperA_reviewer_bundle.pdf`
- `paperA_reviewer_bundle.tar.gz`
- `paperA_submission_bundle_boardless.tar.gz`
- `paperA_text_build.pdf`

Download + verify:

```bash
python tools/fetch_release_assets.py --tag v0.1.0
python tools/fetch_release_assets.py --tag v0.1.0 --check
```
