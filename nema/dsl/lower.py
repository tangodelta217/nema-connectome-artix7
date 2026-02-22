"""NEMA-DSL AST lowering to JSON-serializable IR-like dictionaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .parser import FixedLit, TimeLit


_TIME_FACTORS = {
    "ns": 1,
    "us": 1_000,
    "ms": 1_000_000,
    "s": 1_000_000_000,
}


def _lower_node(node: Any) -> Any:
    if isinstance(node, TimeLit):
        factor = _TIME_FACTORS[node.unit]
        nanoseconds = node.value * factor
        return {"nanoseconds": str(nanoseconds)}

    if isinstance(node, FixedLit):
        key = "unsignedRaw" if node.unsigned else "signedRaw"
        return {"typeId": node.type_id, key: str(node.raw)}

    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "__tag__":
                continue
            out[key] = _lower_node(value)
        return out

    if isinstance(node, list):
        return [_lower_node(item) for item in node]

    return node


def lower_to_ir(ast: object) -> dict:
    """Lower parsed AST object to JSON-serializable dictionary."""
    lowered = _lower_node(ast)
    if not isinstance(lowered, dict):
        raise ValueError("root AST must lower to an object")
    return lowered


def dump_json(obj: Any, path: Path) -> None:
    """Write deterministic JSON payload to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
