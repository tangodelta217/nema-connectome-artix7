"""NEMA-DSL CLI entrypoints."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from .errors import DslError
from .lower import dump_json, lower_to_ir
from .parser import parse
from ..hwtest import run_hwtest_pipeline
from ..ir_validate import IRValidationError, validate_ir


def add_dsl_subparser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    dsl_cmd = subparsers.add_parser("dsl", help="NEMA-DSL v0.1 commands")
    dsl_subparsers = dsl_cmd.add_subparsers(dest="dsl_command", required=True)

    check_cmd = dsl_subparsers.add_parser("check", help="parse/lower DSL and validate IR invariants")
    check_cmd.add_argument("dsl_file", type=Path, help="path to .nema source")

    compile_cmd = dsl_subparsers.add_parser("compile", help="compile NEMA-DSL to IR JSON")
    compile_cmd.add_argument("dsl_file", type=Path, help="path to .nema source")
    compile_cmd.add_argument("--out", type=Path, required=True, help="compiled IR JSON output path")

    hwtest_cmd = dsl_subparsers.add_parser("hwtest", help="compile DSL and run hwtest pipeline")
    hwtest_cmd.add_argument("dsl_file", type=Path, help="path to .nema source")
    hwtest_cmd.add_argument("--ticks", type=int, required=True, help="number of ticks")
    hwtest_cmd.add_argument("--outdir", type=Path, default=Path("build"), help="output directory")

    from_ir_cmd = dsl_subparsers.add_parser("from-ir", help="generate DSL source from IR JSON")
    from_ir_cmd.add_argument("ir_json", type=Path, help="path to IR JSON")
    from_ir_cmd.add_argument("--out", type=Path, required=True, help="DSL output path (.nema)")

    return dsl_cmd


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-/]*$")
_RESERVED = {"true", "false", "null"}
_INT_RE = re.compile(r"^-?[0-9]+$")


def _is_ident(value: str) -> bool:
    return _IDENT_RE.match(value) is not None and value not in _RESERVED


def _emit_key(key: str) -> str:
    if _is_ident(key):
        return key
    return json.dumps(key)


def _is_time_object(value: Any) -> bool:
    if not isinstance(value, dict) or set(value.keys()) != {"nanoseconds"}:
        return False
    raw = value["nanoseconds"]
    if isinstance(raw, int):
        return True
    return isinstance(raw, str) and _INT_RE.match(raw) is not None


def _is_fixed_object(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    keys = set(value.keys())
    if keys == {"typeId", "signedRaw"}:
        raw = value["signedRaw"]
    elif keys == {"typeId", "unsignedRaw"}:
        raw = value["unsignedRaw"]
    else:
        return False
    type_id = value["typeId"]
    if not isinstance(type_id, str) or not _is_ident(type_id):
        return False
    if isinstance(raw, int):
        return True
    return isinstance(raw, str) and _INT_RE.match(raw) is not None


def _emit_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        if _is_ident(value):
            return value
        return json.dumps(value)
    raise ValueError(f"unsupported scalar type: {type(value).__name__}")


def _emit_inline_object(value: dict[str, Any]) -> str:
    if _is_time_object(value):
        raw = value["nanoseconds"]
        return f"{raw}ns"
    if _is_fixed_object(value):
        type_id = str(value["typeId"])
        if "unsignedRaw" in value:
            return f"{type_id}({value['unsignedRaw']}u)"
        return f"{type_id}({value['signedRaw']})"
    if not value:
        return "{}"
    parts: list[str] = []
    for key in sorted(value.keys()):
        child = value[key]
        if isinstance(child, dict) and not _is_time_object(child) and not _is_fixed_object(child):
            parts.append(f"{_emit_key(str(key))} {_emit_inline_object(child)};")
        else:
            parts.append(f"{_emit_key(str(key))} = {_emit_value(child)};")
    return "{ " + " ".join(parts) + " }"


def _emit_value(value: Any) -> str:
    if isinstance(value, dict):
        return _emit_inline_object(value)
    if isinstance(value, list):
        items = ", ".join(_emit_value(item) for item in value)
        return f"[{items}]"
    return _emit_scalar(value)


def _emit_block(name: str, value: dict[str, Any], *, indent: int) -> list[str]:
    pad = "  " * indent
    lines = [f"{pad}{_emit_key(name)} {{"]
    for key in sorted(value.keys()):
        child = value[key]
        if isinstance(child, dict) and not _is_time_object(child) and not _is_fixed_object(child):
            lines.extend(_emit_block(str(key), child, indent=indent + 1))
        else:
            lines.append(f"{'  ' * (indent + 1)}{_emit_key(str(key))} = {_emit_value(child)};")
    lines.append(f"{pad}}};")
    return lines


def _render_dsl(obj: dict[str, Any]) -> str:
    lines: list[str] = []
    for key in sorted(obj.keys()):
        value = obj[key]
        if isinstance(value, dict) and not _is_time_object(value) and not _is_fixed_object(value):
            lines.extend(_emit_block(str(key), value, indent=0))
        else:
            lines.append(f"{_emit_key(str(key))} = {_emit_value(value)};")
    return "\n".join(lines) + "\n"


def _compile_source_to_ir(source_text: str) -> dict[str, Any]:
    ast = parse(source_text)
    return lower_to_ir(ast)


def _resolve_runtime_path(raw: str, *, bases: list[Path]) -> str:
    path = Path(raw)
    if path.is_absolute():
        return str(path)
    for base in bases:
        candidate = (base / path).resolve()
        if candidate.exists():
            return str(candidate)
    return str((bases[0] / path).resolve())


def _absolutize_runtime_ir_paths(ir_obj: dict[str, Any], *, dsl_path: Path) -> dict[str, Any]:
    payload = json.loads(json.dumps(ir_obj))
    bases = [dsl_path.parent.resolve(), Path.cwd().resolve()]

    tanh_lut = payload.get("tanhLut")
    if isinstance(tanh_lut, dict):
        artifact = tanh_lut.get("artifact")
        if isinstance(artifact, str) and artifact:
            tanh_lut["artifact"] = _resolve_runtime_path(artifact, bases=bases)

    graph = payload.get("graph")
    if isinstance(graph, dict):
        external = graph.get("external")
        if isinstance(external, dict):
            for key in ("uri", "path"):
                raw = external.get(key)
                if isinstance(raw, str) and raw:
                    external[key] = _resolve_runtime_path(raw, bases=bases)
    return payload


def run_dsl_command(args: argparse.Namespace) -> tuple[int, dict]:
    command = getattr(args, "dsl_command", None)
    if command not in {"compile", "check", "hwtest", "from-ir"}:
        return 2, {"ok": False, "error": "NYI: unknown DSL subcommand"}

    if command == "compile":
        try:
            source = args.dsl_file.read_text(encoding="utf-8")
        except OSError as exc:
            return 1, {"ok": False, "error": str(exc)}

        try:
            lowered = _compile_source_to_ir(source)
            dump_json(lowered, args.out)
        except (DslError, ValueError) as exc:
            return 1, {"ok": False, "error": str(exc)}

        return 0, {
            "ok": True,
            "dslPath": str(args.dsl_file),
            "outPath": str(args.out),
        }

    if command == "from-ir":
        try:
            raw = json.loads(args.ir_json.read_text(encoding="utf-8"))
        except OSError as exc:
            return 1, {"ok": False, "error": str(exc)}
        except json.JSONDecodeError as exc:
            return 1, {"ok": False, "error": f"invalid JSON: {exc}"}

        if not isinstance(raw, dict):
            return 1, {"ok": False, "error": "IR root must be a JSON object"}

        try:
            source = _render_dsl(raw)
        except ValueError as exc:
            return 1, {"ok": False, "error": str(exc)}

        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(source, encoding="utf-8")
        except OSError as exc:
            return 1, {"ok": False, "error": str(exc)}

        return 0, {
            "ok": True,
            "irPath": str(args.ir_json),
            "outPath": str(args.out),
        }

    if command == "check":
        try:
            source = args.dsl_file.read_text(encoding="utf-8")
            lowered = _compile_source_to_ir(source)
        except OSError as exc:
            return 1, {"ok": False, "error": str(exc)}
        except (DslError, ValueError) as exc:
            return 1, {"ok": False, "error": str(exc)}

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                prefix=".nema_dsl_check_",
                dir=str(Path.cwd()),
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(json.dumps(lowered, indent=2, sort_keys=True) + "\n")
            report = validate_ir(temp_path)
        except (IRValidationError, OSError) as exc:
            return 1, {"ok": False, "error": str(exc)}
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

        return 0, {
            "ok": True,
            "dslPath": str(args.dsl_file),
            "nodeCount": report.get("node_count"),
            "edgeCount": report.get("edge_count"),
            "irSha256": report.get("ir_sha256"),
        }

    if command == "hwtest":
        if args.ticks < 0:
            return 1, {"ok": False, "error": "--ticks must be >= 0"}

        try:
            source = args.dsl_file.read_text(encoding="utf-8")
            lowered = _compile_source_to_ir(source)
        except OSError as exc:
            return 1, {"ok": False, "error": str(exc)}
        except (DslError, ValueError) as exc:
            return 1, {"ok": False, "error": str(exc)}

        model_id = lowered.get("modelId") if isinstance(lowered, dict) else None
        if not isinstance(model_id, str) or not model_id.strip():
            return 1, {"ok": False, "error": "dsl hwtest requires root field 'modelId'"}
        model_id = model_id.strip()

        outdir = args.outdir
        ir_path = outdir / model_id / "dsl" / "ir_from_dsl.json"
        try:
            runtime_ir = _absolutize_runtime_ir_paths(lowered, dsl_path=args.dsl_file)
            dump_json(runtime_ir, ir_path)
        except OSError as exc:
            return 1, {"ok": False, "error": str(exc)}

        code, hw_summary = run_hwtest_pipeline(ir_path=ir_path, outdir=outdir, ticks=args.ticks)
        bench_report = None
        if isinstance(hw_summary, dict):
            raw_bench = hw_summary.get("bench_report")
            if isinstance(raw_bench, str):
                bench_report = raw_bench

        payload: dict[str, Any] = {
            "ok": code == 0,
            "dslPath": str(args.dsl_file),
            "irPath": str(ir_path),
            "benchReport": bench_report,
            "hwtest": hw_summary,
        }
        return code, payload

    return 2, {"ok": False, "error": f"NYI: nema dsl {command}"}


def emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))
