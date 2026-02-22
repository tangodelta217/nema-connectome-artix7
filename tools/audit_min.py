#!/usr/bin/env python3
"""Minimal auditor: bench reports + DSL-ready checks + bench manifest verify."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

DSL_PROGRAMS: dict[str, str] = {
    "B1": "programs/b1_small.nema",
    "B3": "programs/b3_kernel_302.nema",
}

BENCH_MANIFESTS: dict[str, str] = {
    "B1": "benches/B1_small/manifest.json",
    "B3": "benches/B3_kernel_302_7500/manifest.json",
}


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


def _discover_reports(root: Path, pattern: str) -> list[Path]:
    return sorted(path for path in root.glob(pattern) if path.is_file())


def _run_cmd(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True, env=env)
    parsed_json: dict[str, Any] | None = None
    stdout_text = (proc.stdout or "").strip()
    if stdout_text:
        try:
            maybe = json.loads(stdout_text)
        except json.JSONDecodeError:
            maybe = None
        if isinstance(maybe, dict):
            parsed_json = maybe

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "cmd": cmd,
        "stdout": stdout_text,
        "stderr": (proc.stderr or "").strip(),
        "json": parsed_json,
    }


def _check_dsl_programs(repo_root: Path, workdir: Path) -> dict[str, Any]:
    programs: dict[str, Any] = {}
    check_runs: dict[str, Any] = {}
    hwtest_runs: dict[str, Any] = {}

    env = dict(os.environ)
    env["NEMA_HWTEST_DISABLE_VITIS"] = "1"
    env["NEMA_HWTEST_DISABLE_VIVADO"] = "1"

    for key, rel_path in DSL_PROGRAMS.items():
        abs_path = (repo_root / rel_path).resolve()
        programs[key] = {
            "path": rel_path,
            "exists": abs_path.exists(),
        }

        if not abs_path.exists():
            check_runs[key] = {
                "dslPath": rel_path,
                "run": None,
                "ok": False,
            }
            hwtest_runs[key] = {
                "dslPath": rel_path,
                "outdir": None,
                "run": None,
                "ok": False,
            }
            continue

        check_cmd = [
            sys.executable,
            "-m",
            "nema",
            "dsl",
            "check",
            str(abs_path),
        ]
        check_res = _run_cmd(check_cmd, cwd=repo_root, env=env)
        check_runs[key] = {
            "dslPath": rel_path,
            "run": check_res,
            "ok": bool(check_res["ok"]),
        }

        hwtest_outdir = workdir / "dsl_hwtest" / key.lower()
        hwtest_outdir.mkdir(parents=True, exist_ok=True)
        hwtest_cmd = [
            sys.executable,
            "-m",
            "nema",
            "dsl",
            "hwtest",
            str(abs_path),
            "--ticks",
            "2",
            "--outdir",
            str(hwtest_outdir),
        ]
        hwtest_res = _run_cmd(hwtest_cmd, cwd=repo_root, env=env)
        hwtest_runs[key] = {
            "dslPath": rel_path,
            "outdir": str(hwtest_outdir),
            "run": hwtest_res,
            "ok": bool(hwtest_res["ok"]),
        }

    programs_present = all(item["exists"] for item in programs.values()) if programs else False
    check_ok = all(item["ok"] for item in check_runs.values()) if check_runs else False
    hwtest_ok = all(item["ok"] for item in hwtest_runs.values()) if hwtest_runs else False

    return {
        "programs": programs,
        "checkRuns": check_runs,
        "hwtestRuns": hwtest_runs,
        "programs_present": programs_present,
        "check_ok": check_ok,
        "hwtest_ok": hwtest_ok,
        "ok": programs_present and check_ok and hwtest_ok,
    }


def _check_bench_manifests(repo_root: Path, workdir: Path) -> dict[str, Any]:
    checks: dict[str, Any] = {}

    for key, rel_path in BENCH_MANIFESTS.items():
        abs_path = (repo_root / rel_path).resolve()
        exists = abs_path.exists()
        verify_res: dict[str, Any] | None = None
        ok = False

        if exists:
            verify_outdir = workdir / "bench_verify" / key.lower()
            verify_outdir.mkdir(parents=True, exist_ok=True)
            verify_cmd = [
                sys.executable,
                "-m",
                "nema",
                "bench",
                "verify",
                str(abs_path),
                "--outdir",
                str(verify_outdir),
            ]
            verify_res = _run_cmd(verify_cmd, cwd=repo_root)
            ok = bool(verify_res["ok"])

        checks[key] = {
            "path": rel_path,
            "exists": exists,
            "verify": verify_res,
            "ok": ok,
        }

    manifests_present = all(item["exists"] for item in checks.values())
    verify_ok = all(item["ok"] for item in checks.values())

    return {
        "checks": checks,
        "manifestsPresent": manifests_present,
        "verifyOk": verify_ok,
    }


def _evaluate_go(
    summaries: list[dict[str, Any]],
    load_errors: list[str],
    dsl_checks: dict[str, Any],
    manifest_checks: dict[str, Any],
) -> tuple[str, list[str], dict[str, bool]]:
    missing_normalized = [
        item
        for item in summaries
        if item["nodeCount"] is None
        or item["chemicalEdgeCount"] is None
        or item["gapEdgeCount"] is None
        or item["edgeCountTotal"] is None
    ]
    digest_failures = [item for item in summaries if not item["digestMatchOk"]]
    b3_evidence = [item for item in summaries if _is_b3_302_7500(item) and item["digestMatchOk"]]

    criteria: dict[str, bool] = {
        "benchReportsFound": len(summaries) > 0,
        "benchReportsLoadable": len(load_errors) == 0,
        "graphCountsNormalized": len(missing_normalized) == 0,
        "digestMatchAll": len(digest_failures) == 0,
        "b3Evidence302_7500": len(b3_evidence) > 0,
        "dslProgramsPresent": bool(dsl_checks.get("programs_present")),
        "dslCheckOk": bool(dsl_checks.get("check_ok")),
        "dslHwtestOk": bool(dsl_checks.get("hwtest_ok")),
        "benchManifestsPresent": bool(manifest_checks.get("manifestsPresent")),
        "benchVerifyOk": bool(manifest_checks.get("verifyOk")),
    }

    reason_map = {
        "benchReportsFound": "No bench_report.json files found",
        "benchReportsLoadable": "One or more bench_report.json files failed to load",
        "graphCountsNormalized": "Missing normalized graph counts in one or more bench reports",
        "digestMatchAll": "Digest match failed in one or more bench reports",
        "b3Evidence302_7500": "Missing B3 302/7500 evidence with digestMatch.ok=true",
        "dslProgramsPresent": "Missing required DSL programs under programs/",
        "dslCheckOk": "DSL check failed for one or more programs",
        "dslHwtestOk": "DSL hwtest failed for one or more programs",
        "benchManifestsPresent": "Missing required bench manifests under benches/",
        "benchVerifyOk": "Bench manifest verification failed for one or more manifests",
    }

    reasons = [reason_map[key] for key, ok in criteria.items() if not ok]
    decision = "GO" if all(criteria.values()) else "NO-GO"
    return decision, reasons, criteria


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_min.py",
        description="Bench-report auditor with DSL + manifest verification",
    )
    parser.add_argument("--path", type=Path, default=Path("build"), help="Root directory to scan")
    parser.add_argument(
        "--glob",
        default="**/bench_report.json",
        help="Glob pattern under --path to locate bench reports",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root containing programs/ and benches/",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("build/audit_min"),
        help="Working directory for generated audit command artifacts",
    )
    parser.add_argument("--out", type=Path, default=None, help="Optional output JSON path")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    workdir = args.workdir if args.workdir.is_absolute() else (repo_root / args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

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

    dsl_checks = _check_dsl_programs(repo_root, workdir)
    manifest_checks = _check_bench_manifests(repo_root, workdir)

    decision, reasons, criteria = _evaluate_go(
        summaries,
        load_errors,
        dsl_checks,
        manifest_checks,
    )

    dsl_ready = {
        "programs_present": bool(dsl_checks.get("programs_present")),
        "check_ok": bool(dsl_checks.get("check_ok")),
        "hwtest_ok": bool(dsl_checks.get("hwtest_ok")),
        "benchManifestsPresent": bool(manifest_checks.get("manifestsPresent")),
        "benchVerifyOk": bool(manifest_checks.get("verifyOk")),
    }
    dsl_ready["ok"] = all(dsl_ready.values())

    payload = {
        "ok": decision == "GO",
        "decision": decision,
        "benchReportsScanned": len(summaries),
        "loadErrors": load_errors,
        "reasons": reasons,
        "criteria": criteria,
        "dsl": dsl_ready,
        "dslReady": dsl_ready,
        "reports": summaries,
        "dslChecks": dsl_checks,
        "benchManifestChecks": manifest_checks,
    }

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if decision == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
