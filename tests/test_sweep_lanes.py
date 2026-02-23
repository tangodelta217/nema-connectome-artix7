from __future__ import annotations

import csv
import json
from pathlib import Path

from nema.sweep import parse_lane_list, run_lanes_sweep


def _write_base_ir(path: Path, *, model_id: str = "test_model") -> None:
    payload = {
        "modelId": model_id,
        "graph": {
            "nodes": [{"id": "n0", "index": 0, "canonicalOrderId": 0}],
            "edges": [],
            "dt": 1.0,
        },
        "compile": {
            "schedule": {
                "synapseLanes": 1,
                "neuronLanes": 1,
            }
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_bench_report(path: Path, *, lut: int, ff: int, bram: int, dsp: int, ii: int, latency: int) -> None:
    payload = {
        "ok": True,
        "correctness": {"digestMatch": {"ok": True}},
        "hardware": {
            "toolchain": {"available": True},
            "csim": {"ok": True},
            "csynth": {"ok": True},
            "cosim": {"attempted": False, "ok": None},
            "reports": {"files": ["hw_reports/syn/report/csynth.rpt"]},
            "qor": {
                "utilization": {"lut": lut, "ff": ff, "bram": bram, "dsp": dsp},
                "ii": ii,
                "latencyCycles": latency,
                "timingOrLatency": {"ii": ii, "latencyCycles": latency},
                "sourceReports": ["hw_reports/syn/report/csynth.rpt"],
            },
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_parse_lane_list_deterministic() -> None:
    assert parse_lane_list("4,2,4,1") == [1, 2, 4]


def test_run_lanes_sweep_writes_json_and_csv(tmp_path: Path, monkeypatch) -> None:
    ir_path = tmp_path / "ir.json"
    _write_base_ir(ir_path)
    outdir = tmp_path / "sweep_out"

    def fake_run_hwtest(ir_path: Path, outdir: Path, ticks: int, *, hw_mode: str = "auto"):
        ir_payload = json.loads(ir_path.read_text(encoding="utf-8"))
        schedule = ir_payload["compile"]["schedule"]
        syn = int(schedule["synapseLanes"])
        neu = int(schedule["neuronLanes"])
        model_id = str(ir_payload["modelId"])
        bench_path = outdir / model_id / "bench_report.json"
        _write_bench_report(
            bench_path,
            lut=100 * syn + neu,
            ff=1000 * syn + neu,
            bram=syn,
            dsp=neu,
            ii=syn + neu,
            latency=syn + neu + 1,
        )
        return 0, {"ok": True, "bench_report": str(bench_path)}

    monkeypatch.setattr("nema.sweep.run_hwtest", fake_run_hwtest)

    code, payload = run_lanes_sweep(
        ir_path,
        synapse_lanes=[2, 1],
        neuron_lanes=[2, 1],
        ticks=2,
        outdir=outdir,
        hw_mode="require",
    )

    assert code == 0
    assert payload["ok"] is True
    assert payload["resultsCount"] == 4
    combos = [(item["synapseLanes"], item["neuronLanes"]) for item in payload["results"]]
    assert combos == [(1, 1), (1, 2), (2, 1), (2, 2)]

    json_path = outdir / "sweep_results.json"
    csv_path = outdir / "sweep_results.csv"
    assert json_path.exists()
    assert csv_path.exists()

    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["resultsCount"] == 4
    assert all(item["ok"] is True for item in loaded["results"])

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 4
    assert rows[0]["synapseLanes"] == "1"
    assert rows[0]["neuronLanes"] == "1"
    assert rows[0]["lut"] == "101"


def test_run_lanes_sweep_resume_skips_existing_ok_bench_report(tmp_path: Path, monkeypatch) -> None:
    ir_path = tmp_path / "ir.json"
    _write_base_ir(ir_path, model_id="resume_model")
    outdir = tmp_path / "sweep_out"

    existing_report = outdir / "syn1_neu1" / "resume_model" / "bench_report.json"
    _write_bench_report(existing_report, lut=11, ff=101, bram=1, dsp=1, ii=2, latency=3)

    call_count = {"n": 0}

    def fake_run_hwtest(ir_path: Path, outdir: Path, ticks: int, *, hw_mode: str = "auto"):
        call_count["n"] += 1
        ir_payload = json.loads(ir_path.read_text(encoding="utf-8"))
        schedule = ir_payload["compile"]["schedule"]
        syn = int(schedule["synapseLanes"])
        neu = int(schedule["neuronLanes"])
        bench_path = outdir / "resume_model" / "bench_report.json"
        _write_bench_report(
            bench_path,
            lut=100 * syn + neu,
            ff=1000 * syn + neu,
            bram=syn,
            dsp=neu,
            ii=syn + neu,
            latency=syn + neu + 1,
        )
        return 0, {"ok": True, "bench_report": str(bench_path)}

    monkeypatch.setattr("nema.sweep.run_hwtest", fake_run_hwtest)

    code, payload = run_lanes_sweep(
        ir_path,
        synapse_lanes=[1],
        neuron_lanes=[1, 2],
        ticks=2,
        outdir=outdir,
        hw_mode="require",
    )

    assert code == 0
    assert payload["ok"] is True
    assert payload["resultsCount"] == 2
    assert call_count["n"] == 1
    first, second = payload["results"]
    assert first["comboId"] == "syn1_neu1"
    assert first["resumeSkipped"] is True
    assert second["comboId"] == "syn1_neu2"
    assert second["resumeSkipped"] is False


def test_run_lanes_sweep_temp_ir_changes_only_schedule_lanes(tmp_path: Path, monkeypatch) -> None:
    ir_path = tmp_path / "ir.json"
    payload = {
        "modelId": "shape_model",
        "name": "shape_model",
        "graph": {
            "nodes": [{"id": "n0", "index": 0, "canonicalOrderId": 0}],
            "edges": [],
            "dt": 1.0,
        },
        "compile": {
            "schedule": {
                "synapseLanes": 1,
                "neuronLanes": 1,
                "snapshotRule": True,
            }
        },
        "tanhLut": {"artifact": "artifacts/luts/tanh_q8_8.bin"},
    }
    ir_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    outdir = tmp_path / "sweep_out"

    seen_payloads: list[dict] = []

    def fake_run_hwtest(ir_path: Path, outdir: Path, ticks: int, *, hw_mode: str = "auto"):
        ir_payload = json.loads(ir_path.read_text(encoding="utf-8"))
        seen_payloads.append(ir_payload)
        model_id = str(ir_payload["modelId"])
        bench_path = outdir / model_id / "bench_report.json"
        _write_bench_report(bench_path, lut=10, ff=20, bram=1, dsp=1, ii=2, latency=3)
        return 0, {"ok": True, "bench_report": str(bench_path)}

    monkeypatch.setattr("nema.sweep.run_hwtest", fake_run_hwtest)

    code, report = run_lanes_sweep(
        ir_path,
        synapse_lanes=[4],
        neuron_lanes=[2],
        ticks=2,
        outdir=outdir,
        hw_mode="require",
    )

    assert code == 0
    assert report["ok"] is True
    assert len(seen_payloads) == 1

    generated = seen_payloads[0]
    assert generated["modelId"] == payload["modelId"]
    assert generated["name"] == payload["name"]
    assert generated["graph"] == payload["graph"]
    assert generated["compile"]["schedule"]["snapshotRule"] is True
    assert generated["compile"]["schedule"]["synapseLanes"] == 4
    assert generated["compile"]["schedule"]["neuronLanes"] == 2
