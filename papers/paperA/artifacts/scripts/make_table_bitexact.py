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
        evidence_path = evidence_dir / evidence_name
        payload = _safe_load_json(evidence_path)
        if not payload:
            continue

        for key in ("relevantReportPaths",):
            value = payload.get(key)
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

        checks = ((payload.get("benchManifestChecks") or {}).get("checks") or {})
        if isinstance(checks, dict):
            for check in checks.values():
                if not isinstance(check, dict):
                    continue
                verify_json = ((check.get("verify") or {}).get("json") or {})
                if isinstance(verify_json, dict):
                    candidate = verify_json.get("benchReport")
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


def _collect_verify_metadata(repo_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_path: dict[str, dict[str, Any]] = {}
    by_benchmark: dict[str, dict[str, Any]] = {}

    def _update(bench_report_value: str, verify_ok: Any, mismatches: Any) -> None:
        p = Path(bench_report_value)
        if not p.exists():
            return
        key = str(p.resolve())
        meta = {
            "verify_ok": verify_ok,
            "mismatches_len": len(mismatches) if isinstance(mismatches, list) else None,
        }
        by_path[key] = meta

        payload = _safe_load_json(p)
        if not payload:
            return
        model_id = str(payload.get("modelId") or "")
        target_id = str(((payload.get("bench") or {}).get("targetId")) or "")
        bench_id = _benchmark_id(model_id=model_id, target_id=target_id)
        if bench_id:
            by_benchmark[bench_id] = meta

    evidence_dir = repo_root / "papers" / "paperA" / "artifacts" / "evidence"
    for evidence_name in ("audit_software.json", "audit_hardware.json"):
        payload = _safe_load_json(evidence_dir / evidence_name)
        if not payload:
            continue
        checks = ((payload.get("benchManifestChecks") or {}).get("checks") or {})
        if not isinstance(checks, dict):
            continue
        for check in checks.values():
            if not isinstance(check, dict):
                continue
            verify_json = ((check.get("verify") or {}).get("json") or {})
            if not isinstance(verify_json, dict):
                continue
            bench_report = verify_json.get("benchReport")
            if not isinstance(bench_report, str):
                continue
            _update(
                bench_report_value=bench_report,
                verify_ok=verify_json.get("ok"),
                mismatches=verify_json.get("mismatches"),
            )

    for verify_json_path in sorted(repo_root.glob("build/**/verify*.json")):
        payload = _safe_load_json(verify_json_path)
        if not payload:
            continue
        bench_report = payload.get("benchReport")
        if not isinstance(bench_report, str):
            continue
        _update(
            bench_report_value=bench_report,
            verify_ok=payload.get("ok"),
            mismatches=payload.get("mismatches"),
        )

    return by_path, by_benchmark


def _parse_created_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    txt = value.strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _as_bool_text(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "-"


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


@dataclass(frozen=True)
class BitExactRow:
    benchmark_id: str
    model_id: str
    verify_ok: str
    mismatches_len: str
    digest_match_ok: str
    ticks: str
    ir_sha256: str
    bench_report_path: str


def _render_tex(rows: list[BitExactRow], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("\\begin{tabular}{|l|l|c|c|c|c|l|l|}")
    lines.append("\\hline")
    lines.append(
        "benchmarkId & modelId & verify\\_ok & mismatches\\_len & digestMatchOk & ticks & ir\\_sha256 & bench\\_report\\_path \\\\"
    )
    lines.append("\\hline")
    for row in rows:
        cells = [
            row.benchmark_id,
            row.model_id,
            row.verify_ok,
            row.mismatches_len,
            row.digest_match_ok,
            row.ticks,
            row.ir_sha256,
            row.bench_report_path,
        ]
        lines.append(" & ".join(_latex_escape(c) for c in cells) + " \\\\")
    lines.append("\\hline")
    lines.append("\\end{tabular}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate bit-exact result table (CSV + LaTeX) for Paper A.")
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=Path("papers/paperA/artifacts/tables/results_bitexact.csv"),
    )
    parser.add_argument(
        "--out-tex",
        type=Path,
        default=Path("papers/paperA/artifacts/tables/results_bitexact.tex"),
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    verify_meta_by_path, verify_meta_by_benchmark = _collect_verify_metadata(repo_root)
    report_paths = _collect_candidate_report_paths(repo_root)

    selected: dict[tuple[str, str], tuple[int, datetime, BitExactRow]] = {}

    for report_path in report_paths:
        payload = _safe_load_json(report_path)
        if not payload:
            continue

        model_id = str(payload.get("modelId") or "")
        target_id = str(((payload.get("bench") or {}).get("targetId")) or "")
        benchmark_id = _benchmark_id(model_id=model_id, target_id=target_id)
        if benchmark_id is None:
            continue

        created_at = _parse_created_at(payload.get("createdAt"))
        if created_at is None:
            created_at = datetime.fromtimestamp(report_path.stat().st_mtime, tz=timezone.utc)
        source_priority = _source_priority(report_path, repo_root)

        verify_info = verify_meta_by_path.get(str(report_path.resolve()))
        if verify_info is None:
            verify_info = verify_meta_by_benchmark.get(benchmark_id, {})
        mismatches_len = verify_info.get("mismatches_len")

        row = BitExactRow(
            benchmark_id=benchmark_id,
            model_id=model_id or "-",
            verify_ok=_as_bool_text(verify_info.get("verify_ok")),
            mismatches_len=str(mismatches_len) if isinstance(mismatches_len, int) else "-",
            digest_match_ok=_as_bool_text(
                (((payload.get("correctness") or {}).get("digestMatch") or {}).get("ok"))
            ),
            ticks=str(payload.get("ticks")) if payload.get("ticks") is not None else "-",
            ir_sha256=str(payload.get("irSha256") or "-"),
            bench_report_path=report_path.relative_to(repo_root).as_posix(),
        )

        key = (row.benchmark_id, row.model_id)
        prev = selected.get(key)
        if (
            prev is None
            or source_priority < prev[0]
            or (source_priority == prev[0] and created_at > prev[1])
        ):
            selected[key] = (source_priority, created_at, row)

    rows = [v[2] for v in selected.values()]
    rows.sort(key=lambda r: (r.benchmark_id, r.model_id))

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "benchmarkId",
                "modelId",
                "verify_ok",
                "mismatches_len",
                "digestMatchOk",
                "ticks",
                "ir_sha256",
                "bench_report_path",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.benchmark_id,
                    row.model_id,
                    row.verify_ok,
                    row.mismatches_len,
                    row.digest_match_ok,
                    row.ticks,
                    row.ir_sha256,
                    row.bench_report_path,
                ]
            )

    _render_tex(rows, args.out_tex)

    if not rows:
        print("warning: no relevant rows found for B1/B2/B3/B4/B6", file=sys.stderr)

    print(str(args.out_csv))
    print(str(args.out_tex))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
