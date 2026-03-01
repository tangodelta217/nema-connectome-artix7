#!/usr/bin/env python3
"""Extract QoR dataset CSV from bench_report.json files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nema.qor_model import CSV_COLUMNS, discover_bench_reports, extract_rows_from_paths, write_dataset_csv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qor_dataset.py", description="Build QoR CSV from bench reports")
    parser.add_argument(
        "--root",
        action="append",
        type=Path,
        required=True,
        help="Root directory to scan for bench_report.json (repeatable)",
    )
    parser.add_argument(
        "--glob",
        default="**/bench_report.json",
        help="Glob pattern under each root (default: **/bench_report.json)",
    )
    parser.add_argument("--out", type=Path, required=True, help="Output CSV path")
    args = parser.parse_args(argv)

    roots = [path if path.is_absolute() else (REPO_ROOT / path).resolve() for path in args.root]
    report_paths = discover_bench_reports(roots, glob_pattern=args.glob)
    rows, errors = extract_rows_from_paths(report_paths)
    write_dataset_csv(rows, args.out if args.out.is_absolute() else (REPO_ROOT / args.out))

    payload = {
        "ok": True,
        "roots": [str(path) for path in roots],
        "glob": args.glob,
        "reportsFound": len(report_paths),
        "rowsWritten": len(rows),
        "columns": list(CSV_COLUMNS),
        "errors": errors,
        "out": str(args.out),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
