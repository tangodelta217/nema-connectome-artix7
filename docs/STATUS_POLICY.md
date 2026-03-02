# Status Policy

## Canonical Source of Truth

- Canonical file: `release/FINAL_STATUS.json`
- Scope: gate closure (`G1b`, `G1c`, `G1d`), release limits, and evidence pointers.
- Rule: when any status document conflicts with this file, `release/FINAL_STATUS.json` wins.

## Derived Documents

The following files are generated from the canonical source and must not be edited manually:

- `docs/GATE_STATUS.md`
- `docs/CLAIMS.md`
- `FINAL_STATUS.json` (root mirror for convenience)
- `FINAL_STATUS.md` (root human-readable mirror)

## Generation Command

```bash
python tools/sync_status_docs.py
```

## CI/Local Consistency Check

```bash
python tools/sync_status_docs.py --check
```

If check mode fails, regenerate with the write command and commit the updated files.
