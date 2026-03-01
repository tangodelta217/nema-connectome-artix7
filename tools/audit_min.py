#!/usr/bin/env python3
"""Minimal auditor: bench reports + DSL-ready checks + bench manifest verify."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_IMPORT_ROOT = SCRIPT_DIR.parent
if str(REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_IMPORT_ROOT))

from nema.qor_model import extract_rows_from_paths, fit_cost_model

DSL_PROGRAMS: dict[str, str] = {
    "B1": "programs/b1_small.nema",
    "B2": "programs/b2_mid.nema",
    "B3": "programs/b3_kernel_302.nema",
}

BENCH_MANIFESTS: dict[str, str] = {
    "B1": "benches/B1_small/manifest.json",
    "B2": "benches/B2_mid/manifest.json",
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

    hardware = report.get("hardware")
    hardware_toolchain_available = None
    csim_ok = None
    csynth_ok = None
    cosim_ok = None
    cosim_attempted = None
    listed_report_count = 0
    qor_utilization_partial = False
    qor_ii = None
    qor_latency_cycles = None
    vivado_attempted = None
    vivado_ok = None
    vivado_impl_ok = None
    vivado_wns = None
    vivado_utilization_partial = False
    vivado_timing_present = False
    hardware_has_reports = False
    if isinstance(hardware, dict):
        toolchain = hardware.get("toolchain")
        if isinstance(toolchain, dict) and isinstance(toolchain.get("available"), bool):
            hardware_toolchain_available = toolchain.get("available")
        csim = hardware.get("csim")
        if isinstance(csim, dict) and isinstance(csim.get("ok"), bool):
            csim_ok = csim.get("ok")
        csynth = hardware.get("csynth")
        if isinstance(csynth, dict) and isinstance(csynth.get("ok"), bool):
            csynth_ok = csynth.get("ok")
        cosim = hardware.get("cosim")
        if isinstance(cosim, dict):
            if isinstance(cosim.get("ok"), bool):
                cosim_ok = cosim.get("ok")
            if isinstance(cosim.get("attempted"), bool):
                cosim_attempted = cosim.get("attempted")

        reports = hardware.get("reports")
        if isinstance(reports, dict):
            files = reports.get("files")
            if isinstance(files, list):
                listed_report_count = sum(1 for item in files if isinstance(item, str) and item)
                if listed_report_count > 0:
                    hardware_has_reports = True

        qor = hardware.get("qor")
        if isinstance(qor, dict):
            utilization = qor.get("utilization")
            if isinstance(utilization, dict):
                values = []
                for key in ("lut", "ff", "bram", "dsp"):
                    value = utilization.get(key)
                    if isinstance(value, int):
                        values.append(value)
                qor_utilization_partial = len(values) > 0
            ii = qor.get("ii")
            if isinstance(ii, int):
                qor_ii = ii
            latency_cycles = qor.get("latencyCycles")
            if isinstance(latency_cycles, int):
                qor_latency_cycles = latency_cycles
            src_reports = qor.get("sourceReports")
            if isinstance(src_reports, list) and any(isinstance(item, str) and item for item in src_reports):
                hardware_has_reports = True

        vivado = hardware.get("vivado")
        if isinstance(vivado, dict):
            if isinstance(vivado.get("attempted"), bool):
                vivado_attempted = vivado.get("attempted")
            if isinstance(vivado.get("ok"), bool):
                vivado_ok = vivado.get("ok")
            if isinstance(vivado.get("implOk"), bool):
                vivado_impl_ok = vivado.get("implOk")
            elif isinstance(vivado_ok, bool):
                vivado_impl_ok = vivado_ok
            vivado_util = vivado.get("utilization")
            if not isinstance(vivado_util, dict):
                alt_util = vivado.get("util")
                if isinstance(alt_util, dict):
                    vivado_util = alt_util
            if isinstance(vivado_util, dict):
                vivado_utilization_partial = any(isinstance(vivado_util.get(key), (int, float)) for key in ("lut", "ff", "bram", "dsp"))
            vivado_timing = vivado.get("timing")
            if isinstance(vivado_timing, dict):
                vivado_timing_present = any(
                    isinstance(vivado_timing.get(key), (int, float))
                    for key in ("wns", "tns", "whs", "ths", "failingEndpoints")
                )
                if isinstance(vivado_timing.get("wns"), (int, float)):
                    vivado_wns = vivado_timing.get("wns")
            if isinstance(vivado.get("wns"), (int, float)):
                vivado_wns = vivado.get("wns")
            vivado_source = vivado.get("sourceReports")
            if isinstance(vivado_source, list) and any(isinstance(item, str) and item for item in vivado_source):
                hardware_has_reports = True

        if qor_utilization_partial:
            hardware_has_reports = True
        if vivado_utilization_partial or vivado_timing_present:
            hardware_has_reports = True

        # Backward-compatible catch-all for legacy report payloads.
        for key, value in hardware.items():
            if key in {"toolchain", "csim", "csynth", "cosim", "reports", "qor"}:
                continue
            if value is not None:
                hardware_has_reports = True
                break

    return {
        "path": str(path),
        "resolvedPath": str(path.resolve()),
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
        "hardwareToolchainAvailable": hardware_toolchain_available,
        "csimOk": csim_ok,
        "csynthOk": csynth_ok,
        "cosimOk": cosim_ok,
        "cosimAttempted": cosim_attempted,
        "hardwareHasReports": hardware_has_reports,
        "listedReportCount": listed_report_count,
        "qorUtilizationPartial": qor_utilization_partial,
        "qorIi": qor_ii,
        "qorLatencyCycles": qor_latency_cycles,
        "vivadoAttempted": vivado_attempted,
        "vivadoOk": vivado_ok,
        "vivadoImplOk": vivado_impl_ok,
        "vivadoWns": vivado_wns,
        "vivadoUtilizationPartial": vivado_utilization_partial,
        "vivadoTimingPresent": vivado_timing_present,
    }


def _is_b3_302_7500(summary: dict[str, Any]) -> bool:
    node_count = summary.get("nodeCount")
    chemical_edge_count = summary.get("chemicalEdgeCount")
    target_id = summary.get("targetId")
    target_match = isinstance(target_id, str) and "302-7500" in target_id
    count_match = node_count == 302 and chemical_edge_count == 7500
    return bool(count_match or target_match)


def _is_b2(summary: dict[str, Any]) -> bool:
    model_id = summary.get("modelId")
    target_id = summary.get("targetId")
    path = summary.get("path")
    blob = " ".join(
        part
        for part in (
            model_id if isinstance(model_id, str) else "",
            target_id if isinstance(target_id, str) else "",
            path if isinstance(path, str) else "",
        )
    ).lower()
    return "b2" in blob or "mid" in blob


def _is_b4(summary: dict[str, Any]) -> bool:
    model_id = summary.get("modelId")
    target_id = summary.get("targetId")
    path = summary.get("path")
    blob = " ".join(
        part
        for part in (
            model_id if isinstance(model_id, str) else "",
            target_id if isinstance(target_id, str) else "",
            path if isinstance(path, str) else "",
        )
    ).lower()
    return "b4" in blob or "connectome" in blob


def _is_b1(summary: dict[str, Any]) -> bool:
    model_id = summary.get("modelId")
    target_id = summary.get("targetId")
    path = summary.get("path")
    blob = " ".join(
        part
        for part in (
            model_id if isinstance(model_id, str) else "",
            target_id if isinstance(target_id, str) else "",
            path if isinstance(path, str) else "",
        )
    ).lower()
    return "b1" in blob or "example_b1" in blob


def _discover_reports(root: Path, pattern: str) -> list[Path]:
    return sorted(path for path in root.glob(pattern) if path.is_file())


def _discover_hw_reports(root: Path) -> list[Path]:
    if not root.exists():
        return []
    reports: list[Path] = []
    reports.extend(path for path in root.glob("**/*.rpt") if path.is_file())
    reports.extend(path for path in root.glob("**/*.xml") if path.is_file())
    return sorted(set(reports))


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
            "--format",
            "json",
            "--no-color",
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
            "--format",
            "json",
            "--no-color",
        ]
        hwtest_res = _run_cmd(hwtest_cmd, cwd=repo_root, env=env)
        bench_report_path: str | None = None
        if isinstance(hwtest_res.get("json"), dict):
            raw = hwtest_res["json"].get("benchReportPath", hwtest_res["json"].get("benchReport"))
            if isinstance(raw, str) and raw:
                bench_report_path = raw
        hwtest_runs[key] = {
            "dslPath": rel_path,
            "outdir": str(hwtest_outdir),
            "run": hwtest_res,
            "ok": bool(hwtest_res["ok"]),
            "benchReportPath": bench_report_path,
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


def _normalize_path(path: str | Path, *, repo_root: Path) -> Path:
    raw = Path(path)
    if raw.is_absolute():
        return raw.resolve()
    return (repo_root / raw).resolve()


def _relevant_report_paths(
    repo_root: Path,
    summaries: list[dict[str, Any]],
    dsl_checks: dict[str, Any],
    manifest_checks: dict[str, Any],
) -> tuple[set[Path], list[str]]:
    relevant: set[Path] = set()
    warnings: list[str] = []

    checks = manifest_checks.get("checks")
    if isinstance(checks, dict):
        for key, item in checks.items():
            if not isinstance(item, dict):
                continue
            verify = item.get("verify")
            verify_json = verify.get("json") if isinstance(verify, dict) else None
            bench_path = verify_json.get("benchReport") if isinstance(verify_json, dict) else None
            if isinstance(bench_path, str) and bench_path:
                candidate = _normalize_path(bench_path, repo_root=repo_root)
                if candidate.exists():
                    relevant.add(candidate)
                else:
                    warnings.append(f"manifest {key}: benchReport path not found: {bench_path}")

    hw_runs = dsl_checks.get("hwtestRuns")
    if isinstance(hw_runs, dict):
        for key, item in hw_runs.items():
            if not isinstance(item, dict):
                continue
            bench_path = item.get("benchReportPath")
            if isinstance(bench_path, str) and bench_path:
                candidate = _normalize_path(bench_path, repo_root=repo_root)
                if candidate.exists():
                    relevant.add(candidate)
                    continue
                warnings.append(f"dsl hwtest {key}: benchReportPath not found: {bench_path}")

            outdir = item.get("outdir")
            if isinstance(outdir, str) and outdir:
                outdir_path = _normalize_path(outdir, repo_root=repo_root)
                if outdir_path.exists():
                    discovered = sorted(path for path in outdir_path.glob("**/bench_report.json") if path.is_file())
                    if len(discovered) == 1:
                        relevant.add(discovered[0].resolve())
                    elif len(discovered) > 1:
                        warnings.append(
                            f"dsl hwtest {key}: multiple bench_report.json under outdir, using all ({len(discovered)})"
                        )
                        relevant.update(path.resolve() for path in discovered)
                    else:
                        warnings.append(f"dsl hwtest {key}: no bench_report.json under outdir {outdir}")

    scanned_bench_targets = [
        _normalize_path(item["path"], repo_root=repo_root)
        for item in summaries
        if _is_b1(item) or _is_b2(item) or _is_b3_302_7500(item) or _is_b4(item)
    ]
    relevant.update(scanned_bench_targets)
    if not relevant:
        warnings.append("No relevant B1/B2/B3/B4 bench reports resolved from audit runs or scan")

    return relevant, warnings


def _has_g2_reports_or_qor(summary: dict[str, Any]) -> bool:
    if int(summary.get("listedReportCount", 0) or 0) > 0:
        return True
    if summary.get("qorUtilizationPartial") is True:
        return True
    return isinstance(summary.get("qorIi"), int) or isinstance(summary.get("qorLatencyCycles"), int)


def _cost_compare_sanity(
    summaries: list[dict[str, Any]],
    *,
    cost_max_ratio: float,
    cost_min_points: int,
    cost_mean_rel_error_max: float,
    cost_split_by: str,
    cost_test_fraction: float,
    cost_split_seed: int,
) -> dict[str, Any]:
    g2_reports_present = any(_has_g2_reports_or_qor(item) for item in summaries)
    report_paths: list[Path] = []
    for summary in summaries:
        if not _has_g2_reports_or_qor(summary):
            continue
        path_raw = summary.get("resolvedPath", summary.get("path"))
        if not isinstance(path_raw, str) or not path_raw:
            continue
        path_obj = Path(path_raw).resolve()
        if path_obj.exists():
            report_paths.append(path_obj)

    rows, row_errors = extract_rows_from_paths(sorted(set(report_paths)))
    fit_payload = fit_cost_model(
        rows,
        min_points=cost_min_points,
        mean_relative_error_max=cost_mean_rel_error_max,
        split_by=cost_split_by,
        test_fraction=cost_test_fraction,
        split_seed=cost_split_seed,
    )
    checks = fit_payload.get("rows")
    if not isinstance(checks, list):
        checks = []

    k_requirement_met = bool(fit_payload.get("kRequirementMet") is True)
    mean_error_test = fit_payload.get("meanRelativeError_test")
    if not isinstance(mean_error_test, (int, float)):
        mean_error_test = fit_payload.get("meanRelativeError")
    within_threshold = bool(
        isinstance(mean_error_test, (int, float))
        and float(mean_error_test) < float(cost_mean_rel_error_max)
    )
    comparable_present = int(fit_payload.get("pointsWithActualQor", 0) or 0) > 0
    all_compare_ok = bool(fit_payload.get("fitSolved") is True)

    return {
        "thresholdRatio": cost_max_ratio,
        "thresholdMeanRelativeError": cost_mean_rel_error_max,
        "minPointsRequired": cost_min_points,
        "checks": checks,
        "rowsTotal": fit_payload.get("pointsTotal"),
        "rowsWithActualQor": fit_payload.get("pointsWithActualQor"),
        "g2ReportsOrQorPresent": g2_reports_present,
        "comparablePresent": comparable_present,
        "allCostCompareOk": all_compare_ok,
        "kRequirementMet": k_requirement_met,
        "fitSolved": bool(fit_payload.get("fitSolved") is True),
        "meanRelativeError": fit_payload.get("meanRelativeError"),
        "meanRelativeErrorTrain": fit_payload.get("meanRelativeError_train"),
        "meanRelativeErrorTest": fit_payload.get("meanRelativeError_test"),
        "maxRelativeErrorTrain": fit_payload.get("maxRelativeError_train"),
        "maxRelativeErrorTest": fit_payload.get("maxRelativeError_test"),
        "splitBy": fit_payload.get("splitBy"),
        "split": fit_payload.get("split"),
        "withinThreshold": within_threshold,
        "ok": bool(g2_reports_present and k_requirement_met and within_threshold),
        "fit": fit_payload,
        "datasetErrors": row_errors,
    }


def _evaluate_modes(
    *,
    mode: str,
    summaries: list[dict[str, Any]],
    relevant_summaries: list[dict[str, Any]],
    ignored_reports: list[str],
    load_errors: list[str],
    dsl_checks: dict[str, Any],
    manifest_checks: dict[str, Any],
    toolchain_hw_available: bool,
    warnings: list[str],
    cost_max_ratio: float,
    cost_min_points: int,
    cost_mean_rel_error_max: float,
    cost_split_by: str,
    cost_test_fraction: float,
    cost_split_seed: int,
) -> tuple[str, list[str], dict[str, bool], bool, bool, bool, bool, dict[str, Any]]:
    missing_normalized = [
        item
        for item in relevant_summaries
        if item["nodeCount"] is None
        or item["chemicalEdgeCount"] is None
        or item["gapEdgeCount"] is None
        or item["edgeCountTotal"] is None
    ]
    digest_failures = [item for item in relevant_summaries if not item["digestMatchOk"]]
    b3_evidence = [item for item in relevant_summaries if _is_b3_302_7500(item) and item["digestMatchOk"]]

    dsl_ready = (
        bool(dsl_checks.get("programs_present"))
        and bool(dsl_checks.get("check_ok"))
        and bool(dsl_checks.get("hwtest_ok"))
    )
    bench_verify_ok = bool(manifest_checks.get("verifyOk"))

    hardware_scope = relevant_summaries if relevant_summaries else summaries
    cost_sanity = _cost_compare_sanity(
        hardware_scope,
        cost_max_ratio=cost_max_ratio,
        cost_min_points=cost_min_points,
        cost_mean_rel_error_max=cost_mean_rel_error_max,
        cost_split_by=cost_split_by,
        cost_test_fraction=cost_test_fraction,
        cost_split_seed=cost_split_seed,
    )
    dataset_errors = cost_sanity.get("datasetErrors")
    if isinstance(dataset_errors, list) and dataset_errors:
        warnings.append(f"{len(dataset_errors)} QoR dataset rows could not be parsed")
    hardware_g0b = any(
        item.get("hardwareToolchainAvailable") is True
        and item.get("csimOk") is True
        and (
            item.get("cosimAttempted") is not True
            or item.get("cosimOk") is True
        )
        for item in hardware_scope
    )
    hardware_g2_reports = bool(cost_sanity.get("g2ReportsOrQorPresent") is True)
    hardware_g2_min_points = bool(cost_sanity.get("kRequirementMet") is True)
    hardware_g2_mean_error = bool(cost_sanity.get("withinThreshold") is True)
    hardware_g2_cost_ok = bool(hardware_g2_min_points and hardware_g2_mean_error)
    hardware_g2 = bool(hardware_g2_reports and hardware_g2_cost_ok)
    hardware_g3 = any(
        item.get("hardwareToolchainAvailable") is True
        and item.get("vivadoImplOk") is True
        and (
            isinstance(item.get("vivadoWns"), (int, float))
            or item.get("vivadoTimingPresent") is True
            or item.get("vivadoUtilizationPartial") is True
        )
        for item in hardware_scope
    )

    criteria: dict[str, bool] = {
        "benchReportsFound": len(summaries) > 0,
        "benchReportsLoadable": len(load_errors) == 0,
        "relevantReportsFound": len(relevant_summaries) > 0,
        "graphCountsNormalized": len(relevant_summaries) > 0 and len(missing_normalized) == 0,
        "digestMatchAll": len(relevant_summaries) > 0 and len(digest_failures) == 0,
        "b3Evidence302_7500": len(b3_evidence) > 0,
        "dslProgramsPresent": bool(dsl_checks.get("programs_present")),
        "dslCheckOk": bool(dsl_checks.get("check_ok")),
        "dslHwtestOk": bool(dsl_checks.get("hwtest_ok")),
        "dslReady": dsl_ready,
        "benchManifestsPresent": bool(manifest_checks.get("manifestsPresent")),
        "benchVerifyOk": bench_verify_ok,
        "hardwareToolchainAvailable": toolchain_hw_available,
        "hardwareEvidenceG0b": hardware_g0b,
        "hardwareEvidenceG2Reports": hardware_g2_reports,
        "hardwareCostModelMinPoints": hardware_g2_min_points,
        "hardwareCostModelMeanErrorWithinThreshold": hardware_g2_mean_error,
        "hardwareCostCompareWithinThreshold": hardware_g2_cost_ok,
        "hardwareEvidenceG2": hardware_g2,
        "hardwareEvidenceG3": hardware_g3,
        "hardwareEvidenceG3Vivado": hardware_g3,
    }

    software_ok = all(
        criteria[key]
        for key in (
            "dslReady",
            "digestMatchAll",
            "b3Evidence302_7500",
            "benchVerifyOk",
            "graphCountsNormalized",
        )
    )
    hardware_ok = all(
        criteria[key]
        for key in (
            "hardwareToolchainAvailable",
            "hardwareEvidenceG0b",
            "hardwareEvidenceG2Reports",
            "hardwareCostModelMinPoints",
            "hardwareCostModelMeanErrorWithinThreshold",
            "hardwareCostCompareWithinThreshold",
        )
    )
    vivado_ok = all(
        criteria[key]
        for key in (
            "hardwareToolchainAvailable",
            "hardwareEvidenceG0b",
            "hardwareEvidenceG3",
        )
    )
    all_ok = software_ok and hardware_ok

    reason_map = {
        "dslReady": "DSL-ready failed (programs/check/hwtest)",
        "digestMatchAll": "Digest match failed in relevant B1/B2/B3/B4 bench reports",
        "b3Evidence302_7500": "Missing B3 302/7500 evidence with digestMatch.ok=true in relevant bench reports",
        "benchVerifyOk": "Bench manifest verification failed for one or more manifests",
        "graphCountsNormalized": "Missing normalized graph counts in relevant B1/B2/B3/B4 bench reports",
        "hardwareToolchainAvailable": "HW toolchain unavailable (vitis_hls/vivado not found)",
        "hardwareEvidenceG0b": "No hardware evidence for G0b (toolchain.available + csim.ok and cosim.ok if attempted)",
        "hardwareEvidenceG2Reports": "No hardware evidence for G2 (reports.files or qor.utilization)",
        "hardwareCostModelMinPoints": f"Cost model sanity failed: need at least {cost_min_points} QoR points",
        "hardwareCostModelMeanErrorWithinThreshold": (
            f"Cost model sanity failed: mean relative error (test split) must be < {cost_mean_rel_error_max}"
        ),
        "hardwareCostCompareWithinThreshold": (
            f"Cost model sanity failed: mean relative error (test split) < {cost_mean_rel_error_max} with >= {cost_min_points} points"
        ),
        "hardwareEvidenceG2": (
            f"G2 failed: reports/QoR evidence + >= {cost_min_points} points + test mean relative error < {cost_mean_rel_error_max} required"
        ),
        "hardwareEvidenceG3": "No Vivado impl evidence (require hardware.vivado.implOk=true with non-null WNS/timing/utilization)",
        "hardwareEvidenceG3Vivado": "No Vivado impl evidence (require hardware.vivado.implOk=true with non-null WNS/timing/utilization)",
    }

    mode_criteria = {
        "software": (
            "dslReady",
            "digestMatchAll",
            "b3Evidence302_7500",
            "benchVerifyOk",
            "graphCountsNormalized",
        ),
        "hardware": (
            "hardwareToolchainAvailable",
            "hardwareEvidenceG0b",
            "hardwareEvidenceG2Reports",
            "hardwareCostModelMinPoints",
            "hardwareCostModelMeanErrorWithinThreshold",
            "hardwareCostCompareWithinThreshold",
        ),
        "all": (
            "dslReady",
            "digestMatchAll",
            "b3Evidence302_7500",
            "benchVerifyOk",
            "graphCountsNormalized",
            "hardwareToolchainAvailable",
            "hardwareEvidenceG0b",
            "hardwareEvidenceG2Reports",
            "hardwareCostModelMinPoints",
            "hardwareCostModelMeanErrorWithinThreshold",
            "hardwareCostCompareWithinThreshold",
        ),
        "vivado": (
            "hardwareToolchainAvailable",
            "hardwareEvidenceG0b",
            "hardwareEvidenceG3",
        ),
    }

    keys = mode_criteria[mode]
    reasons = [reason_map[key] for key in keys if not criteria.get(key, False)]
    if load_errors:
        warnings.append(f"{len(load_errors)} bench_report load errors observed outside required mode criteria")

    if mode == "software":
        decision_ok = software_ok
    elif mode == "hardware":
        decision_ok = hardware_ok
    elif mode == "vivado":
        decision_ok = vivado_ok
    else:
        decision_ok = all_ok
    decision = "GO" if decision_ok else "NO-GO"
    return decision, reasons, criteria, software_ok, hardware_ok, all_ok, vivado_ok, cost_sanity


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_min.py",
        description="Bench-report auditor with DSL + manifest verification",
    )
    parser.add_argument(
        "--mode",
        choices=("software", "hardware", "vivado", "all"),
        default="software",
        help="Gate mode to evaluate (default: software)",
    )
    parser.add_argument(
        "--path",
        "--scan",
        dest="path",
        type=Path,
        default=Path("build"),
        help="Root directory to scan (alias: --scan)",
    )
    parser.add_argument(
        "--extra-scan-root",
        action="append",
        type=Path,
        default=[],
        help="Additional root(s) to scan for bench_report.json (can be passed multiple times)",
    )
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
    parser.add_argument(
        "--cost-max-ratio",
        type=float,
        default=3.0,
        help="Deprecated legacy ratio knob (kept for backward compatibility)",
    )
    parser.add_argument(
        "--cost-min-points",
        type=int,
        default=3,
        help="Minimum number of QoR points for G2 model sanity (default: 3)",
    )
    parser.add_argument(
        "--cost-mean-rel-error-max",
        type=float,
        default=1.0,
        help="Maximum mean relative error for G2 model sanity (default: 1.0)",
    )
    parser.add_argument(
        "--cost-split-by",
        choices=("none", "benchmark", "seed"),
        default="benchmark",
        help="Cross-validation split key for G2 sanity (default: benchmark)",
    )
    parser.add_argument(
        "--cost-test-fraction",
        type=float,
        default=0.34,
        help="Holdout fraction for G2 cross-validation split (default: 0.34)",
    )
    parser.add_argument(
        "--cost-split-seed",
        type=int,
        default=0,
        help="Deterministic seed for G2 cross-validation split (default: 0)",
    )
    parser.add_argument("--out", type=Path, default=None, help="Optional output JSON path")
    args = parser.parse_args(argv)
    if args.cost_max_ratio <= 1.0:
        parser.error("--cost-max-ratio must be > 1.0")
    if args.cost_min_points < 3:
        parser.error("--cost-min-points must be >= 3")
    if args.cost_mean_rel_error_max <= 0.0:
        parser.error("--cost-mean-rel-error-max must be > 0")
    if args.cost_test_fraction <= 0.0 or args.cost_test_fraction >= 1.0:
        parser.error("--cost-test-fraction must be in (0,1)")

    repo_root = args.repo_root.resolve()
    workdir = args.workdir if args.workdir.is_absolute() else (repo_root / args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    scan_roots_raw: list[Path] = [args.path, *list(args.extra_scan_root or [])]
    scan_roots: list[Path] = []
    for root in scan_roots_raw:
        if root.is_absolute():
            scan_roots.append(root.resolve())
        else:
            scan_roots.append((repo_root / root).resolve())

    report_set: set[Path] = set()
    for scan_root in scan_roots:
        report_set.update(_discover_reports(scan_root, args.glob))
    reports = sorted(report_set)
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
    hw_report_set: set[Path] = set()
    for scan_root in scan_roots:
        hw_report_set.update(_discover_hw_reports(scan_root))
    hw_reports = sorted(hw_report_set)

    relevant_paths, relevance_warnings = _relevant_report_paths(
        repo_root,
        summaries,
        dsl_checks,
        manifest_checks,
    )
    summary_by_path: dict[Path, dict[str, Any]] = {
        _normalize_path(item["path"], repo_root=repo_root): item for item in summaries
    }
    relevant_summaries: list[dict[str, Any]] = []
    for path in sorted(relevant_paths):
        summary = summary_by_path.get(path)
        if summary is not None:
            relevant_summaries.append(summary)
            continue
        try:
            report = _load_report(path)
            relevant_summaries.append(_report_summary(path, report))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            warnings_msg = f"failed to load relevant bench report {path}: {exc}"
            relevance_warnings.append(warnings_msg)

    ignored_reports = sorted(
        item["path"] for item in summaries if _normalize_path(item["path"], repo_root=repo_root) not in relevant_paths
    )
    warnings: list[str] = list(relevance_warnings)
    ignored_missing_normalized_counts: list[str] = []
    for item in summaries:
        path_obj = _normalize_path(item["path"], repo_root=repo_root)
        if path_obj in relevant_paths:
            continue
        if (
            item.get("nodeCount") is None
            or item.get("chemicalEdgeCount") is None
            or item.get("gapEdgeCount") is None
            or item.get("edgeCountTotal") is None
        ):
            ignored_missing_normalized_counts.append(item["path"])

    toolchain_hw_available = bool(shutil.which("vitis_hls") or shutil.which("vivado"))

    decision, reasons, criteria, software_ok, hardware_ok, all_ok, vivado_ok, cost_sanity = _evaluate_modes(
        mode=args.mode,
        summaries=summaries,
        relevant_summaries=relevant_summaries,
        ignored_reports=ignored_reports,
        load_errors=load_errors,
        dsl_checks=dsl_checks,
        manifest_checks=manifest_checks,
        toolchain_hw_available=toolchain_hw_available,
        warnings=warnings,
        cost_max_ratio=float(args.cost_max_ratio),
        cost_min_points=int(args.cost_min_points),
        cost_mean_rel_error_max=float(args.cost_mean_rel_error_max),
        cost_split_by=str(args.cost_split_by),
        cost_test_fraction=float(args.cost_test_fraction),
        cost_split_seed=int(args.cost_split_seed),
    )

    dsl_ready = {
        "programs_present": bool(dsl_checks.get("programs_present")),
        "check_ok": bool(dsl_checks.get("check_ok")),
        "hwtest_ok": bool(dsl_checks.get("hwtest_ok")),
    }
    dsl_ready["ok"] = all(dsl_ready.values())

    payload = {
        "ok": decision == "GO",
        "decision": decision,
        "mode": args.mode,
        "software_ok": software_ok,
        "hardware_ok": hardware_ok,
        "vivado_ok": vivado_ok,
        "all_ok": all_ok,
        "benchReportsScanned": len(summaries),
        "scanRoots": [str(path) for path in scan_roots],
        "relevantReportsScanned": len(relevant_summaries),
        "loadErrors": load_errors,
        "warnings": warnings,
        "ignoredReports": ignored_reports,
        "ignoredReportsMissingNormalizedCounts": ignored_missing_normalized_counts,
        "reasons": reasons,
        "criteria": criteria,
        "dsl": dsl_ready,
        "dslReady": dsl_ready,
        "toolchainHwAvailable": toolchain_hw_available,
        "hwReportFiles": [str(path) for path in hw_reports],
        "costModel": cost_sanity,
        "costModelConfig": {
            "splitBy": args.cost_split_by,
            "testFraction": args.cost_test_fraction,
            "splitSeed": args.cost_split_seed,
            "minPoints": args.cost_min_points,
            "meanRelativeErrorMax": args.cost_mean_rel_error_max,
        },
        "reports": summaries,
        "relevantReports": relevant_summaries,
        "relevantReportPaths": [str(path) for path in sorted(relevant_paths)],
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
