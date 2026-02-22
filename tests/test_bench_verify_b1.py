from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_bench_verify_b1_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VITIS", "1")
    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VIVADO", "1")

    repo_root = Path(__file__).resolve().parents[1]
    manifest = repo_root / "benches" / "B1_small" / "manifest.json"
    outdir = tmp_path / "bench_verify_b1"

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
