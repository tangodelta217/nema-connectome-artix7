from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nema.cli import main


def _kind(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _expect_type(value: object, allowed: set[str]) -> str:
    kind = _kind(value)
    assert kind in allowed
    return "|".join(sorted(allowed))


def _bench_report_schema_projection(report: dict) -> dict:
    hardware = report["hardware"]
    assert isinstance(hardware, dict)
    toolchain = hardware["toolchain"]
    assert isinstance(toolchain, dict)
    vivado = hardware["vivado"]
    assert isinstance(vivado, dict)
    correctness = report["correctness"]
    performance = report["performance"]
    config = report["config"]
    provenance = report["provenance"]
    graph_resolved = report["graphResolved"]
    bench = report["bench"]

    return {
        "topLevelKeys": sorted(report.keys()),
        "ok": _expect_type(report["ok"], {"bool"}),
        "modelId": _expect_type(report["modelId"], {"str"}),
        "bench": {
            "topKeys": sorted(bench.keys()),
            "targetId": _expect_type(bench["targetId"], {"str"}),
        },
        "gitCommit": _expect_type(report["gitCommit"], {"str", "null"}),
        "createdAt": _expect_type(report["createdAt"], {"str"}),
        "ticks": _expect_type(report["ticks"], {"int"}),
        "irPath": _expect_type(report["irPath"], {"str"}),
        "irSha256": _expect_type(report["irSha256"], {"str"}),
        "provenance": {
            "syntheticUsed": _expect_type(provenance["syntheticUsed"], {"bool"}),
            "externalVerified": _expect_type(provenance["externalVerified"], {"bool"}),
        },
        "graphResolved": {
            "topKeys": sorted(graph_resolved.keys()),
            "nodeCount": _expect_type(graph_resolved["nodeCount"], {"int"}),
            "edgeCountsKeys": sorted(graph_resolved["edgeCounts"].keys()),
            "edgeCountsTotal": _expect_type(graph_resolved["edgeCounts"]["total"], {"int"}),
            "edgeCountsChemical": _expect_type(graph_resolved["edgeCounts"]["chemical"], {"int"}),
            "edgeCountsGap": _expect_type(graph_resolved["edgeCounts"]["gap"], {"int"}),
            "edgeCountsGapDirected": _expect_type(graph_resolved["edgeCounts"]["gapDirected"], {"int"}),
        },
        "toolchainVersions": {
            "python": _expect_type(report["toolchainVersions"]["python"], {"str", "null"}),
            "g++": _expect_type(report["toolchainVersions"]["g++"], {"str", "null"}),
            "vitis_hls": _expect_type(report["toolchainVersions"]["vitis_hls"], {"str", "null"}),
            "vivado": _expect_type(report["toolchainVersions"]["vivado"], {"str", "null"}),
        },
        "config": {
            "topKeys": sorted(config.keys()),
            "qformatsKeys": sorted(config["qformats"].keys()),
            "scheduleKeys": sorted(config["schedule"].keys()),
            "graphKeys": sorted(config["graph"].keys()),
            "dt": _expect_type(config["dt"], {"int", "float", "str"}),
            "dtNanoseconds": _expect_type(config["dtNanoseconds"], {"int", "null"}),
            "snapshotRule": _expect_type(config["schedule"]["snapshotRule"], {"bool"}),
            "synapseLanes": _expect_type(config["schedule"]["synapseLanes"], {"int"}),
            "neuronLanes": _expect_type(config["schedule"]["neuronLanes"], {"int"}),
            "graphNodeCount": _expect_type(config["graph"]["nodeCount"], {"int"}),
            "graphChemicalEdgeCount": _expect_type(config["graph"]["chemicalEdgeCount"], {"int"}),
            "graphGapEdgeCount": _expect_type(config["graph"]["gapEdgeCount"], {"int"}),
            "graphEdgeCountTotal": _expect_type(config["graph"]["edgeCountTotal"], {"int"}),
        },
        "correctness": {
            "topKeys": sorted(correctness.keys()),
            "goldenSimKeys": sorted(correctness["goldenSim"].keys()),
            "cppReferenceKeys": sorted(correctness["cppReference"].keys()),
            "digestMatchKeys": sorted(correctness["digestMatch"].keys()),
            "goldenDigests": _expect_type(correctness["goldenSim"]["digests"], {"list"}),
            "cppDigests": _expect_type(correctness["cppReference"]["digests"], {"list"}),
        },
        "performance": {
            "topKeys": sorted(performance.keys()),
            "cpuKeys": sorted(performance["cpu"].keys()),
            "hardware": _expect_type(performance["hardware"], {"object", "null"}),
        },
        "hardware": {
            "topKeys": sorted(hardware.keys()),
            "toolchainKeys": sorted(toolchain.keys()),
            "available": _expect_type(toolchain["available"], {"bool"}),
            "binary": _expect_type(toolchain["binary"], {"str", "null"}),
            "version": _expect_type(toolchain["version"], {"str", "null"}),
            "vivadoAvailable": _expect_type(toolchain["vivadoAvailable"], {"bool"}),
            "vivadoBinary": _expect_type(toolchain["vivadoBinary"], {"str", "null"}),
            "vivadoVersion": _expect_type(toolchain["vivadoVersion"], {"str", "null"}),
            "project": _expect_type(hardware["project"], {"str", "null"}),
            "csim": _expect_type(hardware["csim"], {"object", "null"}),
            "csynth": _expect_type(hardware["csynth"], {"object", "null"}),
            "cosim": _expect_type(hardware["cosim"], {"object", "null"}),
            "vivado": {
                "topKeys": sorted(vivado.keys()),
                "attempted": _expect_type(vivado["attempted"], {"bool"}),
                "ok": _expect_type(vivado["ok"], {"bool", "null"}),
                "implOk": _expect_type(vivado["implOk"], {"bool", "null"}),
                "skipped": _expect_type(vivado["skipped"], {"bool"}),
                "reason": _expect_type(vivado["reason"], {"str", "null"}),
                "returncode": _expect_type(vivado["returncode"], {"int", "null"}),
                "elapsedSeconds": _expect_type(vivado["elapsedSeconds"], {"float", "int", "null"}),
                "projectDir": _expect_type(vivado["projectDir"], {"str", "null"}),
                "runLog": _expect_type(vivado["runLog"], {"str", "null"}),
                "utilizationReport": _expect_type(vivado["utilizationReport"], {"str", "null"}),
                "timingReport": _expect_type(vivado["timingReport"], {"str", "null"}),
                "rtlSourceCount": _expect_type(vivado["rtlSourceCount"], {"int"}),
                "part": _expect_type(vivado["part"], {"str", "null"}),
                "clk_ns": _expect_type(vivado["clk_ns"], {"float", "int", "null"}),
                "wns": _expect_type(vivado["wns"], {"float", "int", "null"}),
                "tns": _expect_type(vivado["tns"], {"float", "int", "null"}),
                "utilKeys": sorted(vivado["util"].keys()),
                "utilLut": _expect_type(vivado["util"]["lut"], {"float", "int", "null"}),
                "utilFf": _expect_type(vivado["util"]["ff"], {"float", "int", "null"}),
                "utilBram": _expect_type(vivado["util"]["bram"], {"float", "int", "null"}),
                "utilDsp": _expect_type(vivado["util"]["dsp"], {"float", "int", "null"}),
                "utilizationKeys": sorted(vivado["utilization"].keys()),
                "timingKeys": sorted(vivado["timing"].keys()),
                "sourceReports": _expect_type(vivado["sourceReports"], {"list"}),
            },
            "reports": _expect_type(hardware["reports"], {"object", "null"}),
            "qor": {
                "topKeys": sorted(hardware["qor"].keys()),
                "utilizationKeys": sorted(hardware["qor"]["utilization"].keys()),
                "timingOrLatencyKeys": sorted(hardware["qor"]["timingOrLatency"].keys()),
                "lut": _expect_type(hardware["qor"]["utilization"]["lut"], {"int", "null"}),
                "ff": _expect_type(hardware["qor"]["utilization"]["ff"], {"int", "null"}),
                "bram": _expect_type(hardware["qor"]["utilization"]["bram"], {"int", "null"}),
                "dsp": _expect_type(hardware["qor"]["utilization"]["dsp"], {"int", "null"}),
                "iiTop": _expect_type(hardware["qor"]["ii"], {"int", "null"}),
                "latencyCyclesTop": _expect_type(hardware["qor"]["latencyCycles"], {"int", "null"}),
                "ii": _expect_type(hardware["qor"]["timingOrLatency"]["ii"], {"int", "null"}),
                "latencyCycles": _expect_type(
                    hardware["qor"]["timingOrLatency"]["latencyCycles"],
                    {"int", "null"},
                ),
                "sourceReports": _expect_type(hardware["qor"]["sourceReports"], {"list"}),
            },
        },
        "artifactsKeys": sorted(report["artifacts"].keys()),
        "validationKeys": sorted(report["validation"].keys()),
    }


def test_bench_report_schema_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    monkeypatch.setenv("NEMA_HWTEST_DISABLE_VITIS", "1")

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
    projection = _bench_report_schema_projection(report)

    snapshot_path = Path(__file__).resolve().parent / "snapshots" / "bench_report_schema.json"
    expected = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert projection == expected
