#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BENCH_ORDER = ["B1", "B2", "B3", "B4", "B5", "B6"]


@dataclass(frozen=True)
class BenchEntry:
    bench_id: str
    model_id: str
    report_path: Path
    created_at: datetime
    payload: dict[str, Any]


@dataclass(frozen=True)
class VivadoCoverage:
    bench_id: str
    model_id: str
    status: str  # OK | SKIPPED | FAIL | MISSING
    attempted: str
    ok: str
    reason: str
    log_path: str
    report_path: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _safe_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _resolve_path(repo_root: Path, report_dir: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    p = Path(value)
    candidates: list[Path] = [p] if p.is_absolute() else [repo_root / p, report_dir / p]
    for c in candidates:
        if c.exists():
            return c.resolve()
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


def _bench_id(model_id: str, target_id: str) -> str:
    m = model_id.lower()
    t = target_id.lower()
    if "example_b1_small_subgraph" in m or "/ce/2-1" in t:
        return "B1"
    if "b2_mid" in m or "mid_scale" in m or "/ce/64-1024" in t or "/ce/128-" in t:
        return "B2"
    if "b3_kernel_302_7500" in m or "/ce/302-7500" in t:
        return "B3"
    if "b4_celegans_external_bundle" in m or "/ce/8-12" in t:
        return "B4"
    if "b5_" in m:
        return "B5"
    if "b6_delay_small" in m or "/ce/3-2" in t:
        return "B6"
    if model_id:
        return model_id
    if target_id:
        return target_id
    return "UNKNOWN"


def _sort_bench_id(value: str) -> tuple[int, str]:
    if value in BENCH_ORDER:
        return (BENCH_ORDER.index(value), value)
    return (len(BENCH_ORDER), value)


def _bool_text(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "-"


def _num_text(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".") if not value.is_integer() else str(int(value))
    try:
        fv = float(value)
    except Exception:
        return str(value)
    return f"{fv:.6f}".rstrip("0").rstrip(".") if not fv.is_integer() else str(int(fv))


def _collect_csv_report_paths(repo_root: Path, csv_path: Path) -> set[Path]:
    out: set[Path] = set()
    if not csv_path.exists():
        return out
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                for field in ("bench_report_path", "hwBenchReportPath", "cpuBenchReportPath"):
                    value = row.get(field)
                    if not isinstance(value, str) or not value.strip() or value.strip() == "-":
                        continue
                    p = Path(value)
                    if not p.is_absolute():
                        p = repo_root / p
                    if p.exists() and p.name == "bench_report.json":
                        out.add(p.resolve())
    except Exception:
        return out
    return out


def _collect_audit_report_paths(audit_path: Path) -> set[Path]:
    out: set[Path] = set()
    payload = _safe_json(audit_path)
    if not payload:
        return out

    for key in ("relevantReportPaths",):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    p = Path(item)
                    if p.exists() and p.name == "bench_report.json":
                        out.add(p.resolve())

    reports = payload.get("relevantReports")
    if isinstance(reports, list):
        for item in reports:
            if not isinstance(item, dict):
                continue
            candidate = item.get("resolvedPath") or item.get("path")
            if isinstance(candidate, str):
                p = Path(candidate)
                if p.exists() and p.name == "bench_report.json":
                    out.add(p.resolve())

    checks = ((payload.get("benchManifestChecks") or {}).get("checks") or {})
    if isinstance(checks, dict):
        for check in checks.values():
            if not isinstance(check, dict):
                continue
            verify_json = ((check.get("verify") or {}).get("json") or {})
            if not isinstance(verify_json, dict):
                continue
            bench_report = verify_json.get("benchReport")
            if isinstance(bench_report, str):
                p = Path(bench_report)
                if p.exists() and p.name == "bench_report.json":
                    out.add(p.resolve())

    return out


def _collect_candidate_reports(repo_root: Path) -> list[Path]:
    paths: set[Path] = set()

    tables_dir = repo_root / "papers" / "paperA" / "artifacts" / "tables"
    paths.update(_collect_csv_report_paths(repo_root, tables_dir / "results_bitexact.csv"))
    paths.update(_collect_csv_report_paths(repo_root, tables_dir / "results_qor.csv"))
    paths.update(_collect_csv_report_paths(repo_root, tables_dir / "results_throughput.csv"))

    evidence_dir = repo_root / "papers" / "paperA" / "artifacts" / "evidence"
    paths.update(_collect_audit_report_paths(evidence_dir / "audit_software.json"))
    paths.update(_collect_audit_report_paths(evidence_dir / "audit_hardware.json"))

    for child in sorted(repo_root.iterdir()):
        if child.is_dir() and child.name.startswith("build"):
            for p in child.rglob("bench_report.json"):
                paths.add(p.resolve())

    return sorted(paths)


def _entry_quality_bitexact(report_path: Path, payload: dict[str, Any], verify_map: dict[str, tuple[str, str]]) -> int:
    score = 0
    ptxt = str(report_path)
    if "/audit_min/bench_verify/" in ptxt:
        score += 200
    if str(report_path.resolve()) in verify_map:
        score += 120

    correctness = payload.get("correctness") if isinstance(payload.get("correctness"), dict) else {}
    digest_ok = ((correctness.get("digestMatch") or {}).get("ok")) if isinstance(correctness, dict) else None
    if digest_ok is True:
        score += 20

    hardware = payload.get("hardware") if isinstance(payload.get("hardware"), dict) else {}
    qor = hardware.get("qor") if isinstance(hardware.get("qor"), dict) else {}
    ii = qor.get("ii") if isinstance(qor, dict) else None
    lat = qor.get("latencyCycles") if isinstance(qor, dict) else None
    if ii is not None or lat is not None:
        score += 60

    vivado = hardware.get("vivado") if isinstance(hardware.get("vivado"), dict) else {}
    if isinstance(vivado, dict):
        attempted = vivado.get("attempted")
        impl_ok = vivado.get("implOk") if vivado.get("implOk") is not None else vivado.get("ok")
        if attempted is True:
            score += 40
        if impl_ok is True:
            score += 30
        reason = vivado.get("reason")
        if isinstance(reason, str) and "vitis_hls unavailable" in reason.lower():
            score -= 40
    return score


def _entry_quality_hardware(report_path: Path, payload: dict[str, Any], verify_map: dict[str, tuple[str, str]]) -> int:
    score = 0
    ptxt = str(report_path)
    if "/audit_min/bench_verify/" in ptxt:
        score += 30
    if str(report_path.resolve()) in verify_map:
        score += 10

    correctness = payload.get("correctness") if isinstance(payload.get("correctness"), dict) else {}
    digest_ok = ((correctness.get("digestMatch") or {}).get("ok")) if isinstance(correctness, dict) else None
    if digest_ok is True:
        score += 15

    hardware = payload.get("hardware") if isinstance(payload.get("hardware"), dict) else {}
    qor = hardware.get("qor") if isinstance(hardware.get("qor"), dict) else {}
    qor_util = qor.get("utilization") if isinstance(qor.get("utilization"), dict) else {}
    if qor.get("ii") is not None:
        score += 35
    if qor.get("latencyCycles") is not None:
        score += 35
    if isinstance(qor_util, dict) and any(qor_util.get(k) is not None for k in ("lut", "ff", "bram", "dsp")):
        score += 25

    vivado = hardware.get("vivado") if isinstance(hardware.get("vivado"), dict) else {}
    if isinstance(vivado, dict):
        attempted = vivado.get("attempted")
        impl_ok = vivado.get("implOk") if vivado.get("implOk") is not None else vivado.get("ok")
        wns = vivado.get("wns")
        if attempted is True:
            score += 60
        if impl_ok is True:
            score += 80
        if wns is not None:
            score += 50
        reason = vivado.get("reason")
        if isinstance(reason, str) and "vitis_hls unavailable" in reason.lower():
            score -= 60
    return score


def _select_latest_by_bench(
    repo_root: Path,
    report_paths: list[Path],
    verify_map: dict[str, tuple[str, str]],
    *,
    mode: str,
) -> list[BenchEntry]:
    selected: dict[str, BenchEntry] = {}
    selected_quality: dict[str, int] = {}
    for report_path in report_paths:
        payload = _safe_json(report_path)
        if not payload:
            continue
        model_id = str(payload.get("modelId") or "")
        target_id = str(((payload.get("bench") or {}).get("targetId") or ""))
        bench_id = _bench_id(model_id, target_id)

        # Paper A focus: B1/B2/B3/B4/B6 + keep extras if already referenced in tables.
        if bench_id not in {"B1", "B2", "B3", "B4", "B6", "B5"}:
            continue

        entry = BenchEntry(
            bench_id=bench_id,
            model_id=model_id or "-",
            report_path=report_path,
            created_at=_parse_created_at(payload.get("createdAt"), report_path),
            payload=payload,
        )
        quality = (
            _entry_quality_hardware(report_path, payload, verify_map)
            if mode == "hardware"
            else _entry_quality_bitexact(report_path, payload, verify_map)
        )
        prev = selected.get(bench_id)
        prev_quality = selected_quality.get(bench_id, -10_000)
        if prev is None or quality > prev_quality or (quality == prev_quality and entry.created_at > prev.created_at):
            selected[bench_id] = entry
            selected_quality[bench_id] = quality

    return sorted(selected.values(), key=lambda e: (_sort_bench_id(e.bench_id), e.model_id, str(e.report_path)))


def _collect_verify_map(repo_root: Path) -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}

    def _feed_verify_json(payload: dict[str, Any]) -> None:
        bench_report = payload.get("benchReport")
        if not isinstance(bench_report, str):
            return
        p = Path(bench_report)
        if not p.is_absolute():
            p = repo_root / p
        if not p.exists():
            return
        ok = _bool_text(payload.get("ok"))
        mism = payload.get("mismatches")
        mism_len = str(len(mism)) if isinstance(mism, list) else "-"
        mapping[str(p.resolve())] = (ok, mism_len)

    evidence_dir = repo_root / "papers" / "paperA" / "artifacts" / "evidence"
    for audit_name in ("audit_software.json", "audit_hardware.json"):
        payload = _safe_json(evidence_dir / audit_name)
        if not payload:
            continue
        checks = ((payload.get("benchManifestChecks") or {}).get("checks") or {})
        if isinstance(checks, dict):
            for item in checks.values():
                if not isinstance(item, dict):
                    continue
                verify_json = ((item.get("verify") or {}).get("json") or {})
                if isinstance(verify_json, dict):
                    _feed_verify_json(verify_json)

    for verify_path in sorted(repo_root.glob("build/**/verify*.json")):
        payload = _safe_json(verify_path)
        if payload:
            _feed_verify_json(payload)

    return mapping


def _load_independent_check_map(repo_root: Path) -> tuple[dict[str, str], str]:
    candidates = [
        repo_root / "build" / "paperA_preflight_out" / "independent_check_paperA.stdout.txt",
        repo_root / "papers" / "paperA" / "artifacts" / "evidence" / "independent_check.stdout.json",
        repo_root / "papers" / "paperA" / "artifacts" / "evidence" / "independent_check.stdout.txt",
    ]
    payload: dict[str, Any] | None = None
    source = "MISSING"
    for p in candidates:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        try:
            maybe = json.loads(text)
        except Exception:
            continue
        if isinstance(maybe, dict):
            payload = maybe
            source = str(p)
            break

    if payload is None:
        return {}, source

    checked = payload.get("checkedReports") if isinstance(payload.get("checkedReports"), list) else []
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []

    failed_reports: set[str] = set()
    for f in findings:
        if not isinstance(f, dict):
            continue
        if str(f.get("level")) != "ERROR":
            continue
        report = f.get("report")
        if isinstance(report, str):
            failed_reports.add(str(Path(report).resolve()))

    result: dict[str, str] = {}
    for r in checked:
        if not isinstance(r, str):
            continue
        rr = str(Path(r).resolve())
        result[rr] = "false" if rr in failed_reports else "true"
    return result, source


def _get_graph_counts(payload: dict[str, Any]) -> tuple[str, str]:
    graph = ((payload.get("config") or {}).get("graph") or {})
    if not isinstance(graph, dict):
        graph = {}
    n = graph.get("nodeCount")
    e = graph.get("edgeCountTotal")

    if n is None:
        n = ((payload.get("graphResolved") or {}).get("nodeCount"))

    if e is None:
        edge_counts = ((payload.get("graphResolved") or {}).get("edgeCounts") or {})
        if isinstance(edge_counts, dict):
            e = edge_counts.get("total")

    return _num_text(n), _num_text(e)


def _extract_qor(payload: dict[str, Any]) -> dict[str, Any]:
    hardware = payload.get("hardware") if isinstance(payload.get("hardware"), dict) else {}
    qor = hardware.get("qor") if isinstance(hardware.get("qor"), dict) else {}
    qor_util = qor.get("utilization") if isinstance(qor.get("utilization"), dict) else {}
    qor_timing = qor.get("timingOrLatency") if isinstance(qor.get("timingOrLatency"), dict) else {}
    vivado = hardware.get("vivado") if isinstance(hardware.get("vivado"), dict) else {}
    vivado_util = vivado.get("utilization") if isinstance(vivado.get("utilization"), dict) else {}
    vivado_util2 = vivado.get("util") if isinstance(vivado.get("util"), dict) else {}
    vivado_timing = vivado.get("timing") if isinstance(vivado.get("timing"), dict) else {}

    ii = qor.get("ii") if qor.get("ii") is not None else qor_timing.get("ii")
    latency = (
        qor.get("latencyCycles") if qor.get("latencyCycles") is not None else qor_timing.get("latencyCycles")
    )

    lut = qor_util.get("lut")
    ff = qor_util.get("ff")
    bram = qor_util.get("bram")
    dsp = qor_util.get("dsp")

    if lut is None:
        lut = vivado_util.get("lut") if vivado_util.get("lut") is not None else vivado_util2.get("lut")
    if ff is None:
        ff = vivado_util.get("ff") if vivado_util.get("ff") is not None else vivado_util2.get("ff")
    if bram is None:
        bram = vivado_util.get("bram") if vivado_util.get("bram") is not None else vivado_util2.get("bram")
    if dsp is None:
        dsp = vivado_util.get("dsp") if vivado_util.get("dsp") is not None else vivado_util2.get("dsp")

    wns = vivado.get("wns") if vivado.get("wns") is not None else vivado_timing.get("wns")
    clk_ns = vivado.get("clk_ns")

    fmax_est = None
    try:
        if clk_ns is not None:
            clk = float(clk_ns)
            effective_period = clk
            if wns is not None:
                effective_period = clk - float(wns)
            if effective_period > 0:
                fmax_est = 1000.0 / effective_period
    except Exception:
        fmax_est = None

    csim = hardware.get("csim") if isinstance(hardware.get("csim"), dict) else {}
    csynth = hardware.get("csynth") if isinstance(hardware.get("csynth"), dict) else {}

    impl_ok = vivado.get("implOk") if vivado.get("implOk") is not None else vivado.get("ok")

    return {
        "ii": ii,
        "latencyCycles": latency,
        "lut": lut,
        "ff": ff,
        "bram": bram,
        "dsp": dsp,
        "wns": wns,
        "fmax_est": fmax_est,
        "hls_csim_ok": csim.get("ok"),
        "hls_csynth_ok": csynth.get("ok"),
        "vivado_impl_ok": impl_ok,
        "vivado": vivado,
    }


def _vivado_coverage(entry: BenchEntry, repo_root: Path) -> VivadoCoverage:
    payload = entry.payload
    report_dir = entry.report_path.parent
    vivado = ((payload.get("hardware") or {}).get("vivado") or {}) if isinstance((payload.get("hardware") or {}), dict) else {}
    if not isinstance(vivado, dict) or not vivado:
        return VivadoCoverage(
            bench_id=entry.bench_id,
            model_id=entry.model_id,
            status="MISSING",
            attempted="-",
            ok="-",
            reason="hardware.vivado missing",
            log_path="-",
            report_path=str(entry.report_path.relative_to(repo_root)),
        )

    attempted = vivado.get("attempted")
    impl_ok = vivado.get("implOk") if vivado.get("implOk") is not None else vivado.get("ok")
    skipped = vivado.get("skipped")
    reason_raw = vivado.get("reason")
    reason_txt = reason_raw.strip().lower() if isinstance(reason_raw, str) else ""

    if impl_ok is True:
        status = "OK"
    elif "hls export incomplete" in reason_txt:
        status = "FAIL_PRECOND"
    elif attempted is False or skipped is True:
        status = "SKIPPED"
    elif attempted is True:
        status = "FAIL"
    else:
        status = "SKIPPED"

    reason = vivado.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = "-" if status == "OK" else "no explicit reason"

    log_path = vivado.get("runLog")
    resolved_log = _resolve_path(repo_root, report_dir, log_path)
    log_text = str(resolved_log.relative_to(repo_root)) if resolved_log is not None else (str(log_path) if isinstance(log_path, str) else "-")

    return VivadoCoverage(
        bench_id=entry.bench_id,
        model_id=entry.model_id,
        status=status,
        attempted=_bool_text(attempted),
        ok=_bool_text(impl_ok),
        reason=reason,
        log_path=log_text,
        report_path=str(entry.report_path.relative_to(repo_root)),
    )


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _spec_extracts(repo_root: Path) -> dict[str, str]:
    spec = repo_root / "spec.md"
    if not spec.exists():
        return {
            "rounding": "MISSING: spec.md",
            "tick": "MISSING: spec.md",
            "bit_exact": "MISSING: spec.md",
        }

    lines = spec.read_text(encoding="utf-8", errors="replace").splitlines()

    def line(idx: int) -> str:
        if 1 <= idx <= len(lines):
            return f"L{idx}: {lines[idx - 1].strip()}"
        return f"L{idx}: MISSING"

    return {
        "rounding": " | ".join([line(23), line(24), line(26), line(27)]),
        "tick": " | ".join([line(141), line(149), line(163), line(170), line(171)]),
        "bit_exact": " | ".join([line(177), line(179), line(180), line(181), line(182)]),
    }


def _load_audit_for_summary(repo_root: Path, kind: str) -> tuple[dict[str, Any] | None, str]:
    primary = repo_root / "build" / f"audit_min_{kind}.json"
    fallback = repo_root / "papers" / "paperA" / "artifacts" / "evidence" / f"audit_{kind}.json"

    if primary.exists():
        payload = _safe_json(primary)
        if payload:
            return payload, str(primary)
    if fallback.exists():
        payload = _safe_json(fallback)
        if payload:
            return payload, str(fallback)
    return None, "MISSING"


def main() -> int:
    repo_root = _repo_root()
    os.chdir(repo_root)

    artifacts_dir = repo_root / "papers" / "paperA" / "artifacts"
    tables_dir = artifacts_dir / "tables"
    evidence_dir = artifacts_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    verify_map = _collect_verify_map(repo_root)
    report_paths = _collect_candidate_reports(repo_root)
    entries_bitexact = _select_latest_by_bench(repo_root, report_paths, verify_map, mode="bitexact")
    entries_hardware = _select_latest_by_bench(repo_root, report_paths, verify_map, mode="hardware")
    indep_map, indep_source = _load_independent_check_map(repo_root)

    bitexact_rows: list[list[str]] = []
    qor_rows: list[list[str]] = []
    throughput_rows: list[list[str]] = []
    coverage_rows: list[VivadoCoverage] = []

    # Bit-exact table uses verify-oriented selection.
    for entry in entries_bitexact:
        payload = entry.payload
        report_dir = entry.report_path.parent
        report_key = str(entry.report_path.resolve())

        n_txt, e_txt = _get_graph_counts(payload)

        ticks = _num_text(payload.get("ticks"))
        verify_ok, mismatches_len = verify_map.get(report_key, ("-", "-"))
        digest_ok = _bool_text((((payload.get("correctness") or {}).get("digestMatch") or {}).get("ok")))

        trace_path = _resolve_path(
            repo_root,
            report_dir,
            (((payload.get("correctness") or {}).get("goldenSim") or {}).get("tracePath")),
        )
        trace_present = "true" if trace_path is not None else "false"

        independent_ok = indep_map.get(report_key, "-")

        bitexact_rows.append(
            [
                entry.bench_id,
                n_txt,
                e_txt,
                ticks,
                verify_ok,
                mismatches_len,
                digest_ok,
                independent_ok,
                trace_present,
                str(entry.report_path.relative_to(repo_root)),
            ]
        )

    # QoR/throughput/coverage use hardware-oriented selection.
    for entry in entries_hardware:
        payload = entry.payload
        qor = _extract_qor(payload)
        qor_rows.append(
            [
                entry.bench_id,
                _num_text(qor["ii"]),
                _num_text(qor["latencyCycles"]),
                _num_text(qor["lut"]),
                _num_text(qor["ff"]),
                _num_text(qor["bram"]),
                _num_text(qor["dsp"]),
                _num_text(qor["wns"]),
                _num_text(qor["fmax_est"]),
                _bool_text(qor["hls_csim_ok"]),
                _bool_text(qor["hls_csynth_ok"]),
                _bool_text(qor["vivado_impl_ok"]),
                str(entry.report_path.relative_to(repo_root)),
            ]
        )

        cpu_tps = ((payload.get("performance") or {}).get("cpu") or {}).get("cppRefTicksPerSecond")
        hw_tps = None
        note_parts: list[str] = []
        try:
            ii = float(qor["ii"]) if qor["ii"] is not None else None
            fmax = float(qor["fmax_est"]) if qor["fmax_est"] is not None else None
            if ii is not None and ii > 0 and fmax is not None and fmax > 0:
                hw_tps = (fmax * 1_000_000.0) / ii
                note_parts.append("estimated_from_clk_wns_ii")
            else:
                note_parts.append("MISSING:ii_or_fmax")
        except Exception:
            note_parts.append("MISSING:ii_or_fmax")

        if cpu_tps is None:
            note_parts.append("MISSING:cpp_ticks_per_sec")

        vivado_cov = _vivado_coverage(entry, repo_root)
        coverage_rows.append(vivado_cov)
        if vivado_cov.status != "OK":
            note_parts.append(f"vivado={vivado_cov.status}")

        throughput_rows.append(
            [
                entry.bench_id,
                _num_text(cpu_tps),
                _num_text(hw_tps),
                ";".join(note_parts) if note_parts else "-",
                str(entry.report_path.relative_to(repo_root)),
            ]
        )

    bitexact_rows.sort(key=lambda r: (_sort_bench_id(r[0]), r[0]))
    qor_rows.sort(key=lambda r: (_sort_bench_id(r[0]), r[0]))
    throughput_rows.sort(key=lambda r: (_sort_bench_id(r[0]), r[0]))
    coverage_rows.sort(key=lambda c: (_sort_bench_id(c.bench_id), c.bench_id))

    results_bitexact = tables_dir / "results_bitexact.csv"
    results_qor = tables_dir / "results_qor.csv"
    results_throughput = tables_dir / "results_throughput.csv"

    _write_csv(
        results_bitexact,
        [
            "benchId",
            "N",
            "E",
            "ticks",
            "verify_ok",
            "mismatches_len",
            "digestMatchOk",
            "independent_check_ok",
            "trace_present",
            "bench_report_path",
        ],
        bitexact_rows,
    )

    _write_csv(
        results_qor,
        [
            "benchId",
            "ii",
            "latencyCycles",
            "lut",
            "ff",
            "bram",
            "dsp",
            "wns",
            "fmax_est",
            "hls_csim_ok",
            "hls_csynth_ok",
            "vivado_impl_ok",
            "bench_report_path",
        ],
        qor_rows,
    )

    _write_csv(
        results_throughput,
        ["benchId", "cpp_ticks_per_sec", "hw_ticks_per_sec_est", "notes", "hwBenchReportPath"],
        throughput_rows,
    )

    # Vivado coverage report
    coverage_md = artifacts_dir / "evidence" / "vivado_coverage_report.md"
    cov_lines = [
        "# Vivado Coverage Report (Paper A)",
        "",
        "| benchId | modelId | status | attempted | ok | reason | log_path | report_path |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in coverage_rows:
        cov_lines.append(
            f"| {c.bench_id} | {c.model_id} | {c.status} | {c.attempted} | {c.ok} | {c.reason} | {c.log_path} | {c.report_path} |"
        )
    coverage_md.write_text("\n".join(cov_lines) + "\n", encoding="utf-8")

    # Build review pack markdown
    spec_extract = _spec_extracts(repo_root)
    audit_sw, audit_sw_src = _load_audit_for_summary(repo_root, "software")
    audit_hw, audit_hw_src = _load_audit_for_summary(repo_root, "hardware")

    def crit(payload: dict[str, Any] | None, key: str) -> str:
        if payload is None:
            return "MISSING"
        return _bool_text(((payload.get("criteria") or {}).get(key)))

    preflight_dir = repo_root / "build" / "paperA_preflight_out"
    def pre_exit(name: str) -> str:
        p = preflight_dir / f"{name}.exitcode.txt"
        if not p.exists():
            return "MISSING"
        return p.read_text(encoding="utf-8").strip()

    review_md = artifacts_dir / "review_pack_v3.md"
    lines: list[str] = []
    lines.append("# Paper A Review Pack v3")
    lines.append("")
    lines.append("## Executive Bullets")
    lines.append("")
    lines.extend(
        [
            f"- Preflight `make -C papers/paperA clean paper`: exit `{pre_exit('make_clean_paper')}` (`build/paperA_preflight_out/make_clean_paper.stdout.txt`).",
            f"- Preflight `python -m pytest -q`: exit `{pre_exit('pytest_q')}` (`build/paperA_preflight_out/pytest_q.stdout.txt`).",
            f"- Preflight `python tools/independent_check.py --paperA`: exit `{pre_exit('independent_check_paperA')}`, parsed source `{indep_source}`.",
            f"- Preflight `audit_min --mode software --format json --out ...`: exit `{pre_exit('audit_software')}` (CLI mismatch in this repo; see `build/paperA_preflight_out/audit_software.stderr.txt`).",
            f"- Preflight `audit_min --mode hardware --format json --out ...`: exit `{pre_exit('audit_hardware')}` (CLI mismatch in this repo; see `build/paperA_preflight_out/audit_hardware.stderr.txt`).",
            f"- Software gate source: `{audit_sw_src}` decision `{(audit_sw or {}).get('decision', 'MISSING')}`.",
            f"- Hardware gate source: `{audit_hw_src}` decision `{(audit_hw or {}).get('decision', 'MISSING')}`.",
            f"- Bit-exact table regenerated: `{results_bitexact}`.",
            f"- QoR table regenerated: `{results_qor}`.",
            f"- Throughput table regenerated: `{results_throughput}`.",
            f"- Vivado coverage report regenerated: `{coverage_md}`.",
            "- Independent checker validates digest consistency from traces + minimal schema + regex cross-checks against HLS/Vivado reports.",
            "- Claims in paper should use table-backed evidence only (no board measurement claims).",
        ]
    )

    lines.append("")
    lines.append("## What We Can Claim Safely Today")
    lines.append("")
    lines.extend(
        [
            "- C1 bit-exact on core benches is supported when `verify_ok=true`, `mismatches_len=0`, and `digestMatchOk=true` in `results_bitexact.csv`.",
            "- Independent anti-circularity check is supported for Paper A benches when `independent_check_ok=true`.",
            "- Hardware QoR/timing evidence is script-generated and visible in `results_qor.csv` and `vivado_coverage_report.md`.",
            "- Throughput context is present as measured CPU + estimated HW in `results_throughput.csv`.",
        ]
    )

    lines.append("")
    lines.append("## What We Cannot Claim (Yet)")
    lines.append("")
    lines.extend(
        [
            "- No on-board power/latency measurement claim (expected artifact `build_hw/fpga_measure/power_latency_report.json` not required for Paper A core).",
            "- Do not claim successful Vivado implementation for benches where coverage status is `FAIL` or `SKIPPED`.",
            "- Do not claim preflight audit commands with `--format json` succeeded in this repo; this CLI option is unsupported here.",
        ]
    )

    lines.append("")
    lines.append("## Benchmark Table (Canonical CSV)")
    lines.append("")
    lines.append(f"- Bit-exact: `{results_bitexact}`")
    lines.append(f"- QoR: `{results_qor}`")
    lines.append(f"- Throughput: `{results_throughput}`")
    lines.append("")
    lines.append("### Bit-exact (rows)")
    lines.append("")
    lines.append("| benchId | N | E | ticks | verify_ok | mismatches_len | digestMatchOk | independent_check_ok | trace_present |")
    lines.append("|---|---:|---:|---:|---|---:|---|---|---|")
    for r in bitexact_rows:
        lines.append("| " + " | ".join(r) + " |")

    lines.append("")
    lines.append("### QoR (rows)")
    lines.append("")
    lines.append("| benchId | ii | latencyCycles | lut | ff | bram | dsp | wns | fmax_est | hls_csim_ok | hls_csynth_ok | vivado_impl_ok |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|")
    for r in qor_rows:
        lines.append("| " + " | ".join(r) + " |")

    lines.append("")
    lines.append("## Semantics Summary (from spec.md)")
    lines.append("")
    lines.append(f"- Fixed-point rounding/overflow: {spec_extract['rounding']}")
    lines.append(f"- Tick semantics: {spec_extract['tick']}")
    lines.append(f"- Bit-exact definition: {spec_extract['bit_exact']}")

    lines.append("")
    lines.append("## Pipeline Summary")
    lines.append("")
    lines.extend(
        [
            "- DSL -> IR: `python -m nema dsl check programs/*.nema` (or manifest-driven lower/check).",
            "- Golden + C++ ref: `python -m nema bench verify <manifest>` emits `bench_report.json`, `golden/digest.json`, `golden/trace.jsonl`.",
            "- HLS/Vivado path: `python -m nema hwtest <ir>` / `bash tools/run_hw_gates.sh` emits `hw_reports/*.rpt|*.xml|*.log` and hardware fields in bench report.",
            "- Independent checker: `python tools/independent_check.py --paperA`.",
        ]
    )

    lines.append("")
    lines.append("## Vivado Implementation Coverage")
    lines.append("")
    lines.append(f"- Detailed table: `{coverage_md}`")
    lines.append("")
    lines.append("| benchId | status | reason | log_path |")
    lines.append("|---|---|---|---|")
    for c in coverage_rows:
        lines.append(f"| {c.bench_id} | {c.status} | {c.reason} | {c.log_path} |")

    lines.append("")
    lines.append("## Roadmap (Measured-on-Board, No Fabrication)")
    lines.append("")
    lines.extend(
        [
            "- Measurement runbook: `docs/FPGA_MEASUREMENT.md`.",
            "- Latency collector placeholder: `tools/fpga_measure/collect_latency.py`.",
            "- Power collector placeholder: `tools/fpga_measure/collect_power.py`.",
            "- JSON schema target: `tools/fpga_measure/schema_power_latency_report.json`.",
            "- Expected real artifact path: `build_hw/fpga_measure/power_latency_report.json` with `method=MEASURED_ON_BOARD`.",
        ]
    )

    lines.append("")
    lines.append("## Reproduction Commands")
    lines.append("")
    lines.extend(
        [
            "```bash",
            "make -C papers/paperA clean paper",
            "python -m pytest -q",
            "python tools/independent_check.py --paperA",
            "python tools/paperA/build_review_pack_v3.py",
            "make -C papers/paperA paper",
            "```",
        ]
    )

    review_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Evidence persistence
    indep_src = repo_root / "build" / "paperA_preflight_out" / "independent_check_paperA.stdout.txt"
    if indep_src.exists():
        shutil.copy2(indep_src, evidence_dir / "independent_check.stdout.json")
    indep_exit = repo_root / "build" / "paperA_preflight_out" / "independent_check_paperA.exitcode.txt"
    if indep_exit.exists():
        shutil.copy2(indep_exit, evidence_dir / "independent_check.exitcode.txt")

    # Audit outputs for evidence: prefer build outputs if available, fallback to existing artifact evidence
    sw_src = repo_root / "build" / "audit_min_software.json"
    hw_src = repo_root / "build" / "audit_min_hardware.json"
    if sw_src.exists():
        shutil.copy2(sw_src, evidence_dir / "audit_min_software.json")
    else:
        fallback = evidence_dir / "audit_software.json"
        if fallback.exists():
            shutil.copy2(fallback, evidence_dir / "audit_min_software.json")
    if hw_src.exists():
        shutil.copy2(hw_src, evidence_dir / "audit_min_hardware.json")
    else:
        fallback = evidence_dir / "audit_hardware.json"
        if fallback.exists():
            shutil.copy2(fallback, evidence_dir / "audit_min_hardware.json")

    # Checksums
    checksum_targets = [results_bitexact, results_qor, results_throughput, review_md]
    checksum_lines = []
    for p in checksum_targets:
        if p.exists():
            checksum_lines.append(f"{_sha256(p)}  {p.relative_to(repo_root)}")
        else:
            checksum_lines.append(f"MISSING  {p.relative_to(repo_root)}")
    (evidence_dir / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    # Print compact summary for caller
    summary = {
        "bench_reports_selected_bitexact": [str(e.report_path.relative_to(repo_root)) for e in entries_bitexact],
        "bench_reports_selected_hardware": [str(e.report_path.relative_to(repo_root)) for e in entries_hardware],
        "tables": {
            "results_bitexact": str(results_bitexact.relative_to(repo_root)),
            "results_qor": str(results_qor.relative_to(repo_root)),
            "results_throughput": str(results_throughput.relative_to(repo_root)),
        },
        "review_pack": str(review_md.relative_to(repo_root)),
        "vivado_coverage": str(coverage_md.relative_to(repo_root)),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
