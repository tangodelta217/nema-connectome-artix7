#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _safe_load_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(raw, dict):
        return raw
    return None


def _collect_candidate_report_paths(repo_root: Path) -> list[Path]:
    paths: set[Path] = set()

    for child in sorted(repo_root.iterdir()):
        if child.is_dir() and child.name.startswith("build"):
            for p in child.rglob("bench_report.json"):
                paths.add(p.resolve())

    evidence_dir = repo_root / "papers" / "paperA" / "artifacts" / "evidence"
    for evidence_name in ("audit_software.json", "audit_hardware.json"):
        payload = _safe_load_json(evidence_dir / evidence_name)
        if not payload:
            continue

        value = payload.get("relevantReportPaths")
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    p = Path(item)
                    if p.exists():
                        paths.add(p.resolve())

        reports = payload.get("relevantReports")
        if isinstance(reports, list):
            for item in reports:
                if isinstance(item, dict):
                    candidate = item.get("path") or item.get("resolvedPath")
                    if isinstance(candidate, str):
                        p = Path(candidate)
                        if p.exists():
                            paths.add(p.resolve())

    return sorted(paths)


def _path_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _source_priority(path: Path, repo_root: Path) -> int:
    # Canonical source precedence for Paper A tables:
    # 0) build/paperA_routeA
    # 1) build/audit_min
    # 2) any other build/evidence source
    if _path_under(path, repo_root / "build" / "paperA_routeA"):
        return 0
    if _path_under(path, repo_root / "build" / "audit_min"):
        return 1
    return 2


def _benchmark_id(model_id: str, target_id: str) -> str | None:
    model_low = model_id.lower()
    target_low = target_id.lower()

    if "example_b1_small_subgraph" in model_low or "/ce/2-1" in target_low:
        return "B1"
    if "b2_mid_64_1024" in model_low or "/ce/64-1024" in target_low:
        return "B2"
    if "b3_kernel_302_7500" in model_low or "/ce/302-7500" in target_low:
        return "B3"
    if "b4_celegans_external_bundle" in model_low or "/ce/8-12" in target_low:
        return "B4"
    if "b6_delay_small" in model_low or "/ce/3-2" in target_low:
        return "B6"
    return None


