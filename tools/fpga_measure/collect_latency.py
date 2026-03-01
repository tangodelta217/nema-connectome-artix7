#!/usr/bin/env python3
"""Placeholder on-board latency collector."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="collect_latency.py",
        description="Collect latency samples from a programmed FPGA board (placeholder).",
    )
    parser.add_argument("--out", type=Path, required=True, help="Output CSV path for raw latency samples")
    args = parser.parse_args(argv)

    hw_manager_present = shutil.which("vivado") is not None
    message = (
        "collect_latency.py is a placeholder and requires real FPGA instrumentation.\n"
        "No on-board measurement was executed. This command intentionally fails until "
        "board-specific acquisition is implemented."
    )
    hint = (
        "Program bitstream first, then implement board counter/host timestamp capture in this script.\n"
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

