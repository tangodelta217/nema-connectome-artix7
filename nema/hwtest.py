"""Hardware test orchestration and bench report generation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

from .codegen.hls_gen import generate_hls_project
from .ir_resolve import resolve_ir_for_execution
from .ir_validate import IRValidationError, validate_ir
from .sim import simulate


@dataclass(frozen=True)
class CmdResult:
    cmd: list[str]
    cwd: str
    returncode: int
    stdout: str
    stderr: str
    elapsed_s: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _cmd(cmd: list[str], *, cwd: Path) -> CmdResult:
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)
    elapsed = time.perf_counter() - start
    return CmdResult(
        cmd=cmd,
        cwd=str(cwd),
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        elapsed_s=elapsed,
    )


def _first_line(text: str) -> str | None:
    lines = text.splitlines()
    return lines[0] if lines else None


def _git_commit() -> str | None:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    commit = proc.stdout.strip()
    return commit or None


def _tool_versions(vitis_binary: str | None) -> dict[str, Any]:
    versions: dict[str, Any] = {
        "python": _first_line(sys.version),
        "g++": None,
        "vitis_hls": None,
    }
    gpp = shutil.which("g++")
    if gpp:
        proc = subprocess.run([gpp, "--version"], check=False, capture_output=True, text=True)
        versions["g++"] = _first_line(proc.stdout or proc.stderr)
    if vitis_binary:
        proc = subprocess.run([vitis_binary, "-version"], check=False, capture_output=True, text=True)
        versions["vitis_hls"] = _first_line(proc.stdout or proc.stderr)
    return versions


def _round_fraction_rne(value: Fraction) -> int:
    sign = -1 if value < 0 else 1
    num = abs(value.numerator)
    den = value.denominator
    q, r = divmod(num, den)
    two_r = 2 * r
    if two_r > den or (two_r == den and (q & 1)):
        q += 1
    return sign * q


def _dt_nanoseconds(dt: Any) -> int | None:
    if isinstance(dt, bool) or not isinstance(dt, (int, float, str)):
        return None
    try:
        frac = Fraction(str(dt))
    except (ValueError, ZeroDivisionError):
        return None
    return _round_fraction_rne(frac * 1_000_000_000)


def _resolved_graph_counts(ir: dict[str, Any], graph_resolved: dict[str, Any] | None) -> dict[str, int]:
    if graph_resolved is not None:
        edge_counts = graph_resolved.get("edgeCounts", {})
        return {
            "nodeCount": int(graph_resolved.get("nodeCount", 0)),
            "chemicalEdgeCount": int(edge_counts.get("chemical", 0)),
            "gapEdgeCount": int(edge_counts.get("gap", 0)),
            "edgeCountTotal": int(edge_counts.get("total", 0)),
        }

    graph = ir.get("graph", {})
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_count = len(nodes) if isinstance(nodes, list) else 0
    if not isinstance(edges, list):
        edges = []
    chemical_count = sum(
        1 for edge in edges if isinstance(edge, dict) and str(edge.get("kind", edge.get("type", ""))).upper() == "CHEMICAL"
    )
    gap_directed_count = sum(
        1 for edge in edges if isinstance(edge, dict) and str(edge.get("kind", edge.get("type", ""))).upper() == "GAP"
    )
    return {
        "nodeCount": node_count,
        "chemicalEdgeCount": chemical_count,
        "gapEdgeCount": gap_directed_count // 2,
        "edgeCountTotal": len(edges),
    }


def _config_summary(ir: dict[str, Any], *, graph_resolved: dict[str, Any] | None = None) -> dict[str, Any]:
    graph = ir.get("graph", {})
    tanh_lut = ir.get("tanhLut", {})
    dt = graph.get("dt", 1.0)
    graph_counts = _resolved_graph_counts(ir, graph_resolved)
    return {
        "qformats": {
            "voltage": "Q8.8",
            "activation": str(tanh_lut.get("outputType", "Q8.8")),
            "accum": "Q12.8",
            "lutInput": str(tanh_lut.get("inputType", "Q8.8")),
            "lutOutput": str(tanh_lut.get("outputType", "Q8.8")),
        },
        "dt": dt,
        "dtNanoseconds": _dt_nanoseconds(dt),
        "schedule": {
            "policy": "nema.tick.v0.1",
            "snapshotRule": True,
            "evalOrder": "index",
        },
        "graph": graph_counts,
    }


def _build_target_id(model_id: str, *, ir: dict[str, Any], graph_resolved: dict[str, Any]) -> str:
    bench_obj = ir.get("bench")
    if isinstance(bench_obj, dict):
        raw_target = bench_obj.get("targetId")
        if isinstance(raw_target, str) and raw_target.strip():
            return raw_target.strip()

    edge_counts = graph_resolved.get("edgeCounts", {})
    node_count = int(graph_resolved.get("nodeCount", 0))
    chemical_edges = int(edge_counts.get("chemical", 0))
    return f"{model_id}/CE/{node_count}-{chemical_edges}"


def _schema_matches_type(value: Any, schema_type: str) -> bool:
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(value, float)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return False


def _schema_validate(value: Any, schema: dict[str, Any], *, path: str = "$") -> None:
    raw_type = schema.get("type")
    if raw_type is not None:
        allowed_types = raw_type if isinstance(raw_type, list) else [raw_type]
        if not any(_schema_matches_type(value, schema_type) for schema_type in allowed_types):
            raise ValueError(f"{path}: expected type {allowed_types}, got {type(value).__name__}")

    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: value '{value}' is not in enum {schema['enum']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            raise ValueError(f"{path}: value {value} is less than minimum {minimum}")
        if maximum is not None and value > maximum:
            raise ValueError(f"{path}: value {value} is greater than maximum {maximum}")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if min_length is not None and len(value) < min_length:
            raise ValueError(f"{path}: string shorter than minLength {min_length}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < min_items:
            raise ValueError(f"{path}: array has fewer than {min_items} items")
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for idx, item in enumerate(value):
                _schema_validate(item, items_schema, path=f"{path}[{idx}]")

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise ValueError(f"{path}: missing required key '{key}'")

        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties and isinstance(properties[key], dict):
                _schema_validate(item, properties[key], path=f"{path}.{key}")
                continue
            if additional is False:
                raise ValueError(f"{path}: unexpected key '{key}'")
            if isinstance(additional, dict):
                _schema_validate(item, additional, path=f"{path}.{key}")


def _validate_bench_report_schema(bench_report: dict[str, Any]) -> None:
    schema_path = Path(__file__).resolve().parents[1] / "tools" / "bench_report_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise ValueError("tools/bench_report_schema.json must contain a JSON object")
    _schema_validate(bench_report, schema, path="$")


def _detect_vitis_hls() -> dict[str, Any]:
    if os.environ.get("NEMA_HWTEST_DISABLE_VITIS", "").lower() in {"1", "true", "yes"}:
        return {
            "available": False,
            "binary": None,
            "version": None,
        }
    binary = shutil.which("vitis_hls")
    if not binary:
        return {
            "available": False,
            "binary": None,
            "version": None,
        }
    proc = subprocess.run([binary, "-version"], check=False, capture_output=True, text=True)
    return {
        "available": True,
        "binary": binary,
        "version": _first_line(proc.stdout or proc.stderr),
    }


def _run_cpp_reference(
    *,
    hls_cpp: Path,
    cpp_ref_main: Path,
    model_root: Path,
    ticks: int,
) -> dict[str, Any]:
    hls_cpp = hls_cpp.resolve()
    cpp_ref_main = cpp_ref_main.resolve()
    model_root = model_root.resolve()
    gpp = shutil.which("g++")
    if not gpp:
        return {
            "ok": False,
            "reason": "g++ not found on PATH",
            "digests": [],
            "ticks": ticks,
            "binaryPath": None,
            "compile": None,
            "run": None,
            "error": "g++ missing",
            "elapsedSeconds": None,
        }

    exe_path = model_root / "cpp_ref" / "nema_cpp_ref"
    compile_cmd = [gpp, "-std=c++17", "-O2", str(cpp_ref_main), str(hls_cpp), "-o", str(exe_path)]
    compile_res = _cmd(compile_cmd, cwd=model_root)
    if not compile_res.ok:
        return {
            "ok": False,
            "reason": "compile_failed",
            "digests": [],
            "ticks": ticks,
            "binaryPath": str(exe_path),
            "compile": {
                "cmd": compile_res.cmd,
                "cwd": compile_res.cwd,
                "returncode": compile_res.returncode,
                "elapsedSeconds": compile_res.elapsed_s,
                "stderr": compile_res.stderr[-4000:],
            },
            "run": None,
            "error": "failed to compile cpp reference harness",
            "elapsedSeconds": None,
        }

    run_cmd = [str(exe_path), str(ticks)]
    run_res = _cmd(run_cmd, cwd=model_root)
    if not run_res.ok:
        return {
            "ok": False,
            "reason": "run_failed",
            "digests": [],
            "ticks": ticks,
            "binaryPath": str(exe_path),
            "compile": {
                "cmd": compile_res.cmd,
                "cwd": compile_res.cwd,
                "returncode": compile_res.returncode,
                "elapsedSeconds": compile_res.elapsed_s,
            },
            "run": {
                "cmd": run_res.cmd,
                "cwd": run_res.cwd,
                "returncode": run_res.returncode,
                "elapsedSeconds": run_res.elapsed_s,
                "stderr": run_res.stderr[-4000:],
            },
            "error": "cpp reference executable failed",
            "elapsedSeconds": run_res.elapsed_s,
        }

    try:
        payload = json.loads(run_res.stdout)
        digests = payload.get("tickDigestsSha256", [])
        if not isinstance(digests, list):
            raise ValueError("tickDigestsSha256 is not a list")
        for item in digests:
            if not isinstance(item, str):
                raise ValueError("digest item is not a string")
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            "ok": False,
            "reason": "invalid_output",
            "digests": [],
            "ticks": ticks,
            "binaryPath": str(exe_path),
            "compile": {
                "cmd": compile_res.cmd,
                "cwd": compile_res.cwd,
                "returncode": compile_res.returncode,
                "elapsedSeconds": compile_res.elapsed_s,
            },
            "run": {
                "cmd": run_res.cmd,
                "cwd": run_res.cwd,
                "returncode": run_res.returncode,
                "elapsedSeconds": run_res.elapsed_s,
                "stdout": run_res.stdout[-4000:],
            },
            "error": str(exc),
            "elapsedSeconds": run_res.elapsed_s,
        }

    return {
        "ok": True,
        "reason": None,
        "digests": digests,
        "ticks": ticks,
        "binaryPath": str(exe_path),
        "compile": {
            "cmd": compile_res.cmd,
            "cwd": compile_res.cwd,
            "returncode": compile_res.returncode,
            "elapsedSeconds": compile_res.elapsed_s,
        },
        "run": {
            "cmd": run_res.cmd,
            "cwd": run_res.cwd,
            "returncode": run_res.returncode,
            "elapsedSeconds": run_res.elapsed_s,
        },
        "error": None,
        "elapsedSeconds": run_res.elapsed_s,
    }


def _collect_hls_reports(solution_dir: Path) -> dict[str, Any] | None:
    if not solution_dir.exists():
        return None
    report_files = sorted(str(p) for p in solution_dir.rglob("*") if p.is_file() and p.suffix in {".rpt", ".xml"})
    util_report = next((p for p in report_files if "util" in p.lower() or "csynth.rpt" in p.lower()), None)
    timing_report = next((p for p in report_files if "timing" in p.lower() or "csynth.rpt" in p.lower()), None)
    return {
        "reportFiles": report_files,
        "utilizationReport": util_report,
        "timingReport": timing_report,
    }


def _run_vitis_hls(
    *,
    vitis_binary: str,
    hls_cpp: Path,
    cpp_ref_main: Path,
    model_root: Path,
    run_cosim: bool,
) -> dict[str, Any]:
    project_dir = model_root / "vitis_hls"
    project_dir.mkdir(parents=True, exist_ok=True)
    tcl_path = project_dir / "run_hls.tcl"
    part = os.environ.get("NEMA_VITIS_PART", "xc7z020clg400-1")
    clock_ns = os.environ.get("NEMA_VITIS_CLOCK_NS", "5.0")
    tcl_lines = [
        "open_project -reset nema_hwtest",
        "set_top nema_kernel",
        f"add_files {{{hls_cpp}}}",
        f"add_files -tb {{{cpp_ref_main}}}",
        "open_solution -reset sol1",
        f"set_part {{{part}}}",
        f"create_clock -period {clock_ns}",
        "csim_design",
        "csynth_design",
    ]
    if run_cosim:
        tcl_lines.append("cosim_design -rtl verilog")
    tcl_lines.append("exit")
    tcl_path.write_text("\n".join(tcl_lines) + "\n", encoding="utf-8")

    proc = _cmd([vitis_binary, "-f", str(tcl_path)], cwd=project_dir)
    solution_dir = project_dir / "nema_hwtest" / "sol1"
    reports = _collect_hls_reports(solution_dir)

    csim_ok = proc.ok
    cosim_result: dict[str, Any] | None
    if run_cosim:
        cosim_result = {
            "attempted": True,
            "ok": proc.ok,
            "skipped": False,
        }
    else:
        cosim_result = {
            "attempted": False,
            "ok": None,
            "skipped": True,
        }

    return {
        "toolchain": {
            "available": True,
            "binary": vitis_binary,
            "version": _detect_vitis_hls().get("version"),
        },
        "project": str(project_dir),
        "csim": {
            "attempted": True,
            "ok": csim_ok,
            "returncode": proc.returncode,
            "elapsedSeconds": proc.elapsed_s,
            "logTail": (proc.stdout + "\n" + proc.stderr)[-4000:],
        },
        "cosim": cosim_result,
        "reports": reports,
    }


def run_hwtest_pipeline(ir_path: Path, outdir: Path, ticks: int) -> tuple[int, dict[str, Any]]:
    """Run golden sim + C++ reference (+ optional Vitis HLS) and emit bench_report.json."""
    if ticks < 0:
        return 1, {"ok": False, "error": "--ticks must be >= 0"}

    try:
        ir_validation = validate_ir(ir_path, allow_external_smoke=True)
        resolved = resolve_ir_for_execution(ir_path)
        ir_payload = resolved["ir"]
        ir_sha256 = resolved["ir_sha256"]
        provenance = resolved["provenance"]
        graph_resolved = resolved["graphResolved"]
    except FileNotFoundError:
        return 1, {"ok": False, "error": f"file not found: {ir_path}"}
    except (IRValidationError, ValueError) as exc:
        return 1, {"ok": False, "error": str(exc)}

    outdir.mkdir(parents=True, exist_ok=True)
    created_at = _utc_now_iso()
    model_id_raw = ir_payload.get("modelId", ir_payload.get("kernelId", ir_payload.get("name", "model")))
    model_id = str(model_id_raw)
    model_root = outdir / model_id
    model_root.mkdir(parents=True, exist_ok=True)

    try:
        gen_report = generate_hls_project(
            ir_path=ir_path,
            outdir=outdir,
            ir_payload_override=ir_payload,
            ir_sha256_override=ir_sha256,
            base_dir=ir_path.parent,
        )
    except (FileNotFoundError, ValueError) as exc:
        return 1, {"ok": False, "error": f"codegen failed: {exc}"}

    hls_cpp = Path(gen_report["hls_cpp"])
    cpp_ref_main = Path(gen_report["cpp_ref_main"])

    golden_trace = model_root / "golden" / "trace.jsonl"
    golden_digest_json = model_root / "golden" / "digest.json"
    start_golden = time.perf_counter()
    try:
        sim_report = simulate(
            ir_payload,
            ticks=ticks,
            seed=0,
            trace_path=golden_trace,
            base_dir=ir_path.parent,
        )
        golden_ok = True
        golden_error = None
    except Exception as exc:  # pragma: no cover - defensive path for runtime issues
        sim_report = None
        golden_ok = False
        golden_error = str(exc)
    golden_elapsed = time.perf_counter() - start_golden
    if sim_report is not None:
        _write_json(golden_digest_json, sim_report)

    cpp_report = _run_cpp_reference(
        hls_cpp=hls_cpp,
        cpp_ref_main=cpp_ref_main,
        model_root=model_root,
        ticks=ticks,
    )

    golden_digests = sim_report["tickDigestsSha256"] if sim_report else []
    cpp_digests = cpp_report["digests"]
    digests_match = golden_ok and cpp_report["ok"] and (golden_digests == cpp_digests)
    mismatch_index = None
    if golden_ok and cpp_report["ok"] and not digests_match:
        for idx, (left, right) in enumerate(zip(golden_digests, cpp_digests)):
            if left != right:
                mismatch_index = idx
                break
        if mismatch_index is None and len(golden_digests) != len(cpp_digests):
            mismatch_index = min(len(golden_digests), len(cpp_digests))

    vitis_info = _detect_vitis_hls()
    run_cosim = os.environ.get("NEMA_HWTEST_RUN_COSIM", "").lower() in {"1", "true", "yes"}
    if vitis_info["available"]:
        hardware = _run_vitis_hls(
            vitis_binary=str(vitis_info["binary"]),
            hls_cpp=hls_cpp,
            cpp_ref_main=cpp_ref_main,
            model_root=model_root,
            run_cosim=run_cosim,
        )
    else:
        hardware = {
            "toolchain": vitis_info,
            "project": None,
            "csim": None,
            "cosim": None,
            "reports": None,
        }

    tool_versions = _tool_versions(vitis_binary=str(vitis_info["binary"]) if vitis_info["available"] else None)
    cpp_tps = (ticks / cpp_report["elapsedSeconds"]) if cpp_report["ok"] and cpp_report["elapsedSeconds"] else None
    golden_tps = (ticks / golden_elapsed) if golden_ok and golden_elapsed > 0 else None

    correctness = {
        "goldenSim": {
            "ok": golden_ok,
            "digests": golden_digests,
            "digestPath": str(golden_digest_json),
            "tracePath": str(golden_trace),
            "error": golden_error,
        },
        "cppReference": {
            "ok": cpp_report["ok"],
            "digests": cpp_digests,
            "binaryPath": cpp_report["binaryPath"],
            "error": cpp_report["error"],
        },
        "digestMatch": {
            "ok": digests_match,
            "mismatchTick": mismatch_index,
        },
    }

    hardware_ok = True
    if hardware["toolchain"]["available"]:
        csim = hardware.get("csim")
        hardware_ok = bool(csim and csim.get("ok"))
        cosim = hardware.get("cosim")
        if cosim and cosim.get("attempted"):
            hardware_ok = hardware_ok and bool(cosim.get("ok"))

    bench_report = {
        "ok": bool(golden_ok and cpp_report["ok"] and digests_match and hardware_ok),
        "modelId": model_id,
        "bench": {
            "targetId": _build_target_id(model_id, ir=ir_payload, graph_resolved=graph_resolved),
        },
        "gitCommit": _git_commit(),
        "createdAt": created_at,
        "toolchainVersions": tool_versions,
        "config": _config_summary(ir_payload, graph_resolved=graph_resolved),
        "provenance": provenance,
        "graphResolved": graph_resolved,
        "correctness": correctness,
        "performance": {
            "cpu": {
                "goldenTicksPerSecond": golden_tps,
                "cppRefTicksPerSecond": cpp_tps,
                "goldenElapsedSeconds": golden_elapsed,
                "cppRefElapsedSeconds": cpp_report["elapsedSeconds"],
            },
            "hardware": None if not hardware["toolchain"]["available"] else {"ticksPerSecond": None},
        },
        "hardware": hardware,
        "ticks": ticks,
        "irPath": str(ir_path),
        "irSha256": ir_sha256,
        "artifacts": {
            "modelRoot": str(model_root),
            "hlsCpp": str(hls_cpp),
            "hlsHeader": str(gen_report["hls_header"]),
            "cppRefMain": str(cpp_ref_main),
            "benchReport": str(model_root / "bench_report.json"),
        },
        "validation": {
            "ok": ir_validation["ok"],
            "invariantsChecked": ir_validation.get("invariants_checked", []),
        },
    }

    try:
        _validate_bench_report_schema(bench_report)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        return 1, {"ok": False, "error": f"bench_report schema validation failed: {exc}"}

    bench_report_path = model_root / "bench_report.json"
    _write_json(bench_report_path, bench_report)

    summary = {
        "ok": bench_report["ok"],
        "bench_report": str(bench_report_path),
        "model_id": model_id,
        "ticks": ticks,
        "golden_ok": golden_ok,
        "cpp_ref_ok": cpp_report["ok"],
        "digest_match": digests_match,
        "hls_toolchain_available": hardware["toolchain"]["available"],
        "synthetic_used": provenance["syntheticUsed"],
        "external_verified": provenance["externalVerified"],
        "graph_resolved": graph_resolved,
    }
    return (0 if bench_report["ok"] else 1), summary