def _parse_created_at(value: Any, fallback_path: Path) -> datetime:
    if isinstance(value, str) and value.strip():
        txt = value.strip()
        if txt.endswith("Z"):
            txt = txt[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(txt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    return datetime.fromtimestamp(fallback_path.stat().st_mtime, tz=timezone.utc)


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        txt = value.strip()
        if not txt or txt == "-":
            return None
        try:
            return float(txt)
        except ValueError:
            return None
    return None


def _fmt_num(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.6f}"


def _latex_escape(value: str) -> str:
    escaped = value.replace("\\", "\\textbackslash{}")
    for src, dst in (
        ("&", "\\&"),
        ("%", "\\%"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("_", "\\_"),
        ("{", "\\{"),
        ("}", "\\}"),
        ("~", "\\textasciitilde{}"),
        ("^", "\\textasciicircum{}"),
    ):
        escaped = escaped.replace(src, dst)
    return escaped


def _vivado_status_reason(vivado: dict[str, Any]) -> tuple[str, str]:
    attempted = vivado.get("attempted")
    skipped = vivado.get("skipped")
    impl_ok = vivado.get("implOk")
    ok = vivado.get("ok")
    reason_raw = vivado.get("reason")
    reason = str(reason_raw).strip() if isinstance(reason_raw, str) and str(reason_raw).strip() else ""

    if impl_ok is True or ok is True:
        return "OK", reason or "-"
    if attempted is False or skipped is True:
        return "SKIPPED", reason or "not attempted"
    if attempted is True:
        return "FAIL", reason or "vivado impl failed"
    return "SKIPPED", reason or "not attempted"


def _load_cpu_rows(csv_path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    if not csv_path.exists():
        return rows
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            bench = (row.get("benchmarkId") or "").strip().upper()
            if not bench:
                continue
            rows[bench] = {k: (v or "") for k, v in row.items()}
    return rows


@dataclass(frozen=True)
class ThroughputRow:
    benchmark_id: str
    cpu_ticks_per_s: str
    ii_cycles_per_tick: str
    clk_ns: str
    wns_ns: str
    fmax_mhz_est: str
    hw_ticks_per_s_est: str
    speedup_est: str
    vivado_status: str
    vivado_reason: str
    cpu_bench_report_path: str
    hw_bench_report_path: str


def _render_tex(rows: list[ThroughputRow], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("\\begin{tabular}{|l|r|r|r|r|r|l|}")
    lines.append("\\hline")
    lines.append(
        "benchmarkId & CPU ticks/s & II (cyc/tick) & Fmax est. (MHz) & HW est. ticks/s & speedup est. & vivado impl status \\\\"
    )
    lines.append("\\hline")
    for row in rows:
        cells = [
            row.benchmark_id,
            row.cpu_ticks_per_s,
            row.ii_cycles_per_tick,
            row.fmax_mhz_est,
            row.hw_ticks_per_s_est,
            row.speedup_est,
            row.vivado_status,
        ]
        lines.append(" & ".join(_latex_escape(c) for c in cells) + " \\\\")
    lines.append("\\hline")
    lines.append("\\end{tabular}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Combine measured CPU throughput with boardless HW throughput estimates.")
    parser.add_argument(
        "--cpu-csv",
        type=Path,
        default=Path("papers/paperA/artifacts/tables/results_cpu.csv"),
        help="CPU throughput CSV produced by tools/bench_cpu_throughput.py",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=Path("papers/paperA/artifacts/tables/results_throughput.csv"),
    )
    parser.add_argument(
        "--out-tex",
        type=Path,
        default=Path("papers/paperA/artifacts/tables/results_throughput.tex"),
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    cpu_rows = _load_cpu_rows((repo_root / args.cpu_csv).resolve() if not args.cpu_csv.is_absolute() else args.cpu_csv)
    if not cpu_rows:
        print(f"warning: no CPU rows found in {args.cpu_csv}", file=sys.stderr)

    selected_hw: dict[str, tuple[int, datetime, Path, dict[str, Any]]] = {}
    for report_path in _collect_candidate_report_paths(repo_root):
        payload = _safe_load_json(report_path)
        if payload is None:
            continue
        model_id = str(payload.get("modelId") or "")
        target_id = str(((payload.get("bench") or {}).get("targetId")) or "")
        benchmark_id = _benchmark_id(model_id, target_id)
        if benchmark_id is None:
            continue

        hardware = payload.get("hardware") if isinstance(payload.get("hardware"), dict) else {}
        vivado = hardware.get("vivado") if isinstance(hardware.get("vivado"), dict) else {}
        # Filter out software-only rows for HW estimate selection.
        has_hw_signal = any(
            [
                vivado.get("attempted") is True,
                isinstance(vivado.get("implOk"), bool),
                isinstance(vivado.get("wns"), (int, float)),
                isinstance((hardware.get("toolchain") or {}).get("available"), bool),
            ]
        )
        if not has_hw_signal:
            continue

        created_at = _parse_created_at(payload.get("createdAt"), report_path)
        source_priority = _source_priority(report_path, repo_root)
        prev = selected_hw.get(benchmark_id)
        if (
            prev is None
            or source_priority < prev[0]
            or (source_priority == prev[0] and created_at > prev[1])
        ):
            selected_hw[benchmark_id] = (source_priority, created_at, report_path, payload)

    rows: list[ThroughputRow] = []
    for benchmark_id in sorted(cpu_rows.keys()):
        cpu = cpu_rows[benchmark_id]
        cpu_tps = _as_float(cpu.get("cpuTicksPerSecondSelected"))

        hw_entry = selected_hw.get(benchmark_id)
        ii: float | None = None
        clk_ns: float | None = None
        wns_ns: float | None = None
        fmax_mhz_est: float | None = None
        hw_ticks_per_s_est: float | None = None
        speedup_est: float | None = None
        vivado_status = "SKIPPED"
        vivado_reason = "no hardware bench_report"
        hw_path = "-"

        if hw_entry is not None:
            _, _, hw_report_path, hw_payload = hw_entry
            hw_path = hw_report_path.relative_to(repo_root).as_posix()
            hardware = hw_payload.get("hardware") if isinstance(hw_payload.get("hardware"), dict) else {}
            qor = hardware.get("qor") if isinstance(hardware.get("qor"), dict) else {}
            tol = qor.get("timingOrLatency") if isinstance(qor.get("timingOrLatency"), dict) else {}
            vivado = hardware.get("vivado") if isinstance(hardware.get("vivado"), dict) else {}
            timing = vivado.get("timing") if isinstance(vivado.get("timing"), dict) else {}

            ii = _as_float(qor.get("ii"))
            if ii is None:
                ii = _as_float(tol.get("ii"))
            clk_ns = _as_float(vivado.get("clk_ns"))
            wns_ns = _as_float(vivado.get("wns"))
            if wns_ns is None:
                wns_ns = _as_float(timing.get("wns"))

            vivado_status, vivado_reason = _vivado_status_reason(vivado)

            effective_period_ns: float | None = None
            if clk_ns is not None and clk_ns > 0:
                if wns_ns is not None:
                    candidate = clk_ns - wns_ns
                    if candidate > 0:
                        effective_period_ns = candidate
                if effective_period_ns is None:
                    effective_period_ns = clk_ns

            if effective_period_ns is not None and effective_period_ns > 0:
                fmax_mhz_est = 1000.0 / effective_period_ns

            if ii is not None and ii > 0 and fmax_mhz_est is not None:
                hw_ticks_per_s_est = (fmax_mhz_est * 1_000_000.0) / ii

            if cpu_tps is not None and cpu_tps > 0 and hw_ticks_per_s_est is not None:
                speedup_est = hw_ticks_per_s_est / cpu_tps

        rows.append(
            ThroughputRow(
                benchmark_id=benchmark_id,
                cpu_ticks_per_s=_fmt_num(cpu_tps),
                ii_cycles_per_tick=_fmt_num(ii),
                clk_ns=_fmt_num(clk_ns),
                wns_ns=_fmt_num(wns_ns),
                fmax_mhz_est=_fmt_num(fmax_mhz_est),
                hw_ticks_per_s_est=_fmt_num(hw_ticks_per_s_est),
                speedup_est=_fmt_num(speedup_est),
                vivado_status=vivado_status,
                vivado_reason=vivado_reason,
                cpu_bench_report_path=cpu.get("benchReportPath", "-"),
                hw_bench_report_path=hw_path,
            )
        )

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "benchmarkId",
                "cpuTicksPerSecond",
                "hwIiCyclesPerTick",
                "clkNs",
                "wnsNs",
                "fmaxMhzEstimated",
                "hwTicksPerSecondEstimated",
                "speedupEstimated",
                "vivadoImplStatus",
                "vivadoImplReason",
                "cpuBenchReportPath",
                "hwBenchReportPath",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.benchmark_id,
                    row.cpu_ticks_per_s,
                    row.ii_cycles_per_tick,
                    row.clk_ns,
                    row.wns_ns,
                    row.fmax_mhz_est,
                    row.hw_ticks_per_s_est,
                    row.speedup_est,
                    row.vivado_status,
                    row.vivado_reason,
                    row.cpu_bench_report_path,
                    row.hw_bench_report_path,
                ]
            )

    _render_tex(rows, args.out_tex)

    print(str(args.out_csv))
    print(str(args.out_tex))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
