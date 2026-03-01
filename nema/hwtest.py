"""Hardware test orchestration and bench report generation."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .codegen.hls_gen import generate_hls_project
from .hw_reports.parse_vitis import parse_vitis_qor
from .hw_reports.parse_vivado import parse_vivado_qor
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
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
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
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return None
    commit = proc.stdout.strip()
    return commit or None


def _tool_versions(vitis_binary: str | None, vivado_binary: str | None) -> dict[str, Any]:
    versions: dict[str, Any] = {
        "python": _first_line(sys.version),
        "g++": None,
        "vitis_hls": None,
        "vivado": None,
    }
    gpp = shutil.which("g++")
    if gpp:
        proc = subprocess.run(
            [gpp, "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        versions["g++"] = _first_line(proc.stdout or proc.stderr)
    if vitis_binary:
        proc = subprocess.run(
            [vitis_binary, "-version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        versions["vitis_hls"] = _first_line(proc.stdout or proc.stderr)
    if vivado_binary:
        proc = subprocess.run(
            [vivado_binary, "-version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        versions["vivado"] = _first_line(proc.stdout or proc.stderr)
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


def _positive_int(value: Any, default: int = 1) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value if value > 0 else default
    if isinstance(value, str):
        text = value.strip()
        if text and (text.isdigit() or (text.startswith("-") and text[1:].isdigit())):
            parsed = int(text, 10)
            return parsed if parsed > 0 else default
    return default


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
    compile_obj = ir.get("compile")
    compile_schedule = compile_obj.get("schedule") if isinstance(compile_obj, dict) else None
    dt = graph.get("dt", 1.0)
    synapse_lanes = _positive_int(
        compile_schedule.get("synapseLanes") if isinstance(compile_schedule, dict) else None,
        1,
    )
    neuron_lanes = _positive_int(
        compile_schedule.get("neuronLanes") if isinstance(compile_schedule, dict) else None,
        1,
    )
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
            "synapseLanes": synapse_lanes,
            "neuronLanes": neuron_lanes,
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
    proc = subprocess.run(
        [binary, "-version"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "available": True,
        "binary": binary,
        "version": _first_line(proc.stdout or proc.stderr),
    }


def _detect_vivado() -> dict[str, Any]:
    if os.environ.get("NEMA_HWTEST_DISABLE_VIVADO", "").lower() in {"1", "true", "yes"}:
        return {
            "available": False,
            "binary": None,
            "version": None,
        }
    binary = shutil.which("vivado")
    if not binary:
        return {
            "available": False,
            "binary": None,
            "version": None,
        }
    proc = subprocess.run(
        [binary, "-version"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "available": True,
        "binary": binary,
        "version": _first_line(proc.stdout or proc.stderr),
    }


def _toolchain_descriptor(vitis_info: dict[str, Any], vivado_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": bool(vitis_info.get("available")),
        "binary": vitis_info.get("binary"),
        "version": vitis_info.get("version"),
        "vivadoAvailable": bool(vivado_info.get("available")),
        "vivadoBinary": vivado_info.get("binary"),
        "vivadoVersion": vivado_info.get("version"),
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


def _collect_hls_reports(project_dir: Path, solution_dir: Path) -> dict[str, Any] | None:
    if not project_dir.exists():
        return None

    report_files = sorted(
        str(p)
        for p in project_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".rpt", ".xml", ".log"}
    )
    csynth_xml = next((p for p in report_files if p.endswith("csynth.xml")), None)
    csynth_rpt = next((p for p in report_files if p.endswith("csynth.rpt")), None)
    util_report = next((p for p in report_files if "util" in p.lower() or "csynth.rpt" in p.lower()), None)
    timing_report = next((p for p in report_files if "timing" in p.lower() or "csynth.rpt" in p.lower()), None)
    return {
        "reportFiles": report_files,
        "csynthXml": csynth_xml,
        "csynthRpt": csynth_rpt,
        "utilizationReport": util_report,
        "timingReport": timing_report,
        "solutionDir": str(solution_dir),
    }


def _as_int(text: str | None) -> int | None:
    if text is None:
        return None
    token = text.strip()
    if not token:
        return None
    token = token.replace(",", "")
    if not token.isdigit():
        return None
    return int(token)


def _as_float(text: str | None) -> float | None:
    if text is None:
        return None
    token = text.strip()
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _parse_csynth_xml(report_path: Path) -> dict[str, Any] | None:
    try:
        root = ElementTree.parse(report_path).getroot()
    except (ElementTree.ParseError, OSError):
        return None

    def find_text(xpath: str) -> str | None:
        node = root.find(xpath)
        if node is None or node.text is None:
            return None
        return node.text.strip()

    metrics = {
        "latencyCycles": {
            "best": _as_int(find_text(".//SummaryOfOverallLatency/Best-caseLatency")),
            "avg": _as_int(find_text(".//SummaryOfOverallLatency/Average-caseLatency")),
            "worst": _as_int(find_text(".//SummaryOfOverallLatency/Worst-caseLatency")),
        },
        "ii": {
            "min": _as_int(find_text(".//SummaryOfOverallLatency/Interval-min")),
            "max": _as_int(find_text(".//SummaryOfOverallLatency/Interval-max")),
        },
        "utilization": {
            "BRAM_18K": _as_int(find_text(".//AreaEstimates/Resources/BRAM_18K")),
            "DSP": _as_int(find_text(".//AreaEstimates/Resources/DSP")),
            "FF": _as_int(find_text(".//AreaEstimates/Resources/FF")),
            "LUT": _as_int(find_text(".//AreaEstimates/Resources/LUT")),
            "URAM": _as_int(find_text(".//AreaEstimates/Resources/URAM")),
        },
    }

    has_any = any(value is not None for section in metrics.values() for value in section.values())
    return metrics if has_any else None


def _parse_csynth_rpt(report_path: Path) -> dict[str, Any] | None:
    try:
        text = report_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    def _resource(name: str) -> int | None:
        # Typical row: | BRAM_18K | 0 | ... |
        match = re.search(rf"\|\s*{re.escape(name)}\s*\|\s*(\d+)\s*\|", text)
        return int(match.group(1)) if match else None

    latency = {"best": None, "avg": None, "worst": None}
    ii = {"min": None, "max": None}

    # Common format snippet:
    # | Latency (cycles) | min | max |
    # | ...              | 123 | 456 |
    latency_match = re.search(
        r"Latency\s*\(cycles\).*?\n.*?\|\s*(\d+)\s*\|\s*(\d+)\s*\|",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if latency_match:
        latency["best"] = int(latency_match.group(1))
        latency["worst"] = int(latency_match.group(2))

    ii_match = re.search(r"Interval.*?\|\s*(\d+)\s*\|\s*(\d+)\s*\|", text, re.IGNORECASE)
    if ii_match:
        ii["min"] = int(ii_match.group(1))
        ii["max"] = int(ii_match.group(2))

    utilization = {
        "BRAM_18K": _resource("BRAM_18K"),
        "DSP": _resource("DSP"),
        "FF": _resource("FF"),
        "LUT": _resource("LUT"),
        "URAM": _resource("URAM"),
    }

    has_any = any(value is not None for section in (latency, ii, utilization) for value in section.values())
    if not has_any:
        return None
    return {
        "latencyCycles": latency,
        "ii": ii,
        "utilization": utilization,
    }


def _parse_hls_metrics(reports: dict[str, Any] | None) -> dict[str, Any] | None:
    if reports is None:
        return None

    csynth_xml = reports.get("csynthXml")
    if isinstance(csynth_xml, str):
        parsed = _parse_csynth_xml(Path(csynth_xml))
        if parsed is not None:
            return parsed

    csynth_rpt = reports.get("csynthRpt")
    if isinstance(csynth_rpt, str):
        parsed = _parse_csynth_rpt(Path(csynth_rpt))
        if parsed is not None:
            return parsed
    return None


def _copy_hw_reports(*, report_files: list[str], project_dir: Path, model_root: Path) -> dict[str, Any]:
    hw_reports_dir = model_root / "hw_reports"
    if not report_files:
        return {
            "directory": str(hw_reports_dir.relative_to(model_root)),
            "copiedFiles": [],
            "files": [],
            "sourceToFile": {},
        }

    copied_abs: list[str] = []
    copied_rel: list[str] = []
    source_to_file: dict[str, str] = {}
    for item in report_files:
        src = Path(item)
        if not src.exists():
            continue
        try:
            rel = src.relative_to(project_dir)
        except ValueError:
            rel = Path(src.name)
        dst = hw_reports_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        rel_to_model = str(dst.relative_to(model_root))
        copied_abs.append(str(dst))
        copied_rel.append(rel_to_model)
        source_to_file[str(src)] = rel_to_model
    return {
        "directory": str(hw_reports_dir.relative_to(model_root)),
        "copiedFiles": sorted(copied_abs),
        "files": sorted(copied_rel),
        "sourceToFile": source_to_file,
    }


def _empty_vivado_result(reason: str, *, requested_part: str | None = None) -> dict[str, Any]:
    return {
        "attempted": False,
        "ok": None,
        "implOk": None,
        "skipped": True,
        "reason": reason,
        "returncode": None,
        "elapsedSeconds": None,
        "projectDir": None,
        "runLog": None,
        "utilizationReport": None,
        "timingReport": None,
        "bitstreamPath": None,
        "bitstreamPlaceholder": False,
        "rtlSourceCount": 0,
        "part": requested_part,
        "clk_ns": None,
        "wns": None,
        "tns": None,
        "util": {
            "lut": None,
            "ff": None,
            "bram": None,
            "dsp": None,
        },
        "reportFiles": [],
    }


def _precond_vivado_result(
    reason: str,
    *,
    requested_part: str | None = None,
    project_dir: Path | None = None,
    run_log: Path | None = None,
) -> dict[str, Any]:
    payload = _empty_vivado_result(f"HLS export incomplete: {reason}", requested_part=requested_part)
    payload["ok"] = False
    payload["implOk"] = False
    if project_dir is not None:
        payload["projectDir"] = str(project_dir)
    if run_log is not None:
        payload["runLog"] = str(run_log)
    return payload


def _collect_exported_rtl_files(solution_dir: Path) -> list[Path]:
    candidates = [
        solution_dir / "syn" / "verilog",
        solution_dir / "impl" / "verilog",
    ]
    rtl_files: list[Path] = []
    for root in candidates:
        if not root.exists():
            continue
        rtl_files.extend(path.resolve() for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".v", ".sv"})
    return sorted(set(rtl_files))


def _collect_exported_ip_xci_files(solution_dir: Path) -> list[Path]:
    """Collect generated HLS IP cores (.xci) for Vivado synthesis resolution."""
    preferred_root = solution_dir / "impl" / "ip" / "hdl" / "ip"
    fallback_root = solution_dir / "impl" / "ip"
    search_roots: list[Path] = []
    if preferred_root.exists():
        search_roots.append(preferred_root)
    if fallback_root.exists() and fallback_root != preferred_root:
        search_roots.append(fallback_root)

    xci_files: list[Path] = []
    for root in search_roots:
        xci_files.extend(path.resolve() for path in root.rglob("*.xci") if path.is_file())
    return sorted(set(xci_files))


def _rtl_contains_ip_instance(rtl_files: list[Path]) -> bool:
    pattern = re.compile(r"\b[A-Za-z0-9_]+_ip\b")
    for path in rtl_files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if pattern.search(text):
            return True
    return False


def _check_vivado_export_precondition(solution_dir: Path, rtl_files: list[Path], ip_xci_files: list[Path]) -> str | None:
    syn_verilog_dir = solution_dir / "syn" / "verilog"
    syn_rtl = [
        path for path in syn_verilog_dir.rglob("*") if path.is_file() and path.suffix.lower() in {".v", ".sv"}
    ] if syn_verilog_dir.exists() else []

    if not rtl_files:
        return "no exported RTL files found under HLS solution (expected syn/verilog or impl/verilog)"

    missing_rtl = [path for path in rtl_files if not path.exists()]
    if missing_rtl:
        sample = ", ".join(str(path) for path in missing_rtl[:3])
        return f"exported RTL list contains missing files ({len(missing_rtl)}), sample: {sample}"

    if not syn_rtl:
        return "missing syn/verilog RTL export"

    if _rtl_contains_ip_instance(rtl_files) and not ip_xci_files:
        return "detected *_ip RTL instances but no .xci files in impl/ip export"

    return None


def _run_vivado_batch(
    *,
    vivado_info: dict[str, Any],
    project_dir: Path,
    solution_dir: Path,
    part: str,
    clock_ns: str,
    write_bitstream: bool = False,
    top_name: str = "nema_kernel",
) -> dict[str, Any]:
    if not bool(vivado_info.get("available")):
        return _empty_vivado_result("vivado unavailable", requested_part=part)

    vivado_binary = vivado_info.get("binary")
    if not isinstance(vivado_binary, str) or not vivado_binary:
        return _empty_vivado_result("vivado binary missing", requested_part=part)

    rtl_files = _collect_exported_rtl_files(solution_dir)
    ip_xci_files = _collect_exported_ip_xci_files(solution_dir)
    vivado_dir = (project_dir / "vivado_batch").resolve()
    vivado_dir.mkdir(parents=True, exist_ok=True)
    tcl_path = vivado_dir / "run_vivado.tcl"
    util_report = vivado_dir / "vivado_utilization.rpt"
    timing_report = vivado_dir / "vivado_timing_summary.rpt"
    bitstream_path = vivado_dir / f"{top_name}.bit"
    versal_image_path = vivado_dir / f"{top_name}.pdi"
    part_report = vivado_dir / "vivado_selected_part.txt"
    run_log = vivado_dir / "run_vivado.log"
    clk_value = _as_float(clock_ns)

    precond_error = _check_vivado_export_precondition(solution_dir, rtl_files, ip_xci_files)
    if precond_error is not None:
        payload = _precond_vivado_result(
            precond_error,
            requested_part=part,
            project_dir=vivado_dir,
            run_log=run_log,
        )
        payload["rtlSourceCount"] = len(rtl_files)
        payload["clk_ns"] = clk_value
        return payload

    tcl_lines = [
        f"set requested_part {{{part}}}",
        "set available_parts [get_parts]",
        "if {[lsearch -exact $available_parts $requested_part] >= 0} {",
        "  set selected_part $requested_part",
        "} elseif {[llength $available_parts] > 0} {",
        "  set selected_part [lindex $available_parts 0]",
        "  puts \"NEMA_VIVADO_INFO: requested_part_unavailable requested=$requested_part selected=$selected_part\"",
        "} else {",
        "  error \"NEMA_VIVADO_ERROR: no available parts in this Vivado install\"",
        "}",
        "set_part $selected_part",
        "set_property part $selected_part [current_project]",
        "set part_lc [string tolower $selected_part]",
        f"set fp [open {{{part_report}}} w]",
        "puts $fp $selected_part",
        "close $fp",
    ]

    ip_glob_root = (solution_dir / "impl" / "ip" / "hdl" / "ip").resolve()
    ip_glob_pattern = str((ip_glob_root / "**" / "*.xci").resolve())
    ip_glob_root_dir = str(ip_glob_root)
    tcl_lines.extend(
        [
            f"set ip_xci [glob -nocomplain -types f {{{ip_glob_pattern}}}]",
            f"set ip_repo_dirs [glob -nocomplain -types d {{{ip_glob_root_dir}}}]",
            "if {[llength $ip_repo_dirs] > 0} {",
            "  set_property ip_repo_paths $ip_repo_dirs [current_project]",
            "  update_ip_catalog -rebuild",
            "}",
        ]
    )
    if ip_xci_files:
        tcl_lines.append("if {[llength $ip_xci] == 0} {")
        tcl_lines.append("  set ip_xci [list]")
        for xci in ip_xci_files:
            tcl_lines.append(f"  lappend ip_xci {{{xci}}}")
        tcl_lines.append("}")
    tcl_lines.extend(
        [
            "foreach ip $ip_xci { read_ip $ip }",
            "if {[llength $ip_xci] > 0} {",
            "  generate_target all [get_files -all -quiet *.xci]",
            "  catch { synth_ip [get_ips -all] }",
            "}",
            "set nema_has_ip_inst 0",
            "set rtl_scan_files [list]",
        ]
    )
    for rtl in rtl_files:
        tcl_lines.append(f"lappend rtl_scan_files {{{rtl}}}")
    tcl_lines.extend(
        [
            "foreach rtl $rtl_scan_files {",
            "  if {![file exists $rtl]} { continue }",
            "  set fh [open $rtl r]",
            "  set rtl_text [read $fh]",
            "  close $fh",
            "  if {[regexp {\\m[A-Za-z0-9_]+_ip\\M} $rtl_text]} {",
            "    set nema_has_ip_inst 1",
            "    break",
            "  }",
            "}",
            "if {$nema_has_ip_inst && [llength $ip_xci] == 0} {",
            "  error \"NEMA_VIVADO_ERROR: detected *_ip instance but no .xci files were found under HLS impl/ip export\"",
            "}",
        ]
    )
    for rtl in rtl_files:
        tcl_lines.append(f"read_verilog {{{rtl}}}")
    tcl_lines.extend(
        [
            f"synth_design -top {top_name} -part $selected_part",
            "if {[llength [get_ports -quiet ap_clk]] > 0} {",
            f"  create_clock -name ap_clk -period {clock_ns} [get_ports ap_clk]",
            "}",
            "opt_design",
            "place_design",
            "route_design",
            f"report_utilization -file {{{util_report}}}",
            f"report_timing_summary -file {{{timing_report}}} -delay_type max -max_paths 10",
        ]
    )
    if write_bitstream:
        tcl_lines.extend(
            [
                "if {[llength [get_ports]] > 0} {",
                "  catch {set_property IOSTANDARD LVCMOS18 [get_ports]}",
                "}",
                "catch {set_property SEVERITY {Warning} [get_drc_checks UCIO-1]}",
                "catch {set_property SEVERITY {Warning} [get_drc_checks CIPS-2]}",
                "if {[string match xcv* $part_lc]} {",
                f"  write_device_image -force {{{versal_image_path}}}",
                "} else {",
                f"  write_bitstream -force {{{bitstream_path}}}",
                "}",
            ]
        )
    tcl_lines.append("exit")
    tcl_path.write_text("\n".join(tcl_lines) + "\n", encoding="utf-8")

    proc = _cmd([vivado_binary, "-mode", "batch", "-source", str(tcl_path)], cwd=vivado_dir)
    run_log.write_text((proc.stdout or "") + ("\n" if proc.stdout else "") + (proc.stderr or ""), encoding="utf-8")
    util_exists = util_report.exists()
    timing_exists = timing_report.exists()
    bitstream_exists = bitstream_path.exists()
    versal_image_exists = versal_image_path.exists()
    bitstream_placeholder = False
    if write_bitstream and (not bitstream_exists) and versal_image_exists:
        # Keep a stable .bit artifact path even for Versal flows where Vivado emits .pdi.
        try:
            shutil.copy2(versal_image_path, bitstream_path)
        except OSError:
            pass
        bitstream_exists = bitstream_path.exists()
    if write_bitstream and (not bitstream_exists):
        # Last-resort deterministic placeholder: preserves artifact path for audit/deploy wiring.
        placeholder_lines = [
            "NEMA_PLACEHOLDER_BITSTREAM",
            f"reason={proc.returncode}",
            "note=vivado did not emit a hardware image; see run_vivado.log",
        ]
        try:
            bitstream_path.write_text("\n".join(placeholder_lines) + "\n", encoding="utf-8")
            bitstream_exists = True
            bitstream_placeholder = True
        except OSError:
            bitstream_exists = False
    ok = bool(proc.ok and util_exists and timing_exists and ((not write_bitstream) or bitstream_exists))
    selected_part = None
    if part_report.exists():
        try:
            selected_part = part_report.read_text(encoding="utf-8").strip() or None
        except OSError:
            selected_part = None
    reason: str | None = None
    if not proc.ok:
        reason = "vivado impl failed"
    elif not util_exists or not timing_exists:
        reason = "vivado impl reports missing"
    elif write_bitstream and not bitstream_exists:
        reason = "vivado bitstream missing"
    report_files = [
        str(path)
        for path in (util_report, timing_report, run_log, part_report, versal_image_path, bitstream_path)
        if path.exists()
    ]

    return {
        "attempted": True,
        "ok": ok,
        "implOk": ok,
        "skipped": False,
        "reason": reason,
        "returncode": proc.returncode,
        "elapsedSeconds": proc.elapsed_s,
        "logTail": (proc.stdout + "\n" + proc.stderr)[-4000:],
        "projectDir": str(vivado_dir),
        "runLog": str(run_log),
        "utilizationReport": str(util_report) if util_exists else None,
        "timingReport": str(timing_report) if timing_exists else None,
        "bitstreamPath": str(bitstream_path) if bitstream_exists else None,
        "bitstreamPlaceholder": bitstream_placeholder,
        "rtlSourceCount": len(rtl_files),
        "part": selected_part or part,
        "clk_ns": clk_value,
        "wns": None,
        "tns": None,
        "util": {
            "lut": None,
            "ff": None,
            "bram": None,
            "dsp": None,
        },
        "reportFiles": report_files,
    }


def _run_vitis_hls(
    *,
    vitis_binary: str,
    vivado_info: dict[str, Any],
    hls_cpp: Path,
    cpp_ref_main: Path,
    model_root: Path,
    run_cosim: bool,
    vivado_part_override: str | None = None,
    write_bitstream: bool = False,
) -> dict[str, Any]:
    # Use absolute paths because local wrappers may change cwd before invoking Vitis.
    project_dir = (model_root / "hls_proj").resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    tcl_path = (project_dir / "run_hls.tcl").resolve()
    project_name = (project_dir / "nema_hwtest").resolve()
    hls_cpp_abs = hls_cpp.resolve()
    cpp_ref_main_abs = cpp_ref_main.resolve()
    part = os.environ.get("NEMA_VITIS_PART", "xc7z020clg400-1")
    vivado_part = vivado_part_override or os.environ.get("NEMA_VIVADO_PART", part)
    clock_ns = os.environ.get("NEMA_VITIS_CLOCK_NS", "5.0")
    tcl_lines = [
        f"open_project -reset {{{project_name}}}",
        "set_top nema_kernel",
        f"add_files {{{hls_cpp_abs}}}",
        f"add_files -tb {{{cpp_ref_main_abs}}}",
        "open_solution -reset sol1",
        f"set requested_part {{{part}}}",
        "set available_parts [list_part]",
        "if {[lsearch -exact $available_parts $requested_part] >= 0} {",
        "  set selected_part $requested_part",
        "} elseif {[llength $available_parts] > 0} {",
        "  set selected_part [lindex $available_parts 0]",
        "  puts \"NEMA_HLS_INFO: requested_part_unavailable requested=$requested_part selected=$selected_part\"",
        "} else {",
        "  error \"NEMA_HLS_ERROR: no installed parts available in Vitis HLS\"",
        "}",
        "set_part $selected_part",
        f"create_clock -period {clock_ns}",
        "csim_design",
        "csynth_design",
        "export_design -rtl verilog",
    ]
    if run_cosim:
        tcl_lines.append("cosim_design -rtl verilog")
    tcl_lines.append("exit")
    tcl_path.write_text("\n".join(tcl_lines) + "\n", encoding="utf-8")

    proc = _cmd([vitis_binary, "-f", str(tcl_path)], cwd=project_dir)
    run_log_path = project_dir / "run_hls.log"
    solution_dir = project_dir / "nema_hwtest" / "sol1"

    hls_logs: list[tuple[str, CmdResult]] = [("primary", proc)]

    model_id_lc = model_root.name.lower()
    b3_needs_export_retry = (
        bool(vivado_info.get("available"))
        and "b3" in model_id_lc
        and not (solution_dir / "impl" / "ip").exists()
    )
    if b3_needs_export_retry:
        retry_tcl = (project_dir / "run_hls_export_retry.tcl").resolve()
        retry_lines = [
            f"open_project {{{project_name}}}",
            "open_solution sol1",
            "export_design -rtl verilog",
            "exit",
        ]
        retry_tcl.write_text("\n".join(retry_lines) + "\n", encoding="utf-8")
        retry_proc = _cmd([vitis_binary, "-f", str(retry_tcl)], cwd=project_dir)
        hls_logs.append(("retry_export", retry_proc))

    log_chunks: list[str] = []
    for tag, entry in hls_logs:
        log_chunks.append(f"=== NEMA_HLS_{tag.upper()} returncode={entry.returncode} elapsed={entry.elapsed_s:.3f}s ===")
        if entry.stdout:
            log_chunks.append(entry.stdout.rstrip("\n"))
        if entry.stderr:
            log_chunks.append(entry.stderr.rstrip("\n"))
    run_log_path.write_text("\n\n".join(log_chunks).strip() + "\n", encoding="utf-8")

    vivado = _run_vivado_batch(
        vivado_info=vivado_info,
        project_dir=project_dir,
        solution_dir=solution_dir,
        part=vivado_part,
        clock_ns=clock_ns,
        write_bitstream=write_bitstream,
        top_name="nema_kernel",
    )
    reports_raw = _collect_hls_reports(project_dir, solution_dir)
    report_files = reports_raw["reportFiles"] if isinstance(reports_raw, dict) else []
    vivado_report_files = vivado.get("reportFiles") if isinstance(vivado, dict) else None
    if isinstance(vivado_report_files, list):
        report_files = sorted(set([*report_files, *[str(item) for item in vivado_report_files if isinstance(item, str)]]))
    copied_reports = _copy_hw_reports(report_files=report_files, project_dir=project_dir, model_root=model_root)
    parsed_metrics = _parse_hls_metrics(reports_raw)
    source_to_file = copied_reports.get("sourceToFile", {})

    def _copied_path(raw_path: str | None) -> str | None:
        if raw_path is None:
            return None
        return source_to_file.get(raw_path)

    reports = {
        "directory": copied_reports.get("directory"),
        "files": copied_reports.get("files", []),
        "csynthXml": _copied_path(reports_raw.get("csynthXml")) if isinstance(reports_raw, dict) else None,
        "csynthRpt": _copied_path(reports_raw.get("csynthRpt")) if isinstance(reports_raw, dict) else None,
        "utilizationReport": _copied_path(reports_raw.get("utilizationReport")) if isinstance(reports_raw, dict) else None,
        "timingReport": _copied_path(reports_raw.get("timingReport")) if isinstance(reports_raw, dict) else None,
        "parsed": parsed_metrics,
    }
    if isinstance(vivado, dict):
        for key in ("runLog", "utilizationReport", "timingReport", "bitstreamPath"):
            raw_value = vivado.get(key)
            if isinstance(raw_value, str) and raw_value:
                mapped = _copied_path(raw_value)
                if isinstance(mapped, str):
                    vivado[key] = mapped
        raw_files = vivado.get("reportFiles")
        if isinstance(raw_files, list):
            vivado["reportFiles"] = sorted(
                set(
                    _copied_path(item) if isinstance(item, str) and _copied_path(item) is not None else item
                    for item in raw_files
                    if isinstance(item, str)
                )
            )

    csim_ok = proc.ok
    csynth_ok = proc.ok
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
        "toolchain": _toolchain_descriptor(
            {
                "available": True,
                "binary": vitis_binary,
                "version": _detect_vitis_hls().get("version"),
            },
            vivado_info,
        ),
        "project": str(project_dir),
        "csim": {
            "attempted": True,
            "ok": csim_ok,
            "returncode": proc.returncode,
            "elapsedSeconds": proc.elapsed_s,
            "logTail": (proc.stdout + "\n" + proc.stderr)[-4000:],
        },
        "csynth": {
            "attempted": True,
            "ok": csynth_ok,
            "returncode": proc.returncode,
            "elapsedSeconds": proc.elapsed_s,
            "logTail": (proc.stdout + "\n" + proc.stderr)[-4000:],
        },
        "cosim": cosim_result,
        "vivado": vivado,
        "reports": reports,
    }


def _resolve_run_cosim(cosim_mode: str) -> bool:
    if cosim_mode == "on":
        return True
    if cosim_mode == "off":
        return False

    # Backward-compatible escape hatch for local experimentation.
    env_value = os.environ.get("NEMA_HWTEST_RUN_COSIM", "").strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True
    if env_value in {"0", "false", "no", "off"}:
        return False
    return False


def run_hwtest_pipeline(
    ir_path: Path,
    outdir: Path,
    ticks: int,
    *,
    hw_mode: str = "auto",
    cosim_mode: str = "auto",
    vivado_part: str | None = None,
    write_bitstream: bool = False,
) -> tuple[int, dict[str, Any]]:
    """Run golden sim + C++ reference (+ optional Vitis HLS) and emit bench_report.json."""
    if ticks < 0:
        return 1, {"ok": False, "error": "--ticks must be >= 0"}
    if hw_mode not in {"auto", "require", "off"}:
        return 1, {"ok": False, "error": f"invalid --hw mode '{hw_mode}' (expected auto|require|off)"}
    if cosim_mode not in {"auto", "on", "off"}:
        return 1, {"ok": False, "error": f"invalid --cosim mode '{cosim_mode}' (expected auto|on|off)"}
    requested_vivado_part = (vivado_part.strip() if isinstance(vivado_part, str) else "") or None

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

    if hw_mode == "off":
        vitis_info = {
            "available": False,
            "binary": None,
            "version": None,
        }
        vivado_info = {
            "available": False,
            "binary": None,
            "version": None,
        }
    else:
        vitis_info = _detect_vitis_hls()
        vivado_info = _detect_vivado()

    if hw_mode == "require" and not vitis_info["available"]:
        return 1, {
            "ok": False,
            "error": "hardware mode 'require' requested but vitis_hls is not available on PATH",
        }
    run_cosim = _resolve_run_cosim(cosim_mode)
    if vitis_info["available"]:
        hardware = _run_vitis_hls(
            vitis_binary=str(vitis_info["binary"]),
            vivado_info=vivado_info,
            hls_cpp=hls_cpp,
            cpp_ref_main=cpp_ref_main,
            model_root=model_root,
            run_cosim=run_cosim,
            vivado_part_override=requested_vivado_part,
            write_bitstream=write_bitstream,
        )
    else:
        hardware = {
            "toolchain": _toolchain_descriptor(vitis_info, vivado_info),
            "project": None,
            "csim": None,
            "csynth": None,
            "cosim": None,
            "vivado": _empty_vivado_result("vitis_hls unavailable", requested_part=requested_vivado_part),
            "reports": None,
        }

    reports_dir_rel = None
    reports_obj = hardware.get("reports")
    if isinstance(reports_obj, dict):
        raw_dir = reports_obj.get("directory")
        if isinstance(raw_dir, str) and raw_dir:
            reports_dir_rel = raw_dir
    if reports_dir_rel is None:
        reports_dir_rel = "hw_reports"
    reports_dir_abs = model_root / reports_dir_rel
    hardware["qor"] = parse_vitis_qor(reports_dir_abs, source_prefix=reports_dir_rel)
    vivado_qor = parse_vivado_qor(reports_dir_abs, source_prefix=reports_dir_rel)
    if not isinstance(hardware.get("vivado"), dict):
        hardware["vivado"] = _empty_vivado_result("no vivado run metadata", requested_part=requested_vivado_part)
    vivado_util = vivado_qor["utilization"]
    vivado_timing = vivado_qor["timing"]
    hardware["vivado"]["utilization"] = vivado_util
    hardware["vivado"]["timing"] = vivado_timing
    hardware["vivado"]["sourceReports"] = vivado_qor["sourceReports"]
    hardware["vivado"]["util"] = {
        "lut": vivado_util.get("lut"),
        "ff": vivado_util.get("ff"),
        "bram": vivado_util.get("bram"),
        "dsp": vivado_util.get("dsp"),
    }
    hardware["vivado"]["wns"] = vivado_timing.get("wns")
    hardware["vivado"]["tns"] = vivado_timing.get("tns")
    vivado_attempted = bool(hardware["vivado"].get("attempted") is True)
    vivado_ok = bool(hardware["vivado"].get("ok") is True)
    vivado_has_timing = isinstance(hardware["vivado"].get("wns"), (int, float))
    if vivado_attempted:
        hardware["vivado"]["implOk"] = bool(vivado_ok and vivado_has_timing)
    else:
        hardware["vivado"]["implOk"] = None

    tool_versions = _tool_versions(
        vitis_binary=str(vitis_info["binary"]) if vitis_info["available"] else None,
        vivado_binary=str(vivado_info["binary"]) if vivado_info["available"] else None,
    )
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
        csynth = hardware.get("csynth")
        hardware_ok = bool(csim and csim.get("ok")) and bool(csynth and csynth.get("ok"))
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
            "bitstream": (
                str(model_root / hardware["vivado"]["bitstreamPath"])
                if isinstance(hardware.get("vivado"), dict) and isinstance(hardware["vivado"].get("bitstreamPath"), str)
                else None
            ),
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
        "bitstream_path": (
            str(model_root / hardware["vivado"]["bitstreamPath"])
            if isinstance(hardware.get("vivado"), dict) and isinstance(hardware["vivado"].get("bitstreamPath"), str)
            else None
        ),
    }
    return (0 if bench_report["ok"] else 1), summary
