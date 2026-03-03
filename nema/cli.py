"""CLI entrypoint for NEMA scaffold commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cost import run_cost_compare, run_cost_estimate
from .dsl.cli import add_dsl_subparser, emit as emit_dsl, run_dsl_command
from .hw_doctor import render_hw_doctor_text
from .toolchain import (
    run_connectome_ingest,
    run_connectome_verify,
    run_connectome_bundle_build,
    run_connectome_bundle_verify,
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
from .sweep import parse_lane_list, run_lanes_sweep


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

    connectome_cmd = subparsers.add_parser("connectome", help="connectome bundle utilities")
    connectome_subparsers = connectome_cmd.add_subparsers(dest="connectome_command", required=True)

    connectome_ingest_cmd = connectome_subparsers.add_parser(
        "ingest",
        help="ingest nodes/edges CSV and emit deterministic JSON connectome bundle",
    )
    connectome_ingest_cmd.add_argument("--nodes", type=Path, required=True, help="input nodes.csv path")
    connectome_ingest_cmd.add_argument("--edges", type=Path, required=True, help="input edges.csv path")
    connectome_ingest_cmd.add_argument("--out", type=Path, required=True, help="output bundle JSON path")
    connectome_ingest_cmd.add_argument("--subgraph-id", default="default", help="subgraph id")
    connectome_ingest_cmd.add_argument("--license-spdx", default="MIT", help="license SPDX id")
    connectome_ingest_cmd.add_argument(
        "--source-url",
        action="append",
        default=[],
        help="source URL (repeatable)",
    )
    connectome_ingest_cmd.add_argument(
        "--source-sha256",
        default=None,
        help="optional source artifact sha256 token",
    )
    connectome_ingest_cmd.add_argument(
        "--retrieved-at",
        default="1970-01-01T00:00:00Z",
        help="retrieval timestamp string (deterministic default)",
    )
    connectome_ingest_cmd.add_argument(
        "--schema-version",
        default="0.1",
        help="bundle schema version (default: 0.1)",
    )

    connectome_verify_cmd = connectome_subparsers.add_parser(
        "verify",
        help="verify connectome bundle artifact (JSON file or directory bundle)",
    )
    connectome_verify_cmd.add_argument("path", type=Path, help="bundle path")

    bundle_cmd = connectome_subparsers.add_parser("bundle", help="connectome bundle build/verify")
    bundle_subparsers = bundle_cmd.add_subparsers(dest="bundle_command", required=True)
    bundle_build_cmd = bundle_subparsers.add_parser("build", help="build connectome bundle directory")
    bundle_build_cmd.add_argument("--nodes", type=Path, required=True, help="input nodes.csv path")
    bundle_build_cmd.add_argument("--edges", type=Path, required=True, help="input edges.csv path")
    bundle_build_cmd.add_argument("--out", type=Path, required=True, help="output bundle directory path")
    bundle_build_cmd.add_argument("--source", default="UNKNOWN", help="source label for metadata.json")
    bundle_build_cmd.add_argument("--license", default="UNKNOWN", dest="license_id", help="license label for metadata.json")
    bundle_build_cmd.add_argument("--subgraph-id", default="default", help="subgraph id for metadata.json")
    bundle_verify_cmd = bundle_subparsers.add_parser("verify", help="verify connectome bundle directory")
    bundle_verify_cmd.add_argument("bundle_dir", type=Path, help="bundle directory path")

    hwtest_cmd = subparsers.add_parser(
        "hwtest",
        help="run sim + optional Vitis HLS detection and emit bench_report.json",
    )
    hwtest_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    hwtest_cmd.add_argument("--outdir", type=Path, default=Path("build"), help="output directory")
    hwtest_cmd.add_argument("--ticks", type=int, default=8, help="number of ticks for sim stage")
    hwtest_cmd.add_argument(
        "--hw",
        choices=("auto", "require", "off"),
        default="auto",
        help="hardware toolchain policy (default: auto)",
    )
    hwtest_cmd.add_argument(
        "--cosim",
        choices=("auto", "on", "off"),
        default="auto",
        help="C/RTL cosim policy (default: auto; run with --cosim on to force)",
    )
    hwtest_cmd.add_argument(
        "--vivado-part",
        default=None,
        help="override Vivado target part for implementation reports (e.g. xc7a35tcsg324-1)",
    )
    hwtest_cmd.add_argument(
        "--write-bitstream",
        action="store_true",
        help="request Vivado to emit a .bit artifact after route_design",
    )
    hwtest_cmd.add_argument(
        "--allow-part-fallback",
        action="store_true",
        help="allow selecting a different installed FPGA part when requested part is unavailable",
    )

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
    bench_verify_cmd.add_argument(
        "--hw",
        choices=("off", "auto", "require"),
        default="off",
        help=(
            "hardware rerun policy for verification (default: off). "
            "Use --hw require for end-to-end HW reproduction."
        ),
    )
    bench_verify_cmd.add_argument(
        "--strict-part",
        action="store_true",
        help="disable automatic fallback to a non-target installed part during HW reruns",
    )

    cost_cmd = subparsers.add_parser("cost", help="cost model utilities")
    cost_subparsers = cost_cmd.add_subparsers(dest="cost_command", required=True)
    cost_estimate_cmd = cost_subparsers.add_parser("estimate", help="estimate v0 cost metrics for an IR")
    cost_estimate_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    cost_compare_cmd = cost_subparsers.add_parser(
        "compare",
        help="compare v0 estimate against hardware QoR from bench_report.json",
    )
    cost_compare_cmd.add_argument("bench_report_json", type=Path, help="path to bench_report.json")

    sweep_cmd = subparsers.add_parser("sweep", help="parameter sweep utilities")
    sweep_subparsers = sweep_cmd.add_subparsers(dest="sweep_command", required=True)
    sweep_lanes_cmd = sweep_subparsers.add_parser(
        "lanes",
        help="sweep compile.schedule synapseLanes/neuronLanes and aggregate QoR",
    )
    sweep_lanes_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    sweep_lanes_cmd.add_argument("--synapse", required=True, help="comma-separated synapse lanes (e.g. 1,2,4,8)")
    sweep_lanes_cmd.add_argument("--neuron", required=True, help="comma-separated neuron lanes (e.g. 1,2,4)")
    sweep_lanes_cmd.add_argument("--ticks", type=int, default=2, help="number of ticks per hwtest run")
    sweep_lanes_cmd.add_argument("--outdir", type=Path, default=Path("sweep_out"), help="sweep output directory")
    sweep_lanes_cmd.add_argument(
        "--hw",
        choices=("auto", "require", "off"),
        default="require",
        help="hardware toolchain policy for hwtest runs (default: require)",
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

    vivado_cmd = subparsers.add_parser("vivado", help="Vivado flow utilities")
    vivado_subparsers = vivado_cmd.add_subparsers(dest="vivado_command", required=True)
    vivado_bitstream_cmd = vivado_subparsers.add_parser(
        "bitstream",
        help="run hwtest in --hw require mode and emit a Vivado bitstream",
    )
    vivado_bitstream_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    vivado_bitstream_cmd.add_argument("--outdir", type=Path, default=Path("build_hw"), help="output directory")
    vivado_bitstream_cmd.add_argument("--ticks", type=int, default=2, help="number of ticks for sim stage")
    vivado_bitstream_cmd.add_argument(
        "--part",
        required=True,
        help="target Vivado FPGA part (e.g. xc7a35tcsg324-1)",
    )
    vivado_bitstream_cmd.add_argument(
        "--cosim",
        choices=("auto", "on", "off"),
        default="off",
        help="C/RTL cosim policy for this run (default: off)",
    )
    vivado_bitstream_cmd.add_argument(
        "--allow-part-fallback",
        action="store_true",
        help="allow selecting a different installed FPGA part when requested part is unavailable",
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

    if args.command == "connectome":
        if args.connectome_command == "ingest":
            code, report = run_connectome_ingest(
                nodes_csv=args.nodes,
                edges_csv=args.edges,
                out_path=args.out,
                subgraph_id=args.subgraph_id,
                license_spdx=args.license_spdx,
                source_urls=args.source_url,
                source_sha256=args.source_sha256,
                retrieved_at=args.retrieved_at,
                schema_version=args.schema_version,
            )
            _emit(report)
            return code
        if args.connectome_command == "verify":
            code, report = run_connectome_verify(args.path)
            _emit(report)
            return code
        if args.connectome_command == "bundle":
            if args.bundle_command == "build":
                code, report = run_connectome_bundle_build(
                    nodes_csv=args.nodes,
                    edges_csv=args.edges,
                    out_dir=args.out,
                    source=args.source,
                    license_id=args.license_id,
                    subgraph_id=args.subgraph_id,
                )
                _emit(report)
                return code
            if args.bundle_command == "verify":
                code, report = run_connectome_bundle_verify(args.bundle_dir)
                _emit(report)
                return code
            parser.error(f"unknown connectome bundle command: {args.bundle_command}")
        parser.error(f"unknown connectome command: {args.connectome_command}")

    if args.command == "hwtest":
        code, report = run_hwtest(
            args.ir_json,
            outdir=args.outdir,
            ticks=args.ticks,
            hw_mode=args.hw,
            cosim_mode=args.cosim,
            vivado_part=args.vivado_part,
            allow_part_fallback=bool(args.allow_part_fallback),
            write_bitstream=bool(args.write_bitstream),
        )
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
            code, report = run_bench_verify(
                args.manifest_json,
                outdir=args.outdir,
                hw_mode=args.hw,
                strict_target_part=bool(args.strict_part),
            )
            _emit(report)
            return code
        parser.error(f"unknown bench command: {args.bench_command}")

    if args.command == "cost":
        if args.cost_command == "estimate":
            code, report = run_cost_estimate(args.ir_json)
            _emit(report)
            return code
        if args.cost_command == "compare":
            code, report = run_cost_compare(args.bench_report_json)
            _emit(report)
            return code
        parser.error(f"unknown cost command: {args.cost_command}")

    if args.command == "sweep":
        if args.sweep_command == "lanes":
            try:
                synapse_lanes = parse_lane_list(args.synapse)
                neuron_lanes = parse_lane_list(args.neuron)
            except ValueError as exc:
                _emit({"ok": False, "error": str(exc)})
                return 1
            code, report = run_lanes_sweep(
                args.ir_json,
                synapse_lanes=synapse_lanes,
                neuron_lanes=neuron_lanes,
                ticks=args.ticks,
                outdir=args.outdir,
                hw_mode=args.hw,
            )
            _emit(report)
            return code
        parser.error(f"unknown sweep command: {args.sweep_command}")

    if args.command == "hw":
        if args.hw_command == "doctor":
            code, report = run_hw_doctor()
            if args.format == "json":
                _emit(report)
            else:
                print(render_hw_doctor_text(report))
            return code
        parser.error(f"unknown hw command: {args.hw_command}")

    if args.command == "vivado":
        if args.vivado_command == "bitstream":
            code, report = run_hwtest(
                args.ir_json,
                outdir=args.outdir,
                ticks=args.ticks,
                hw_mode="require",
                cosim_mode=args.cosim,
                vivado_part=args.part,
                allow_part_fallback=bool(args.allow_part_fallback),
                write_bitstream=True,
            )
            _emit(report)
            return code
        parser.error(f"unknown vivado command: {args.vivado_command}")

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
