#!/usr/bin/env python3
"""Collect HW gate evidence into checkpoint_hw_out/ and build a tar bundle."""

from __future__ import annotations

import argparse
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPORT_SUFFIXES = {".rpt", ".xml", ".log"}


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"invalid json: {exc}"
    if not isinstance(payload, dict):
        return None, "root must be an object"
    return payload, None


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def _bench_kind(path: Path, payload: dict[str, Any]) -> str | None:
    model_id = payload.get("modelId")
    target_id = payload.get("bench", {}).get("targetId") if isinstance(payload.get("bench"), dict) else None
    blob = " ".join(
        part
        for part in (
            str(model_id) if isinstance(model_id, str) else "",
            str(target_id) if isinstance(target_id, str) else "",
            str(path),
        )
    ).lower()
    if "b3" in blob or "302-7500" in blob:
        return "B3"
    if "b1" in blob or "small_subgraph" in blob:
        return "B1"
    return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_markdown(
    *,
    created_at: str,
    build_dir: Path,
    out_dir: Path,
    gate_rows: list[tuple[str, str, str]],
    bench_reports: list[Path],
    b1_copy: Path | None,
    b3_copy: Path | None,
    hw_reports_copied: list[Path],
    errors: list[str],
) -> str:
    lines: list[str] = []
    lines.append("# HW_STATUS")
    lines.append("")
    lines.append(f"- Generated: `{created_at}`")
    lines.append(f"- Build dir: `{build_dir}`")
    lines.append(f"- Output dir: `{out_dir}`")
    lines.append("")
    lines.append("## Gates table")
    lines.append("")
    lines.append("| Gate | Value | Source |")
    lines.append("|---|---:|---|")
    for gate, value, src in gate_rows:
        lines.append(f"| {gate} | {value} | `{src}` |")
    lines.append("")
    lines.append("## Bench reports")
    lines.append("")
    if bench_reports:
        for path in bench_reports:
            lines.append(f"- `{path}`")
    else:
        lines.append("- MISSING: no `bench_report.json` found under build dir")
    lines.append("")
    lines.append("## Copied benchmark reports")
    lines.append("")
    lines.append(f"- B1: `{b1_copy}`" if b1_copy is not None else "- B1: MISSING")
    lines.append(f"- B3: `{b3_copy}`" if b3_copy is not None else "- B3: MISSING")
    lines.append("")
    lines.append("## Copied HW reports (.rpt/.xml/.log)")
    lines.append("")
    if hw_reports_copied:
        for path in hw_reports_copied:
            lines.append(f"- `{path}`")
    else:
        lines.append("- none found under `build_hw/**/hw_reports/`")
    lines.append("")
    lines.append("## Errors")
    lines.append("")
    if errors:
        for err in errors:
            lines.append(f"- {err}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create hardware-gates checkpoint evidence bundle")
    parser.add_argument("--build-dir", type=Path, default=Path("build_hw"), help="build directory root")
    parser.add_argument("--out-dir", type=Path, default=Path("checkpoint_hw_out"), help="checkpoint output directory")
    args = parser.parse_args(argv)

    build_dir = args.build_dir.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    created_at = _now_utc_iso()
    errors: list[str] = []

    # Copy audit_min outputs (if present).
    audit_hw_src = build_dir / "audit_min_hardware.json"
    audit_sw_src = build_dir / "audit_min_software.json"
    audit_hw_dst = out_dir / "audit_min_hardware.json"
    audit_sw_dst = out_dir / "audit_min_software.json"
    if audit_hw_src.exists():
        _copy_file(audit_hw_src, audit_hw_dst)
    else:
        errors.append(f"MISSING: {audit_hw_src}")
    if audit_sw_src.exists():
        _copy_file(audit_sw_src, audit_sw_dst)
    else:
        errors.append(f"MISSING: {audit_sw_src}")

    audit_hw_payload, audit_hw_err = _read_json(audit_hw_src)
    if audit_hw_err is not None:
        errors.append(f"{audit_hw_src}: {audit_hw_err}")

    # Discover and copy bench reports.
    bench_reports = sorted(path for path in build_dir.rglob("bench_report.json") if path.is_file())
    bench_list_path = out_dir / "bench_reports_found.txt"
    bench_list_path.write_text(
        "\n".join(str(path) for path in bench_reports) + ("\n" if bench_reports else ""),
        encoding="utf-8",
    )

    b1_copy: Path | None = None
    b3_copy: Path | None = None
    bench_copies_dir = out_dir / "bench_reports"
    for bench_path in bench_reports:
        payload, bench_err = _read_json(bench_path)
        if bench_err is not None:
            errors.append(f"{bench_path}: {bench_err}")
            continue
        kind = _bench_kind(bench_path, payload or {})
        if kind == "B1" and b1_copy is None:
            b1_copy = bench_copies_dir / "B1_bench_report.json"
            _copy_file(bench_path, b1_copy)
        elif kind == "B3" and b3_copy is None:
            b3_copy = bench_copies_dir / "B3_bench_report.json"
            _copy_file(bench_path, b3_copy)

    # Copy hardware report files under build_hw/**/hw_reports/.
    hw_reports_copied: list[Path] = []
    for src in sorted(path for path in build_dir.rglob("*") if path.is_file() and path.suffix.lower() in REPORT_SUFFIXES):
        if "hw_reports" not in src.parts:
            continue
        rel = src.relative_to(build_dir)
        dst = out_dir / "hw_reports" / rel
        _copy_file(src, dst)
        hw_reports_copied.append(dst)

    criteria = audit_hw_payload.get("criteria", {}) if isinstance(audit_hw_payload, dict) else {}
    toolchain_available = criteria.get("hardwareToolchainAvailable")
    g0b = criteria.get("hardwareEvidenceG0b")
    g2 = criteria.get("hardwareEvidenceG2")
    decision = audit_hw_payload.get("decision") if isinstance(audit_hw_payload, dict) else None
    reasons = audit_hw_payload.get("reasons") if isinstance(audit_hw_payload, dict) else None

    gate_rows: list[tuple[str, str, str]] = [
        ("toolchain.available", str(toolchain_available), "audit_min_hardware.json:criteria.hardwareToolchainAvailable"),
        ("G0b", str(g0b), "audit_min_hardware.json:criteria.hardwareEvidenceG0b"),
        ("G2", str(g2), "audit_min_hardware.json:criteria.hardwareEvidenceG2"),
        ("decision", str(decision), "audit_min_hardware.json:decision"),
    ]

    if isinstance(reasons, list) and reasons:
        for reason in reasons:
            errors.append(f"NO-GO reason: {reason}")

    hw_status_path = out_dir / "HW_STATUS.md"
    hw_status_path.write_text(
        _build_markdown(
            created_at=created_at,
            build_dir=build_dir,
            out_dir=out_dir,
            gate_rows=gate_rows,
            bench_reports=bench_reports,
            b1_copy=b1_copy,
            b3_copy=b3_copy,
            hw_reports_copied=hw_reports_copied,
            errors=errors,
        ),
        encoding="utf-8",
    )

    summary = {
        "createdAt": created_at,
        "buildDir": str(build_dir),
        "outDir": str(out_dir),
        "auditFiles": {
            "hardware": str(audit_hw_dst) if audit_hw_dst.exists() else None,
            "software": str(audit_sw_dst) if audit_sw_dst.exists() else None,
        },
        "benchReportsFound": [str(path) for path in bench_reports],
        "benchCopies": {
            "B1": str(b1_copy) if b1_copy is not None else None,
            "B3": str(b3_copy) if b3_copy is not None else None,
        },
        "hwReportsCopiedCount": len(hw_reports_copied),
        "gates": {
            "toolchainAvailable": toolchain_available,
            "g0b": g0b,
            "g2": g2,
            "decision": decision,
        },
        "errors": errors,
    }
    _write_json(out_dir / "checkpoint_summary.json", summary)

    bundle_path = out_dir / "nema_hw_checkpoint_bundle.tar.gz"
    with tarfile.open(bundle_path, "w:gz") as tar:
        for path in sorted(out_dir.rglob("*")):
            if path == bundle_path:
                continue
            tar.add(path, arcname=path.relative_to(out_dir.parent))

    print(f"HW status report: {hw_status_path}")
    print(f"HW checkpoint bundle: {bundle_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
