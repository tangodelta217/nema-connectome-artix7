"""CLI entrypoint for NEMA scaffold commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .dsl.cli import add_dsl_subparser, emit as emit_dsl, run_dsl_command
from .hw_doctor import render_hw_doctor_text
from .toolchain import (
    run_bench_verify,
    check_ir,
    dump_csr,
    run_hw_doctor,
    run_compile,
    run_hwtest,
    run_materialize_external,
    run_sim,
    selftest_fixed,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nema", description="NEMA v0.1 scaffold CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_cmd = subparsers.add_parser("check", help="validate IR JSON against invariants")
    check_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")

    sim_cmd = subparsers.add_parser("sim", help="run golden simulation (nema.tick.v0.1)")
    sim_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    sim_cmd.add_argument("--ticks", type=int, required=True, help="number of ticks")
    sim_cmd.add_argument("--out", type=Path, required=True, help="trace JSONL output path")
    sim_cmd.add_argument(
        "--digest-out",
        type=Path,
        default=None,
        help="digest JSON output path (default: sibling digest.json)",
    )
    sim_cmd.add_argument("--seed", type=int, default=0, help="deterministic simulation seed")

    compile_cmd = subparsers.add_parser("compile", help="generate HLS kernel + C++ reference harness")
    compile_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    compile_cmd.add_argument("--outdir", type=Path, default=Path("build"), help="output directory")

    dump_csr_cmd = subparsers.add_parser("dump-csr", help="lower graph and dump deterministic CSR JSON")
    dump_csr_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    dump_csr_cmd.add_argument("--out", type=Path, required=True, help="CSR dump output path")

    materialize_cmd = subparsers.add_parser(
        "materialize-external",
        help="materialize deterministic external connectome bundle for IR graph.external",
    )
    materialize_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    materialize_cmd.add_argument("--out", type=Path, required=True, help="output JSON bundle path")

    hwtest_cmd = subparsers.add_parser(
        "hwtest",
        help="run sim + optional Vitis HLS detection and emit bench_report.json",
    )
    hwtest_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    hwtest_cmd.add_argument("--outdir", type=Path, default=Path("build"), help="output directory")
    hwtest_cmd.add_argument("--ticks", type=int, default=8, help="number of ticks for sim stage")

    selftest_cmd = subparsers.add_parser("selftest", help="run built-in deterministic self tests")
    selftest_cmd.add_argument("target", choices=["fixed"], help="selftest suite target")

    bench_cmd = subparsers.add_parser("bench", help="benchmark utilities")
    bench_subparsers = bench_cmd.add_subparsers(dest="bench_command", required=True)
    bench_verify_cmd = bench_subparsers.add_parser("verify", help="run hwtest and verify against manifest")
    bench_verify_cmd.add_argument("manifest_json", type=Path, help="path to bench manifest JSON")
    bench_verify_cmd.add_argument(
        "--outdir",
        type=Path,
        default=None,
        help="optional isolated output directory (default: temp dir under build/)",
    )

    hw_cmd = subparsers.add_parser("hw", help="hardware toolchain utilities")
    hw_subparsers = hw_cmd.add_subparsers(dest="hw_command", required=True)
    hw_doctor_cmd = hw_subparsers.add_parser("doctor", help="diagnose hardware toolchain environment")
    hw_doctor_cmd.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )

    add_dsl_subparser(subparsers)

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
        code, report = run_sim(
            args.ir_json,
            ticks=args.ticks,
            out_path=args.out,
            digest_path=args.digest_out,
            seed=args.seed,
        )
        _emit(report)
        return code

    if args.command == "compile":
        code, report = run_compile(args.ir_json, outdir=args.outdir)
        _emit(report)
        return code

    if args.command == "dump-csr":
        code, report = dump_csr(args.ir_json, out_path=args.out)
        _emit(report)
        return code

    if args.command == "materialize-external":
        code, report = run_materialize_external(args.ir_json, out_path=args.out)
        _emit(report)
        return code

    if args.command == "hwtest":
        code, report = run_hwtest(args.ir_json, outdir=args.outdir, ticks=args.ticks)
        _emit(report)
        return code

    if args.command == "selftest":
        if args.target == "fixed":
            code, report = selftest_fixed()
            _emit(report)
            return code
        parser.error(f"unknown selftest target: {args.target}")

    if args.command == "bench":
        if args.bench_command == "verify":
            code, report = run_bench_verify(args.manifest_json, outdir=args.outdir)
            _emit(report)
            return code
        parser.error(f"unknown bench command: {args.bench_command}")

    if args.command == "hw":
        if args.hw_command == "doctor":
            code, report = run_hw_doctor()
            if args.format == "json":
                _emit(report)
            else:
                print(render_hw_doctor_text(report))
            return code
        parser.error(f"unknown hw command: {args.hw_command}")

    if args.command == "dsl":
        code, report = run_dsl_command(args)
        emit_dsl(
            report,
            fmt=getattr(args, "format", "text"),
            no_color=bool(getattr(args, "no_color", True)),
        )
        return code

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
