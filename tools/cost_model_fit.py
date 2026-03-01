#!/usr/bin/env python3
"""Fit baseline cost model against a QoR CSV dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nema.qor_model import fit_cost_model, load_dataset_csv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cost_model_fit.py", description="Fit baseline cost model from QoR CSV")
    parser.add_argument("--csv", type=Path, required=True, help="Input QoR CSV path")
    parser.add_argument(
        "--min-points",
        type=int,
        default=3,
        help="Minimum number of points with actual QoR required (default: 3)",
    )
    parser.add_argument(
        "--mean-rel-error-max",
        type=float,
        default=1.0,
        help="Mean relative error threshold (default: 1.0)",
    )
    parser.add_argument(
        "--split-by",
        choices=("none", "benchmark", "seed"),
        default="none",
        help="Cross-validation split key (default: none)",
    )
    parser.add_argument(
        "--test-fraction",
        type=float,
        default=0.34,
        help="Fraction of groups held out for test (default: 0.34)",
    )
    parser.add_argument(
        "--split-seed",
        type=int,
        default=0,
        help="Deterministic seed for group split ordering (default: 0)",
    )
    args = parser.parse_args(argv)

    if args.min_points < 3:
        parser.error("--min-points must be >= 3")
    if args.mean_rel_error_max <= 0:
        parser.error("--mean-rel-error-max must be > 0")
    if args.test_fraction <= 0.0 or args.test_fraction >= 1.0:
        parser.error("--test-fraction must be in (0,1)")

    csv_path = args.csv if args.csv.is_absolute() else (REPO_ROOT / args.csv)
    rows = load_dataset_csv(csv_path)
    fit = fit_cost_model(
        rows,
        min_points=args.min_points,
        mean_relative_error_max=float(args.mean_rel_error_max),
        split_by=args.split_by,
        test_fraction=float(args.test_fraction),
        split_seed=int(args.split_seed),
    )

    payload = {
        "ok": fit.get("ok") is True,
        "csvPath": str(args.csv),
        "fit": fit,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
