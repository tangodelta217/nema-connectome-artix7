"""Cost model v0 helpers for estimate/compare workflows."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .ir_resolve import resolve_ir_for_execution


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return default
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return default


def _read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("top-level JSON must be an object")
    return raw


def _extract_lanes(ir_payload: dict[str, Any]) -> dict[str, Any]:
    compile_obj = ir_payload.get("compile")
    schedule_obj = compile_obj.get("schedule") if isinstance(compile_obj, dict) else None
    synapse_raw = schedule_obj.get("synapseLanes") if isinstance(schedule_obj, dict) else None
    neuron_raw = schedule_obj.get("neuronLanes") if isinstance(schedule_obj, dict) else None

    synapse_lanes = _safe_int(synapse_raw, default=1)
    neuron_lanes = _safe_int(neuron_raw, default=1)
    if synapse_lanes <= 0:
        synapse_lanes = 1
    if neuron_lanes <= 0:
        neuron_lanes = 1

    return {
        "synapseLanes": synapse_lanes,
        "neuronLanes": neuron_lanes,
        "source": "compile.schedule" if isinstance(schedule_obj, dict) else "default",
    }


def _estimate_from_counts(*, node_count: int, chemical_edges: int, gap_edges: int, synapse_lanes: int, neuron_lanes: int) -> dict[str, Any]:
    syn_lane = max(1, synapse_lanes)
    neu_lane = max(1, neuron_lanes)

    ops = {
        "activationLookup": node_count,
        "chemicalMulAdd": chemical_edges * 2,
        "gapSubMulAdd": gap_edges * 3,
        "neuronUpdateOps": node_count * 4,
    }
    ops["total"] = sum(int(v) for v in ops.values())

    # bytes/tick is intentionally simple and architecture-agnostic in v0.
    state_snapshot_read = node_count * 2
    state_write_back = node_count * 2
    lut_read = node_count * 2
    chemical_edge_stream = chemical_edges * 6
    gap_edge_stream = gap_edges * 8

    states_total = state_snapshot_read + state_write_back + lut_read
    csr_total = chemical_edge_stream + gap_edge_stream
    bytes_tick = {
        "stateSnapshotRead": state_snapshot_read,
        "stateWriteBack": state_write_back,
        "lutRead": lut_read,
        "statesTotal": states_total,
        "chemicalEdgeStream": chemical_edge_stream,
        "gapEdgeStream": gap_edge_stream,
        "csrTotal": csr_total,
        "total": states_total + csr_total,
    }

    synapse_work_items = chemical_edges + gap_edges
    cycles = {
        "startup": 32,
        # v0 throughput assumptions: 3 synapse-edge ops/cycle/lane.
        "synapseStage": int(math.ceil(synapse_work_items / float(syn_lane * 3))),
        # v0 neuron throughput: 1 neuron update per cycle/lane.
        "neuronStage": int(math.ceil(node_count / float(neu_lane))),
    }
    cycles["perTick"] = int(cycles["startup"] + cycles["synapseStage"] + cycles["neuronStage"])

    return {
        "modelVersion": "nema.cost.v0",
        "inputs": {
            "nodeCount": node_count,
            "chemicalEdgeCount": chemical_edges,
            "gapEdgeCount": gap_edges,
            "synapseLanes": synapse_lanes,
            "neuronLanes": neuron_lanes,
        },
        "opsPerTick": ops,
        "bytesPerTick": bytes_tick,
        "cyclesPerTick": cycles,
    }


def _relative_error(*, predicted: int | None, actual: int | None) -> float | None:
    if predicted is None or actual is None:
        return None
    if actual == 0:
        return 0.0 if predicted == 0 else None
    return abs(float(predicted - actual)) / abs(float(actual))


def _ratio_to_actual(*, predicted: int | None, actual: int | None) -> float | None:
    if predicted is None or actual is None:
        return None
    if predicted <= 0 or actual <= 0:
        return None
    upper = max(float(predicted) / float(actual), float(actual) / float(predicted))
    return upper


def _actual_qor(bench_report: dict[str, Any]) -> dict[str, Any]:
    hardware = bench_report.get("hardware")
    if not isinstance(hardware, dict):
        return {"ii": None, "latencyCycles": None}
    qor = hardware.get("qor")
    if not isinstance(qor, dict):
        return {"ii": None, "latencyCycles": None}

    ii = qor.get("ii")
    latency = qor.get("latencyCycles")
    timing = qor.get("timingOrLatency")
    if isinstance(timing, dict):
        if ii is None:
            ii = timing.get("ii")
        if latency is None:
            latency = timing.get("latencyCycles")
    return {
        "ii": _safe_int(ii, default=0) if ii is not None else None,
        "latencyCycles": _safe_int(latency, default=0) if latency is not None else None,
    }


def _graph_counts_from_bench(bench_report: dict[str, Any]) -> dict[str, int]:
    config = bench_report.get("config")
    graph = config.get("graph") if isinstance(config, dict) else None
    if isinstance(graph, dict):
        return {
            "nodeCount": _safe_int(graph.get("nodeCount"), 0),
            "chemicalEdgeCount": _safe_int(graph.get("chemicalEdgeCount"), 0),
            "gapEdgeCount": _safe_int(graph.get("gapEdgeCount"), 0),
        }

    resolved = bench_report.get("graphResolved")
    edges = resolved.get("edgeCounts") if isinstance(resolved, dict) else None
    if isinstance(resolved, dict) and isinstance(edges, dict):
        return {
            "nodeCount": _safe_int(resolved.get("nodeCount"), 0),
            "chemicalEdgeCount": _safe_int(edges.get("chemical"), 0),
            "gapEdgeCount": _safe_int(edges.get("gap"), 0),
        }

    return {"nodeCount": 0, "chemicalEdgeCount": 0, "gapEdgeCount": 0}


def run_cost_estimate(ir_path: Path) -> tuple[int, dict[str, Any]]:
    try:
        resolved = resolve_ir_for_execution(ir_path)
    except FileNotFoundError:
        return 1, {"ok": False, "error": f"file not found: {ir_path}"}
    except (ValueError, json.JSONDecodeError) as exc:
        return 1, {"ok": False, "error": str(exc)}

    ir_payload = resolved.get("ir")
    graph_resolved = resolved.get("graphResolved")
    if not isinstance(ir_payload, dict) or not isinstance(graph_resolved, dict):
        return 1, {"ok": False, "error": "failed to resolve IR graph"}

    edge_counts = graph_resolved.get("edgeCounts", {})
    if not isinstance(edge_counts, dict):
        edge_counts = {}
    node_count = _safe_int(graph_resolved.get("nodeCount"), 0)
    chemical_edges = _safe_int(edge_counts.get("chemical"), 0)
    gap_edges = _safe_int(edge_counts.get("gap"), 0)
    lanes = _extract_lanes(ir_payload)

    estimate = _estimate_from_counts(
        node_count=node_count,
        chemical_edges=chemical_edges,
        gap_edges=gap_edges,
        synapse_lanes=lanes["synapseLanes"],
        neuron_lanes=lanes["neuronLanes"],
    )
    return 0, {
        "ok": True,
        "command": "cost estimate",
        "irPath": str(ir_path),
        "modelId": str(ir_payload.get("modelId", ir_payload.get("kernelId", "model"))),
        "provenance": resolved.get("provenance"),
        "graphResolved": graph_resolved,
        "lanes": lanes,
        "estimate": estimate,
    }


def _lanes_from_bench_or_ir(bench_report: dict[str, Any], bench_report_path: Path) -> dict[str, Any]:
    config = bench_report.get("config")
    schedule = config.get("schedule") if isinstance(config, dict) else None
    if isinstance(schedule, dict):
        syn = schedule.get("synapseLanes")
        neu = schedule.get("neuronLanes")
        if syn is not None or neu is not None:
            lanes = {
                "synapseLanes": max(1, _safe_int(syn, 1)),
                "neuronLanes": max(1, _safe_int(neu, 1)),
                "source": "bench_report.config.schedule",
            }
            return lanes

    ir_raw = bench_report.get("irPath")
    if isinstance(ir_raw, str) and ir_raw:
        ir_path = Path(ir_raw)
        if not ir_path.is_absolute():
            ir_path = (bench_report_path.parent / ir_path).resolve()
        if ir_path.exists():
            try:
                ir_payload = _read_json(ir_path)
                lanes = _extract_lanes(ir_payload)
                lanes["source"] = f"ir:{ir_path}"
                return lanes
            except (ValueError, OSError, json.JSONDecodeError):
                pass

    return {"synapseLanes": 1, "neuronLanes": 1, "source": "default"}


def run_cost_compare(bench_report_path: Path) -> tuple[int, dict[str, Any]]:
    try:
        bench_report = _read_json(bench_report_path)
    except FileNotFoundError:
        return 1, {"ok": False, "error": f"file not found: {bench_report_path}"}
    except (ValueError, json.JSONDecodeError) as exc:
        return 1, {"ok": False, "error": str(exc)}

    counts = _graph_counts_from_bench(bench_report)
    lanes = _lanes_from_bench_or_ir(bench_report, bench_report_path.resolve())
    estimate = _estimate_from_counts(
        node_count=counts["nodeCount"],
        chemical_edges=counts["chemicalEdgeCount"],
        gap_edges=counts["gapEdgeCount"],
        synapse_lanes=lanes["synapseLanes"],
        neuron_lanes=lanes["neuronLanes"],
    )

    predicted_cycles = estimate["cyclesPerTick"]["perTick"]
    actual = _actual_qor(bench_report)
    ratio_ii = _ratio_to_actual(predicted=predicted_cycles, actual=actual["ii"])
    ratio_latency = _ratio_to_actual(predicted=predicted_cycles, actual=actual["latencyCycles"])
    rel_err_ii = _relative_error(predicted=predicted_cycles, actual=actual["ii"])
    rel_err_latency = _relative_error(predicted=predicted_cycles, actual=actual["latencyCycles"])

    ratio_values = [value for value in (ratio_ii, ratio_latency) if isinstance(value, float)]
    rel_err_values = [value for value in (rel_err_ii, rel_err_latency) if isinstance(value, float)]
    compare = {
        "predictedCyclesPerTick": predicted_cycles,
        "actual": actual,
        "relativeError": {
            "ii": rel_err_ii,
            "latencyCycles": rel_err_latency,
        },
        "ratioToActual": {
            "ii": ratio_ii,
            "latencyCycles": ratio_latency,
        },
        "hasActualQor": len(ratio_values) > 0,
        "maxRatio": max(ratio_values) if ratio_values else None,
        "maxRelativeError": max(rel_err_values) if rel_err_values else None,
    }

    reports = bench_report.get("hardware", {}).get("reports", {}).get("files", [])
    util = bench_report.get("hardware", {}).get("qor", {}).get("utilization", {})
    util_non_null = False
    if isinstance(util, dict):
        util_non_null = any(value is not None for value in util.values())

    return 0, {
        "ok": True,
        "command": "cost compare",
        "benchReportPath": str(bench_report_path),
        "modelId": bench_report.get("modelId"),
        "counts": counts,
        "lanes": lanes,
        "estimate": estimate,
        "comparison": compare,
        "g2Evidence": {
            "reportsFilesNonEmpty": isinstance(reports, list) and len(reports) > 0,
            "qorUtilizationNonNull": util_non_null,
            "meetsG2": bool((isinstance(reports, list) and len(reports) > 0) or util_non_null),
        },
    }
