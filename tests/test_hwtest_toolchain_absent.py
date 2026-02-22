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
