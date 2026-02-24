from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_bench_verify_b6_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VITIS", "1")
    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VIVADO", "1")

    repo_root = Path(__file__).resolve().parents[1]
    manifest = repo_root / "benches" / "B6_delay_small" / "manifest.json"
    outdir = tmp_path / "bench_verify_b6"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "bench",
            "verify",
            str(manifest),
            "--outdir",
            str(outdir),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["mismatches"] == []


def test_b6_delay_bit_exact_golden_vs_cpp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VITIS", "1")
    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VIVADO", "1")

    repo_root = Path(__file__).resolve().parents[1]
    ir_path = repo_root / "example_b6_delay_small.json"
    outdir = tmp_path / "b6_hwtest"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "hwtest",
            str(ir_path),
            "--ticks",
            "20",
            "--outdir",
            str(outdir),
            "--hw",
            "off",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    summary = json.loads(proc.stdout)
    bench_report = Path(summary["bench_report"])
    report = json.loads(bench_report.read_text(encoding="utf-8"))
    assert report["correctness"]["goldenSim"]["ok"] is True
    assert report["correctness"]["cppReference"]["ok"] is True
    assert report["correctness"]["digestMatch"]["ok"] is True
