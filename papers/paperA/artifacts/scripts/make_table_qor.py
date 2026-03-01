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


def _source_priority(path: Path, repo_root: Path) -> tuple[int, str]:
    # Canonical source precedence for Paper A tables:
    # 0) build/paperA_routeA
    # 1) build_hw OR build/audit_min/bench_verify (HW-gates / verified bench runs)
    # 2) build/bench_verify* (general bench verify runs)
    # 4) build/audit_min/*
    # 5) any other build/evidence source
    if _path_under(path, repo_root / "build" / "paperA_routeA"):
        return 0, "build/paperA_routeA"
    if _path_under(path, repo_root / "build_hw"):
        return 1, "build_hw"
    if _path_under(path, repo_root / "build" / "audit_min" / "bench_verify"):
        return 1, "build/audit_min/bench_verify"
    if _path_under(path, repo_root / "build" / "bench_verify"):
        return 2, "build/bench_verify*"
    if _path_under(path, repo_root / "build" / "audit_min"):
        return 4, "build/audit_min"
    return 5, "other"


def _hw_quality_score(payload: dict[str, Any]) -> int:
    hardware = payload.get("hardware") if isinstance(payload.get("hardware"), dict) else {}
    if not isinstance(hardware, dict):
        return 0
    toolchain = (hardware.get("toolchain") or {}) if isinstance(hardware.get("toolchain"), dict) else {}
    csim = (hardware.get("csim") or {}) if isinstance(hardware.get("csim"), dict) else {}
    csynth = (hardware.get("csynth") or {}) if isinstance(hardware.get("csynth"), dict) else {}
    cosim = (hardware.get("cosim") or {}) if isinstance(hardware.get("cosim"), dict) else {}
    vivado = (hardware.get("vivado") or {}) if isinstance(hardware.get("vivado"), dict) else {}

    score = 0
    if toolchain.get("available") is True:
        score += 100
    if csim.get("ok") is True:
        score += 30
    if csynth.get("ok") is True:
        score += 30
    if cosim.get("ok") is True:
        score += 10
    if vivado.get("attempted") is True:
        score += 20
    if vivado.get("implOk") is True or vivado.get("ok") is True:
        score += 60
    if isinstance(vivado.get("wns"), (int, float)):
        score += 15
    return score


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


def _to_text(value: Any) -> str:
    if value is None:
        return "-"
    return str(value)


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


