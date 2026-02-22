"""CLI entrypoint for NEMA scaffold commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .toolchain import check_ir, run_compile, run_hwtest, run_sim


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nema", description="NEMA v0.1 scaffold CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_cmd = subparsers.add_parser("check", help="validate IR JSON against invariants")
    check_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")

    sim_cmd = subparsers.add_parser("sim", help="run golden simulation placeholder")
    sim_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    sim_cmd.add_argument("--ticks", type=int, required=True, help="number of ticks")
    sim_cmd.add_argument("--out", type=Path, required=True, help="trace JSONL output path")

    compile_cmd = subparsers.add_parser("compile", help="generate HLS C++ placeholder")
    compile_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    compile_cmd.add_argument("--outdir", type=Path, default=Path("build"), help="output directory")

    hwtest_cmd = subparsers.add_parser(
        "hwtest",
        help="run sim + optional Vitis HLS detection and emit bench_report.json",
    )
    hwtest_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    hwtest_cmd.add_argument("--outdir", type=Path, default=Path("build"), help="output directory")
    hwtest_cmd.add_argument("--ticks", type=int, default=8, help="number of ticks for sim stage")

    return parser


def _emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        code, report = check_ir(args.ir_json)
        _emit(report)
        return code

    if args.command == "sim":
        code, report = run_sim(args.ir_json, ticks=args.ticks, out_path=args.out)
        _emit(report)
        return code

    if args.command == "compile":
        code, report = run_compile(args.ir_json, outdir=args.outdir)
        _emit(report)
        return code

    if args.command == "hwtest":
        code, report = run_hwtest(args.ir_json, outdir=args.outdir, ticks=args.ticks)
        _emit(report)
        return code

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
