"""Golden simulation for NEMA tick semantics (nema.tick.v0.1)."""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

from .fixed import FixedType


V_TYPE = FixedType.signed_type(int_bits=8, frac_bits=8, total_bits=16)
A_TYPE = FixedType.signed_type(int_bits=8, frac_bits=8, total_bits=16)
ACCUM_TYPE = FixedType.signed_type(int_bits=12, frac_bits=8, total_bits=20)


@dataclass(frozen=True)
class Node:
    node_id: str
    index: int
    canonical_order_id: int
    tau_m: Fraction
    v_init_raw: int


@dataclass(frozen=True)
class ChemicalEdge:
    edge_id: str
    source: str
    target: str
    weight: Fraction


@dataclass(frozen=True)
class GapPair:
    pair_key: tuple[str, str, Fraction]
    a: str
    b: str
    conductance: Fraction


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


def _as_fraction(value: Any, *, field_name: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{field_name} must be int/float/string")
    return Fraction(str(value))


def _saturating_add(raw_a: int, raw_b: int, ftype: FixedType) -> int:
    return ftype.saturate_raw(raw_a + raw_b)


def _quantize_weighted_raw(coeff: Fraction, input_raw_q8_8: int, out_type: FixedType) -> int:
    # input_raw_q8_8 represents input_real * 2^8. For out Q*.8:
    # out_raw = round(coeff * input_raw_q8_8), then saturate.
    rounded = _round_fraction_rne(coeff * input_raw_q8_8)
    return out_type.saturate_raw(rounded)


def _pack_v_array_le_i16(v_by_index: list[int]) -> bytes:
    return b"".join(struct.pack("<h", v) for v in v_by_index)


def _digest_v(v_by_index: list[int]) -> str:
    return hashlib.sha256(_pack_v_array_le_i16(v_by_index)).hexdigest()


def _parse_q_type_id(type_id: str) -> tuple[bool, int, int, int]:
    token = type_id.strip().upper()
    if token.startswith("UQ"):
        signed = False
        body = token[2:]
    elif token.startswith("Q"):
        signed = True
        body = token[1:]
    else:
        raise ValueError(f"unsupported fixed type ID: {type_id}")
    if "." not in body:
        raise ValueError(f"invalid fixed type ID: {type_id}")
    int_bits_s, frac_bits_s = body.split(".", 1)
    int_bits = int(int_bits_s)
    frac_bits = int(frac_bits_s)
    total_bits = int_bits + frac_bits
    return signed, int_bits, frac_bits, total_bits


def _load_tanh_lut(ir: dict[str, Any], *, base_dir: Path) -> list[int]:
    tanh_lut = ir.get("tanhLut")
    if not isinstance(tanh_lut, dict):
        raise ValueError("IR missing tanhLut object")

    input_type = tanh_lut.get("inputType", "Q8.8")
    output_type = tanh_lut.get("outputType", "Q8.8")
    in_signed, in_int, in_frac, in_total = _parse_q_type_id(str(input_type))
    out_signed, out_int, out_frac, out_total = _parse_q_type_id(str(output_type))

    if (in_signed, in_int, in_frac, in_total) != (True, 8, 8, 16):
        raise ValueError("sim currently supports tanh LUT input type Q8.8 only")
    if (out_signed, out_int, out_frac, out_total) != (True, 8, 8, 16):
        raise ValueError("sim currently supports tanh LUT output type Q8.8 only")

    artifact = tanh_lut.get("artifact")
    if not isinstance(artifact, str) or not artifact:
        raise ValueError("tanhLut.artifact must be a non-empty string")
    lut_path = Path(artifact)
    resolved = lut_path if lut_path.is_absolute() else (base_dir / lut_path)
    payload = resolved.read_bytes()
    if len(payload) % 2 != 0:
        raise ValueError(f"invalid tanh LUT byte length: {len(payload)}")
    values = [struct.unpack("<h", payload[i : i + 2])[0] for i in range(0, len(payload), 2)]
    if len(values) != (1 << 16):
        raise ValueError(f"expected 65536 LUT entries for Q8.8, got {len(values)}")
    return values


def _node_initial_v_raw(node: dict[str, Any]) -> int:
    for key in ("vInitRaw", "v0Raw", "vRaw", "initialVRaw"):
        if key in node:
            return V_TYPE.saturate_raw(int(node[key]))
    return 0


def _node_tau_m(node: dict[str, Any], graph: dict[str, Any]) -> Fraction:
    for key in ("tauM", "tau_m"):
        if key in node:
            tau = _as_fraction(node[key], field_name=f"node.{key}")
            break
    else:
        tau = _as_fraction(graph.get("tauM", graph.get("tau_m", 1.0)), field_name="graph.tauM")
    if tau <= 0:
        raise ValueError("tau_m must be > 0")
    return tau


def _graph_dt(graph: dict[str, Any]) -> Fraction:
    for key in ("dt",):
        if key in graph:
            dt = _as_fraction(graph[key], field_name=f"graph.{key}")
            break
    else:
        dt = Fraction(1, 1)
    if dt <= 0:
        raise ValueError("dt must be > 0")
    return dt


def _parse_graph(ir: dict[str, Any]) -> tuple[list[Node], list[ChemicalEdge], list[GapPair], Fraction]:
    graph = ir.get("graph")
    if not isinstance(graph, dict):
        raise ValueError("IR missing graph object")

    node_raw = graph.get("nodes")
    if not isinstance(node_raw, list):
        raise ValueError("graph.nodes must be an array")
    edge_raw = graph.get("edges")
    if not isinstance(edge_raw, list):
        raise ValueError("graph.edges must be an array")

    dt = _graph_dt(graph)

    nodes: list[Node] = []
    nodes_by_id: dict[str, Node] = {}
    for idx, entry in enumerate(node_raw):
        if not isinstance(entry, dict):
            raise ValueError(f"graph.nodes[{idx}] must be an object")
        node_id = entry["id"]
        index = int(entry["index"])
        canonical_order_id = int(entry["canonicalOrderId"])
        node = Node(
            node_id=str(node_id),
            index=index,
            canonical_order_id=canonical_order_id,
            tau_m=_node_tau_m(entry, graph),
            v_init_raw=_node_initial_v_raw(entry),
        )
        nodes.append(node)
        nodes_by_id[node.node_id] = node
    nodes.sort(key=lambda n: n.index)

    chemicals: list[ChemicalEdge] = []
    gap_pairs: dict[tuple[str, str, Fraction], GapPair] = {}

    for idx, edge in enumerate(edge_raw):
        if not isinstance(edge, dict):
            raise ValueError(f"graph.edges[{idx}] must be an object")
        edge_id = str(edge["id"])
        kind = str(edge.get("kind", edge.get("type"))).upper()
        src = str(edge.get("source", edge.get("src", edge.get("from"))))
        dst = str(edge.get("target", edge.get("dst", edge.get("to"))))
        if src not in nodes_by_id or dst not in nodes_by_id:
            raise ValueError(f"edge '{edge_id}' references unknown node")

        if kind == "CHEMICAL":
            weight_raw = edge.get("weight", edge.get("conductance", 0))
            weight = _as_fraction(weight_raw, field_name=f"edge[{edge_id}].weight")
            chemicals.append(ChemicalEdge(edge_id=edge_id, source=src, target=dst, weight=weight))
            continue

        if kind == "GAP":
            g = _as_fraction(edge.get("conductance", 0), field_name=f"edge[{edge_id}].conductance")
            a, b = sorted((src, dst))
            key = (a, b, g)
            if key not in gap_pairs:
                gap_pairs[key] = GapPair(pair_key=key, a=a, b=b, conductance=g)
            continue

    return nodes, chemicals, list(gap_pairs.values()), dt


def _tanh_lookup(v_raw_q8_8: int, lut_q8_8: list[int]) -> int:
    idx = (v_raw_q8_8 - V_TYPE.raw_min) & 0xFFFF
    return lut_q8_8[idx]


def simulate(
    ir: dict[str, Any],
    ticks: int,
    seed: int = 0,
    *,
    trace_path: Path | None = None,
    base_dir: Path = Path("."),
    eval_order: Literal["index", "reverse"] = "index",
) -> dict[str, Any]:
    """Run golden simulation with snapshot semantics.

    Returns per-tick digests and final state. If trace_path is provided,
    writes JSONL with one line per tick.
    """
    if ticks < 0:
        raise ValueError("ticks must be >= 0")

    nodes, chem_edges, gap_pairs, dt = _parse_graph(ir)
    lut_q8_8 = _load_tanh_lut(ir, base_dir=base_dir)

    by_id: dict[str, Node] = {node.node_id: node for node in nodes}
    v_state: dict[str, int] = {node.node_id: node.v_init_raw for node in nodes}
    tick_digests: list[str] = []

    order = list(nodes)
    if eval_order == "reverse":
        order = list(reversed(order))
    elif eval_order != "index":
        raise ValueError(f"unsupported eval_order: {eval_order}")

    trace_stream = None
    if trace_path is not None:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_stream = trace_path.open("w", encoding="utf-8")

    try:
        for tick in range(ticks):
            # 1) Snapshot.
            v_snapshot = {node_id: raw for node_id, raw in v_state.items()}
            # 2) Activation from snapshot.
            a_snapshot = {
                node_id: _tanh_lookup(v_raw_q8_8, lut_q8_8)
                for node_id, v_raw_q8_8 in v_snapshot.items()
            }

            i_chem = {node.node_id: 0 for node in nodes}
            i_gap = {node.node_id: 0 for node in nodes}

            # 3a) Chemical accumulation (msg quantized to Q12.8).
            for edge in chem_edges:
                msg = _quantize_weighted_raw(edge.weight, a_snapshot[edge.source], ACCUM_TYPE)
                i_chem[edge.target] = _saturating_add(i_chem[edge.target], msg, ACCUM_TYPE)

            # 3b) GAP accumulation once per symmetric pair.
            for pair in gap_pairs:
                va = v_snapshot[pair.a]
                vb = v_snapshot[pair.b]
                msg = _quantize_weighted_raw(pair.conductance, vb - va, ACCUM_TYPE)
                i_gap[pair.a] = _saturating_add(i_gap[pair.a], msg, ACCUM_TYPE)
                i_gap[pair.b] = _saturating_add(i_gap[pair.b], -msg, ACCUM_TYPE)

            # 4) Euler update using snapshot currents.
            next_v = dict(v_state)
            for node in order:
                total_i = _saturating_add(i_chem[node.node_id], i_gap[node.node_id], ACCUM_TYPE)
                inv_tau = dt / node.tau_m
                delta_v_raw = _quantize_weighted_raw(inv_tau, total_i, V_TYPE)
                next_v[node.node_id] = V_TYPE.saturate_raw(v_snapshot[node.node_id] + delta_v_raw)

            v_state = next_v
            v_by_index = [v_state[node.node_id] for node in nodes]
            digest = _digest_v(v_by_index)
            tick_digests.append(digest)

            if trace_stream is not None:
                trace_stream.write(
                    json.dumps(
                        {
                            "tick": tick,
                            "digestSha256": digest,
                            "vRawByIndex": v_by_index,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
    finally:
        if trace_stream is not None:
            trace_stream.close()

    return {
        "ok": True,
        "policy": "nema.tick.v0.1",
        "seed": seed,
        "ticks": ticks,
        "tickDigestsSha256": tick_digests,
        "finalVRawByIndex": [v_state[node.node_id] for node in nodes],
    }