def _pick_num(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


@dataclass(frozen=True)
class QorRow:
    benchmark_id: str
    model_id: str
    ii: str
    latency_cycles: str
    lut: str
    ff: str
    bram: str
    dsp: str
    wns: str
    csim_ok: str
    csynth_ok: str
    cosim_ok: str
    vivado_impl_ok: str
    vivado_impl_status: str
    vivado_impl_reason: str
    chosen_bench_report_path: str


def _vivado_status_reason(vivado: dict[str, Any]) -> tuple[str, str]:
    attempted = vivado.get("attempted")
    skipped = vivado.get("skipped")
    impl_ok = vivado.get("implOk")
    ok = vivado.get("ok")
    reason_raw = vivado.get("reason")
    reason = str(reason_raw).strip() if isinstance(reason_raw, str) and str(reason_raw).strip() else ""
    reason_lc = reason.lower()

    if impl_ok is True or ok is True:
        return "OK", reason or "-"

    if "hls export incomplete" in reason_lc:
        return "FAIL_PRECOND", reason

    if attempted is False or skipped is True:
        return "SKIPPED", reason or "not attempted"

    if attempted is True:
        return "FAIL", reason or "vivado impl failed"

    # Unknown/absent metadata is treated as not attempted to avoid conflating with fail.
    return "SKIPPED", reason or "not attempted"


def _render_tex(rows: list[QorRow], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("\\begin{tabular}{|l|c|c|c|c|c|c|c|c|c|c|c|c|l|}")
    lines.append("\\hline")
    lines.append(
        "benchmarkId & ii & latencyCycles & lut & ff & bram & dsp & wns & csim\\_ok & csynth\\_ok & cosim\\_ok & vivado\\_impl\\_ok & vivado\\_impl\\_status & vivado\\_impl\\_reason \\\\"
    )
    lines.append("\\hline")
    for row in rows:
        cells = [
            row.benchmark_id,
            row.ii,
            row.latency_cycles,
            row.lut,
            row.ff,
            row.bram,
            row.dsp,
            row.wns,
            row.csim_ok,
            row.csynth_ok,
            row.cosim_ok,
            row.vivado_impl_ok,
            row.vivado_impl_status,
            row.vivado_impl_reason,
        ]
        lines.append(" & ".join(_latex_escape(c) for c in cells) + " \\\\")
    lines.append("\\hline")
    lines.append("\\end{tabular}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate QoR result table (CSV + LaTeX) for Paper A.")
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=Path("papers/paperA/artifacts/tables/results_qor.csv"),
    )
    parser.add_argument(
        "--out-tex",
        type=Path,
        default=Path("papers/paperA/artifacts/tables/results_qor.tex"),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print selected bench_report path per benchmark and selection rationale.",
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    report_paths = _collect_candidate_report_paths(repo_root)
    selected: dict[tuple[str, str], tuple[int, int, datetime, QorRow, str]] = {}

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
        source_priority, source_label = _source_priority(report_path, repo_root)
        hw_quality = _hw_quality_score(payload)

        hardware = payload.get("hardware") if isinstance(payload.get("hardware"), dict) else {}
        qor = hardware.get("qor") if isinstance(hardware.get("qor"), dict) else {}
        qor_util = qor.get("utilization") if isinstance(qor.get("utilization"), dict) else {}
        qor_tol = qor.get("timingOrLatency") if isinstance(qor.get("timingOrLatency"), dict) else {}
        vivado = hardware.get("vivado") if isinstance(hardware.get("vivado"), dict) else {}
        vivado_util = vivado.get("utilization") if isinstance(vivado.get("utilization"), dict) else {}
        vivado_util_2 = vivado.get("util") if isinstance(vivado.get("util"), dict) else {}
        vivado_timing = vivado.get("timing") if isinstance(vivado.get("timing"), dict) else {}

        vivado_impl_status, vivado_impl_reason = _vivado_status_reason(vivado)
        impl_ok_val = vivado.get("implOk")
        if not isinstance(impl_ok_val, bool):
            ok_val = vivado.get("ok")
            if isinstance(ok_val, bool):
                impl_ok_val = ok_val
            elif vivado_impl_status in {"OK", "FAIL", "FAIL_PRECOND", "SKIPPED"}:
                impl_ok_val = vivado_impl_status == "OK"
            else:
                impl_ok_val = None
        row = QorRow(
            benchmark_id=benchmark_id,
            model_id=model_id or "-",
            ii=_to_text(_pick_num(qor.get("ii"), qor_tol.get("ii"))),
            latency_cycles=_to_text(_pick_num(qor.get("latencyCycles"), qor_tol.get("latencyCycles"))),
            lut=_to_text(_pick_num(qor_util.get("lut"), vivado_util.get("lut"), vivado_util_2.get("lut"))),
            ff=_to_text(_pick_num(qor_util.get("ff"), vivado_util.get("ff"), vivado_util_2.get("ff"))),
            bram=_to_text(_pick_num(qor_util.get("bram"), vivado_util.get("bram"), vivado_util_2.get("bram"))),
            dsp=_to_text(_pick_num(qor_util.get("dsp"), vivado_util.get("dsp"), vivado_util_2.get("dsp"))),
            wns=_to_text(_pick_num(vivado.get("wns"), vivado_timing.get("wns"))),
            csim_ok=_as_bool_text((hardware.get("csim") or {}).get("ok") if isinstance(hardware.get("csim"), dict) else None),
            csynth_ok=_as_bool_text((hardware.get("csynth") or {}).get("ok") if isinstance(hardware.get("csynth"), dict) else None),
            cosim_ok=_as_bool_text((hardware.get("cosim") or {}).get("ok") if isinstance(hardware.get("cosim"), dict) else None),
            vivado_impl_ok=_as_bool_text(impl_ok_val),
            vivado_impl_status=vivado_impl_status,
            vivado_impl_reason=vivado_impl_reason,
            chosen_bench_report_path=report_path.relative_to(repo_root).as_posix(),
        )

        key = (row.benchmark_id, row.model_id)
        prev = selected.get(key)
        should_take = False
        if prev is None:
            should_take = True
        else:
            prev_source_priority, prev_hw_quality, prev_created_at, _, _ = prev
            if source_priority < prev_source_priority:
                should_take = True
            elif source_priority == prev_source_priority:
                # Within the same source bucket, prefer richer HW evidence first.
                if hw_quality > prev_hw_quality:
                    should_take = True
                elif hw_quality == prev_hw_quality and created_at > prev_created_at:
                    should_take = True

        if should_take:
            debug_reason = (
                f"source={source_label} priority={source_priority} hw_quality={hw_quality} "
                f"created_at={created_at.isoformat()}"
            )
            selected[key] = (source_priority, hw_quality, created_at, row, debug_reason)

    rows = [v[3] for v in selected.values()]
    rows.sort(key=lambda r: (r.benchmark_id, r.model_id))

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "benchmarkId",
                "ii",
                "latencyCycles",
                "lut",
                "ff",
                "bram",
                "dsp",
                "wns",
                "csim_ok",
                "csynth_ok",
                "cosim_ok",
                "vivado_impl_ok",
                "vivado_impl_status",
                "vivado_impl_reason",
                "chosen_bench_report_path",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.benchmark_id,
                    row.ii,
                    row.latency_cycles,
                    row.lut,
                    row.ff,
                    row.bram,
                    row.dsp,
                    row.wns,
                    row.csim_ok,
                    row.csynth_ok,
                    row.cosim_ok,
                    row.vivado_impl_ok,
                    row.vivado_impl_status,
                    row.vivado_impl_reason,
                    row.chosen_bench_report_path,
                ]
            )

    _render_tex(rows, args.out_tex)

    if not rows:
        print("warning: no relevant rows found for B1/B2/B3/B4/B6", file=sys.stderr)

    if args.debug:
        for _, _, _, row, debug_reason in sorted(selected.values(), key=lambda t: (t[3].benchmark_id, t[3].model_id)):
            print(
                "DEBUG_SELECT "
                f"bench={row.benchmark_id} "
                f"model={row.model_id} "
                f"path={row.chosen_bench_report_path} "
                f"{debug_reason}"
            )
    print(str(args.out_csv))
    print(str(args.out_tex))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
