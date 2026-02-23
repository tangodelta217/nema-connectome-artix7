from __future__ import annotations

import json
from pathlib import Path

import pytest

from nema.cli import main


def _write_ir(path: Path) -> None:
    payload = {
        "modelId": "cost_estimate_test",
        "compile": {
            "schedule": {
                "synapseLanes": 2,
                "neuronLanes": 1,
            }
        },
        "graph": {
            "nodes": [
                {"id": "n0", "index": 0, "canonicalOrderId": 0},
                {"id": "n1", "index": 1, "canonicalOrderId": 1},
            ],
            "edges": [
                {
                    "id": "e0",
                    "kind": "CHEMICAL",
                    "source": "n0",
                    "target": "n1",
                    "conductance": 0.1,
                    "directed": True,
                }
            ],
        },
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_cost_estimate_cli(tmp_path: Path, capsys) -> None:
    ir_path = tmp_path / "ir.json"
    _write_ir(ir_path)

    code = main(["cost", "estimate", str(ir_path)])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["command"] == "cost estimate"
    assert payload["estimate"]["modelVersion"] == "nema.cost.v0"
    assert payload["estimate"]["inputs"]["nodeCount"] == 2
    assert payload["estimate"]["inputs"]["chemicalEdgeCount"] == 1
    assert payload["estimate"]["inputs"]["gapEdgeCount"] == 0
    assert payload["estimate"]["opsPerTick"]["total"] == 12
    assert payload["estimate"]["bytesPerTick"]["total"] == 18
    assert payload["estimate"]["bytesPerTick"]["statesTotal"] == 12
    assert payload["estimate"]["bytesPerTick"]["csrTotal"] == 6
    assert payload["estimate"]["cyclesPerTick"]["perTick"] == 35


def test_cost_compare_cli_fixture(capsys) -> None:
    bench_report_path = Path("tests/fixtures/cost/bench_report_mock.json")

    code = main(["cost", "compare", str(bench_report_path)])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["command"] == "cost compare"
    assert payload["counts"]["nodeCount"] == 4
    assert payload["counts"]["chemicalEdgeCount"] == 6
    assert payload["counts"]["gapEdgeCount"] == 2
    assert payload["comparison"]["predictedCyclesPerTick"] == 38
    assert payload["comparison"]["actual"]["ii"] == 12
    assert payload["comparison"]["actual"]["latencyCycles"] == 30
    assert payload["comparison"]["relativeError"]["ii"] == pytest.approx(26.0 / 12.0)
    assert payload["comparison"]["relativeError"]["latencyCycles"] == pytest.approx(8.0 / 30.0)
    assert payload["comparison"]["ratioToActual"]["ii"] == pytest.approx(38.0 / 12.0)
    assert payload["comparison"]["ratioToActual"]["latencyCycles"] == pytest.approx(38.0 / 30.0)
    assert payload["comparison"]["hasActualQor"] is True
    assert payload["comparison"]["maxRatio"] == pytest.approx(38.0 / 12.0)
    assert payload["g2Evidence"]["reportsFilesNonEmpty"] is True
    assert payload["g2Evidence"]["qorUtilizationNonNull"] is True
    assert payload["g2Evidence"]["meetsG2"] is True
