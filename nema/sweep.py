"""Lane sweep utilities for NEMA hwtest/QoR exploration."""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
from typing import Any

from .toolchain import run_hwtest


def parse_lane_list(raw: str) -> list[int]:
    """Parse comma-separated positive integer lane values into deterministic order."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("lane list must be a non-empty comma-separated string")

    values: list[int] = []
    for token in raw.split(","):
        part = token.strip()
        if not part:
            continue
        try:
            parsed = int(part, 10)
        except ValueError as exc:
            raise ValueError(f"invalid lane value '{part}'") from exc
        if parsed <= 0:
            raise ValueError(f"lane value must be > 0 (got {parsed})")
        values.append(parsed)

    if not values:
        raise ValueError("lane list produced no values")

    return sorted(set(values))


def _model_id_from_ir(ir_payload: dict[str, Any]) -> str:
    raw = ir_payload.get("modelId", ir_payload.get("kernelId", ir_payload.get("name", "model")))
    return str(raw)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _apply_lane_overrides(base_ir: dict[str, Any], *, synapse_lanes: int, neuron_lanes: int) -> dict[str, Any]:
    ir_payload = copy.deepcopy(base_ir)

    compile_obj = ir_payload.get("compile")
    if not isinstance(compile_obj, dict):
        compile_obj = {}
        ir_payload["compile"] = compile_obj

    schedule_obj = compile_obj.get("schedule")
    if not isinstance(schedule_obj, dict):
        schedule_obj = {}
        compile_obj["schedule"] = schedule_obj

    schedule_obj["synapseLanes"] = synapse_lanes
    schedule_obj["neuronLanes"] = neuron_lanes
    return ir_payload


def _absolutize_runtime_paths(ir_payload: dict[str, Any], *, base_dir: Path) -> None:
    tanh_lut = ir_payload.get("tanhLut")
    if isinstance(tanh_lut, dict):
        artifact = tanh_lut.get("artifact")
        if isinstance(artifact, str) and artifact:
            artifact_path = Path(artifact)
            if not artifact_path.is_absolute():
                tanh_lut["artifact"] = str((base_dir / artifact_path).resolve())

    graph = ir_payload.get("graph")
    if isinstance(graph, dict):
        external = graph.get("external")
        if isinstance(external, dict):
            for key in ("uri", "path"):
                raw = external.get(key)
                if isinstance(raw, str) and raw:
                    raw_path = Path(raw)
                    if not raw_path.is_absolute():
                        external[key] = str((base_dir / raw_path).resolve())


def _extract_qor_metrics(bench_report: dict[str, Any]) -> dict[str, Any]:
    hardware = bench_report.get("hardware")
    if not isinstance(hardware, dict):
        return {
            "toolchainAvailable": None,
            "csimOk": None,
            "csynthOk": None,
            "cosimAttempted": None,
            "cosimOk": None,
            "digestMatchOk": None,
            "utilization": {"lut": None, "ff": None, "bram": None, "dsp": None},
            "ii": None,
            "latencyCycles": None,
        }

    toolchain = hardware.get("toolchain")
    toolchain_available = toolchain.get("available") if isinstance(toolchain, dict) else None
    csim = hardware.get("csim")
    csynth = hardware.get("csynth")
    cosim = hardware.get("cosim")
    qor = hardware.get("qor")
    digest_match = bench_report.get("correctness", {}).get("digestMatch", {}).get("ok")

    utilization: dict[str, Any] = {"lut": None, "ff": None, "bram": None, "dsp": None}
    ii = None
    latency_cycles = None
    if isinstance(qor, dict):
        util_obj = qor.get("utilization")
        if isinstance(util_obj, dict):
            utilization = {
                "lut": util_obj.get("lut"),
                "ff": util_obj.get("ff"),
                "bram": util_obj.get("bram"),
                "dsp": util_obj.get("dsp"),
            }
        ii = qor.get("ii")
        latency_cycles = qor.get("latencyCycles")
        if ii is None or latency_cycles is None:
            timing = qor.get("timingOrLatency")
            if isinstance(timing, dict):
                if ii is None:
                    ii = timing.get("ii")
                if latency_cycles is None:
                    latency_cycles = timing.get("latencyCycles")

    return {
        "toolchainAvailable": toolchain_available,
        "csimOk": csim.get("ok") if isinstance(csim, dict) else None,
        "csynthOk": csynth.get("ok") if isinstance(csynth, dict) else None,
        "cosimAttempted": cosim.get("attempted") if isinstance(cosim, dict) else None,
        "cosimOk": cosim.get("ok") if isinstance(cosim, dict) else None,
        "digestMatchOk": digest_match,
        "utilization": utilization,
        "ii": ii,
        "latencyCycles": latency_cycles,
    }


def _bench_report_from_summary(summary: dict[str, Any], *, fallback: Path) -> tuple[Path, dict[str, Any] | None]:
    raw_path = summary.get("bench_report")
    if isinstance(raw_path, str) and raw_path:
        path = Path(raw_path)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
    else:
        path = fallback
    return path, _read_json(path)


def _write_results_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "comboId",
        "synapseLanes",
        "neuronLanes",
        "resumeSkipped",
        "ok",
        "hwtestExitCode",
        "benchReportPath",
        "digestMatchOk",
        "toolchainAvailable",
        "csimOk",
        "csynthOk",
        "cosimAttempted",
        "cosimOk",
        "lut",
        "ff",
        "bram",
        "dsp",
        "ii",
        "latencyCycles",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            util = row.get("utilization", {})
            writer.writerow(
                {
                    "comboId": row.get("comboId"),
                    "synapseLanes": row.get("synapseLanes"),
                    "neuronLanes": row.get("neuronLanes"),
                    "resumeSkipped": row.get("resumeSkipped"),
                    "ok": row.get("ok"),
                    "hwtestExitCode": row.get("hwtestExitCode"),
                    "benchReportPath": row.get("benchReportPath"),
                    "digestMatchOk": row.get("digestMatchOk"),
                    "toolchainAvailable": row.get("toolchainAvailable"),
                    "csimOk": row.get("csimOk"),
                    "csynthOk": row.get("csynthOk"),
                    "cosimAttempted": row.get("cosimAttempted"),
                    "cosimOk": row.get("cosimOk"),
                    "lut": util.get("lut"),
                    "ff": util.get("ff"),
                    "bram": util.get("bram"),
                    "dsp": util.get("dsp"),
                    "ii": row.get("ii"),
                    "latencyCycles": row.get("latencyCycles"),
                }
            )


def run_lanes_sweep(
    ir_path: Path,
    *,
    synapse_lanes: list[int],
    neuron_lanes: list[int],
    ticks: int,
    outdir: Path,
    hw_mode: str = "require",
) -> tuple[int, dict[str, Any]]:
    """Run a lane-parameter sweep by mutating compile.schedule lanes per combination."""
    if ticks < 0:
        return 1, {"ok": False, "error": "--ticks must be >= 0"}
    if hw_mode not in {"auto", "require", "off"}:
        return 1, {"ok": False, "error": f"invalid --hw mode '{hw_mode}' (expected auto|require|off)"}
    if not synapse_lanes:
        return 1, {"ok": False, "error": "--synapse produced no lanes"}
    if not neuron_lanes:
        return 1, {"ok": False, "error": "--neuron produced no lanes"}

    try:
        base_ir = json.loads(ir_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 1, {"ok": False, "error": f"IR file not found: {ir_path}"}
    except json.JSONDecodeError as exc:
        return 1, {"ok": False, "error": f"invalid IR JSON: {exc}"}

    if not isinstance(base_ir, dict):
        return 1, {"ok": False, "error": "IR root must be a JSON object"}

    base_ir_dir = ir_path.resolve().parent
    model_id = _model_id_from_ir(base_ir)
    outdir.mkdir(parents=True, exist_ok=True)

    combos: list[tuple[int, int]] = []
    for syn in sorted(set(synapse_lanes)):
        for neu in sorted(set(neuron_lanes)):
            combos.append((syn, neu))

    results: list[dict[str, Any]] = []
    for syn, neu in combos:
        combo_id = f"syn{syn}_neu{neu}"
        combo_outdir = outdir / combo_id
        combo_outdir.mkdir(parents=True, exist_ok=True)

        bench_report_path = (combo_outdir / model_id / "bench_report.json").resolve()
        ir_temp_path = combo_outdir / "ir_lanes.json"

        existing = _read_json(bench_report_path)
        if isinstance(existing, dict) and existing.get("ok") is True:
            metrics = _extract_qor_metrics(existing)
            results.append(
                {
                    "comboId": combo_id,
                    "synapseLanes": syn,
                    "neuronLanes": neu,
                    "resumeSkipped": True,
                    "ok": True,
                    "hwtestExitCode": 0,
                    "irPath": str(ir_temp_path.resolve()),
                    "benchReportPath": str(bench_report_path),
                    **metrics,
                }
            )
            continue

        combo_ir = _apply_lane_overrides(base_ir, synapse_lanes=syn, neuron_lanes=neu)
        _absolutize_runtime_paths(combo_ir, base_dir=base_ir_dir)
        _write_json(ir_temp_path, combo_ir)

        run_code, summary = run_hwtest(ir_temp_path, outdir=combo_outdir, ticks=ticks, hw_mode=hw_mode)
        if not isinstance(summary, dict):
            summary = {}
        bench_path, bench_payload = _bench_report_from_summary(summary, fallback=bench_report_path)
        metrics = _extract_qor_metrics(bench_payload or {})
        result_ok = bool(run_code == 0 and isinstance(bench_payload, dict) and bench_payload.get("ok") is True)

        results.append(
            {
                "comboId": combo_id,
                "synapseLanes": syn,
                "neuronLanes": neu,
                "resumeSkipped": False,
                "ok": result_ok,
                "hwtestExitCode": run_code,
                "irPath": str(ir_temp_path.resolve()),
                "benchReportPath": str(bench_path.resolve()),
                **metrics,
            }
        )

    json_path = outdir / "sweep_results.json"
    csv_path = outdir / "sweep_results.csv"
    _write_results_csv(csv_path, results)

    payload = {
        "ok": all(bool(item.get("ok")) for item in results),
        "irPath": str(ir_path),
        "ticks": ticks,
        "hwMode": hw_mode,
        "outdir": str(outdir),
        "synapseLanes": sorted(set(synapse_lanes)),
        "neuronLanes": sorted(set(neuron_lanes)),
        "resultsCount": len(results),
        "results": results,
        "resultsJson": str(json_path),
        "resultsCsv": str(csv_path),
    }
    _write_json(json_path, payload)
    return (0 if payload["ok"] else 1), payload
