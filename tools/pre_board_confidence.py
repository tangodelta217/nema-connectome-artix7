#!/usr/bin/env python3
"""Build pre-board confidence report from hwtest run artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CaseSpec:
    case_id: str
    benchmark_id: str
    ir_path: str
    ticks: int
    mode: str


CASE_SPECS: list[CaseSpec] = [
    CaseSpec("b1_sw", "B1", "example_b1_small_subgraph.json", 20, "software"),
    CaseSpec("b1_hw", "B1", "example_b1_small_subgraph.json", 2, "hw_require"),
    CaseSpec("b3_sw", "B3", "example_b3_kernel_302.json", 20, "software"),
    CaseSpec("b3_hw", "B3", "example_b3_kernel_302.json", 2, "hw_require"),
    CaseSpec("b4_hw", "B4", "example_b4_celegans_external_bundle.json", 2, "hw_require"),
]


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_int(path: Path) -> int | None:
    try:
        return int(_read_text(path).strip())
    except Exception:
        return None


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(_read_text(path))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _find_bench_report(case_dir: Path) -> Path | None:
    reports = sorted(case_dir.glob("**/bench_report.json"))
    if not reports:
        return None
    return reports[0]


def _extract_metrics(report: dict[str, Any]) -> dict[str, Any]:
    correctness = report.get("correctness", {}) if isinstance(report.get("correctness"), dict) else {}
    digest = correctness.get("digestMatch", {}) if isinstance(correctness.get("digestMatch"), dict) else {}
    mismatches = correctness.get("mismatches")
    if not isinstance(mismatches, list):
        mismatches = []

    provenance = report.get("provenance", {}) if isinstance(report.get("provenance"), dict) else {}
    hardware = report.get("hardware", {}) if isinstance(report.get("hardware"), dict) else {}
    csim = hardware.get("csim", {}) if isinstance(hardware.get("csim"), dict) else {}
    csynth = hardware.get("csynth", {}) if isinstance(hardware.get("csynth"), dict) else {}
    cosim = hardware.get("cosim", {}) if isinstance(hardware.get("cosim"), dict) else {}
    qor = hardware.get("qor", {}) if isinstance(hardware.get("qor"), dict) else {}
    vivado = hardware.get("vivado", {}) if isinstance(hardware.get("vivado"), dict) else {}

    timing = vivado.get("timing", {}) if isinstance(vivado.get("timing"), dict) else {}
    utilization = qor.get("utilization", {}) if isinstance(qor.get("utilization"), dict) else {}

    return {
        "modelId": report.get("modelId"),
        "targetId": (report.get("bench", {}) or {}).get("targetId") if isinstance(report.get("bench"), dict) else None,
        "ok": bool(report.get("ok") is True),
        "digestMatchOk": bool(digest.get("ok") is True),
        "mismatchesLen": len(mismatches),
        "externalVerified": provenance.get("externalVerified"),
        "syntheticUsed": provenance.get("syntheticUsed"),
        "csimOk": csim.get("ok"),
        "csynthOk": csynth.get("ok"),
        "cosimOk": cosim.get("ok"),
        "cosimAttempted": cosim.get("attempted"),
        "ii": qor.get("ii"),
        "latencyCycles": qor.get("latencyCycles"),
        "utilization": {
            "lut": utilization.get("lut"),
            "ff": utilization.get("ff"),
            "bram": utilization.get("bram"),
            "dsp": utilization.get("dsp"),
        },
        "vivado": {
            "attempted": vivado.get("attempted"),
            "implOk": vivado.get("implOk"),
            "ok": vivado.get("ok"),
            "skipped": vivado.get("skipped"),
            "reason": vivado.get("reason"),
            "wns": vivado.get("wns") if vivado.get("wns") is not None else timing.get("wns"),
            "tns": vivado.get("tns") if vivado.get("tns") is not None else timing.get("tns"),
            "timingReport": vivado.get("timingReport"),
        },
    }


def _has_post_route_timing_sim(case_root: Path, report: dict[str, Any]) -> tuple[str, str]:
    # Current flow may expose it either in bench_report fields or by xsim/sdf artifacts.
    hardware = report.get("hardware", {}) if isinstance(report.get("hardware"), dict) else {}
    vivado = hardware.get("vivado", {}) if isinstance(hardware.get("vivado"), dict) else {}
    for key in ("timingSim", "postRouteTimingSim", "xsimTiming"):
        if key in vivado:
            return "AVAILABLE", f"bench_report contains hardware.vivado.{key}"

    patterns = [
        "**/*timing*sim*.log",
        "**/*post_route*sim*.log",
        "**/*xsim*.log",
        "**/*.sdf",
    ]
    for pattern in patterns:
        if any(case_root.glob(pattern)):
            return "AVAILABLE", f"found artifact matching {pattern}"
    return "NOT_AVAILABLE", "No timing-sim fields or xsim/sdf artifacts found in run outdirs"


def _power_estimation(case_roots: list[Path]) -> dict[str, Any]:
    power_files: list[str] = []
    for root in case_roots:
        for pattern in ("**/*power*.rpt", "**/*power*.csv", "**/*power*.json"):
            power_files.extend(str(p) for p in root.glob(pattern) if p.is_file())
    power_files = sorted(set(power_files))
    if power_files:
        return {
            "status": "ESTIMATED_AVAILABLE",
            "method": "ESTIMATED_FROM_TOOL_REPORT",
            "measuredOnBoard": False,
            "files": power_files,
        }
    return {
        "status": "ESTIMATED_NOT_AVAILABLE",
        "method": "ESTIMATED_TOOL_REPORT_NOT_FOUND",
        "measuredOnBoard": False,
        "reason": "No power estimation artifacts found under run outdirs",
        "files": [],
    }


def _toolchain_summary(outdir: Path) -> dict[str, Any]:
    logs = outdir / "logs"
    clean_stdout = _read_text(logs / "toolchain_clean.stdout.txt")
    clean_lines = [ln.strip() for ln in clean_stdout.splitlines() if ln.strip()]
    activate_stdout = _read_text(logs / "toolchain_activate.stdout.txt")
    activate_lines = [ln.strip() for ln in activate_stdout.splitlines() if ln.strip()]
    return {
        "clean": {
            "exitcode": _read_int(logs / "toolchain_clean.exitcode.txt"),
            "hasVivado": any("vivado" in ln for ln in clean_lines),
            "hasVitisHls": any("vitis_hls" in ln or "Vitis HLS" in ln for ln in clean_lines),
            "lines": clean_lines[:20],
        },
        "activate": {
            "scriptExists": (Path("tools/hw/activate_xilinx.sh")).exists(),
            "exitcode": _read_int(logs / "toolchain_activate.exitcode.txt"),
            "lines": activate_lines[:30],
            "warnings": [ln.strip() for ln in _read_text(logs / "toolchain_activate.stderr.txt").splitlines() if ln.strip()],
        },
    }


def generate(outdir: Path, json_path: Path, md_path: Path) -> None:
    runs_dir = outdir / "runs"
    pointers_dir = outdir / "pointers"
    pointers_dir.mkdir(parents=True, exist_ok=True)

    toolchain = _toolchain_summary(outdir)

    run_entries: list[dict[str, Any]] = []
    bench_report_pointers: list[str] = []

    for case in CASE_SPECS:
        case_dir = runs_dir / case.case_id
        exitcode = _read_int(outdir / "logs" / f"{case.case_id}.exitcode.txt")
        report_path = _find_bench_report(case_dir)
        report_rel = str(report_path.relative_to(Path.cwd())) if report_path and report_path.exists() else None
        bench_report = _load_json(report_path) if report_path else None

        metrics: dict[str, Any] | None = None
        post_route_status = "NOT_AVAILABLE"
        post_route_reason = "bench_report missing"
        if bench_report is not None:
            metrics = _extract_metrics(bench_report)
            post_route_status, post_route_reason = _has_post_route_timing_sim(case_dir, bench_report)
            if report_rel:
                bench_report_pointers.append(report_rel)

        run_entries.append(
            {
                "caseId": case.case_id,
                "benchmarkId": case.benchmark_id,
                "irPath": case.ir_path,
                "ticks": case.ticks,
                "mode": case.mode,
                "exitcode": exitcode,
                "benchReportPath": report_rel,
                "metrics": metrics,
                "postRouteTimingSim": {
                    "status": post_route_status,
                    "reason": post_route_reason,
                },
            }
        )

    # benchmark-level bit-exact summary from available runs
    bitexact_by_bench: dict[str, dict[str, Any]] = {}
    for bench in ("B1", "B3", "B4"):
        candidates = [r for r in run_entries if r["benchmarkId"] == bench and isinstance(r.get("metrics"), dict)]
        digest_ok = any((c["metrics"] or {}).get("digestMatchOk") is True for c in candidates)
        mismatch_zero = any((c["metrics"] or {}).get("mismatchesLen") == 0 for c in candidates)
        bitexact_by_bench[bench] = {
            "digestMatchOk": digest_ok,
            "mismatchesZero": mismatch_zero,
            "runsConsidered": [c["caseId"] for c in candidates],
        }

    hw_runs = [r for r in run_entries if r["mode"] == "hw_require" and isinstance(r.get("metrics"), dict)]
    timing_static = []
    for r in hw_runs:
        metrics = r["metrics"]
        viv = metrics.get("vivado", {}) if isinstance(metrics, dict) else {}
        timing_static.append(
            {
                "caseId": r["caseId"],
                "benchmarkId": r["benchmarkId"],
                "vivadoImplOk": viv.get("implOk"),
                "wns": viv.get("wns"),
                "ii": metrics.get("ii"),
                "latencyCycles": metrics.get("latencyCycles"),
            }
        )

    cycle_accurate = {
        "csimAllHwRunsOk": all((r["metrics"] or {}).get("csimOk") is True for r in hw_runs) if hw_runs else False,
        "csynthAllHwRunsOk": all((r["metrics"] or {}).get("csynthOk") is True for r in hw_runs) if hw_runs else False,
        "cosimAttemptedAny": any((r["metrics"] or {}).get("cosimAttempted") is True for r in hw_runs),
        "cosimOkAny": any((r["metrics"] or {}).get("cosimOk") is True for r in hw_runs),
    }

    post_route_statuses = [r["postRouteTimingSim"]["status"] for r in hw_runs]
    if post_route_statuses and any(s == "AVAILABLE" for s in post_route_statuses):
        post_route = {"status": "AVAILABLE", "reason": "At least one hw run has timing-sim evidence"}
    else:
        reason = "No hw runs" if not hw_runs else "All hw runs report NOT_AVAILABLE"
        post_route = {"status": "NOT_AVAILABLE", "reason": reason}

    power = _power_estimation([runs_dir / case.case_id for case in CASE_SPECS if (runs_dir / case.case_id).exists()])

    payload = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "outdir": str(outdir),
        "toolchain": toolchain,
        "runs": run_entries,
        "summary": {
            "bitExactness": bitexact_by_bench,
            "cycleAccurateEvidence": cycle_accurate,
            "timingStatic": timing_static,
            "postRouteTimingSim": post_route,
            "powerEstimation": power,
            "notes": [
                "This report is boardless; no MEASURED_ON_BOARD claims are made.",
                "Power section is ESTIMATED_* only, never measured on board.",
            ],
        },
    }

    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pointers_dir.joinpath("bench_reports_used.txt").write_text("\n".join(sorted(set(bench_report_pointers))) + "\n", encoding="utf-8")

    md_lines: list[str] = []
    md_lines.append("# Pre-Board Confidence Report")
    md_lines.append("")
    md_lines.append(f"- Generated: {payload['generatedAtUtc']}")
    md_lines.append(f"- Outdir: `{outdir}`")
    md_lines.append("")
    md_lines.append("## Toolchain")
    md_lines.append("")
    md_lines.append(f"- Clean shell: exit `{toolchain['clean']['exitcode']}`, vivado=`{toolchain['clean']['hasVivado']}`, vitis_hls=`{toolchain['clean']['hasVitisHls']}`")
    md_lines.append(f"- activate_xilinx.sh: exit `{toolchain['activate']['exitcode']}`, scriptExists=`{toolchain['activate']['scriptExists']}`")
    if toolchain["activate"]["warnings"]:
        for warn in toolchain["activate"]["warnings"]:
            md_lines.append(f"- Warning: `{warn}`")
    md_lines.append("")
    md_lines.append("## Bit-Exactness")
    md_lines.append("")
    md_lines.append("| Bench | digestMatchOk | mismatches=0 | runs |")
    md_lines.append("|---|---:|---:|---|")
    for bench in ("B1", "B3", "B4"):
        row = bitexact_by_bench.get(bench, {})
        md_lines.append(
            f"| {bench} | {row.get('digestMatchOk')} | {row.get('mismatchesZero')} | {', '.join(row.get('runsConsidered', []))} |"
        )
    md_lines.append("")
    md_lines.append("## Cycle-Accurate Evidence (boardless)")
    md_lines.append("")
    md_lines.append(f"- csim all hw runs ok: `{cycle_accurate['csimAllHwRunsOk']}`")
    md_lines.append(f"- csynth all hw runs ok: `{cycle_accurate['csynthAllHwRunsOk']}`")
    md_lines.append(f"- cosim attempted any: `{cycle_accurate['cosimAttemptedAny']}`")
    md_lines.append(f"- cosim ok any: `{cycle_accurate['cosimOkAny']}`")
    md_lines.append("")
    md_lines.append("## Timing Static (Vivado impl)")
    md_lines.append("")
    md_lines.append("| Case | Bench | Vivado impl | WNS | II | LatencyCycles |")
    md_lines.append("|---|---|---:|---:|---:|---:|")
    for row in timing_static:
        md_lines.append(
            f"| {row['caseId']} | {row['benchmarkId']} | {row['vivadoImplOk']} | {row['wns']} | {row['ii']} | {row['latencyCycles']} |"
        )
    md_lines.append("")
    md_lines.append("## Post-Route Timing Sim")
    md_lines.append("")
    md_lines.append(f"- Status: `{post_route['status']}`")
    md_lines.append(f"- Reason: {post_route['reason']}")
    md_lines.append("")
    md_lines.append("## Power Estimation (never measured on board)")
    md_lines.append("")
    md_lines.append(f"- Status: `{power['status']}`")
    md_lines.append(f"- Method: `{power['method']}`")
    md_lines.append(f"- measuredOnBoard: `{power['measuredOnBoard']}`")
    if power.get("reason"):
        md_lines.append(f"- Reason: {power['reason']}")
    if power.get("files"):
        md_lines.append("- Files:")
        for path in power["files"]:
            md_lines.append(f"  - `{path}`")
    md_lines.append("")
    md_lines.append("## Bench Report Pointers")
    md_lines.append("")
    for ptr in sorted(set(bench_report_pointers)):
        md_lines.append(f"- `{ptr}`")

    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate boardless pre-board confidence artifacts")
    parser.add_argument("--outdir", required=True, help="Output directory containing logs/ and runs/")
    parser.add_argument("--json", default=None, help="Output JSON path (default: <outdir>/pre_board_confidence.json)")
    parser.add_argument("--md", default=None, help="Output Markdown path (default: <outdir>/pre_board_confidence.md)")
    args = parser.parse_args()

    outdir = Path(args.outdir).resolve()
    json_path = Path(args.json).resolve() if args.json else outdir / "pre_board_confidence.json"
    md_path = Path(args.md).resolve() if args.md else outdir / "pre_board_confidence.md"

    generate(outdir=outdir, json_path=json_path, md_path=md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
