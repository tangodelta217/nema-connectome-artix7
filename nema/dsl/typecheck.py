"""Semantic diagnostics for NEMA-DSL v0.1."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any

from .catalog import make_diag
from .diagnostics import Diagnostic, Severity
from .parser import LocationMap


def _loc(locs: LocationMap, field_path: str, *, default_path: str) -> tuple[str, int, int]:
    item = locs.get(field_path)
    if not isinstance(item, dict):
        return (default_path, 1, 1)
    path = item.get("path")
    if not isinstance(path, str) or not path:
        path = default_path
    line = item.get("line")
    col = item.get("col")
    if not isinstance(line, int) or not isinstance(col, int):
        return (path, 1, 1)
    return (path, line, col)


def _diag(
    out: list[Diagnostic],
    *,
    code: str,
    severity: Severity,
    path: str,
    locs: LocationMap,
    field_path: str,
    **kwargs: object,
) -> None:
    loc_path, line, col = _loc(locs, field_path, default_path=path)
    out.append(
        make_diag(
            code=code,
            severity=severity,
            path=loc_path,
            line=line,
            col=col,
            **kwargs,
        )
    )


def _mode(ir_like: dict[str, Any]) -> str:
    constraints = ir_like.get("constraints")
    if not isinstance(constraints, dict):
        return "FAITHFUL"
    raw = constraints.get("mode")
    if not isinstance(raw, str):
        return "FAITHFUL"
    token = raw.strip().upper()
    return token if token in {"FAITHFUL", "AUGMENTED"} else "FAITHFUL"


def _is_placeholder_sha(raw: str) -> bool:
    token = raw.strip().lower()
    if token.startswith("sha256:"):
        token = token[len("sha256:") :]
    if not token:
        return True
    return (
        "placeholder" in token
        or "replace" in token
        or token in {"todo", "tbd", "none", "unknown", "na", "n/a"}
        or token == "0" * 64
    )


def _normalize_sha(raw: str) -> str:
    token = raw.strip().lower()
    if token.startswith("sha256:"):
        token = token[len("sha256:") :]
    return token


def _severity_for_external(mode: str) -> Severity:
    return Severity.ERROR if mode == "FAITHFUL" else Severity.WARNING


def _resolve_external_artifact(path: str, uri: str) -> Path:
    target = Path(uri)
    if target.is_absolute():
        return target

    bases = [Path(path).parent, Path.cwd()]
    for base in bases:
        candidate = (base / target).resolve()
        if candidate.exists():
            return candidate
    return (bases[0] / target).resolve()


def _known_type_ids(type_table: Any) -> set[str]:
    known: set[str] = set()
    if isinstance(type_table, dict):
        for key, value in type_table.items():
            if isinstance(key, str) and key:
                known.add(key)
            if isinstance(value, dict):
                for candidate in ("typeId", "id", "name"):
                    raw = value.get(candidate)
                    if isinstance(raw, str) and raw:
                        known.add(raw)
        return known

    if isinstance(type_table, list):
        for item in type_table:
            if not isinstance(item, dict):
                continue
            for candidate in ("typeId", "id", "name"):
                raw = item.get(candidate)
                if isinstance(raw, str) and raw:
                    known.add(raw)
    return known


def _iter_conductance_paths(graph: dict[str, Any]) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []

    inline = graph.get("inline")
    if isinstance(inline, dict):
        gap_edges = inline.get("gapEdges")
        if isinstance(gap_edges, list):
            for idx, edge in enumerate(gap_edges):
                if not isinstance(edge, dict):
                    continue
                if "conductance" in edge:
                    out.append((f"graph.inline.gapEdges[{idx}].conductance", edge["conductance"]))

        chem_edges = inline.get("chemicalEdges")
        if isinstance(chem_edges, list):
            for idx, edge in enumerate(chem_edges):
                if not isinstance(edge, dict):
                    continue
                if "conductance" in edge:
                    out.append((f"graph.inline.chemicalEdges[{idx}].conductance", edge["conductance"]))

    edges = graph.get("edges")
    if isinstance(edges, list):
        for idx, edge in enumerate(edges):
            if not isinstance(edge, dict):
                continue
            if "conductance" in edge:
                out.append((f"graph.edges[{idx}].conductance", edge["conductance"]))
    return out


def _toolchain_available() -> bool:
    forced = os.environ.get("NEMA_DSL_FORCE_HW_UNAVAILABLE", "").strip().lower()
    if forced in {"1", "true", "yes"}:
        return False
    return bool(shutil.which("vitis_hls")) or bool(shutil.which("vivado"))


def typecheck(ir_like_dict: dict[str, Any], locs: LocationMap, path: str) -> list[Diagnostic]:
    """Return semantic diagnostics. Does not raise for normal semantic failures."""
    diagnostics: list[Diagnostic] = []

    if not isinstance(ir_like_dict, dict):
        _diag(
            diagnostics,
            code="NEMA-DSL2001",
            severity=Severity.ERROR,
            path=path,
            locs=locs,
            field_path="",
            field="graph",
        )
        return diagnostics

    if "graph" not in ir_like_dict:
        _diag(
            diagnostics,
            code="NEMA-DSL2001",
            severity=Severity.ERROR,
            path=path,
            locs=locs,
            field_path="graph",
            field="graph",
        )

    ir_version = ir_like_dict.get("irVersion")
    if ir_version is not None and ir_version != "0.1":
        _diag(
            diagnostics,
            code="NEMA-DSL2002",
            severity=Severity.ERROR,
            path=path,
            locs=locs,
            field_path="irVersion",
            got=str(ir_version),
        )

    graph = ir_like_dict.get("graph")
    if isinstance(graph, dict):
        has_inline = "inline" in graph and graph.get("inline") is not None
        has_external = "external" in graph and graph.get("external") is not None
        if has_inline and has_external:
            _diag(
                diagnostics,
                code="NEMA-DSL2101",
                severity=Severity.ERROR,
                path=path,
                locs=locs,
                field_path="graph",
            )

        mode = _mode(ir_like_dict)
        ext_severity = _severity_for_external(mode)
        external = graph.get("external")
        if isinstance(external, dict):
            sha_raw = external.get("sha256")
            sha_value = sha_raw if isinstance(sha_raw, str) else None
            if isinstance(sha_value, str) and _is_placeholder_sha(sha_value):
                _diag(
                    diagnostics,
                    code="NEMA-DSL2201",
                    severity=ext_severity,
                    path=path,
                    locs=locs,
                    field_path="graph.external.sha256",
                    mode=mode,
                )
            elif isinstance(sha_value, str):
                expected = _normalize_sha(sha_value)
                uri_raw = external.get("uri", external.get("path"))
                uri = uri_raw if isinstance(uri_raw, str) else ""
                artifact = _resolve_external_artifact(path, uri)
                if not artifact.exists():
                    _diag(
                        diagnostics,
                        code="NEMA-DSL2202",
                        severity=ext_severity,
                        path=path,
                        locs=locs,
                        field_path="graph.external.sha256",
                        detail=f"artifact not found: {uri or '<missing uri/path>'}",
                    )
                elif len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
                    _diag(
                        diagnostics,
                        code="NEMA-DSL2202",
                        severity=ext_severity,
                        path=path,
                        locs=locs,
                        field_path="graph.external.sha256",
                        detail="sha256 is not a valid 64-hex digest",
                    )
                else:
                    actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
                    if actual != expected:
                        _diag(
                            diagnostics,
                            code="NEMA-DSL2202",
                            severity=ext_severity,
                            path=path,
                            locs=locs,
                            field_path="graph.external.sha256",
                            detail=f"sha mismatch for {uri}: expected {expected}, got {actual}",
                        )

        for cond_path, raw_value in _iter_conductance_paths(graph):
            if isinstance(raw_value, bool):
                continue
            if not isinstance(raw_value, (int, float)):
                continue
            if raw_value < 0:
                _diag(
                    diagnostics,
                    code="NEMA-DSL2303",
                    severity=Severity.ERROR,
                    path=path,
                    locs=locs,
                    field_path=cond_path,
                    value=str(raw_value),
                )

    compile_obj = ir_like_dict.get("compile")
    qformats = compile_obj.get("qformats") if isinstance(compile_obj, dict) else None
    if isinstance(qformats, dict):
        known = _known_type_ids(ir_like_dict.get("typeTable"))
        for key, value in qformats.items():
            if not (isinstance(key, str) and key.endswith("TypeId")):
                continue
            if not isinstance(value, str):
                continue
            if value not in known:
                _diag(
                    diagnostics,
                    code="NEMA-DSL2301",
                    severity=Severity.ERROR,
                    path=path,
                    locs=locs,
                    field_path=f"compile.qformats.{key}",
                    field=f"compile.qformats.{key}",
                    type_id=value,
                )

    schedule = ir_like_dict.get("schedule")
    if isinstance(schedule, dict):
        policy = schedule.get("policy")
        snapshot_rule = schedule.get("snapshotRule")
        if policy != "nema.tick.v0.1" or snapshot_rule is not True:
            field = "schedule.policy" if policy != "nema.tick.v0.1" else "schedule.snapshotRule"
            _diag(
                diagnostics,
                code="NEMA-DSL2302",
                severity=Severity.ERROR,
                path=path,
                locs=locs,
                field_path=field,
            )

    constraints = ir_like_dict.get("constraints")
    license_obj = ir_like_dict.get("license")
    if isinstance(constraints, dict) and isinstance(license_obj, dict):
        allowed = constraints.get("allowedSpdx")
        spdx = license_obj.get("spdxId")
        if isinstance(allowed, list) and isinstance(spdx, str):
            allowed_set = {item for item in allowed if isinstance(item, str)}
            if spdx not in allowed_set:
                _diag(
                    diagnostics,
                    code="NEMA-DSL2304",
                    severity=Severity.ERROR,
                    path=path,
                    locs=locs,
                    field_path="license.spdxId",
                    spdx_id=spdx,
                )

    require_hw = False
    if isinstance(compile_obj, dict):
        require_hw = bool(compile_obj.get("requireHwToolchain"))
    if require_hw and not _toolchain_available():
        _diag(
            diagnostics,
            code="NEMA-DSL2401",
            severity=Severity.WARNING,
            path=path,
            locs=locs,
            field_path="compile.requireHwToolchain",
        )

    return diagnostics
