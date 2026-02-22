from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nema.cli import main
from nema.ir_validate import validate_ir


def test_dsl_check_reports_field_path_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dsl = tmp_path / "bad.nema.toml"
    dsl.write_text(
        """
[module]
name = "bad"
licenseSpdx = "MIT"
allowedSpdx = ["MIT"]

[graph]
dt = 1.0

[graph.external]
uri = "foo.json"
path = "foo.json"
subgraphId = "s0"
formatId = "nema.connectome.bundle.v0.1"

[[graph.nodes]]
id = "n0"
index = 0
canonicalOrderId = 0

[schedule]
policy = "nema.tick.v0.1"
snapshotRule = true
evalOrder = "index"

[qformats]
voltage = "Q8.8"
activation = "Q8.8"
accum = "Q12.8"
lutInput = "Q8.8"
lutOutput = "Q8.8"

[compile]
tanhLutPolicy = "nema.tanh_lut.v0.1"
tanhLutArtifact = "lut.bin"
tanhLutChecksumSha256 = "abc"

[run]
defaultTicks = 1
seed = 0
""".strip()
        + "\n",
        encoding="utf-8",
    )

    code = main(["dsl", "check", str(dsl)])

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "graph.external.sha256" in payload["error"]


def test_dsl_compile_is_deterministic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dsl = Path("programs/b1_small.nema.toml")
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"

    code_a = main(["dsl", "compile", str(dsl), "--out", str(out_a)])
    assert code_a == 0
    payload_a = json.loads(capsys.readouterr().out)
    assert payload_a["ok"] is True

    code_b = main(["dsl", "compile", str(dsl), "--out", str(out_b)])
    assert code_b == 0
    payload_b = json.loads(capsys.readouterr().out)
    assert payload_b["ok"] is True

    assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")
    validate_ir(out_a)


def test_dsl_hwtest_b1_pipeline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    dsl = Path("programs/b1_small.nema.toml")
    outdir = tmp_path / "build"

    code = main(["dsl", "hwtest", str(dsl), "--ticks", "5", "--outdir", str(outdir)])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    hwtest = payload["hwtest"]
    bench_report = Path(hwtest["bench_report"])
    assert bench_report.exists()
    report = json.loads(bench_report.read_text(encoding="utf-8"))
    assert report["correctness"]["digestMatch"]["ok"] is True
