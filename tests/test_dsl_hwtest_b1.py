from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_dsl_hwtest_b1_generates_bench_report_and_digest_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VITIS", "1")
    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VIVADO", "1")

    repo_root = Path(__file__).resolve().parents[1]
    outdir = tmp_path / "build"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "dsl",
            "hwtest",
            "programs/b1_small.nema.toml",
            "--ticks",
            "20",
            "--outdir",
            str(outdir),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout)

    assert payload["ok"] is True
    hw_summary = payload["hwtest"]

    bench_report_path = Path(hw_summary["bench_report"])
    if not bench_report_path.is_absolute():
        bench_report_path = (repo_root / bench_report_path).resolve()

    assert bench_report_path.exists()
    report = json.loads(bench_report_path.read_text(encoding="utf-8"))

    expected_path = (outdir / report["modelId"] / "bench_report.json").resolve()
    assert bench_report_path.resolve() == expected_path
    assert report["correctness"]["digestMatch"]["ok"] is True
