from __future__ import annotations

import json
from pathlib import Path


def test_bench_report_schema_defines_cosim_contract() -> None:
    schema_path = Path("tools/bench_report_schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    cosim = (
        schema["properties"]["hardware"]["properties"]["cosim"]
    )
    assert sorted(cosim["type"]) == ["null", "object"]
    assert cosim["required"] == ["attempted", "ok", "skipped"]
    assert cosim["properties"]["attempted"]["type"] == "boolean"
    assert sorted(cosim["properties"]["ok"]["type"]) == ["boolean", "null"]
    assert cosim["properties"]["skipped"]["type"] == "boolean"


def test_bench_report_schema_defines_vivado_impl_contract() -> None:
    schema_path = Path("tools/bench_report_schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    vivado = schema["properties"]["hardware"]["properties"]["vivado"]
    required = set(vivado["required"])
    for key in ("implOk", "part", "requested_part", "selected_part", "part_match_requested", "clk_ns", "wns", "tns", "util"):
        assert key in required

    props = vivado["properties"]
    assert sorted(props["implOk"]["type"]) == ["boolean", "null"]
    assert sorted(props["part"]["type"]) == ["null", "string"]
    assert sorted(props["requested_part"]["type"]) == ["null", "string"]
    assert sorted(props["selected_part"]["type"]) == ["null", "string"]
    assert props["part_match_requested"]["type"] == "boolean"
    assert sorted(props["clk_ns"]["type"]) == ["null", "number"]
    assert sorted(props["wns"]["type"]) == ["null", "number"]
    assert sorted(props["tns"]["type"]) == ["null", "number"]
    assert props["util"]["type"] == "object"
    assert props["util"]["required"] == ["lut", "ff", "bram", "dsp"]


def test_bench_report_schema_defines_schedule_lanes_contract() -> None:
    schema_path = Path("tools/bench_report_schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    schedule = schema["properties"]["config"]["properties"]["schedule"]
    required = set(schedule["required"])
    assert "synapseLanes" in required
    assert "neuronLanes" in required

    props = schedule["properties"]
    assert props["synapseLanes"]["type"] == "integer"
    assert props["synapseLanes"]["minimum"] == 1
    assert props["neuronLanes"]["type"] == "integer"
    assert props["neuronLanes"]["minimum"] == 1
