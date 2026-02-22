from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _normalize_sha256(value: str) -> str:
    token = value.strip().lower()
    if token.startswith("sha256:"):
        token = token[len("sha256:") :]
    return token


def test_b3_external_sha256_is_not_placeholder() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    ir_path = repo_root / "example_b3_kernel_302.json"
    ir = json.loads(ir_path.read_text(encoding="utf-8"))
    external = ir["graph"]["external"]

    raw_sha = external["sha256"]
    normalized_sha = _normalize_sha256(raw_sha)
    assert "replace" not in normalized_sha
    assert "placeholder" not in normalized_sha
    assert len(normalized_sha) == 64

    uri = external.get("uri", external.get("path"))
    assert isinstance(uri, str) and uri
    bundle_path = repo_root / uri
    assert bundle_path.exists()

    actual_sha = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    assert actual_sha == normalized_sha


def test_b3_external_verified_in_hwtest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VITIS", "1")
    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VIVADO", "1")

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
    bench_report_path = Path(summary["bench_report"])
    if not bench_report_path.is_absolute():
        bench_report_path = repo_root / bench_report_path
    report = json.loads(bench_report_path.read_text(encoding="utf-8"))

    assert report["provenance"]["externalVerified"] is True
    assert report["provenance"]["syntheticUsed"] is False
    assert report["correctness"]["digestMatch"]["ok"] is True


def test_b3_external_sha_mismatch_falls_back_to_synthetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VITIS", "1")
    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VIVADO", "1")

    repo_root = Path(__file__).resolve().parents[1]
    source_ir = repo_root / "example_b3_kernel_302.json"
    payload = json.loads(source_ir.read_text(encoding="utf-8"))
    payload["graph"]["external"]["sha256"] = "sha256:" + ("f" * 64)
    payload["tanhLut"]["artifact"] = str((repo_root / "artifacts/luts/tanh_q8_8.bin").resolve())
    bad_ir = tmp_path / "b3_bad_sha.json"
    bad_ir.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    outdir = tmp_path / "build"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "hwtest",
            str(bad_ir),
            "--outdir",
            str(outdir),
            "--ticks",
            "10",
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

    assert report["provenance"]["externalVerified"] is False
    assert report["provenance"]["syntheticUsed"] is True
    assert report["correctness"]["digestMatch"]["ok"] is True
