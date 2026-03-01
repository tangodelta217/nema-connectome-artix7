# Reproduce Round9 Final Release

## Preconditions

- Vivado 2025.2 and Vitis HLS 2025.2 available in PATH.
- Existing Round8/Round9 evidence directories present under `build/`.

## One-command verification (integrity)

```bash
sha256sum -c release/SHA256SUMS.txt
```

## Reference artifacts

- Gate status: `docs/GATE_STATUS.md`
- Power methodology: `docs/POWER_METHODOLOGY.md`
- Reviewer guide: `release/REVIEWER_GUIDE.md`

