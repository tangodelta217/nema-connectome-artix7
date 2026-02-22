"""Deterministic CSR lowering for NEMA graphs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from fractions import Fraction
from typing import Any


class ChemicalModelId(IntEnum):
    CHEMICAL_CURRENT_V0 = 0


class GapModelId(IntEnum):
    GAP_CONDUCTANCE_V0 = 0


@dataclass(frozen=True)
class CanonicalNode:
    node_id: str
    original_index: int
    canonical_index: int
    canonical_order_id: int


@dataclass(frozen=True)
class ChemicalEdgeRecord:
    edge_id: str
    pre_idx: int
    post_idx: int
    weight_s8: int
    model_id_u8: int


@dataclass(frozen=True)
class GapEdgeRecord:
    edge_id: str
    a_idx: int
    b_idx: int
    conductance_u8: int
    model_id_u8: int


def _to_fraction(value: Any, *, field_name: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{field_name} must be int/float/string")
    return Fraction(str(value))


def _round_fraction_rne(value: Fraction) -> int:
    sign = -1 if value < 0 else 1
    num = abs(value.numerator)
    den = value.denominator
    q, r = divmod(num, den)
    two_r = 2 * r
    if two_r > den:
        q += 1
    elif two_r == den and (q & 1):
        q += 1
    return sign * q


def _clamp(value: int, lo: int, hi: int) -> int:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _quantize_weight_s8(raw_value: Any) -> int:
    # s8 Q0.7 representation.
    scaled = _to_fraction(raw_value, field_name="edge.weight") * 128
    return _clamp(_round_fraction_rne(scaled), -128, 127)


def _quantize_conductance_u8(raw_value: Any) -> int:
    # u8 Q0.8 representation.
    scaled = _to_fraction(raw_value, field_name="edge.conductance") * 256
    return _clamp(_round_fraction_rne(scaled), 0, 255)


def _u8(value: int) -> int:
    return value & 0xFF


def _u16(value: int) -> int:
    return value & 0xFFFF


def _extract_endpoint(edge: dict[str, Any], key_group: tuple[str, ...], edge_id: str, name: str) -> str:
    for key in key_group:
        if key in edge:
            value = edge[key]
            if not isinstance(value, str) or not value:
                raise ValueError(f"edge '{edge_id}' field '{key}' must be non-empty string")
            return value
    raise ValueError(f"edge '{edge_id}' missing {name} endpoint")


def _parse_chemical_model_id(raw_model: Any) -> int:
    if raw_model is None:
        return int(ChemicalModelId.CHEMICAL_CURRENT_V0)
    if isinstance(raw_model, int):
        return _u8(raw_model)
    if isinstance(raw_model, str):
        token = raw_model.strip().upper()
        mapping = {
            "CHEMICAL_CURRENT_V0": int(ChemicalModelId.CHEMICAL_CURRENT_V0),
        }
        if token in mapping:
            return mapping[token]
    raise ValueError(f"unsupported chemical modelId: {raw_model}")


def _parse_gap_model_id(raw_model: Any) -> int:
    if raw_model is None:
        return int(GapModelId.GAP_CONDUCTANCE_V0)
    if isinstance(raw_model, int):
        return _u8(raw_model)
    if isinstance(raw_model, str):
        token = raw_model.strip().upper()
        mapping = {
            "GAP_CONDUCTANCE_V0": int(GapModelId.GAP_CONDUCTANCE_V0),
        }
        if token in mapping:
            return mapping[token]
    raise ValueError(f"unsupported gap modelId: {raw_model}")


def _canonicalize_nodes(graph: dict[str, Any]) -> tuple[list[CanonicalNode], dict[str, int]]:
    raw_nodes = graph.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ValueError("graph.nodes must be an array")

    indexed: list[CanonicalNode] = []
    for pos, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            raise ValueError(f"graph.nodes[{pos}] must be an object")
        node_id = raw.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError(f"graph.nodes[{pos}].id must be a non-empty string")
        original_index = raw.get("index", pos)
        canonical_order_id = raw.get("canonicalOrderId", pos)
        if not isinstance(original_index, int):
            raise ValueError(f"graph.nodes[{pos}].index must be integer")
        if not isinstance(canonical_order_id, int):
            raise ValueError(f"graph.nodes[{pos}].canonicalOrderId must be integer")
        indexed.append(
            CanonicalNode(
                node_id=node_id,
                original_index=original_index,
                canonical_index=-1,
                canonical_order_id=canonical_order_id,
            )
        )

    sorted_nodes = sorted(
        indexed,
        key=lambda n: (n.canonical_order_id, n.original_index, n.node_id),
    )
    canonical_nodes: list[CanonicalNode] = []
    id_to_canonical: dict[str, int] = {}
    for idx, node in enumerate(sorted_nodes):
        canonical = CanonicalNode(
            node_id=node.node_id,
            original_index=node.original_index,
            canonical_index=idx,
            canonical_order_id=node.canonical_order_id,
        )
        canonical_nodes.append(canonical)
        id_to_canonical[canonical.node_id] = canonical.canonical_index
    return canonical_nodes, id_to_canonical


def _parse_chemical_edges(graph: dict[str, Any], id_to_canonical: dict[str, int]) -> list[ChemicalEdgeRecord]:
    raw_edges = graph.get("edges")
    if not isinstance(raw_edges, list):
        raise ValueError("graph.edges must be an array")

    chemicals: list[ChemicalEdgeRecord] = []
    for pos, raw in enumerate(raw_edges):
        if not isinstance(raw, dict):
            raise ValueError(f"graph.edges[{pos}] must be an object")
        kind = str(raw.get("kind", raw.get("type", ""))).upper()
        if kind != "CHEMICAL":
            continue
        edge_id = str(raw.get("id", f"chem_{pos}"))
        src = _extract_endpoint(raw, ("source", "src", "sourceNodeId", "from"), edge_id, "source")
        dst = _extract_endpoint(raw, ("target", "dst", "targetNodeId", "to"), edge_id, "target")
        if src not in id_to_canonical or dst not in id_to_canonical:
            raise ValueError(f"edge '{edge_id}' references unknown node")
        weight_source = raw.get("weight", raw.get("conductance", 0))
        weight_s8 = _quantize_weight_s8(weight_source)
        model_id_u8 = _parse_chemical_model_id(raw.get("modelId"))
        chemicals.append(
            ChemicalEdgeRecord(
                edge_id=edge_id,
                pre_idx=id_to_canonical[src],
                post_idx=id_to_canonical[dst],
                weight_s8=weight_s8,
                model_id_u8=model_id_u8,
            )
        )
    chemicals.sort(
        key=lambda e: (e.post_idx, e.pre_idx, e.model_id_u8, e.weight_s8, e.edge_id),
    )
    return chemicals


def _parse_gap_edges(graph: dict[str, Any], id_to_canonical: dict[str, int]) -> list[GapEdgeRecord]:
    raw_edges = graph.get("edges")
    if not isinstance(raw_edges, list):
        raise ValueError("graph.edges must be an array")

    unique_pairs: dict[tuple[int, int, int, int], GapEdgeRecord] = {}
    for pos, raw in enumerate(raw_edges):
        if not isinstance(raw, dict):
            raise ValueError(f"graph.edges[{pos}] must be an object")
        kind = str(raw.get("kind", raw.get("type", ""))).upper()
        if kind != "GAP":
            continue
        edge_id = str(raw.get("id", f"gap_{pos}"))
        src = _extract_endpoint(raw, ("source", "src", "sourceNodeId", "from"), edge_id, "source")
        dst = _extract_endpoint(raw, ("target", "dst", "targetNodeId", "to"), edge_id, "target")
        if src not in id_to_canonical or dst not in id_to_canonical:
            raise ValueError(f"edge '{edge_id}' references unknown node")
        a_idx, b_idx = sorted((id_to_canonical[src], id_to_canonical[dst]))
        conductance_u8 = _quantize_conductance_u8(raw.get("conductance", 0))
        model_id_u8 = _parse_gap_model_id(raw.get("modelId"))
        key = (a_idx, b_idx, conductance_u8, model_id_u8)
        if key not in unique_pairs or edge_id < unique_pairs[key].edge_id:
            unique_pairs[key] = GapEdgeRecord(
                edge_id=edge_id,
                a_idx=a_idx,
                b_idx=b_idx,
                conductance_u8=conductance_u8,
                model_id_u8=model_id_u8,
            )

    gaps = sorted(
        unique_pairs.values(),
        key=lambda e: (e.a_idx, e.b_idx, e.model_id_u8, e.conductance_u8, e.edge_id),
    )
    return gaps


def _build_chemical_csr(
    chemicals: list[ChemicalEdgeRecord],
    node_count: int,
) -> dict[str, list[int]]:
    row_ptr = [0] * (node_count + 1)
    for edge in chemicals:
        row_ptr[edge.post_idx + 1] += 1
    for idx in range(node_count):
        row_ptr[idx + 1] += row_ptr[idx]

    col_or_pre_u16 = [_u16(edge.pre_idx) for edge in chemicals]
    weight_s8 = [edge.weight_s8 for edge in chemicals]
    weight_u8 = [_u8(edge.weight_s8) for edge in chemicals]
    model_id_u8 = [_u8(edge.model_id_u8) for edge in chemicals]
    padding_u8 = [0] * len(chemicals)

    return {
        "row_ptr_u16": [_u16(v) for v in row_ptr],
        "col_or_pre_u16": col_or_pre_u16,
        "weight_s8": weight_s8,
        "weight_u8": weight_u8,
        "model_id_u8": model_id_u8,
        "padding_u8": padding_u8,
    }


def _build_gap_arrays(gaps: list[GapEdgeRecord]) -> dict[str, list[int]]:
    return {
        "a_idx_u16": [_u16(edge.a_idx) for edge in gaps],
        "b_idx_u16": [_u16(edge.b_idx) for edge in gaps],
        "conductance_u8": [_u8(edge.conductance_u8) for edge in gaps],
        "model_id_u8": [_u8(edge.model_id_u8) for edge in gaps],
        "padding_u8": [0] * len(gaps),
    }


def lower_ir_to_csr(ir: dict[str, Any]) -> dict[str, Any]:
    """Lower an IR graph to deterministic CSR + packed arrays."""
    graph = ir.get("graph")
    if not isinstance(graph, dict):
        raise ValueError("IR missing graph object")

    canonical_nodes, id_to_canonical = _canonicalize_nodes(graph)
    chemicals = _parse_chemical_edges(graph, id_to_canonical)
    gaps = _parse_gap_edges(graph, id_to_canonical)

    node_count = len(canonical_nodes)
    chemical_arrays = _build_chemical_csr(chemicals, node_count=node_count)
    gap_arrays = _build_gap_arrays(gaps)

    return {
        "ok": True,
        "loweringPolicy": "nema.lowering.csr.v0.1",
        "node_count": node_count,
        "chemical_edge_count": len(chemicals),
        "gap_edge_count": len(gaps),
        "canonical": {
            "node_id_by_canonical_idx": [node.node_id for node in canonical_nodes],
            "canonical_idx_by_node_id": {
                node.node_id: node.canonical_index for node in canonical_nodes
            },
            "original_index_by_node_id": {
                node.node_id: node.original_index for node in canonical_nodes
            },
        },
        "chemical_csr": chemical_arrays,
        "gap_records": gap_arrays,
    }
