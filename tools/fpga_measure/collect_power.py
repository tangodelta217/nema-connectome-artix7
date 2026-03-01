#!/usr/bin/env python3
"""Placeholder on-board power collector."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="collect_power.py",
        description="Collect power samples from FPGA board sensors/power meter (placeholder).",
    )
    parser.add_argument("--out", type=Path, required=True, help="Output CSV path for raw power samples")
    args = parser.parse_args(argv)

    hw_manager_present = shutil.which("vivado") is not None
    message = (
        "collect_power.py is a placeholder and requires real measurement hardware.\n"
        "No board sensor or external power meter was queried. This command intentionally fails "
        "until lab-specific acquisition is implemented."
    )
    hint = (
        "Implement PMBus/INA/power-meter reader in this script and write raw CSV to --out.\n"
        f"Requested output path: {args.out}"
    )
    payload = {
        "ok": False,
        "reason": "HW_NOT_AVAILABLE_OR_NOT_IMPLEMENTED",
        "vivadoFound": hw_manager_present,
        "message": message,
        "hint": hint,
    }
    sys.stderr.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

