#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BENCHMARK_IRS: dict[str, str] = {
    "B1": "example_b1_small_subgraph.json",
    "B2": "example_b2_mid_scale.json",
    "B3": "example_b3_kernel_302.json",
    "B6": "example_b6_delay_small.json",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_load_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(raw, dict):
        return raw
    return None


def _fmt_num(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return "-"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _parse_benchmark_list(raw: str, include_optional: bool) -> list[str]:
    items: list[str] = []
    for token in raw.split(","):
        name = token.strip().upper()
        if not name:
            continue
        if name not in BENCHMARK_IRS:
            raise ValueError(f"unknown benchmark '{name}', expected one of {sorted(BENCHMARK_IRS.keys())}")
        if name not in items:
            items.append(name)
    if include_optional:
        for opt_name in ("B2", "B6"):
            if opt_name not in items:
                items.append(opt_name)
    return items


@dataclass(frozen=True)
class CpuRow:
    benchmark_id: str
    ir_path: str
    ticks: int
    golden_tps: str
    cpp_tps: str
    cpu_tps_selected: str
    golden_elapsed_s: str
    cpp_elapsed_s: str
    bench_report_path: str
    hwtest_ok: str
    hwtest_exit_code: int
    error: str


def _run_benchmark(
    *,
    repo_root: Path,
    benchmark_id: str,
    ir_path: Path,
    ir_display: str,
    ticks: int,
    outdir_root: Path,
) -> CpuRow:
    run_dir = outdir_root / benchmark_id.lower()
    run_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "nema",
        "hwtest",
        str(ir_path),
        "--ticks",
        str(ticks),
        "--outdir",
        str(run_dir),
        "--hw",
        "off",
        "--cosim",
        "off",
    ]
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True)

    stdout_path = run_dir / "hwtest.stdout.json"
    stderr_path = run_dir / "hwtest.stderr.txt"
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")

    payload: dict[str, Any] | None = None
    if proc.stdout.strip():
        try:
            raw = json.loads(proc.stdout)
            if isinstance(raw, dict):
                payload = raw
        except Exception:
            payload = None

    if proc.returncode != 0 or payload is None:
        return CpuRow(
            benchmark_id=benchmark_id,
            ir_path=ir_display,
            ticks=ticks,
            golden_tps="-",
            cpp_tps="-",
            cpu_tps_selected="-",
            golden_elapsed_s="-",
            cpp_elapsed_s="-",
            bench_report_path="-",
            hwtest_ok="false",
            hwtest_exit_code=proc.returncode,
            error=f"hwtest failed (see {stderr_path.relative_to(repo_root).as_posix()})",
        )

    bench_report_raw = payload.get("bench_report")
    if not isinstance(bench_report_raw, str) or not bench_report_raw:
        return CpuRow(
            benchmark_id=benchmark_id,
            ir_path=ir_display,
            ticks=ticks,
            golden_tps="-",
            cpp_tps="-",
            cpu_tps_selected="-",
            golden_elapsed_s="-",
            cpp_elapsed_s="-",
            bench_report_path="-",
            hwtest_ok="false",
            hwtest_exit_code=proc.returncode,
            error="hwtest output missing bench_report path",
        )

    bench_report_path = Path(bench_report_raw)
    if not bench_report_path.is_absolute():
        bench_report_path = (repo_root / bench_report_path).resolve()
    bench_payload = _safe_load_json(bench_report_path)
    if bench_payload is None:
        return CpuRow(
            benchmark_id=benchmark_id,
            ir_path=ir_display,
            ticks=ticks,
            golden_tps="-",
            cpp_tps="-",
            cpu_tps_selected="-",
            golden_elapsed_s="-",
            cpp_elapsed_s="-",
            bench_report_path=bench_report_path.as_posix(),
            hwtest_ok="false",
            hwtest_exit_code=proc.returncode,
            error="failed to parse bench_report.json",
        )

    perf_cpu = ((bench_payload.get("performance") or {}).get("cpu") or {})
    if not isinstance(perf_cpu, dict):
        perf_cpu = {}

    golden_tps = perf_cpu.get("goldenTicksPerSecond")
    cpp_tps = perf_cpu.get("cppRefTicksPerSecond")
    golden_elapsed = perf_cpu.get("goldenElapsedSeconds")
    cpp_elapsed = perf_cpu.get("cppRefElapsedSeconds")

    selected = cpp_tps if isinstance(cpp_tps, (int, float)) else golden_tps

    rel_bench_report = bench_report_path.relative_to(repo_root).as_posix()

    return CpuRow(
        benchmark_id=benchmark_id,
        ir_path=ir_display,
        ticks=ticks,
        golden_tps=_fmt_num(golden_tps),
        cpp_tps=_fmt_num(cpp_tps),
        cpu_tps_selected=_fmt_num(selected),
        golden_elapsed_s=_fmt_num(golden_elapsed),
        cpp_elapsed_s=_fmt_num(cpp_elapsed),
        bench_report_path=rel_bench_report,
        hwtest_ok="true" if proc.returncode == 0 else "false",
        hwtest_exit_code=proc.returncode,
        error="-",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure CPU ticks/s via `nema hwtest --hw off` for selected benchmarks.")
    parser.add_argument(
        "--benchmarks",
        default="B1,B3",
        help="comma-separated benchmark IDs to run (subset of B1,B2,B3,B6); default: B1,B3",
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="include optional B2/B6 in addition to --benchmarks",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=1000,
        help="ticks per run (default: 1000)",
    )
    parser.add_argument(
        "--outdir-root",
        type=Path,
        default=Path("paper_cpu_runs"),
        help="output root for run artifacts/logs (default: paper_cpu_runs)",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=Path("papers/paperA/artifacts/tables/results_cpu.csv"),
        help="CSV output path (default: papers/paperA/artifacts/tables/results_cpu.csv)",
    )
    args = parser.parse_args()

    if args.ticks <= 0:
        raise SystemExit("--ticks must be > 0")

    repo_root = _repo_root()
    try:
        benchmarks = _parse_benchmark_list(args.benchmarks, args.include_optional)
    except ValueError as exc:
        raise SystemExit(str(exc))
    if not benchmarks:
        raise SystemExit("no benchmarks selected")

    outdir_root = args.outdir_root
    if not outdir_root.is_absolute():
        outdir_root = (repo_root / outdir_root).resolve()
    outdir_root.mkdir(parents=True, exist_ok=True)

    rows: list[CpuRow] = []
    for benchmark_id in sorted(benchmarks):
        ir_rel = BENCHMARK_IRS[benchmark_id]
        ir_path = (repo_root / ir_rel).resolve()
        if not ir_path.exists():
            rows.append(
                CpuRow(
                    benchmark_id=benchmark_id,
                    ir_path=ir_rel,
                    ticks=args.ticks,
                    golden_tps="-",
                    cpp_tps="-",
                    cpu_tps_selected="-",
                    golden_elapsed_s="-",
                    cpp_elapsed_s="-",
                    bench_report_path="-",
                    hwtest_ok="false",
                    hwtest_exit_code=127,
                    error=f"missing IR file: {ir_rel}",
                )
            )
            continue
        row = _run_benchmark(
            repo_root=repo_root,
            benchmark_id=benchmark_id,
            ir_path=ir_path,
            ir_display=ir_rel,
            ticks=args.ticks,
            outdir_root=outdir_root,
        )
        rows.append(row)

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "benchmarkId",
                "irPath",
                "ticks",
                "goldenTicksPerSecond",
                "cppRefTicksPerSecond",
                "cpuTicksPerSecondSelected",
                "goldenElapsedSeconds",
                "cppRefElapsedSeconds",
                "benchReportPath",
                "hwtestOk",
                "hwtestExitCode",
                "error",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.benchmark_id,
                    row.ir_path,
                    row.ticks,
                    row.golden_tps,
                    row.cpp_tps,
                    row.cpu_tps_selected,
                    row.golden_elapsed_s,
                    row.cpp_elapsed_s,
                    row.bench_report_path,
                    row.hwtest_ok,
                    row.hwtest_exit_code,
                    row.error,
                ]
            )

    print(str(args.out_csv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
