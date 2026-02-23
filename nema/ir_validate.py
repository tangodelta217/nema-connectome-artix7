"""IR validation for NEMA graphs."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .connectome_bundle import (
    ConnectomeBundleError,
    external_artifact_sha256,
    is_placeholder_sha256,
    is_valid_sha256_hex,
    normalize_sha256_token,
)


class IRValidationError(ValueError):
    """Raised when an IR file fails invariant checks."""


@dataclass(frozen=True)
class EdgeView:
    edge_id: str
    kind: str
    source: str
    target: str
    directed: bool
    conductance: Decimal


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def load_ir(path: Path) -> tuple[dict[str, Any], str]:
    """Load an IR JSON file and return (payload, sha256)."""
    raw = path.read_bytes()
    digest = _sha256_bytes(raw)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise IRValidationError(f"invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise IRValidationError("top-level JSON value must be an object")
    if not payload:
        raise IRValidationError("top-level JSON object must not be empty")
    return payload, digest


def _require_object(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IRValidationError(f"{field_name} must be an object")
    return value


def _require_array(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise IRValidationError(f"{field_name} must be an array")
    return value


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise IRValidationError(f"{field_name} must be a non-empty string")
    return value


def _require_nonnegative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise IRValidationError(f"{field_name} must be a non-negative integer")
    return value


def _extract_endpoint(edge: dict[str, Any], names: tuple[str, ...], label: str, edge_id: str) -> str:
    for name in names:
        if name in edge:
            return _require_string(edge[name], f"edge '{edge_id}' {name}")
    raise IRValidationError(f"edge '{edge_id}' missing {label} endpoint")


def _extract_conductance(edge: dict[str, Any], edge_id: str) -> Decimal:
    if "conductance" not in edge:
        raise IRValidationError(f"edge '{edge_id}' missing conductance")
    raw_value = edge["conductance"]
    if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
        raise IRValidationError(f"edge '{edge_id}' conductance must be numeric")
    value = Decimal(str(raw_value))
    if value < 0:
        raise IRValidationError(f"edge '{edge_id}' has negative conductance")
    return value


def _extract_kind(edge: dict[str, Any], edge_id: str) -> str:
    raw_kind = edge.get("kind", edge.get("type"))
    if not isinstance(raw_kind, str) or not raw_kind:
        raise IRValidationError(f"edge '{edge_id}' missing kind/type")
    kind = raw_kind.upper()
    if kind not in {"CHEMICAL", "GAP"}:
        raise IRValidationError(f"edge '{edge_id}' has unsupported kind '{raw_kind}'")
    return kind


def _extract_directed(edge: dict[str, Any], edge_id: str) -> bool:
    directed = edge.get("directed", True)
    if not isinstance(directed, bool):
        raise IRValidationError(f"edge '{edge_id}' directed flag must be boolean")
    return directed


def _validate_external(
    graph: dict[str, Any],
    ir_path: Path,
    *,
    allow_missing_for_smoke: bool = False,
) -> None:
    external = graph.get("external")
    if external is None:
        return

    entries = [external] if isinstance(external, dict) else _require_array(external, "graph.external")
    for idx, entry in enumerate(entries):
        item = _require_object(entry, f"graph.external[{idx}]")
        raw_path = item.get("uri", item.get("path", item.get("file")))
        rel_path = _require_string(raw_path, f"graph.external[{idx}].path")
        target = Path(rel_path)
        resolved = target if target.is_absolute() else (ir_path.parent / target)
        if not resolved.exists():
            if allow_missing_for_smoke:
                continue
            raise IRValidationError(
                f"graph.external[{idx}] file does not exist: {resolved}"
            )

        sha = item.get("sha256")
        if sha is None:
            continue
        if not isinstance(sha, str):
            raise IRValidationError(f"graph.external[{idx}].sha256 must be a string")
        if is_placeholder_sha256(sha):
            continue
        expected = normalize_sha256_token(sha)
        if not is_valid_sha256_hex(expected):
            if allow_missing_for_smoke:
                continue
            raise IRValidationError(f"graph.external[{idx}] sha256 is not a valid hex digest")
        try:
            actual = external_artifact_sha256(resolved)
        except ConnectomeBundleError as exc:
            if allow_missing_for_smoke:
                continue
            raise IRValidationError(
                f"graph.external[{idx}] invalid external artifact: {exc}"
            ) from exc
        if actual != expected:
            if allow_missing_for_smoke:
                continue
            raise IRValidationError(
                f"graph.external[{idx}] sha256 mismatch for {resolved}: expected {expected}, got {actual}"
            )


def _validate_license(payload: dict[str, Any]) -> None:
    constraints = _require_object(payload.get("constraints"), "constraints")
    allowed = _require_array(constraints.get("allowedSpdx"), "constraints.allowedSpdx")
    if not allowed:
        raise IRValidationError("constraints.allowedSpdx must not be empty")
    allowed_spdx: set[str] = set()
    for idx, value in enumerate(allowed):
        allowed_spdx.add(_require_string(value, f"constraints.allowedSpdx[{idx}]"))

    license_obj = _require_object(payload.get("license"), "license")
    spdx_id = _require_string(license_obj.get("spdxId"), "license.spdxId")
    if spdx_id not in allowed_spdx:
        raise IRValidationError(
            f"license.spdxId '{spdx_id}' is not allowed by constraints.allowedSpdx"
        )


def _validate_graph(
    payload: dict[str, Any],
    ir_path: Path,
    *,
    allow_external_smoke: bool = False,
) -> tuple[int, int]:
    graph = _require_object(payload.get("graph"), "graph")
    nodes = _require_array(graph.get("nodes"), "graph.nodes")
    edges = _require_array(graph.get("edges"), "graph.edges")

    node_ids: set[str] = set()
    node_indices: set[int] = set()
    for idx, node_raw in enumerate(nodes):
        node = _require_object(node_raw, f"graph.nodes[{idx}]")
        node_id = _require_string(node.get("id"), f"graph.nodes[{idx}].id")
        node_index = _require_nonnegative_int(node.get("index"), f"graph.nodes[{idx}].index")
        if node_id in node_ids:
            raise IRValidationError(f"duplicate node id '{node_id}'")
        if node_index in node_indices:
            raise IRValidationError(f"duplicate node index '{node_index}'")
        if "canonicalOrderId" not in node:
            raise IRValidationError(f"graph.nodes[{idx}] missing canonicalOrderId")
        _require_nonnegative_int(node.get("canonicalOrderId"), f"graph.nodes[{idx}].canonicalOrderId")
        node_ids.add(node_id)
        node_indices.add(node_index)

    edge_ids: set[str] = set()
    edge_views: list[EdgeView] = []
    for idx, edge_raw in enumerate(edges):
        edge = _require_object(edge_raw, f"graph.edges[{idx}]")
        edge_id = _require_string(edge.get("id"), f"graph.edges[{idx}].id")
        if edge_id in edge_ids:
            raise IRValidationError(f"duplicate edge id '{edge_id}'")
        edge_ids.add(edge_id)

        source = _extract_endpoint(edge, ("source", "src", "sourceNodeId", "from"), "source", edge_id)
        target = _extract_endpoint(edge, ("target", "dst", "targetNodeId", "to"), "target", edge_id)
        if source not in node_ids:
            raise IRValidationError(f"edge '{edge_id}' references missing source node '{source}'")
        if target not in node_ids:
            raise IRValidationError(f"edge '{edge_id}' references missing target node '{target}'")

        kind = _extract_kind(edge, edge_id)
        directed = _extract_directed(edge, edge_id)
        conductance = _extract_conductance(edge, edge_id)

        if kind == "CHEMICAL" and not directed:
            raise IRValidationError(f"edge '{edge_id}' kind CHEMICAL must be directed")

        edge_views.append(
            EdgeView(
                edge_id=edge_id,
                kind=kind,
                source=source,
                target=target,
                directed=directed,
                conductance=conductance,
            )
        )

    gap_directed = [
        edge
        for edge in edge_views
        if edge.kind == "GAP" and edge.directed
    ]
    gap_counter = Counter((edge.source, edge.target, edge.conductance) for edge in gap_directed)
    for (source, target, conductance), count in gap_counter.items():
        mirror_count = gap_counter.get((target, source, conductance), 0)
        if mirror_count < count:
            raise IRValidationError(
                "GAP edge symmetry violation: directed representation must contain mirror edges "
                f"for {source}->{target} (conductance={conductance})"
            )

    _validate_external(graph, ir_path, allow_missing_for_smoke=allow_external_smoke)
    return len(nodes), len(edges)


def validate_ir(path: Path, *, allow_external_smoke: bool = False) -> dict[str, Any]:
    payload, digest = load_ir(path)
    _validate_license(payload)
    node_count, edge_count = _validate_graph(
        payload,
        path,
        allow_external_smoke=allow_external_smoke,
    )
    return {
        "ok": True,
        "ir_sha256": digest,
        "node_count": node_count,
        "edge_count": edge_count,
        "invariants_checked": [
            "json_parseable",
            "top_level_is_object",
            "top_level_not_empty",
            "license_spdx_in_allowed",
            "unique_node_ids",
            "unique_node_indices",
            "unique_edge_ids",
            "edges_reference_existing_nodes",
            "chemical_edges_are_directed",
            "gap_edges_are_symmetric",
            "non_negative_conductance",
            "canonical_order_id_present",
            "graph_external_file_and_sha256",
        ],
        "top_level_keys": sorted(payload.keys()),
    }
