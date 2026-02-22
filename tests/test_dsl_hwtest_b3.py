from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_dsl_hwtest_b3_end_to_end(tmp_path: Path) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    repo_root = Path(__file__).resolve().parents[1]
    outdir = tmp_path / "build_test"

    env = os.environ.copy()
    env["NEMA_HWTEST_DISABLE_VITIS"] = "1"
    env["NEMA_HWTEST_DISABLE_VIVADO"] = "1"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "dsl",
            "hwtest",
            "programs/b3_kernel_302.nema",
            "--ticks",
            "2",
            "--outdir",
            str(outdir),
        ],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True

    bench_report_path = Path(payload["benchReport"])
    if not bench_report_path.is_absolute():
        bench_report_path = (repo_root / bench_report_path).resolve()
    assert bench_report_path.exists()

    report = json.loads(bench_report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["correctness"]["digestMatch"]["ok"] is True
    assert report["config"]["graph"]["nodeCount"] == 302
    assert report["config"]["graph"]["chemicalEdgeCount"] == 7500
