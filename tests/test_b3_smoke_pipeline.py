from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_b3_smoke_hwtest_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VITIS", "1")

    repo_root = Path(__file__).resolve().parents[1]
    ir_path = repo_root / "example_b3_kernel_302.json"
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
            "20",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(proc.stdout)
    assert summary["ok"] is True

    bench_report_path = Path(summary["bench_report"])
    if not bench_report_path.is_absolute():
        bench_report_path = repo_root / bench_report_path
    assert bench_report_path.exists()
    bench_report = json.loads(bench_report_path.read_text(encoding="utf-8"))

    assert bench_report["correctness"]["digestMatch"]["ok"] is True
    assert bench_report["provenance"]["syntheticUsed"] is False
    assert bench_report["provenance"]["externalVerified"] is True
    assert bench_report["graphResolved"]["nodeCount"] == 302
    assert bench_report["graphResolved"]["edgeCounts"]["chemical"] == 7500
    assert bench_report["config"]["graph"]["nodeCount"] == 302
    assert bench_report["config"]["graph"]["chemicalEdgeCount"] == 7500
    assert bench_report["config"]["graph"]["gapEdgeCount"] == 0
    assert bench_report["config"]["graph"]["edgeCountTotal"] == 7500
    assert bench_report["config"]["schedule"]["snapshotRule"] is True
    assert isinstance(bench_report["config"]["dtNanoseconds"], int)
    assert isinstance(bench_report["bench"]["targetId"], str)

    assert Path(bench_report["correctness"]["goldenSim"]["digestPath"]).exists()
    assert Path(bench_report["correctness"]["goldenSim"]["tracePath"]).exists()
    assert Path(bench_report["artifacts"]["cppRefMain"]).exists()
    assert Path(bench_report["artifacts"]["hlsCpp"]).exists()
