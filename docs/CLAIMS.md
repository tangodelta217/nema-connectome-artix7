# Claims Ledger (Canonical)

This file is generated from `release/FINAL_STATUS.json`.
Do not edit manually. Regenerate with `python tools/sync_status_docs.py`.

## Canonical Source

- File: `release/FINAL_STATUS.json`
- Synced-at (UTC): `2026-03-02T20:56:50+00:00`

## Canonical Gate Snapshot

```json
{
  "G1b": "CLOSED",
  "G1c": "CLOSED",
  "G1d": "CLOSED"
}
```

## Claims We Can Make

- Gate `G1b` is `CLOSED` for target part `xc7a200tsbg484-1`.
- Gate `G1c` is `CLOSED` for target part `xc7a200tsbg484-1`.
- Gate `G1d` is `CLOSED` for target part `xc7a200tsbg484-1`.
- Power and energy are `ESTIMATED_PRE_BOARD_ONLY`.
- No board measurement is claimed in this release state.

## Claims We Cannot Make

- Cannot claim measured-on-board power, energy, or latency.
- Boundary: No board measurement is claimed.
- Boundary: Power/energy remain ESTIMATED_PRE_BOARD_ONLY.
- Boundary: SAIF activity uses functional xsim harness (/tb_tick/dut/*) and is not board traffic.
