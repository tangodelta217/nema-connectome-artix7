from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nema.cli import main


def test_hwtest_bench_report_records_schedule_lanes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VITIS", "1")
    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VIVADO", "1")

    base_ir_path = Path("example_b1_small_subgraph.json")
    ir_payload = json.loads(base_ir_path.read_text(encoding="utf-8"))
    compile_obj = ir_payload.get("compile")
    if not isinstance(compile_obj, dict):
        compile_obj = {}
        ir_payload["compile"] = compile_obj
    schedule_obj = compile_obj.get("schedule")
    if not isinstance(schedule_obj, dict):
        schedule_obj = {}
        compile_obj["schedule"] = schedule_obj
    schedule_obj["synapseLanes"] = 8
    schedule_obj["neuronLanes"] = 4
    ir_payload["modelId"] = "b1_schedule_lanes_test"
    tanh_lut = ir_payload.get("tanhLut")
    if isinstance(tanh_lut, dict):
        artifact = tanh_lut.get("artifact")
        if isinstance(artifact, str) and artifact:
            tanh_lut["artifact"] = str((Path.cwd() / artifact).resolve())

    ir_path = tmp_path / "b1_schedule_lanes.json"
    ir_path.write_text(json.dumps(ir_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    outdir = tmp_path / "build"
    code = main(
        [
            "hwtest",
            str(ir_path),
            "--outdir",
            str(outdir),
            "--ticks",
            "2",
            "--hw",
            "off",
        ]
    )
    assert code == 0

    reports = list(outdir.glob("*/bench_report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    schedule = report["config"]["schedule"]
    assert schedule["synapseLanes"] == 8
    assert schedule["neuronLanes"] == 4
