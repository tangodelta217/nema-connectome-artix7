"""Typecheck NEMA TOML DSL programs and produce normalized typed structures."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .parse_toml import DSLProgram


class DSLTypeError(ValueError):
    """Raised when DSL type checking fails."""


@dataclass(frozen=True)
class CheckedModule:
    name: str
    model_id: str | None
    kernel_id: int | None
    license_spdx: str
    allowed_spdx: list[str]


@dataclass(frozen=True)
class CheckedGraphStats:
    node_count: int
    chemical_edge_count: int
    gap_edge_count: int


@dataclass(frozen=True)
class CheckedGraphExternal:
    uri: str
    path: str
    subgraph_id: str
    format_id: str
    sha256: str


@dataclass(frozen=True)
class CheckedNode:
    node_id: str
    index: int
    canonical_order_id: int
    v_init_raw: int | None
    tau_m: float | None


@dataclass(frozen=True)
class CheckedEdge:
    edge_id: str
    kind: str
    source: str
    target: str
    directed: bool
    conductance: float
    weight: float | None
    model_id: int | str | None


@dataclass(frozen=True)
class CheckedGraph:
    dt: float | None
    tau_m: float | None
    stats: CheckedGraphStats | None
    external: CheckedGraphExternal | None
    nodes: list[CheckedNode]
    edges: list[CheckedEdge]


@dataclass(frozen=True)
class CheckedSchedule:
    policy: str
    snapshot_rule: bool
    eval_order: str


@dataclass(frozen=True)
class CheckedQFormats:
    voltage: str
    activation: str
    accum: str
    lut_input: str
    lut_output: str


@dataclass(frozen=True)
class CheckedCompile:
    tanh_lut_policy: str
    tanh_lut_artifact: str
    tanh_lut_checksum_sha256: str


@dataclass(frozen=True)
class CheckedRun:
    default_ticks: int
    seed: int


@dataclass(frozen=True)
class CheckedProgram:
    source_path: Path
    module: CheckedModule
    graph: CheckedGraph
    schedule: CheckedSchedule
    qformats: CheckedQFormats
    compile: CheckedCompile
    run: CheckedRun


def _fail(path: str, message: str) -> DSLTypeError:
    return DSLTypeError(f"{path}: {message}")


def _as_nonempty_str(path: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(path, "expected non-empty string")
    return value.strip()


def _as_optional_nonempty_str(path: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _fail(path, "expected non-empty string or null")
    return value.strip()


def _as_bool(path: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise _fail(path, "expected boolean")
    return value


def _as_nonneg_int(path: str, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _fail(path, "expected non-negative integer")
    return value


def _as_optional_nonneg_int(path: str, value: Any) -> int | None:
    if value is None:
        return None
    return _as_nonneg_int(path, value)


def _as_int(path: str, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _fail(path, "expected integer")
    return value


def _as_optional_int(path: str, value: Any) -> int | None:
    if value is None:
        return None
    return _as_int(path, value)


def _as_number(path: str, value: Any, *, positive: bool = False, non_negative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail(path, "expected number")
    out = float(value)
    if positive and out <= 0:
        raise _fail(path, "expected number > 0")
    if non_negative and out < 0:
        raise _fail(path, "expected number >= 0")
    return out


def _as_optional_number(path: str, value: Any, *, positive: bool = False, non_negative: bool = False) -> float | None:
    if value is None:
        return None
    return _as_number(path, value, positive=positive, non_negative=non_negative)


def _as_str_list(path: str, value: Any) -> list[str]:
    if not isinstance(value, list):
        raise _fail(path, "expected array of strings")
    out: list[str] = []
    for idx, item in enumerate(value):
        out.append(_as_nonempty_str(f"{path}[{idx}]", item))
    if not out:
        raise _fail(path, "must not be empty")
    return out


def _check_unique_strings(path: str, values: list[str], kind: str) -> None:
    seen: set[str] = set()
    for idx, value in enumerate(values):
        if value in seen:
            raise _fail(f"{path}[{idx}]", f"duplicate {kind} '{value}'")
        seen.add(value)


def _normalize_kind(path: str, value: Any) -> str:
    kind = _as_nonempty_str(path, value).upper()
    if kind not in {"CHEMICAL", "GAP"}:
        raise _fail(path, "expected 'CHEMICAL' or 'GAP'")
    return kind


def _normalize_eval_order(path: str, value: Any) -> str:
    order = _as_nonempty_str(path, value)
    if order not in {"index", "reverse"}:
        raise _fail(path, "expected 'index' or 'reverse'")
    return order


_QFORMAT_RE = re.compile(r"^(?:Q|UQ)[0-9]+\.[0-9]+$")


def _as_qformat(path: str, value: Any) -> str:
    token = _as_nonempty_str(path, value)
    if _QFORMAT_RE.match(token) is None:
        raise _fail(path, "expected fixed type ID like Q8.8 or UQ8.8")
    return token


def _typecheck_module(program: DSLProgram) -> CheckedModule:
    allowed_spdx = _as_str_list("module.allowedSpdx", program.module.allowed_spdx)
    _check_unique_strings("module.allowedSpdx", allowed_spdx, "SPDX")

    license_spdx = _as_nonempty_str("module.licenseSpdx", program.module.license_spdx)
    if license_spdx not in set(allowed_spdx):
        raise _fail("module.licenseSpdx", "must be listed in module.allowedSpdx")

    return CheckedModule(
        name=_as_nonempty_str("module.name", program.module.name),
        model_id=_as_optional_nonempty_str("module.modelId", program.module.model_id),
        kernel_id=_as_optional_nonneg_int("module.kernelId", program.module.kernel_id),
        license_spdx=license_spdx,
        allowed_spdx=allowed_spdx,
    )


def _typecheck_graph(program: DSLProgram) -> CheckedGraph:
    nodes: list[CheckedNode] = []
    node_ids: set[str] = set()
    node_indices: set[int] = set()

    if len(program.graph.nodes) == 0:
        raise _fail("graph.nodes", "must contain at least one node")

    for idx, raw_node in enumerate(program.graph.nodes):
        raw = raw_node.raw
        node_id = _as_nonempty_str(f"graph.nodes[{idx}].id", raw.get("id"))
        if node_id in node_ids:
            raise _fail(f"graph.nodes[{idx}].id", f"duplicate node id '{node_id}'")
        node_ids.add(node_id)

        node_index = _as_nonneg_int(f"graph.nodes[{idx}].index", raw.get("index"))
        if node_index in node_indices:
            raise _fail(f"graph.nodes[{idx}].index", f"duplicate node index '{node_index}'")
        node_indices.add(node_index)

        canonical_order_id = _as_nonneg_int(
            f"graph.nodes[{idx}].canonicalOrderId",
            raw.get("canonicalOrderId"),
        )
        v_init_raw = _as_optional_int(f"graph.nodes[{idx}].vInitRaw", raw.get("vInitRaw"))
        tau_m = _as_optional_number(f"graph.nodes[{idx}].tauM", raw.get("tauM"), positive=True)

        nodes.append(
            CheckedNode(
                node_id=node_id,
                index=node_index,
                canonical_order_id=canonical_order_id,
                v_init_raw=v_init_raw,
                tau_m=tau_m,
            )
        )

    edge_ids: set[str] = set()
    edges: list[CheckedEdge] = []
    for idx, raw_edge in enumerate(program.graph.edges):
        raw = raw_edge.raw
        edge_id = _as_nonempty_str(f"graph.edges[{idx}].id", raw.get("id"))
        if edge_id in edge_ids:
            raise _fail(f"graph.edges[{idx}].id", f"duplicate edge id '{edge_id}'")
        edge_ids.add(edge_id)

        source = _as_nonempty_str(f"graph.edges[{idx}].source", raw.get("source"))
        target = _as_nonempty_str(f"graph.edges[{idx}].target", raw.get("target"))
        if source not in node_ids:
            raise _fail(f"graph.edges[{idx}].source", f"unknown node '{source}'")
        if target not in node_ids:
            raise _fail(f"graph.edges[{idx}].target", f"unknown node '{target}'")

        kind = _normalize_kind(f"graph.edges[{idx}].kind", raw.get("kind"))
        directed = _as_bool(f"graph.edges[{idx}].directed", raw.get("directed"))
        conductance = _as_number(f"graph.edges[{idx}].conductance", raw.get("conductance"), non_negative=True)

        if kind == "CHEMICAL" and not directed:
            raise _fail(f"graph.edges[{idx}].directed", "CHEMICAL edges must be directed=true")

        weight = _as_optional_number(f"graph.edges[{idx}].weight", raw.get("weight"))

        model_id_raw = raw.get("modelId")
        if model_id_raw is None:
            model_id: int | str | None = None
        elif isinstance(model_id_raw, int) and not isinstance(model_id_raw, bool):
            model_id = model_id_raw
        elif isinstance(model_id_raw, str) and model_id_raw.strip():
            model_id = model_id_raw.strip()
        else:
            raise _fail(f"graph.edges[{idx}].modelId", "expected int, non-empty string, or null")

        edges.append(
            CheckedEdge(
                edge_id=edge_id,
                kind=kind,
                source=source,
                target=target,
                directed=directed,
                conductance=conductance,
                weight=weight,
                model_id=model_id,
            )
        )

    # GAP symmetry check for directed representation.
    gap_directed = [
        edge
        for edge in edges
        if edge.kind == "GAP" and edge.directed
    ]
    gap_counter = Counter((edge.source, edge.target, edge.conductance) for edge in gap_directed)
    for (source, target, conductance), count in gap_counter.items():
        mirror_count = gap_counter.get((target, source, conductance), 0)
        if mirror_count < count:
            raise _fail(
                "graph.edges",
                "GAP directed representation must include mirrored edges",
            )

    stats_checked: CheckedGraphStats | None = None
    if program.graph.stats is not None:
        stats_checked = CheckedGraphStats(
            node_count=_as_nonneg_int("graph.stats.nodeCount", program.graph.stats.node_count),
            chemical_edge_count=_as_nonneg_int(
                "graph.stats.chemicalEdgeCount",
                program.graph.stats.chemical_edge_count,
            ),
            gap_edge_count=_as_nonneg_int("graph.stats.gapEdgeCount", program.graph.stats.gap_edge_count),
        )

    external_checked: CheckedGraphExternal | None = None
    if program.graph.external is not None:
        raw_uri = _as_optional_nonempty_str("graph.external.uri", program.graph.external.uri)
        raw_path = _as_optional_nonempty_str("graph.external.path", program.graph.external.path)
        if raw_uri is None and raw_path is None:
            raise _fail("graph.external", "requires at least one of uri/path")

        uri_value = raw_uri or raw_path
        path_value = raw_path or raw_uri
        if uri_value is None or path_value is None:
            raise _fail("graph.external", "requires at least one of uri/path")

        external_checked = CheckedGraphExternal(
            uri=uri_value,
            path=path_value,
            subgraph_id=_as_nonempty_str("graph.external.subgraphId", program.graph.external.subgraph_id),
            format_id=_as_nonempty_str("graph.external.formatId", program.graph.external.format_id),
            sha256=_as_nonempty_str("graph.external.sha256", program.graph.external.sha256),
        )

    return CheckedGraph(
        dt=_as_optional_number("graph.dt", program.graph.dt, positive=True),
        tau_m=_as_optional_number("graph.tauM", program.graph.tau_m, positive=True),
        stats=stats_checked,
        external=external_checked,
        nodes=nodes,
        edges=edges,
    )


def _typecheck_schedule(program: DSLProgram) -> CheckedSchedule:
    return CheckedSchedule(
        policy=_as_nonempty_str("schedule.policy", program.schedule.policy),
        snapshot_rule=_as_bool("schedule.snapshotRule", program.schedule.snapshot_rule),
        eval_order=_normalize_eval_order("schedule.evalOrder", program.schedule.eval_order),
    )


def _typecheck_qformats(program: DSLProgram) -> CheckedQFormats:
    return CheckedQFormats(
        voltage=_as_qformat("qformats.voltage", program.qformats.voltage),
        activation=_as_qformat("qformats.activation", program.qformats.activation),
        accum=_as_qformat("qformats.accum", program.qformats.accum),
        lut_input=_as_qformat("qformats.lutInput", program.qformats.lut_input),
        lut_output=_as_qformat("qformats.lutOutput", program.qformats.lut_output),
    )


def _typecheck_compile(program: DSLProgram) -> CheckedCompile:
    return CheckedCompile(
        tanh_lut_policy=_as_nonempty_str("compile.tanhLutPolicy", program.compile.tanh_lut_policy),
        tanh_lut_artifact=_as_nonempty_str("compile.tanhLutArtifact", program.compile.tanh_lut_artifact),
        tanh_lut_checksum_sha256=_as_nonempty_str(
            "compile.tanhLutChecksumSha256",
            program.compile.tanh_lut_checksum_sha256,
        ),
    )


def _typecheck_run(program: DSLProgram) -> CheckedRun:
    return CheckedRun(
        default_ticks=_as_nonneg_int("run.defaultTicks", program.run.default_ticks),
        seed=_as_nonneg_int("run.seed", program.run.seed),
    )


def typecheck_program(program: DSLProgram) -> CheckedProgram:
    """Typecheck a parsed DSL program and return normalized values."""
    checked = CheckedProgram(
        source_path=program.source_path,
        module=_typecheck_module(program),
        graph=_typecheck_graph(program),
        schedule=_typecheck_schedule(program),
        qformats=_typecheck_qformats(program),
        compile=_typecheck_compile(program),
        run=_typecheck_run(program),
    )

    # Preserve v0.1 contract invariants in the frontend.
    if checked.schedule.policy != "nema.tick.v0.1":
        raise _fail("schedule.policy", "must be 'nema.tick.v0.1' for v0.1")
    if checked.schedule.snapshot_rule is not True:
        raise _fail("schedule.snapshotRule", "must be true for v0.1")
    if checked.compile.tanh_lut_policy != "nema.tanh_lut.v0.1":
        raise _fail("compile.tanhLutPolicy", "must be 'nema.tanh_lut.v0.1' for v0.1")

    return checked
