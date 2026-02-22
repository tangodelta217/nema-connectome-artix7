"""Canonical normalization utilities for NEMA IR JSON payloads."""

from __future__ import annotations

import json
from typing import Any


def _sort_nodes(nodes: list[Any]) -> list[Any]:
    def key(item: Any) -> tuple[int, int, int, str]:
        if not isinstance(item, dict):
            return (1, 0, 0, "")
        canonical = item.get("canonicalOrderId")
        index = item.get("index")
        node_id = item.get("id")
        canonical_key = canonical if isinstance(canonical, int) else (index if isinstance(index, int) else 0)
        index_key = index if isinstance(index, int) else 0
        id_key = node_id if isinstance(node_id, str) else ""
        return (0, canonical_key, index_key, id_key)

    return sorted(nodes, key=key)


def _sort_edges(edges: list[Any]) -> list[Any]:
    def key(item: Any) -> tuple[int, str, str, str, str]:
        if not isinstance(item, dict):
            return (1, "", "", "", "")
        edge_id = item.get("id")
        kind = item.get("kind", item.get("type"))
        source = item.get("source", item.get("src", item.get("from", "")))
        target = item.get("target", item.get("dst", item.get("to", "")))
        return (
            0,
            str(edge_id) if edge_id is not None else "",
            str(kind) if kind is not None else "",
            str(source),
            str(target),
        )

    return sorted(edges, key=key)


def canonicalize_ir(value: Any, *, path: tuple[str, ...] = ()) -> Any:
    """Recursively canonicalize IR structures for deterministic comparison/output."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value.keys()):
            out[key] = canonicalize_ir(value[key], path=(*path, key))
        return out

    if isinstance(value, list):
        normalized = [canonicalize_ir(item, path=path) for item in value]
        if path[-2:] == ("graph", "nodes"):
            return _sort_nodes(normalized)
        if path[-2:] == ("graph", "edges"):
            return _sort_edges(normalized)
        return normalized

    return value


def canonical_json(value: Any) -> str:
    """Serialize JSON payload with canonical normalization and formatting."""
    normalized = canonicalize_ir(value)
    return json.dumps(normalized, indent=2, sort_keys=True) + "\n"
