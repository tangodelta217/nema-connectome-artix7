from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nema.sweep import run_lanes_sweep
from tools.knob_sanity import run_knob_sanity


def test_lane_knobs_end_to_end_affect_codegen_and_report(tmp_path: Path) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    outdir = tmp_path / "sweep"
    code, payload = run_lanes_sweep(
        Path("example_b1_small_subgraph.json"),
        synapse_lanes=[1, 8],
        neuron_lanes=[1],
        ticks=2,
        outdir=outdir,
        hw_mode="off",
    )
    assert code == 0
    assert payload["ok"] is True

    sweep_results = outdir / "sweep_results.json"
    assert sweep_results.exists()

    summary = run_knob_sanity(sweep_results)
    assert summary["ok"] is True
    assert summary["criteria"]["kernelHashDiversity"] is True
    assert summary["criteria"]["benchScheduleMatchesSweep"] is True
    assert summary["counts"]["rows"] == 2
    assert summary["counts"]["uniqueBenchReportPaths"] == 2

    by_combo = {row["comboId"]: row for row in summary["rows"]}
    assert by_combo["syn1_neu1"]["kernelHashSha256"] != by_combo["syn8_neu1"]["kernelHashSha256"]

    for combo_id, expect_syn in (("syn1_neu1", 1), ("syn8_neu1", 8)):
        bench_path = Path(by_combo[combo_id]["benchReportPath"])
        bench = json.loads(bench_path.read_text(encoding="utf-8"))
        schedule = bench["config"]["schedule"]
        assert schedule["synapseLanes"] == expect_syn
        assert schedule["neuronLanes"] == 1
