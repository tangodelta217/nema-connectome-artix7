#!/usr/bin/env python3
"""Sanity-check lane knob wiring from sweep artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected JSON object")
    return payload


def _bench_schedule_lanes(bench_report: dict[str, Any]) -> tuple[int | None, int | None]:
    config = bench_report.get("config")
    if not isinstance(config, dict):
        return None, None
    schedule = config.get("schedule")
    if not isinstance(schedule, dict):
        return None, None
    syn = schedule.get("synapseLanes")
    neu = schedule.get("neuronLanes")
    syn_i = syn if isinstance(syn, int) and not isinstance(syn, bool) else None
    neu_i = neu if isinstance(neu, int) and not isinstance(neu, bool) else None
    return syn_i, neu_i


def run_knob_sanity(sweep_results: Path) -> dict[str, Any]:
    payload = _read_json(sweep_results)
    rows_raw = payload.get("results")
    if not isinstance(rows_raw, list):
        raise ValueError(f"{sweep_results}: missing 'results' list")

    rows: list[dict[str, Any]] = []
    kernel_hashes: set[str] = set()
    bench_paths: list[str] = []
    lanes_mismatch: list[str] = []

    for raw in rows_raw:
        if not isinstance(raw, dict):
            continue
        combo_id = str(raw.get("comboId", ""))
        syn = raw.get("synapseLanes")
        neu = raw.get("neuronLanes")
        bench_path_raw = raw.get("benchReportPath")
        bench_path = Path(bench_path_raw).resolve() if isinstance(bench_path_raw, str) and bench_path_raw else None
        bench_paths.append(str(bench_path) if bench_path is not None else "")

        kernel_path: Path | None = None
        kernel_hash: str | None = None
        bench_syn: int | None = None
        bench_neu: int | None = None
        if bench_path is not None and bench_path.exists():
            model_root = bench_path.parent
            kernel_candidate = model_root / "hls" / "nema_kernel.cpp"
            if kernel_candidate.exists():
                kernel_path = kernel_candidate
                kernel_hash = _sha256_file(kernel_path)
                kernel_hashes.add(kernel_hash)
            bench_payload = _read_json(bench_path)
            bench_syn, bench_neu = _bench_schedule_lanes(bench_payload)
            if isinstance(syn, int) and isinstance(neu, int):
                if bench_syn != syn or bench_neu != neu:
                    lanes_mismatch.append(combo_id)

        rows.append(
            {
                "comboId": combo_id,
                "synapseLanes": syn,
                "neuronLanes": neu,
                "benchReportPath": str(bench_path) if bench_path is not None else None,
                "benchScheduleSynapseLanes": bench_syn,
                "benchScheduleNeuronLanes": bench_neu,
                "kernelPath": str(kernel_path) if kernel_path is not None else None,
                "kernelHashSha256": kernel_hash,
            }
        )

    non_empty_bench_paths = [p for p in bench_paths if p]
    unique_bench_count = len(set(non_empty_bench_paths))
    unique_kernel_hashes = len(kernel_hashes)
    total_rows = len(rows)

    criteria = {
        "benchReportPathsUnique": unique_bench_count == total_rows,
        "kernelHashDiversity": unique_kernel_hashes > 1,
        "benchScheduleMatchesSweep": len(lanes_mismatch) == 0,
    }
    ok = all(criteria.values())
    return {
        "ok": ok,
        "generatedAt": _utc_now(),
        "sweepResultsPath": str(sweep_results.resolve()),
        "counts": {
            "rows": total_rows,
            "uniqueBenchReportPaths": unique_bench_count,
            "uniqueKernelHashes": unique_kernel_hashes,
        },
        "criteria": criteria,
        "laneMismatches": lanes_mismatch,
        "rows": rows,
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Knob Sanity")
    lines.append("")
    lines.append(f"- ok: **{payload['ok']}**")
    counts = payload["counts"]
    lines.append(f"- rows: **{counts['rows']}**")
    lines.append(f"- unique bench_report paths: **{counts['uniqueBenchReportPaths']}**")
    lines.append(f"- unique kernel hashes: **{counts['uniqueKernelHashes']}**")
    lines.append("")
    lines.append("## Criteria")
    lines.append("")
    for key, value in payload["criteria"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## Combos")
    lines.append("")
    lines.append("| combo | syn | neu | bench syn | bench neu | kernel hash (12) |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for row in sorted(payload["rows"], key=lambda r: str(r.get("comboId", ""))):
        digest = row.get("kernelHashSha256")
        short = digest[:12] if isinstance(digest, str) else "-"
        lines.append(
            f"| {row.get('comboId')} | {row.get('synapseLanes')} | {row.get('neuronLanes')} | "
            f"{row.get('benchScheduleSynapseLanes')} | {row.get('benchScheduleNeuronLanes')} | `{short}` |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="knob_sanity.py", description="Check lane knob wiring from sweep outputs")
    parser.add_argument(
        "--sweep-results",
        type=Path,
        default=Path("build/sweep_lanes_full/sweep_results.json"),
        help="Path to sweep_results.json",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("build/knob_sanity_after_fix.json"),
        help="Output JSON summary path",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=Path("build/knob_sanity_after_fix.md"),
        help="Output Markdown report path",
    )
    args = parser.parse_args(argv)

    summary = run_knob_sanity(args.sweep_results)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.out_md.write_text(_render_markdown(summary), encoding="utf-8")
    print(json.dumps({"ok": summary["ok"], "outJson": str(args.out_json), "outMd": str(args.out_md)}, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
