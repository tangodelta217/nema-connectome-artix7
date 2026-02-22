"""IR loader with execution-time graph resolution for hwtest/simulation."""

from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path
from typing import Any

from .ir_validate import IRValidationError, load_ir


DEFAULT_SMOKE_NODE_COUNT = 302
DEFAULT_SMOKE_CHEMICAL_EDGE_COUNT = 7500
DEFAULT_SMOKE_GAP_EDGE_COUNT = 0


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_placeholder_sha256(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return True
    return (
        "placeholder" in normalized
        or "replace" in normalized
        or normalized in {"todo", "tbd", "none", "unknown", "na", "n/a"}
        or normalized == "0" * 64
    )


def _parse_nonnegative_int(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= 0 else None
    if isinstance(raw, float):
        if raw.is_integer() and raw >= 0:
            return int(raw)
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text.isdigit():
            return int(text)
        match = re.search(r"\d+", text)
        if match is None:
            return None
        return int(match.group(0))
    return None


def _count_from_candidates(source: dict[str, Any], keys: tuple[str, ...], default: int) -> int:
    for key in keys:
        if key not in source:
            continue
        parsed = _parse_nonnegative_int(source[key])
        if parsed is not None:
            return parsed
    return default


def _resolve_target_counts(graph: dict[str, Any]) -> tuple[int, int, int]:
    stats = graph.get("stats")
    stats_obj = stats if isinstance(stats, dict) else {}

    inline_nodes = graph.get("nodes")
    inline_node_count = len(inline_nodes) if isinstance(inline_nodes, list) else 0
    inline_edges = graph.get("edges")
    if isinstance(inline_edges, list):
        inline_chemical_count = sum(
            1 for edge in inline_edges if str(edge.get("kind", edge.get("type", ""))).upper() == "CHEMICAL"
        )
        inline_gap_count = sum(
            1 for edge in inline_edges if str(edge.get("kind", edge.get("type", ""))).upper() == "GAP"
        )
    else:
        inline_chemical_count = 0
        inline_gap_count = 0

    node_count = _count_from_candidates(
        stats_obj,
        ("nodeCount", "nodes", "nNodes", "numNodes"),
        inline_node_count or DEFAULT_SMOKE_NODE_COUNT,
    )
    chemical_count = _count_from_candidates(
        stats_obj,
        ("chemicalEdgeCount", "chemicalEdges", "chemEdgeCount", "nChemicalEdges"),
        inline_chemical_count or DEFAULT_SMOKE_CHEMICAL_EDGE_COUNT,
    )
    gap_count = _count_from_candidates(
        stats_obj,
        ("gapEdgeCount", "gapEdges", "nGapEdges"),
        inline_gap_count or DEFAULT_SMOKE_GAP_EDGE_COUNT,
    )
    return node_count, chemical_count, gap_count


def _build_synthetic_graph(
    *,
    node_count: int,
    chemical_edge_count: int,
    gap_edge_count: int,
) -> dict[str, Any]:
    if node_count <= 0:
        raise IRValidationError("synthetic graph node_count must be > 0")

    nodes: list[dict[str, Any]] = []
    for idx in range(node_count):
        nodes.append(
            {
                "id": f"n{idx}",
                "index": idx,
                "canonicalOrderId": idx,
                "vInitRaw": ((idx * 73 + 19) % 512) - 256,
                "tauM": 2 + (idx % 5),
            }
        )

    edges: list[dict[str, Any]] = []
    for edge_idx in range(chemical_edge_count):
        pre_idx = edge_idx % node_count
        post_idx = (edge_idx * 17 + 1) % node_count
        if post_idx == pre_idx:
            post_idx = (post_idx + 1) % node_count
        conductance = ((edge_idx * 13) % 32 + 1) / 256.0
        edges.append(
            {
                "id": f"e_chem_smoke_{edge_idx:05d}",
                "kind": "CHEMICAL",
                "source": f"n{pre_idx}",
                "target": f"n{post_idx}",
                "directed": True,
                "conductance": conductance,
            }
        )

    for gap_idx in range(gap_edge_count):
        a_idx = gap_idx % node_count
        b_idx = (gap_idx * 29 + 3) % node_count
        if b_idx == a_idx:
            b_idx = (b_idx + 1) % node_count
        conductance = ((gap_idx * 11) % 16 + 1) / 256.0
        edge_id = f"e_gap_smoke_{gap_idx:05d}"
        edges.append(
            {
                "id": f"{edge_id}_fwd",
                "kind": "GAP",
                "source": f"n{a_idx}",
                "target": f"n{b_idx}",
                "directed": True,
                "conductance": conductance,
            }
        )
        edges.append(
            {
                "id": f"{edge_id}_rev",
                "kind": "GAP",
                "source": f"n{b_idx}",
                "target": f"n{a_idx}",
                "directed": True,
                "conductance": conductance,
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
    }


def _edge_endpoint(edge: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        raw = edge.get(key)
        if isinstance(raw, str) and raw:
            return raw
    return None


def _summarize_resolved_graph(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_count = len(nodes) if isinstance(nodes, list) else 0
    total_edge_count = len(edges) if isinstance(edges, list) else 0

    chemical_edge_count = 0
    gap_directed_count = 0
    gap_pairs: set[tuple[str, str, str]] = set()
    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            kind = str(edge.get("kind", edge.get("type", ""))).upper()
            if kind == "CHEMICAL":
                chemical_edge_count += 1
                continue
            if kind == "GAP":
                gap_directed_count += 1
                src = _edge_endpoint(edge, ("source", "src", "sourceNodeId", "from"))
                dst = _edge_endpoint(edge, ("target", "dst", "targetNodeId", "to"))
                if src is None or dst is None:
                    continue
                a, b = sorted((src, dst))
                conductance = str(edge.get("conductance", ""))
                gap_pairs.add((a, b, conductance))

    return {
        "nodeCount": node_count,
        "edgeCounts": {
            "total": total_edge_count,
            "chemical": chemical_edge_count,
            "gap": len(gap_pairs),
            "gapDirected": gap_directed_count,
        },
    }


def _validate_external_hex_sha(sha256: str, *, index: int) -> str:
    normalized = sha256.lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise IRValidationError(f"graph.external[{index}] sha256 is not a valid hex digest")
    return normalized


def _external_entries(graph: dict[str, Any]) -> list[dict[str, Any]]:
    external = graph.get("external")
    if external is None:
        return []
    if isinstance(external, dict):
        return [external]
    if isinstance(external, list):
        entries: list[dict[str, Any]] = []
        for idx, item in enumerate(external):
            if not isinstance(item, dict):
                raise IRValidationError(f"graph.external[{idx}] must be an object")
            entries.append(item)
        return entries
    raise IRValidationError("graph.external must be an object or array")


def resolve_ir_for_execution(ir_path: Path) -> dict[str, Any]:
    """Load IR and resolve graph inputs for execution pipelines.

    Policy:
    - verified external artifact (exists + non-placeholder sha256 match): keep non-synthetic graph
    - missing external file OR placeholder sha256: enable deterministic SMOKE synthetic graph
    """
    ir_payload, ir_sha256 = load_ir(ir_path)
    resolved = copy.deepcopy(ir_payload)
    graph = resolved.get("graph")
    if not isinstance(graph, dict):
        raise IRValidationError("graph must be an object")

    entries = _external_entries(graph)
    synthetic_used = False
    external_verified = False

    if entries:
        needs_smoke = False
        verified_entries = 0
        for idx, entry in enumerate(entries):
            raw_path = entry.get("path", entry.get("file"))
            if not isinstance(raw_path, str) or not raw_path:
                raise IRValidationError(f"graph.external[{idx}].path must be a non-empty string")
            target = Path(raw_path)
            resolved_path = target if target.is_absolute() else (ir_path.parent / target)

            raw_sha = entry.get("sha256")
            if raw_sha is None:
                needs_smoke = True
                continue
            if not isinstance(raw_sha, str):
                raise IRValidationError(f"graph.external[{idx}].sha256 must be a string")
            if _is_placeholder_sha256(raw_sha):
                needs_smoke = True
                continue

            expected_sha = _validate_external_hex_sha(raw_sha, index=idx)
            if not resolved_path.exists():
                needs_smoke = True
                continue
            actual_sha = _sha256_file(resolved_path)
            if actual_sha != expected_sha:
                raise IRValidationError(
                    f"graph.external[{idx}] sha256 mismatch for "
                    f"{resolved_path}: expected {expected_sha}, got {actual_sha}"
                )
            verified_entries += 1

        external_verified = verified_entries == len(entries) and not needs_smoke
        if needs_smoke:
            synthetic_used = True
            target_nodes, target_chemical_edges, target_gap_edges = _resolve_target_counts(graph)
            synthetic_graph = _build_synthetic_graph(
                node_count=target_nodes,
                chemical_edge_count=target_chemical_edges,
                gap_edge_count=target_gap_edges,
            )
            graph["nodes"] = synthetic_graph["nodes"]
            graph["edges"] = synthetic_graph["edges"]

    graph_resolved = _summarize_resolved_graph(graph)
    return {
        "ir": resolved,
        "ir_sha256": ir_sha256,
        "provenance": {
            "syntheticUsed": synthetic_used,
            "externalVerified": external_verified,
        },
        "graphResolved": graph_resolved,
    }
