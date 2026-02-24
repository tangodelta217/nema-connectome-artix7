from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nema.cli import main


def test_hwtest_vivado_part_override_recorded_without_toolchain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VITIS", "1")
    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VIVADO", "1")
    requested_part = "xc7a35tcsg324-1"

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
            "off",
            "--vivado-part",
            requested_part,
        ]
    )
    assert code == 0

    reports = list(outdir.glob("*/bench_report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["hardware"]["vivado"]["part"] == requested_part
