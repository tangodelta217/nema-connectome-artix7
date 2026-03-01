#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _row(mode: str, payload: dict) -> dict[str, str]:
    return {
        "mode": mode,
        "ok": str(bool(payload.get("ok"))).lower(),
        "decision": str(payload.get("decision", "")),
        "toolchainHwAvailable": str(payload.get("toolchainHwAvailable", "")),
        "software_ok": str(payload.get("software_ok", "")),
        "hardware_ok": str(payload.get("hardware_ok", "")),
        "all_ok": str(payload.get("all_ok", "")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Paper A gate summary tables from audit outputs.")
    parser.add_argument("--software", type=Path, required=True)
    parser.add_argument("--hardware", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--md", type=Path, required=True)
    parser.add_argument("--figure", type=Path, required=True)
    args = parser.parse_args()

    sw = _load(args.software)
    hw = _load(args.hardware)

    rows = [_row("software", sw), _row("hardware", hw)]
    fieldnames = list(rows[0].keys())

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    args.md.parent.mkdir(parents=True, exist_ok=True)
    with args.md.open("w", encoding="utf-8") as handle:
        handle.write("| mode | ok | decision | toolchainHwAvailable | software_ok | hardware_ok | all_ok |\n")
        handle.write("|---|---|---|---|---|---|---|\n")
        for row in rows:
            handle.write(
                f"| {row['mode']} | {row['ok']} | {row['decision']} | {row['toolchainHwAvailable']} "
                f"| {row['software_ok']} | {row['hardware_ok']} | {row['all_ok']} |\n"
            )

    args.figure.parent.mkdir(parents=True, exist_ok=True)
    with args.figure.open("w", encoding="utf-8") as handle:
        handle.write("Gate status snapshot\n")
        handle.write("====================\n")
        for row in rows:
            handle.write(f"{row['mode']}: decision={row['decision']} ok={row['ok']}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
