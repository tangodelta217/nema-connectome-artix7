"""Parse .nema.toml DSL files into structured AST dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # pragma: no cover - Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback if tomli is available
    try:
        import tomli as tomllib
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("Python 3.10 requires 'tomli' for DSL TOML parsing") from exc


class DSLParseError(ValueError):
    """Raised when DSL TOML parsing fails."""


@dataclass(frozen=True)
class ModuleSection:
    name: Any
    model_id: Any
    kernel_id: Any
    license_spdx: Any
    allowed_spdx: Any


@dataclass(frozen=True)
class GraphStatsSection:
    node_count: Any
    chemical_edge_count: Any
    gap_edge_count: Any


@dataclass(frozen=True)
class GraphExternalSection:
    uri: Any
    path: Any
    subgraph_id: Any
    format_id: Any
    sha256: Any


@dataclass(frozen=True)
class GraphNodeDecl:
    raw: dict[str, Any]


@dataclass(frozen=True)
class GraphEdgeDecl:
    raw: dict[str, Any]


@dataclass(frozen=True)
class GraphSection:
    dt: Any
    tau_m: Any
    stats: GraphStatsSection | None
    external: GraphExternalSection | None
    nodes: list[GraphNodeDecl]
    edges: list[GraphEdgeDecl]


@dataclass(frozen=True)
class ScheduleSection:
    policy: Any
    snapshot_rule: Any
    eval_order: Any


@dataclass(frozen=True)
class QFormatsSection:
    voltage: Any
    activation: Any
    accum: Any
    lut_input: Any
    lut_output: Any


@dataclass(frozen=True)
class CompileSection:
    tanh_lut_policy: Any
    tanh_lut_artifact: Any
    tanh_lut_checksum_sha256: Any


@dataclass(frozen=True)
class RunSection:
    default_ticks: Any
    seed: Any


@dataclass(frozen=True)
class DSLProgram:
    source_path: Path
    raw: dict[str, Any]
    module: ModuleSection
    graph: GraphSection
    schedule: ScheduleSection
    qformats: QFormatsSection
    compile: CompileSection
    run: RunSection


def _as_object(value: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DSLParseError(f"{path}: expected table/object")
    return value


def _as_array_of_objects(value: Any, *, path: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DSLParseError(f"{path}: expected array of tables")
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            raise DSLParseError(f"{path}[{idx}]: expected table/object")
        out.append(item)
    return out


def parse_toml_file(path: Path) -> DSLProgram:
    """Parse a .nema.toml file into a structured AST."""
    try:
        raw_bytes = path.read_bytes()
    except FileNotFoundError as exc:
        raise DSLParseError(f"file not found: {path}") from exc

    try:
        payload = tomllib.loads(raw_bytes.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise DSLParseError(f"TOML parse error in {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise DSLParseError(f"{path}: expected UTF-8 text") from exc

    if not isinstance(payload, dict):
        raise DSLParseError("top-level TOML value must be a table/object")

    module_obj = _as_object(payload.get("module"), path="module")
    graph_obj = _as_object(payload.get("graph"), path="graph")
    schedule_obj = _as_object(payload.get("schedule"), path="schedule")
    qformats_obj = _as_object(payload.get("qformats"), path="qformats")
    compile_obj = _as_object(payload.get("compile"), path="compile")
    run_obj = _as_object(payload.get("run"), path="run")

    stats_obj_raw = graph_obj.get("stats")
    external_obj_raw = graph_obj.get("external")

    stats_obj = _as_object(stats_obj_raw, path="graph.stats") if stats_obj_raw is not None else None
    external_obj = _as_object(external_obj_raw, path="graph.external") if external_obj_raw is not None else None

    nodes_obj = _as_array_of_objects(graph_obj.get("nodes"), path="graph.nodes")
    edges_obj = _as_array_of_objects(graph_obj.get("edges"), path="graph.edges")

    return DSLProgram(
        source_path=path,
        raw=payload,
        module=ModuleSection(
            name=module_obj.get("name"),
            model_id=module_obj.get("modelId"),
            kernel_id=module_obj.get("kernelId"),
            license_spdx=module_obj.get("licenseSpdx"),
            allowed_spdx=module_obj.get("allowedSpdx"),
        ),
        graph=GraphSection(
            dt=graph_obj.get("dt"),
            tau_m=graph_obj.get("tauM"),
            stats=(
                GraphStatsSection(
                    node_count=stats_obj.get("nodeCount"),
                    chemical_edge_count=stats_obj.get("chemicalEdgeCount"),
                    gap_edge_count=stats_obj.get("gapEdgeCount"),
                )
                if stats_obj is not None
                else None
            ),
            external=(
                GraphExternalSection(
                    uri=external_obj.get("uri"),
                    path=external_obj.get("path"),
                    subgraph_id=external_obj.get("subgraphId"),
                    format_id=external_obj.get("formatId"),
                    sha256=external_obj.get("sha256"),
                )
                if external_obj is not None
                else None
            ),
            nodes=[GraphNodeDecl(raw=item) for item in nodes_obj],
            edges=[GraphEdgeDecl(raw=item) for item in edges_obj],
        ),
        schedule=ScheduleSection(
            policy=schedule_obj.get("policy"),
            snapshot_rule=schedule_obj.get("snapshotRule"),
            eval_order=schedule_obj.get("evalOrder"),
        ),
        qformats=QFormatsSection(
            voltage=qformats_obj.get("voltage"),
            activation=qformats_obj.get("activation"),
            accum=qformats_obj.get("accum"),
            lut_input=qformats_obj.get("lutInput"),
            lut_output=qformats_obj.get("lutOutput"),
        ),
        compile=CompileSection(
            tanh_lut_policy=compile_obj.get("tanhLutPolicy"),
            tanh_lut_artifact=compile_obj.get("tanhLutArtifact"),
            tanh_lut_checksum_sha256=compile_obj.get("tanhLutChecksumSha256"),
        ),
        run=RunSection(
            default_ticks=run_obj.get("defaultTicks"),
            seed=run_obj.get("seed"),
        ),
    )
