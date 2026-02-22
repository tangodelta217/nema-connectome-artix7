"""NEMA-DSL CLI scaffold (NYI)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def add_dsl_subparser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    dsl_cmd = subparsers.add_parser("dsl", help="NEMA-DSL v0.1 scaffold commands")
    dsl_subparsers = dsl_cmd.add_subparsers(dest="dsl_command", required=True)

    check_cmd = dsl_subparsers.add_parser("check", help="typecheck NEMA-DSL source (NYI)")
    check_cmd.add_argument("dsl_file", type=Path, help="path to .nema.dsl source")

    compile_cmd = dsl_subparsers.add_parser("compile", help="compile NEMA-DSL to IR JSON (NYI)")
    compile_cmd.add_argument("dsl_file", type=Path, help="path to .nema.dsl source")
    compile_cmd.add_argument("--out", type=Path, required=True, help="compiled IR JSON output path")

    hwtest_cmd = dsl_subparsers.add_parser("hwtest", help="compile and run hwtest pipeline (NYI)")
    hwtest_cmd.add_argument("dsl_file", type=Path, help="path to .nema.dsl source")
    hwtest_cmd.add_argument("--ticks", type=int, required=True, help="number of ticks")
    hwtest_cmd.add_argument("--outdir", type=Path, default=Path("build"), help="output directory")

    from_ir_cmd = dsl_subparsers.add_parser("from-ir", help="generate DSL skeleton from IR JSON (NYI)")
    from_ir_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    from_ir_cmd.add_argument("--out", type=Path, required=True, help="DSL output path")

    return dsl_cmd


def run_dsl_command(args: argparse.Namespace) -> tuple[int, dict]:
    command = getattr(args, "dsl_command", None)
    if command not in {"compile", "check", "hwtest", "from-ir"}:
        return 2, {"ok": False, "error": "NYI: unknown DSL subcommand"}
    return 2, {"ok": False, "error": f"NYI: nema dsl {command}"}


def emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))
