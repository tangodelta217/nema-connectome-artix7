from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


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
