from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _run_audit_min(*args: str) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [sys.executable, "tools/audit_min.py", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )


def _parse_stdout_json(proc: subprocess.CompletedProcess[str]) -> dict:
    payload = json.loads(proc.stdout)
    assert isinstance(payload, dict)
    return payload


def _write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_software_mode_passes_without_hw_toolchain() -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    proc = _run_audit_min("--mode", "software")
    assert proc.returncode == 0

    payload = _parse_stdout_json(proc)
    assert payload["ok"] is True
    assert payload["decision"] == "GO"
    assert payload["criteria"]["graphCountsNormalized"] is True
    assert payload["mode"] == "software"


def test_hardware_mode_fails_without_hw_toolchain() -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")
    if shutil.which("vitis_hls") is not None or shutil.which("vivado") is not None:
        pytest.skip("HW toolchain detected; this test validates no-toolchain behavior")

    proc = _run_audit_min("--mode", "hardware")
    assert proc.returncode == 1

    payload = _parse_stdout_json(proc)
    assert payload["ok"] is False
    assert payload["decision"] == "NO-GO"
    reasons = [str(reason).lower() for reason in payload.get("reasons", [])]
    assert any("toolchain" in reason or "hardware evidence" in reason for reason in reasons)


def test_legacy_report_ignored_in_software_mode(tmp_path: Path) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    legacy_root = tmp_path / "legacy_scan"
    legacy_report = legacy_root / "legacy" / "bench_report.json"
    legacy_report.parent.mkdir(parents=True, exist_ok=True)
    legacy_report.write_text(
        json.dumps(
            {
                "modelId": "legacy_302",
                "ok": True,
                "correctness": {"digestMatch": {"ok": True}},
                "config": {"graph": {"nodeCount": 3}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = _run_audit_min("--mode", "software", "--extra-scan-root", str(legacy_root))
    assert proc.returncode == 0

    payload = _parse_stdout_json(proc)
    assert payload["ok"] is True
    assert payload["decision"] == "GO"
    assert payload["mode"] == "software"
    assert payload["criteria"]["graphCountsNormalized"] is True

    ignored = payload.get("ignoredReports", [])
    assert any(Path(path).resolve() == legacy_report.resolve() for path in ignored)


def test_warnings_empty_with_ignored_legacy_for_software_and_hardware(tmp_path: Path) -> None:
    root = tmp_path / "scan_root"
    b1_report = root / "B1" / "bench_report.json"
    b3_report = root / "B3" / "bench_report.json"
    legacy_report = root / "legacy" / "bench_report.json"

    _write_report(
        b1_report,
        {
            "modelId": "example_b1_small_subgraph",
            "bench": {"targetId": "B1/CE/2-1"},
            "ok": True,
            "correctness": {"digestMatch": {"ok": True}},
            "config": {
                "graph": {
                    "nodeCount": 2,
                    "chemicalEdgeCount": 1,
                    "gapEdgeCount": 1,
                    "edgeCountTotal": 3,
                }
            },
        },
    )
    _write_report(
        b3_report,
        {
            "modelId": "B3_kernel_302_7500",
            "bench": {"targetId": "B3/CE/302-7500"},
            "ok": True,
            "correctness": {"digestMatch": {"ok": True}},
            "config": {
                "graph": {
                    "nodeCount": 302,
                    "chemicalEdgeCount": 7500,
                    "gapEdgeCount": 0,
                    "edgeCountTotal": 7500,
                }
            },
        },
    )
    _write_report(
        legacy_report,
        {
            "modelId": "legacy_302",
            "ok": True,
            "correctness": {"digestMatch": {"ok": True}},
            "config": {"graph": {"nodeCount": 3}},
        },
    )

    isolated_repo = tmp_path / "isolated_repo"
    isolated_repo.mkdir(parents=True, exist_ok=True)
    workdir = tmp_path / "audit_work"

    for mode in ("software", "hardware"):
        proc = _run_audit_min(
            "--mode",
            mode,
            "--path",
            str(root),
            "--repo-root",
            str(isolated_repo),
            "--workdir",
            str(workdir / mode),
        )
        payload = _parse_stdout_json(proc)
        assert payload.get("warnings") == []
        ignored = payload.get("ignoredReports", [])
        assert any(Path(path).resolve() == legacy_report.resolve() for path in ignored)
        ignored_missing = payload.get("ignoredReportsMissingNormalizedCounts", [])
        assert any(Path(path).resolve() == legacy_report.resolve() for path in ignored_missing)
