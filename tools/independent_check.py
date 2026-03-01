#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Finding:
    level: str  # ERROR | WARNING
    code: str
    message: str
    report: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _resolve_path(repo_root: Path, report_dir: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    p = Path(value)
    candidates: list[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(repo_root / p)
        candidates.append(report_dir / p)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _collect_reports_from_csv(
    repo_root: Path,
    csv_path: Path,
    *,
    allowed_bench_ids: set[str] | None = None,
) -> set[Path]:
    paths: set[Path] = set()
    if not csv_path.exists():
        return paths
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if allowed_bench_ids is not None:
                    bench_id = row.get("benchId") or row.get("benchmarkId")
                    if isinstance(bench_id, str) and bench_id.strip() and bench_id.strip() not in allowed_bench_ids:
                        continue
                value = row.get("bench_report_path")
                if not isinstance(value, str) or not value.strip():
                    continue
                p = Path(value)
                if not p.is_absolute():
                    p = repo_root / p
                if p.exists():
                    paths.add(p.resolve())
    except Exception:
        return paths
    return paths


def _collect_reports_from_audit(audit_path: Path) -> set[Path]:
    paths: set[Path] = set()
    payload = _safe_load_json(audit_path)
    if not payload:
        return paths

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
            if not isinstance(item, dict):
                continue
            candidate = item.get("path") or item.get("resolvedPath")
            if isinstance(candidate, str):
                p = Path(candidate)
                if p.exists():
                    paths.add(p.resolve())

    checks = ((payload.get("benchManifestChecks") or {}).get("checks") or {})
    if isinstance(checks, dict):
        for check in checks.values():
            if not isinstance(check, dict):
                continue
            verify_json = ((check.get("verify") or {}).get("json") or {})
            if not isinstance(verify_json, dict):
                continue
            candidate = verify_json.get("benchReport")
            if isinstance(candidate, str):
                p = Path(candidate)
                if p.exists():
                    paths.add(p.resolve())

    return paths


def _collect_papera_reports(repo_root: Path) -> list[Path]:
    table_paths: set[Path] = set()
    core_bench_ids = {"B1", "B2", "B3", "B4", "B6"}

    tables_dir = repo_root / "papers" / "paperA" / "artifacts" / "tables"
    table_paths.update(
        _collect_reports_from_csv(
            repo_root,
            tables_dir / "results_bitexact.csv",
            allowed_bench_ids=core_bench_ids,
        )
    )

    # Prefer bit-exact canonical table for Paper A core set.
    if table_paths:
        return sorted(table_paths)

    table_paths.update(
        _collect_reports_from_csv(
            repo_root,
            tables_dir / "results_qor.csv",
            allowed_bench_ids=core_bench_ids,
        )
    )
    if table_paths:
        return sorted(table_paths)

    paths: set[Path] = set()

    evidence_dir = repo_root / "papers" / "paperA" / "artifacts" / "evidence"
    paths.update(_collect_reports_from_audit(evidence_dir / "audit_software.json"))
    paths.update(_collect_reports_from_audit(evidence_dir / "audit_hardware.json"))

    if not paths:
        for p in sorted((repo_root / "build_hw").glob("**/bench_report.json")):
            paths.add(p.resolve())

    return sorted(paths)


def _require_fields(payload: dict[str, Any], report: Path) -> list[Finding]:
    findings: list[Finding] = []

    def _err(code: str, message: str) -> None:
        findings.append(Finding(level="ERROR", code=code, message=message, report=str(report)))

    def _warn(code: str, message: str) -> None:
        findings.append(Finding(level="WARNING", code=code, message=message, report=str(report)))

    if not isinstance(payload.get("ok"), bool):
        _err("SCHEMA_TOP_OK", "top-level 'ok' must be boolean")
    if not isinstance(payload.get("modelId"), str) or not payload.get("modelId"):
        _err("SCHEMA_MODEL_ID", "missing or invalid 'modelId'")

    bench = payload.get("bench")
    if not isinstance(bench, dict) or not isinstance(bench.get("targetId"), str) or not bench.get("targetId"):
        _err("SCHEMA_BENCH", "missing or invalid 'bench.targetId'")

    created_at = payload.get("createdAt")
    if not isinstance(created_at, str) or not created_at:
        _err("SCHEMA_CREATED_AT", "missing or invalid 'createdAt'")

    schedule = ((payload.get("config") or {}).get("schedule") or {})
    if not isinstance(schedule, dict):
        _err("SCHEMA_SCHEDULE", "missing 'config.schedule'")
    else:
        if not isinstance(schedule.get("policy"), str):
            _err("SCHEMA_SCHEDULE_POLICY", "missing or invalid 'config.schedule.policy'")
        if not isinstance(schedule.get("snapshotRule"), bool):
            _err("SCHEMA_SCHEDULE_SNAPSHOT", "missing or invalid 'config.schedule.snapshotRule'")
        if not isinstance(schedule.get("synapseLanes"), int) or int(schedule.get("synapseLanes", 0)) < 1:
            _warn(
                "SCHEMA_SCHEDULE_SYN_LANES",
                "missing or invalid 'config.schedule.synapseLanes' (legacy report tolerated)",
            )
        if not isinstance(schedule.get("neuronLanes"), int) or int(schedule.get("neuronLanes", 0)) < 1:
            _warn(
                "SCHEMA_SCHEDULE_NEU_LANES",
                "missing or invalid 'config.schedule.neuronLanes' (legacy report tolerated)",
            )

    correctness = payload.get("correctness")
    if not isinstance(correctness, dict):
        _err("SCHEMA_CORRECTNESS", "missing 'correctness'")
        return findings

    golden = correctness.get("goldenSim")
    if not isinstance(golden, dict):
        _err("SCHEMA_GOLDEN", "missing 'correctness.goldenSim'")
    else:
        if not isinstance(golden.get("digests"), list):
            _err("SCHEMA_GOLDEN_DIGESTS", "missing or invalid 'correctness.goldenSim.digests'")
        if not isinstance(golden.get("digestPath"), str):
            _err("SCHEMA_GOLDEN_DIGEST_PATH", "missing or invalid 'correctness.goldenSim.digestPath'")
        if not isinstance(golden.get("tracePath"), str):
            _err("SCHEMA_GOLDEN_TRACE_PATH", "missing or invalid 'correctness.goldenSim.tracePath'")

    cpp = correctness.get("cppReference")
    if not isinstance(cpp, dict) or not isinstance(cpp.get("digests"), list):
        _err("SCHEMA_CPP_DIGESTS", "missing or invalid 'correctness.cppReference.digests'")

    digest_match = correctness.get("digestMatch")
    if not isinstance(digest_match, dict) or not isinstance(digest_match.get("ok"), bool):
        _err("SCHEMA_DIGEST_MATCH", "missing or invalid 'correctness.digestMatch.ok'")

    hardware = payload.get("hardware")
    if not isinstance(hardware, dict):
        _err("SCHEMA_HARDWARE", "missing 'hardware'")
        return findings

    toolchain = hardware.get("toolchain")
    if not isinstance(toolchain, dict) or not isinstance(toolchain.get("available"), bool):
        _err("SCHEMA_TOOLCHAIN", "missing or invalid 'hardware.toolchain.available'")

    if not isinstance(hardware.get("qor"), dict):
        _err("SCHEMA_QOR", "missing or invalid 'hardware.qor'")

    if not isinstance(hardware.get("vivado"), dict):
        _err("SCHEMA_VIVADO", "missing or invalid 'hardware.vivado'")

    return findings


def _sha256_for_vraw(values: list[Any]) -> str | None:
    try:
        buf = bytearray()
        for item in values:
            if not isinstance(item, int):
                return None
            if item < -32768 or item > 32767:
                return None
            buf.extend(int(item).to_bytes(2, byteorder="little", signed=True))
        return hashlib.sha256(bytes(buf)).hexdigest()
    except Exception:
        return None


def _read_digest_file(path: Path) -> list[str] | None:
    payload = _safe_load_json(path)
    if not payload:
        return None
    candidate = payload.get("tickDigestsSha256")
    if isinstance(candidate, list) and all(isinstance(x, str) for x in candidate):
        return [str(x) for x in candidate]
    candidate = payload.get("digests")
    if isinstance(candidate, list) and all(isinstance(x, str) for x in candidate):
        return [str(x) for x in candidate]
    return None


def _parse_trace(path: Path) -> tuple[list[str] | None, list[Finding]]:
    findings: list[Finding] = []
    recomputed: list[str] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_idx, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    record = json.loads(text)
                except json.JSONDecodeError as exc:
                    findings.append(
                        Finding(
                            level="ERROR",
                            code="TRACE_JSONL_INVALID",
                            message=f"invalid JSON at line {line_idx}: {exc}",
                            report=str(path),
                        )
                    )
                    return None, findings
                if not isinstance(record, dict):
                    findings.append(
                        Finding(
                            level="ERROR",
                            code="TRACE_RECORD_INVALID",
                            message=f"line {line_idx} is not an object",
                            report=str(path),
                        )
                    )
                    return None, findings
                vraw = record.get("vRawByIndex")
                if not isinstance(vraw, list):
                    findings.append(
                        Finding(
                            level="ERROR",
                            code="TRACE_VRAW_MISSING",
                            message=f"line {line_idx} missing vRawByIndex",
                            report=str(path),
                        )
                    )
                    return None, findings
                digest = _sha256_for_vraw(vraw)
                if digest is None:
                    findings.append(
                        Finding(
                            level="ERROR",
                            code="TRACE_VRAW_INVALID",
                            message=f"line {line_idx} has invalid int16 values in vRawByIndex",
                            report=str(path),
                        )
                    )
                    return None, findings
                recomputed.append(digest)

                recorded = record.get("digestSha256")
                if isinstance(recorded, str) and recorded != digest:
                    findings.append(
                        Finding(
                            level="ERROR",
                            code="TRACE_DIGEST_MISMATCH",
                            message=f"line {line_idx} digestSha256 does not match recomputed SHA-256",
                            report=str(path),
                        )
                    )
    except OSError as exc:
        findings.append(
            Finding(level="ERROR", code="TRACE_READ_FAILED", message=str(exc), report=str(path))
        )
        return None, findings

    return recomputed, findings


def _extract_first_num(text: str, patterns: list[str]) -> int | float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            continue
        for idx in range(1, (match.lastindex or 0) + 1):
            token = match.group(idx)
            if token is None:
                continue
            clean = token.strip().replace(",", "")
            try:
                val = float(clean)
            except ValueError:
                continue
            if val.is_integer():
                return int(val)
            return val
    return None


def _parse_hls_summary_metrics(text: str) -> tuple[int | None, int | None]:
    # Vitis csynth.rpt summary table:
    # | Latency (cycles) ... | Interval ... |
    # |   min | max | ... | min | max | ...
    # |  2745 | ... |      | 2746 | ... |
    summary_match = re.search(
        r"Latency\s*\(cycles\).*?Interval.*?\n.*?\n.*?\n\s*\|\s*([0-9,]+)\s*\|\s*([0-9,]+)\s*\|.*?\|\s*([0-9,]+)\s*\|\s*([0-9,]+)\s*\|",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if summary_match:
        try:
            latency_min = int(summary_match.group(1).replace(",", ""))
            interval_min = int(summary_match.group(3).replace(",", ""))
            return interval_min, latency_min
        except ValueError:
            pass
    return None, None


def _extract_design_timing_wns(text: str) -> float | None:
    marker = re.search(r"Design Timing Summary", text, flags=re.IGNORECASE)
    if not marker:
        return None
    lines = text[marker.end() :].splitlines()
    header_idx: int | None = None
    for idx, line in enumerate(lines):
        if "WNS(ns)" in line and "TNS(ns)" in line:
            header_idx = idx
            break
    if header_idx is None:
        return None
    for line in lines[header_idx + 1 : header_idx + 30]:
        stripped = line.strip()
        if not stripped or set(stripped) <= {"-", " ", "|"}:
            continue
        nums = re.findall(r"-?[0-9]+(?:\.[0-9]+)?", stripped)
        if nums:
            try:
                return float(nums[0])
            except ValueError:
                return None
    return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _compare_metric(
    findings: list[Finding],
    *,
    report: Path,
    code: str,
    parsed: int | float | None,
    bench: Any,
    tolerance: float = 1e-6,
) -> None:
    if parsed is None or bench is None:
        return
    try:
        parsed_f = float(parsed)
        bench_f = float(bench)
    except (TypeError, ValueError):
        findings.append(
            Finding(
                level="ERROR",
                code=code,
                message=f"non-numeric benchmark metric value: parsed={parsed!r}, bench={bench!r}",
                report=str(report),
            )
        )
        return
    if abs(parsed_f - bench_f) > tolerance:
        findings.append(
            Finding(
                level="ERROR",
                code=code,
                message=f"metric mismatch: parsed={parsed_f}, bench_report={bench_f}",
                report=str(report),
            )
        )


def _validate_report(report_path: Path, repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []

    payload = _safe_load_json(report_path)
    if payload is None:
        return [
            Finding(
                level="ERROR",
                code="REPORT_JSON_INVALID",
                message="bench_report is not valid JSON object",
                report=str(report_path),
            )
        ]

    report_dir = report_path.parent
    findings.extend(_require_fields(payload, report_path))

    correctness = payload.get("correctness") if isinstance(payload.get("correctness"), dict) else {}
    golden = correctness.get("goldenSim") if isinstance(correctness.get("goldenSim"), dict) else {}
    cpp = correctness.get("cppReference") if isinstance(correctness.get("cppReference"), dict) else {}
    digest_match = correctness.get("digestMatch") if isinstance(correctness.get("digestMatch"), dict) else {}

    golden_digests = golden.get("digests") if isinstance(golden.get("digests"), list) else None
    if isinstance(golden_digests, list):
        golden_digests = [str(x) for x in golden_digests]

    cpp_digests = cpp.get("digests") if isinstance(cpp.get("digests"), list) else None
    if isinstance(cpp_digests, list):
        cpp_digests = [str(x) for x in cpp_digests]

    digest_path = _resolve_path(repo_root, report_dir, golden.get("digestPath"))
    digest_file_digests: list[str] | None = None
    if digest_path is None:
        findings.append(
            Finding(
                level="ERROR",
                code="GOLDEN_DIGEST_PATH_MISSING",
                message="cannot resolve correctness.goldenSim.digestPath",
                report=str(report_path),
            )
        )
    else:
        digest_file_digests = _read_digest_file(digest_path)
        if digest_file_digests is None:
            findings.append(
                Finding(
                    level="ERROR",
                    code="GOLDEN_DIGEST_FILE_INVALID",
                    message=f"digest file missing tickDigestsSha256/digests list: {digest_path}",
                    report=str(report_path),
                )
            )

    trace_path = _resolve_path(repo_root, report_dir, golden.get("tracePath"))
    recomputed_digests: list[str] | None = None
    if trace_path is None:
        findings.append(
            Finding(
                level="WARNING",
                code="GOLDEN_TRACE_PATH_MISSING",
                message="cannot resolve correctness.goldenSim.tracePath; recompute skipped",
                report=str(report_path),
            )
        )
    else:
        recomputed_digests, trace_findings = _parse_trace(trace_path)
        findings.extend(
            Finding(level=f.level, code=f.code, message=f.message, report=str(report_path)) for f in trace_findings
        )

    if golden_digests is not None and digest_file_digests is not None and golden_digests != digest_file_digests:
        findings.append(
            Finding(
                level="ERROR",
                code="DIGEST_FILE_MISMATCH",
                message="bench_report golden digests differ from digest.json tickDigestsSha256",
                report=str(report_path),
            )
        )

    if golden_digests is not None and recomputed_digests is not None and golden_digests != recomputed_digests:
        findings.append(
            Finding(
                level="ERROR",
                code="DIGEST_RECOMPUTE_MISMATCH",
                message="bench_report golden digests differ from recomputed trace digests",
                report=str(report_path),
            )
        )

    if digest_file_digests is not None and recomputed_digests is not None and digest_file_digests != recomputed_digests:
        findings.append(
            Finding(
                level="ERROR",
                code="DIGEST_FILE_TRACE_MISMATCH",
                message="digest.json tickDigestsSha256 differ from recomputed trace digests",
                report=str(report_path),
            )
        )

    if cpp_digests is not None and golden_digests is not None and cpp_digests != golden_digests:
        findings.append(
            Finding(
                level="ERROR",
                code="CPP_DIGEST_MISMATCH",
                message="cppReference digests differ from goldenSim digests",
                report=str(report_path),
            )
        )

    # Optional hardware digests (if any pipeline stage records them)
    hardware = payload.get("hardware") if isinstance(payload.get("hardware"), dict) else {}
    for stage_name in ("csim", "csynth", "cosim"):
        stage = hardware.get(stage_name)
        if not isinstance(stage, dict):
            continue
        stage_digests = stage.get("digests")
        if isinstance(stage_digests, list) and golden_digests is not None:
            stage_digests_txt = [str(x) for x in stage_digests]
            if stage_digests_txt != golden_digests:
                findings.append(
                    Finding(
                        level="ERROR",
                        code=f"{stage_name.upper()}_DIGEST_MISMATCH",
                        message=f"{stage_name} digests differ from goldenSim digests",
                        report=str(report_path),
                    )
                )

    digest_match_ok = digest_match.get("ok")
    has_digest_error = any(f.level == "ERROR" and f.code.endswith("MISMATCH") for f in findings)
    if isinstance(digest_match_ok, bool):
        if digest_match_ok and has_digest_error:
            findings.append(
                Finding(
                    level="ERROR",
                    code="DIGEST_MATCH_FLAG_INCONSISTENT",
                    message="correctness.digestMatch.ok=true but independent digest checks found mismatches",
                    report=str(report_path),
                )
            )

    # Independent regex extraction from HLS/Vivado reports.
    reports_obj = hardware.get("reports") if isinstance(hardware.get("reports"), dict) else {}
    files_list = reports_obj.get("files") if isinstance(reports_obj.get("files"), list) else []
    resolved_reports: list[Path] = []
    for item in files_list:
        p = _resolve_path(repo_root, report_dir, item)
        if p is not None:
            resolved_reports.append(p)

    def _find_report_by_name(name_fragment: str, *, exact_name: str | None = None) -> Path | None:
        if exact_name is not None:
            for p in resolved_reports:
                if p.name == exact_name:
                    return p
        for p in resolved_reports:
            if name_fragment.lower() in p.name.lower():
                return p
        if exact_name is not None:
            for p in report_dir.rglob("*.rpt"):
                if p.name == exact_name:
                    return p
        for p in report_dir.rglob("*.rpt"):
            if name_fragment.lower() in p.name.lower():
                return p
        return None

    csynth_rpt = _find_report_by_name("nema_kernel_csynth.rpt", exact_name="nema_kernel_csynth.rpt")
    if csynth_rpt is None:
        csynth_rpt = _find_report_by_name("csynth.rpt", exact_name="csynth.rpt")
    if csynth_rpt is not None:
        text = _read_text(csynth_rpt)
        if text is not None:
            parsed_ii, parsed_latency = _parse_hls_summary_metrics(text)
            parsed_ii = _extract_first_num(
                text, [r"\bInterval-min[^0-9\-]*([0-9]+)", r"\bII[^0-9\-]*([0-9]+)"]
            ) if parsed_ii is None else parsed_ii
            parsed_latency = _extract_first_num(
                text, [r"\bLatency\s*\(cycles\)[^0-9\-]*([0-9]+)", r"\bLatency[^0-9\-]*([0-9]+)"]
            ) if parsed_latency is None else parsed_latency
            qor = hardware.get("qor") if isinstance(hardware.get("qor"), dict) else {}
            _compare_metric(
                findings,
                report=report_path,
                code="HLS_II_MISMATCH",
                parsed=parsed_ii,
                bench=qor.get("ii") or ((qor.get("timingOrLatency") or {}).get("ii") if isinstance(qor.get("timingOrLatency"), dict) else None),
                tolerance=0.0,
            )
            _compare_metric(
                findings,
                report=report_path,
                code="HLS_LATENCY_MISMATCH",
                parsed=parsed_latency,
                bench=qor.get("latencyCycles")
                or ((qor.get("timingOrLatency") or {}).get("latencyCycles") if isinstance(qor.get("timingOrLatency"), dict) else None),
                tolerance=0.0,
            )

    vivado = hardware.get("vivado") if isinstance(hardware.get("vivado"), dict) else {}
    timing_report_path = _resolve_path(repo_root, report_dir, vivado.get("timingReport"))
    if timing_report_path is None:
        timing_report_path = _find_report_by_name("vivado_timing_summary.rpt", exact_name="vivado_timing_summary.rpt")
    if timing_report_path is None:
        timing_report_path = _find_report_by_name("timing_summary")
    if timing_report_path is not None:
        text = _read_text(timing_report_path)
        if text is not None:
            parsed_wns = _extract_first_num(text, [r"\bWNS(?:\(ns\))?\s*[:=]\s*(-?[0-9]+(?:\.[0-9]+)?)"])
            if parsed_wns is None:
                parsed_wns = _extract_design_timing_wns(text)
            _compare_metric(
                findings,
                report=report_path,
                code="VIVADO_WNS_MISMATCH",
                parsed=parsed_wns,
                bench=vivado.get("wns")
                or ((vivado.get("timing") or {}).get("wns") if isinstance(vivado.get("timing"), dict) else None),
                tolerance=1e-3,
            )

    util_report_path = _resolve_path(repo_root, report_dir, vivado.get("utilizationReport"))
    if util_report_path is None:
        util_report_path = _find_report_by_name("vivado_utilization.rpt", exact_name="vivado_utilization.rpt")
    if util_report_path is None:
        util_report_path = _find_report_by_name("utilization")
    if util_report_path is not None:
        text = _read_text(util_report_path)
        if text is not None:
            parsed_lut = _extract_first_num(
                text,
                [
                    r"\|\s*(?:CLB LUTs\*?|Slice LUTs\*?)\s*\|\s*([0-9,]+(?:\.[0-9]+)?)\s*\|",
                    r"\b(?:CLB LUTs|Slice LUTs)\b[^0-9\-]*([0-9,]+(?:\.[0-9]+)?)",
                ],
            )
            bench_lut = None
            if isinstance(vivado.get("utilization"), dict):
                bench_lut = vivado["utilization"].get("lut")
            if bench_lut is None and isinstance(vivado.get("util"), dict):
                bench_lut = vivado["util"].get("lut")
            _compare_metric(
                findings,
                report=report_path,
                code="VIVADO_LUT_MISMATCH",
                parsed=parsed_lut,
                bench=bench_lut,
                tolerance=0.0,
            )

    return findings


def _print_human(report_paths: list[Path], findings: list[Finding]) -> None:
    errors = [f for f in findings if f.level == "ERROR"]
    warnings = [f for f in findings if f.level != "ERROR"]
    print(f"checked_reports={len(report_paths)}")
    print(f"errors={len(errors)} warnings={len(warnings)}")
    for finding in findings:
        print(f"[{finding.level}] {finding.code} {finding.report}: {finding.message}")


def _print_json(report_paths: list[Path], findings: list[Finding]) -> None:
    payload = {
        "ok": not any(f.level == "ERROR" for f in findings),
        "checkedReports": [str(p) for p in report_paths],
        "findings": [
            {
                "level": f.level,
                "code": f.code,
                "report": f.report,
                "message": f.message,
            }
            for f in findings
        ],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Independent consistency checker for NEMA bench artifacts.")
    parser.add_argument(
        "--bench-report",
        dest="bench_reports",
        action="append",
        default=[],
        help="Path to a bench_report.json (repeatable).",
    )
    parser.add_argument(
        "--paperA",
        action="store_true",
        help="Check Paper A relevant bench reports inferred from artifact tables/evidence.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output.",
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    report_paths: set[Path] = set()

    for value in args.bench_reports:
        p = Path(value)
        if not p.is_absolute():
            p = repo_root / p
        if p.exists():
            report_paths.add(p.resolve())
        else:
            missing = Finding(
                level="ERROR",
                code="REPORT_PATH_MISSING",
                message=f"bench_report path does not exist: {value}",
                report=str(p),
            )
            findings = [missing]
            if args.json:
                _print_json([], findings)
            else:
                _print_human([], findings)
            return 1

    if args.paperA:
        report_paths.update(_collect_papera_reports(repo_root))

    if not report_paths:
        findings = [
            Finding(
                level="ERROR",
                code="NO_REPORTS",
                message="no bench_report.json inputs; pass --paperA or --bench-report",
                report="-",
            )
        ]
        if args.json:
            _print_json([], findings)
        else:
            _print_human([], findings)
        return 1

    sorted_reports = sorted(report_paths)
    findings: list[Finding] = []
    for report_path in sorted_reports:
        findings.extend(_validate_report(report_path, repo_root))

    # Stable ordering for deterministic output.
    findings.sort(key=lambda f: (f.level, f.code, f.report, f.message))

    if args.json:
        _print_json(sorted_reports, findings)
    else:
        _print_human(sorted_reports, findings)

    return 0 if not any(f.level == "ERROR" for f in findings) else 1


if __name__ == "__main__":
    raise SystemExit(main())
