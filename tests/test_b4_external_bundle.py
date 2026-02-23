from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_b4_external_bundle_verified_in_hwtest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VITIS", "1")
    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VIVADO", "1")

    repo_root = Path(__file__).resolve().parents[1]
    ir_path = repo_root / "example_b4_celegans_external_bundle.json"
    outdir = tmp_path / "build"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "hwtest",
            str(ir_path),
            "--outdir",
            str(outdir),
            "--ticks",
            "8",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    summary = json.loads(proc.stdout)
    bench_report_path = Path(summary["bench_report"])
    if not bench_report_path.is_absolute():
        bench_report_path = repo_root / bench_report_path
    report = json.loads(bench_report_path.read_text(encoding="utf-8"))

    assert report["provenance"]["externalVerified"] is True
    assert report["provenance"]["syntheticUsed"] is False
    assert report["correctness"]["digestMatch"]["ok"] is True
    assert report["graphResolved"]["nodeCount"] == 8
    assert report["graphResolved"]["edgeCounts"]["chemical"] == 12
    assert report["config"]["graph"]["nodeCount"] == 8
    assert report["config"]["graph"]["chemicalEdgeCount"] == 12
    assert report["config"]["graph"]["gapEdgeCount"] == 0

