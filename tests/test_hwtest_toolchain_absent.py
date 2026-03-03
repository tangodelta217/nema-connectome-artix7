from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nema.cli import main


def test_hwtest_graceful_without_vitis_or_vivado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_which = shutil.which
    gpp = real_which("g++")
    if gpp is None:
        pytest.skip("g++ not available")

    def fake_which(name: str) -> str | None:
        if name in {"vitis_hls", "vivado"}:
            return None
        return real_which(name)

    monkeypatch.setattr("nema.hwtest.shutil.which", fake_which)

    outdir = tmp_path / "build"
    code = main(
        [
            "hwtest",
            "example_b1_small_subgraph.json",
            "--outdir",
            str(outdir),
            "--ticks",
            "4",
        ]
    )
    assert code == 0

    reports = list(outdir.glob("*/bench_report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))

    toolchain = report["hardware"]["toolchain"]
    assert toolchain["available"] is False
    assert toolchain["vivadoAvailable"] is False
    assert report["hardware"]["csynth"] is None
    assert report["correctness"]["digestMatch"]["ok"] is True


def test_hwtest_require_fails_without_vitis_or_vivado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_which = shutil.which
    gpp = real_which("g++")
    if gpp is None:
        pytest.skip("g++ not available")

    def fake_which(name: str) -> str | None:
        if name in {"vitis_hls", "vivado"}:
            return None
        return real_which(name)

    monkeypatch.setattr("nema.hwtest.shutil.which", fake_which)

    outdir = tmp_path / "build"
    code = main(
        [
            "hwtest",
            "example_b1_small_subgraph.json",
            "--outdir",
            str(outdir),
            "--ticks",
            "1",
            "--hw",
            "require",
        ]
    )
    assert code == 1
    reports = list(outdir.glob("*/bench_report.json"))
    assert reports == []


def test_hwtest_fails_early_when_requested_part_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_which = shutil.which
    gpp = real_which("g++")
    if gpp is None:
        pytest.skip("g++ not available")

    monkeypatch.setattr(
        "nema.hwtest._detect_vitis_hls",
        lambda: {"available": True, "binary": "/tmp/fake_vitis_hls", "version": "fake"},
    )
    monkeypatch.setattr(
        "nema.hwtest._detect_vivado",
        lambda: {"available": True, "binary": "/tmp/fake_vivado", "version": "fake"},
    )

    def fake_part_check(*, vivado_binary: str, requested_part: str, cwd: Path) -> dict:
        return {
            "ok": False,
            "reason": "requested_part_unavailable",
            "requested_part": requested_part,
            "checker_tcl": "tools/hw/check_part_available.tcl",
            "returncode": 3,
            "stdout": "",
            "stderr": "NEMA_PART_CHECK_FAIL",
            "cmd": [vivado_binary],
        }

    def fail_if_called(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("_run_vitis_hls must not run when part precheck fails")

    monkeypatch.setattr("nema.hwtest._run_vivado_part_check", fake_part_check)
    monkeypatch.setattr("nema.hwtest._run_vitis_hls", fail_if_called)

    outdir = tmp_path / "build"
    code = main(
        [
            "hwtest",
            "example_b1_small_subgraph.json",
            "--outdir",
            str(outdir),
            "--ticks",
            "1",
            "--hw",
            "auto",
        ]
    )
    assert code == 1
