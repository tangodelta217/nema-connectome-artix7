"""NEMA-DSL CLI entrypoints."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from .catalog import make_diag
from .diagnostics import Diagnostic, Severity, sort_key
from .errors import DslError
from .lower import dump_json, lower_to_ir_with_locs
from .parser import parse_with_locs
from .preprocess import PREPROCESSED_PATH, preprocess_file
from .typecheck import typecheck
from ..hwtest import run_hwtest_pipeline
from ..ir_validate import IRValidationError, validate_ir


def _add_diag_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="diagnostics output format",
    )
    parser.add_argument(
        "--Werror",
        dest="werror",
        action="store_true",
        help="treat warnings as errors",
    )
    parser.set_defaults(no_color=True)
    parser.add_argument(
        "--no-color",
        dest="no_color",
        action="store_true",
        help="disable ANSI color in text diagnostics",
    )
    parser.add_argument(
        "--color",
        dest="no_color",
        action="store_false",
        help=argparse.SUPPRESS,
    )


def add_dsl_subparser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    dsl_cmd = subparsers.add_parser("dsl", help="NEMA-DSL v0.1 commands")
    _add_diag_flags(dsl_cmd)
    dsl_subparsers = dsl_cmd.add_subparsers(dest="dsl_command", required=True)

    check_cmd = dsl_subparsers.add_parser("check", help="parse/lower DSL and validate IR invariants")
    _add_diag_flags(check_cmd)
    check_cmd.add_argument("dsl_file", type=Path, help="path to .nema source")

    compile_cmd = dsl_subparsers.add_parser("compile", help="compile NEMA-DSL to IR JSON")
    _add_diag_flags(compile_cmd)
    compile_cmd.add_argument("dsl_file", type=Path, help="path to .nema source")
    compile_cmd.add_argument("--out", type=Path, required=True, help="compiled IR JSON output path")

    hwtest_cmd = dsl_subparsers.add_parser("hwtest", help="compile DSL and run hwtest pipeline")
    _add_diag_flags(hwtest_cmd)
    hwtest_cmd.add_argument("dsl_file", type=Path, help="path to .nema source")
    hwtest_cmd.add_argument("--ticks", type=int, required=True, help="number of ticks")
    hwtest_cmd.add_argument("--outdir", type=Path, default=Path("build"), help="output directory")
    hwtest_cmd.add_argument(
        "--hw",
        choices=("auto", "require", "off"),
        default="auto",
        help="hardware toolchain policy (default: auto)",
    )

    from_ir_cmd = dsl_subparsers.add_parser("from-ir", help="generate DSL source from IR JSON")
    _add_diag_flags(from_ir_cmd)
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


def _compile_dsl_file_to_ir_with_locs(dsl_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    preprocessed = preprocess_file(dsl_path)
    try:
        ast, locs = parse_with_locs(preprocessed.text, PREPROCESSED_PATH)
    except DslError as exc:
        raise preprocessed.remap_error(exc) from exc
    remapped_locs = preprocessed.source_map.remap_locs(locs)
    lowered, lowered_locs = lower_to_ir_with_locs(ast, remapped_locs)
    return lowered, lowered_locs


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


def _sorted_diagnostics(diags: list[Diagnostic]) -> list[Diagnostic]:
    return sorted(diags, key=sort_key)


def _with_path(diag: Diagnostic, fallback_path: str) -> Diagnostic:
    if diag.path and diag.path != "<input>":
        return diag
    return replace(diag, path=fallback_path)


def _loc_from_map(locs: dict[str, dict[str, Any]], field_path: str) -> tuple[str | None, int, int]:
    raw = locs.get(field_path)
    if not isinstance(raw, dict):
        return (None, 1, 1)
    path = raw.get("path")
    if not isinstance(path, str) or not path:
        path = None
    line = raw.get("line")
    col = raw.get("col")
    if not isinstance(line, int) or not isinstance(col, int):
        return (path, 1, 1)
    return (path, line, col)


def _hw_toolchain_available() -> bool:
    forced_unavailable = os.environ.get("NEMA_DSL_FORCE_HW_UNAVAILABLE", "").strip().lower()
    if forced_unavailable in {"1", "true", "yes"}:
        return False
    return shutil.which("vitis_hls") is not None and shutil.which("vivado") is not None


def _run_hwtest_pipeline_with_hw_mode(
    *,
    ir_path: Path,
    outdir: Path,
    ticks: int,
    hw_mode: str,
) -> tuple[int, dict[str, Any]]:
    return run_hwtest_pipeline(ir_path=ir_path, outdir=outdir, ticks=ticks, hw_mode=hw_mode)


def _finalize(
    *,
    code: int,
    payload: dict[str, Any] | None = None,
    diagnostics: list[Diagnostic] | None = None,
    werror: bool = False,
) -> tuple[int, dict]:
    ordered = _sorted_diagnostics(diagnostics or [])
    has_error = any(diag.severity == Severity.ERROR for diag in ordered)
    has_warning = any(diag.severity == Severity.WARNING for diag in ordered)

    effective_code = code
    if has_error and effective_code == 0:
        effective_code = 1
    if werror and has_warning and effective_code == 0:
        effective_code = 1

    out = dict(payload or {})
    out["diagnostics"] = [diag.to_dict() for diag in ordered]
    out["ok"] = effective_code == 0
    return effective_code, out


def _diag_from_file_error(path: Path, exc: OSError) -> Diagnostic:
    return make_diag(
        code="NEMA-DSL9002",
        severity=Severity.ERROR,
        path=str(path),
        line=1,
        col=1,
        detail=str(exc),
    )


def _diag_from_write_error(path: Path, exc: OSError) -> Diagnostic:
    return make_diag(
        code="NEMA-DSL9003",
        severity=Severity.ERROR,
        path=str(path),
        line=1,
        col=1,
        detail=str(exc),
    )


def _diag_from_exception(path: Path, exc: Exception) -> Diagnostic:
    if isinstance(exc, DslError):
        return _with_path(exc.diagnostic, str(path))
    return make_diag(
        code="NEMA-DSL9001",
        severity=Severity.ERROR,
        path=str(path),
        line=1,
        col=1,
        detail=str(exc),
    )


def run_dsl_command(args: argparse.Namespace) -> tuple[int, dict]:
    werror = bool(getattr(args, "werror", False))
    command = getattr(args, "dsl_command", None)
    if command not in {"compile", "check", "hwtest", "from-ir"}:
        diag = make_diag(
            code="NEMA-DSL9004",
            severity=Severity.ERROR,
            path="<cli>",
            line=1,
            col=1,
            command=str(command),
        )
        return _finalize(
            code=2,
            payload={"command": command},
            diagnostics=[diag],
            werror=werror,
        )

    if command == "compile":
        try:
            lowered, _ = _compile_dsl_file_to_ir_with_locs(args.dsl_file)
            dump_json(lowered, args.out)
        except OSError as exc:
            return _finalize(
                code=1,
                payload={"dslPath": str(args.dsl_file), "outPath": str(args.out)},
                diagnostics=[_diag_from_write_error(args.out, exc)],
                werror=werror,
            )
        except (DslError, ValueError) as exc:
            return _finalize(
                code=1,
                payload={"dslPath": str(args.dsl_file), "outPath": str(args.out)},
                diagnostics=[_diag_from_exception(args.dsl_file, exc)],
                werror=werror,
            )

        return _finalize(
            code=0,
            payload={
                "dslPath": str(args.dsl_file),
                "outPath": str(args.out),
            },
            diagnostics=[],
            werror=werror,
        )

    if command == "from-ir":
        try:
            raw = json.loads(args.ir_json.read_text(encoding="utf-8"))
        except OSError as exc:
            return _finalize(
                code=1,
                payload={"irPath": str(args.ir_json), "outPath": str(args.out)},
                diagnostics=[_diag_from_file_error(args.ir_json, exc)],
                werror=werror,
            )
        except json.JSONDecodeError as exc:
            diag = make_diag(
                code="NEMA-DSL9001",
                severity=Severity.ERROR,
                path=str(args.ir_json),
                line=exc.lineno or 1,
                col=exc.colno or 1,
                detail=str(exc),
            )
            return _finalize(
                code=1,
                payload={"irPath": str(args.ir_json), "outPath": str(args.out)},
                diagnostics=[diag],
                werror=werror,
            )

        if not isinstance(raw, dict):
            diag = make_diag(
                code="NEMA-DSL9001",
                severity=Severity.ERROR,
                path=str(args.ir_json),
                line=1,
                col=1,
                detail="IR root must be a JSON object",
            )
            return _finalize(
                code=1,
                payload={"irPath": str(args.ir_json), "outPath": str(args.out)},
                diagnostics=[diag],
                werror=werror,
            )

        try:
            source = _render_dsl(raw)
        except ValueError as exc:
            return _finalize(
                code=1,
                payload={"irPath": str(args.ir_json), "outPath": str(args.out)},
                diagnostics=[
                    make_diag(
                        code="NEMA-DSL9001",
                        severity=Severity.ERROR,
                        path=str(args.ir_json),
                        line=1,
                        col=1,
                        detail=str(exc),
                    )
                ],
                werror=werror,
            )

        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(source, encoding="utf-8")
        except OSError as exc:
            return _finalize(
                code=1,
                payload={"irPath": str(args.ir_json), "outPath": str(args.out)},
                diagnostics=[_diag_from_write_error(args.out, exc)],
                werror=werror,
            )

        return _finalize(
            code=0,
            payload={
                "irPath": str(args.ir_json),
                "outPath": str(args.out),
            },
            diagnostics=[],
            werror=werror,
        )

    if command == "check":
        try:
            lowered, lowered_locs = _compile_dsl_file_to_ir_with_locs(args.dsl_file)
        except (DslError, ValueError) as exc:
            return _finalize(
                code=1,
                payload={},
                diagnostics=[_diag_from_exception(args.dsl_file, exc)],
                werror=werror,
            )

        diagnostics = typecheck(lowered, lowered_locs, str(args.dsl_file))

        has_typecheck_error = any(diag.severity == Severity.ERROR for diag in diagnostics)
        if not has_typecheck_error:
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
                validate_ir(temp_path)
            except OSError as exc:
                diagnostics.append(_diag_from_write_error(args.dsl_file, exc))
            except IRValidationError as exc:
                loc_path, line, col = _loc_from_map(lowered_locs, "graph")
                diagnostics.append(
                    make_diag(
                        code="NEMA-DSL2999",
                        severity=Severity.ERROR,
                        path=(loc_path if loc_path is not None else str(args.dsl_file)),
                        line=line,
                        col=col,
                        detail=str(exc),
                    )
                )
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)

        return _finalize(
            code=0,
            payload={},
            diagnostics=diagnostics,
            werror=werror,
        )

    if command == "hwtest":
        hw_mode = getattr(args, "hw", "auto")
        hw_available = _hw_toolchain_available()
        base_payload: dict[str, Any] = {
            "benchReportPath": None,
            "hwToolchainAvailable": hw_available,
        }

        if args.ticks < 0:
            diag = make_diag(
                code="NEMA-DSL9001",
                severity=Severity.ERROR,
                path=str(args.dsl_file),
                line=1,
                col=1,
                detail="--ticks must be >= 0",
            )
            return _finalize(
                code=1,
                payload=base_payload,
                diagnostics=[diag],
                werror=werror,
            )

        try:
            lowered, lowered_locs = _compile_dsl_file_to_ir_with_locs(args.dsl_file)
        except (DslError, ValueError) as exc:
            return _finalize(
                code=1,
                payload=base_payload,
                diagnostics=[_diag_from_exception(args.dsl_file, exc)],
                werror=werror,
            )

        diagnostics: list[Diagnostic] = []
        loc_path, line, col = _loc_from_map(lowered_locs, "compile.requireHwToolchain")
        if hw_mode == "require" and not hw_available:
            diagnostics.append(
                make_diag(
                    code="NEMA-DSL2401",
                    severity=Severity.ERROR,
                    path=(loc_path if loc_path is not None else str(args.dsl_file)),
                    line=line,
                    col=col,
                )
            )
            return _finalize(
                code=1,
                payload=base_payload,
                diagnostics=diagnostics,
                werror=werror,
            )

        if hw_mode == "auto" and not hw_available:
            diagnostics.append(
                make_diag(
                    code="NEMA-DSL2401",
                    severity=Severity.WARNING,
                    path=(loc_path if loc_path is not None else str(args.dsl_file)),
                    line=line,
                    col=col,
                )
            )

        model_id = lowered.get("modelId") if isinstance(lowered, dict) else None
        if not isinstance(model_id, str) or not model_id.strip():
            diag = make_diag(
                code="NEMA-DSL9001",
                severity=Severity.ERROR,
                path=str(args.dsl_file),
                line=1,
                col=1,
                detail="dsl hwtest requires root field 'modelId'",
            )
            diagnostics.append(diag)
            return _finalize(
                code=1,
                payload=base_payload,
                diagnostics=diagnostics,
                werror=werror,
            )
        model_id = model_id.strip()

        outdir = args.outdir
        ir_path = outdir / model_id / "dsl" / "ir_from_dsl.json"
        try:
            runtime_ir = _absolutize_runtime_ir_paths(lowered, dsl_path=args.dsl_file)
            dump_json(runtime_ir, ir_path)
        except OSError as exc:
            return _finalize(
                code=1,
                payload=base_payload,
                diagnostics=diagnostics + [_diag_from_write_error(ir_path, exc)],
                werror=werror,
            )

        code, hw_summary = _run_hwtest_pipeline_with_hw_mode(
            ir_path=ir_path,
            outdir=outdir,
            ticks=args.ticks,
            hw_mode=hw_mode,
        )
        bench_report_path = None
        if isinstance(hw_summary, dict):
            raw_bench = hw_summary.get("bench_report")
            if isinstance(raw_bench, str):
                bench_report_path = raw_bench

        payload: dict[str, Any] = {
            "benchReportPath": bench_report_path,
            "hwToolchainAvailable": hw_available,
        }
        return _finalize(
            code=code,
            payload=payload,
            diagnostics=diagnostics,
            werror=werror,
        )

    diag = make_diag(
        code="NEMA-DSL9004",
        severity=Severity.ERROR,
        path="<cli>",
        line=1,
        col=1,
        command=str(command),
    )
    return _finalize(
        code=2,
        payload={"command": command},
        diagnostics=[diag],
        werror=werror,
    )


def _payload_to_diagnostics(payload: dict[str, Any]) -> list[Diagnostic]:
    raw = payload.get("diagnostics")
    if not isinstance(raw, list):
        return []

    diags: list[Diagnostic] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        severity_raw = str(item.get("severity", "ERROR"))
        try:
            severity = Severity(severity_raw)
        except ValueError:
            severity = Severity.ERROR
        diags.append(
            Diagnostic(
                code=str(item.get("code", "NEMA-DSL9001")),
                severity=severity,
                path=str(item.get("path", "<input>")),
                line=int(item.get("line", 1)),
                col=int(item.get("col", 1)),
                message=str(item.get("message", "")),
                hint=None if item.get("hint") is None else str(item.get("hint")),
                note=None if item.get("note") is None else str(item.get("note")),
            )
        )
    return _sorted_diagnostics(diags)


def emit(payload: dict, *, fmt: str = "text", no_color: bool = True) -> None:
    if fmt == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    diagnostics = _payload_to_diagnostics(payload)
    if diagnostics:
        print("\n".join(diag.format_text(no_color=no_color) for diag in diagnostics))
        return

    print(json.dumps(payload, indent=2, sort_keys=True))
