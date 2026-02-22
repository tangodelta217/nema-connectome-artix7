#!/usr/bin/env python3
"""Minimal bench_report-only auditor for GO/NO-GO decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: bench_report must be a JSON object")
    return payload


def _graph_counts(report: dict[str, Any]) -> tuple[int | None, int | None, int | None, int | None]:
    graph = report.get("config", {}).get("graph", {})
    if not isinstance(graph, dict):
        return None, None, None, None
    node_count = graph.get("nodeCount")
    chemical_edge_count = graph.get("chemicalEdgeCount")
    gap_edge_count = graph.get("gapEdgeCount")
    edge_count_total = graph.get("edgeCountTotal")
    if not isinstance(node_count, int):
        node_count = None
    if not isinstance(chemical_edge_count, int):
        chemical_edge_count = None
    if not isinstance(gap_edge_count, int):
        gap_edge_count = None
    if not isinstance(edge_count_total, int):
        edge_count_total = None
    return node_count, chemical_edge_count, gap_edge_count, edge_count_total


def _report_summary(path: Path, report: dict[str, Any]) -> dict[str, Any]:
    digest_ok = bool(report.get("correctness", {}).get("digestMatch", {}).get("ok") is True)
    node_count, chemical_edge_count, gap_edge_count, edge_count_total = _graph_counts(report)
    target_id = report.get("bench", {}).get("targetId")
    if not isinstance(target_id, str):
        target_id = None
    synthetic_used = report.get("provenance", {}).get("syntheticUsed")
    if not isinstance(synthetic_used, bool):
        synthetic_used = None
    external_verified = report.get("provenance", {}).get("externalVerified")
    if not isinstance(external_verified, bool):
        external_verified = None

    return {
        "path": str(path),
        "modelId": report.get("modelId"),
        "targetId": target_id,
        "ok": bool(report.get("ok") is True),
        "digestMatchOk": digest_ok,
        "nodeCount": node_count,
        "chemicalEdgeCount": chemical_edge_count,
        "gapEdgeCount": gap_edge_count,
        "edgeCountTotal": edge_count_total,
        "syntheticUsed": synthetic_used,
        "externalVerified": external_verified,
    }


def _is_b3_302_7500(summary: dict[str, Any]) -> bool:
    node_count = summary.get("nodeCount")
    chemical_edge_count = summary.get("chemicalEdgeCount")
    target_id = summary.get("targetId")
    target_match = isinstance(target_id, str) and "302-7500" in target_id
    count_match = node_count == 302 and chemical_edge_count == 7500
    return bool(count_match or target_match)


def _evaluate_go(summaries: list[dict[str, Any]]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not summaries:
        reasons.append("No bench_report.json files found")
        return "NO-GO", reasons

    missing_normalized = [
        item
        for item in summaries
        if item["nodeCount"] is None
        or item["chemicalEdgeCount"] is None
        or item["gapEdgeCount"] is None
        or item["edgeCountTotal"] is None
    ]
    if missing_normalized:
        reasons.append("Missing normalized graph counts in one or more bench reports")

    digest_failures = [item for item in summaries if not item["digestMatchOk"]]
    if digest_failures:
        reasons.append("Digest match failed in one or more bench reports")

    b3_evidence = [item for item in summaries if _is_b3_302_7500(item) and item["digestMatchOk"]]
    if not b3_evidence:
        reasons.append("Missing B3 302/7500 evidence with digestMatch.ok=true")

    decision = "GO" if not reasons else "NO-GO"
    return decision, reasons


def _discover_reports(root: Path, pattern: str) -> list[Path]:
    return sorted(path for path in root.glob(pattern) if path.is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_min.py",
        description="Bench-report-only auditor for NEMA GO/NO-GO checks",
    )
    parser.add_argument("--path", type=Path, default=Path("build"), help="Root directory to scan")
    parser.add_argument(
        "--glob",
        default="**/bench_report.json",
        help="Glob pattern under --path to locate bench reports",
    )
    parser.add_argument("--out", type=Path, default=None, help="Optional output JSON path")
    args = parser.parse_args(argv)

    reports = _discover_reports(args.path, args.glob)
    summaries: list[dict[str, Any]] = []
    load_errors: list[str] = []
    for report_path in reports:
        try:
            report = _load_report(report_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            load_errors.append(f"{report_path}: {exc}")
            continue
        summaries.append(_report_summary(report_path, report))

    decision, reasons = _evaluate_go(summaries)
    payload = {
        "ok": decision == "GO",
        "decision": decision,
        "benchReportsScanned": len(summaries),
        "loadErrors": load_errors,
        "reasons": reasons,
        "reports": summaries,
    }

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if decision == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
