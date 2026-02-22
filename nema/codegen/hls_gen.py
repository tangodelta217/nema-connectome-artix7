"""HLS/C++ reference codegen for NEMA models."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..ir_validate import load_ir


ACCUM_MIN = -(1 << 19)
ACCUM_MAX = (1 << 19) - 1
V_MIN = -(1 << 15)
V_MAX = (1 << 15) - 1


@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    idx: int
    v_init_raw: int
    inv_tau_num: int
    inv_tau_den: int


@dataclass(frozen=True)
class ChemicalEdgeSpec:
    edge_id: str
    pre_idx: int
    post_idx: int
    weight_num: int
    weight_den: int
    model_id: int


@dataclass(frozen=True)
class GapEdgeSpec:
    edge_id: str
    a_idx: int
    b_idx: int
    conductance_num: int
    conductance_den: int
    model_id: int


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    lut_path: Path
    nodes: list[NodeSpec]
    chemicals: list[ChemicalEdgeSpec]
    gaps: list[GapEdgeSpec]


def _to_fraction(value: Any, *, field_name: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{field_name} must be int/float/string")
    return Fraction(str(value))


def _sanitize_model_id(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_")
    return cleaned or "model"


def _extract_model_id(ir: dict[str, Any]) -> str:
    if "modelId" in ir and ir["modelId"] is not None:
        return _sanitize_model_id(str(ir["modelId"]))
    if "kernelId" in ir and ir["kernelId"] is not None:
        return _sanitize_model_id(str(ir["kernelId"]))
    if "name" in ir and ir["name"] is not None:
        return _sanitize_model_id(str(ir["name"]))
    return "model"


def _extract_endpoint(edge: dict[str, Any], keys: tuple[str, ...], edge_id: str, label: str) -> str:
    for key in keys:
        if key in edge:
            value = edge[key]
            if not isinstance(value, str) or not value:
                raise ValueError(f"edge '{edge_id}' {key} must be non-empty string")
            return value
    raise ValueError(f"edge '{edge_id}' missing {label} endpoint")


def _node_v_init_raw(node: dict[str, Any]) -> int:
    for key in ("vInitRaw", "v0Raw", "vRaw", "initialVRaw"):
        if key in node:
            value = int(node[key])
            if value < V_MIN:
                return V_MIN
            if value > V_MAX:
                return V_MAX
            return value
    return 0


def _node_tau(node: dict[str, Any], graph: dict[str, Any]) -> Fraction:
    for key in ("tauM", "tau_m"):
        if key in node:
            tau = _to_fraction(node[key], field_name=f"node.{key}")
            break
    else:
        tau = _to_fraction(graph.get("tauM", graph.get("tau_m", 1.0)), field_name="graph.tauM")
    if tau <= 0:
        raise ValueError("tau_m must be > 0")
    return tau


def _graph_dt(graph: dict[str, Any]) -> Fraction:
    if "dt" not in graph:
        return Fraction(1, 1)
    dt = _to_fraction(graph["dt"], field_name="graph.dt")
    if dt <= 0:
        raise ValueError("dt must be > 0")
    return dt


def _parse_chemical_model_id(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value & 0xFF
    if isinstance(value, str):
        token = value.strip().upper()
        if token == "CHEMICAL_CURRENT_V0":
            return 0
    raise ValueError(f"unsupported chemical modelId: {value}")


def _parse_gap_model_id(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value & 0xFF
    if isinstance(value, str):
        token = value.strip().upper()
        if token == "GAP_CONDUCTANCE_V0":
            return 0
    raise ValueError(f"unsupported gap modelId: {value}")


def _parse_spec(ir: dict[str, Any], *, base_dir: Path) -> ModelSpec:
    graph = ir.get("graph")
    if not isinstance(graph, dict):
        raise ValueError("IR missing graph object")

    node_raw = graph.get("nodes")
    edge_raw = graph.get("edges")
    if not isinstance(node_raw, list):
        raise ValueError("graph.nodes must be an array")
    if not isinstance(edge_raw, list):
        raise ValueError("graph.edges must be an array")

    dt = _graph_dt(graph)

    sorted_nodes = sorted(
        node_raw,
        key=lambda n: (int(n.get("index", 0)), str(n.get("id", ""))),
    )
    node_specs: list[NodeSpec] = []
    node_idx_by_id: dict[str, int] = {}
    for idx, raw in enumerate(sorted_nodes):
        if not isinstance(raw, dict):
            raise ValueError("graph.nodes entries must be objects")
        node_id = raw.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("graph.nodes[].id must be non-empty string")
        tau = _node_tau(raw, graph)
        inv_tau = dt / tau
        node = NodeSpec(
            node_id=node_id,
            idx=idx,
            v_init_raw=_node_v_init_raw(raw),
            inv_tau_num=inv_tau.numerator,
            inv_tau_den=inv_tau.denominator,
        )
        node_specs.append(node)
        node_idx_by_id[node.node_id] = idx

    chemical_specs: list[ChemicalEdgeSpec] = []
    gap_specs_by_key: dict[tuple[int, int, int, int, int], GapEdgeSpec] = {}
    for pos, raw in enumerate(edge_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"graph.edges[{pos}] must be object")
        edge_id = str(raw.get("id", f"e{pos}"))
        kind = str(raw.get("kind", raw.get("type", ""))).upper()
        src = _extract_endpoint(raw, ("source", "src", "sourceNodeId", "from"), edge_id, "source")
        dst = _extract_endpoint(raw, ("target", "dst", "targetNodeId", "to"), edge_id, "target")
        if src not in node_idx_by_id or dst not in node_idx_by_id:
            raise ValueError(f"edge '{edge_id}' references unknown node")

        if kind == "CHEMICAL":
            w = _to_fraction(raw.get("weight", raw.get("conductance", 0.0)), field_name=f"edge[{edge_id}].weight")
            chemical_specs.append(
                ChemicalEdgeSpec(
                    edge_id=edge_id,
                    pre_idx=node_idx_by_id[src],
                    post_idx=node_idx_by_id[dst],
                    weight_num=w.numerator,
                    weight_den=w.denominator,
                    model_id=_parse_chemical_model_id(raw.get("modelId")),
                )
            )
        elif kind == "GAP":
            g = _to_fraction(raw.get("conductance", 0.0), field_name=f"edge[{edge_id}].conductance")
            a_idx, b_idx = sorted((node_idx_by_id[src], node_idx_by_id[dst]))
            model_id = _parse_gap_model_id(raw.get("modelId"))
            key = (a_idx, b_idx, g.numerator, g.denominator, model_id)
            if key not in gap_specs_by_key or edge_id < gap_specs_by_key[key].edge_id:
                gap_specs_by_key[key] = GapEdgeSpec(
                    edge_id=edge_id,
                    a_idx=a_idx,
                    b_idx=b_idx,
                    conductance_num=g.numerator,
                    conductance_den=g.denominator,
                    model_id=model_id,
                )

    # Deterministic postsynaptic ordering for CSR traversal.
    chemical_specs.sort(
        key=lambda e: (e.post_idx, e.pre_idx, e.model_id, e.weight_num, e.weight_den, e.edge_id),
    )
    gap_specs = sorted(
        gap_specs_by_key.values(),
        key=lambda e: (e.a_idx, e.b_idx, e.model_id, e.conductance_num, e.conductance_den, e.edge_id),
    )

    tanh_lut = ir.get("tanhLut")
    if not isinstance(tanh_lut, dict):
        raise ValueError("IR missing tanhLut")
    artifact = tanh_lut.get("artifact")
    if not isinstance(artifact, str) or not artifact:
        raise ValueError("tanhLut.artifact must be non-empty string")
    lut_path = Path(artifact)
    lut_path = lut_path if lut_path.is_absolute() else (base_dir / lut_path)

    return ModelSpec(
        model_id=_extract_model_id(ir),
        lut_path=lut_path.resolve(),
        nodes=node_specs,
        chemicals=chemical_specs,
        gaps=gap_specs,
    )


def _format_c_array(values: list[int], *, default_value: int = 0) -> str:
    if not values:
        return str(default_value)
    return ", ".join(str(v) for v in values)


def _build_row_ptr(node_count: int, chemicals: list[ChemicalEdgeSpec]) -> list[int]:
    row_ptr = [0] * (node_count + 1)
    for edge in chemicals:
        row_ptr[edge.post_idx + 1] += 1
    for i in range(node_count):
        row_ptr[i + 1] += row_ptr[i]
    return row_ptr


def _emit_kernel_header(spec: ModelSpec, path: Path) -> None:
    node_count = len(spec.nodes)
    chem_count = len(spec.chemicals)
    gap_count = len(spec.gaps)
    row_ptr = _build_row_ptr(node_count, spec.chemicals)
    v_init = [n.v_init_raw for n in spec.nodes]
    inv_tau_num = [n.inv_tau_num for n in spec.nodes]
    inv_tau_den = [n.inv_tau_den for n in spec.nodes]
    chem_pre = [e.pre_idx for e in spec.chemicals]
    chem_weight_num = [e.weight_num for e in spec.chemicals]
    chem_weight_den = [e.weight_den for e in spec.chemicals]
    chem_model = [e.model_id for e in spec.chemicals]
    gap_a = [e.a_idx for e in spec.gaps]
    gap_b = [e.b_idx for e in spec.gaps]
    gap_num = [e.conductance_num for e in spec.gaps]
    gap_den = [e.conductance_den for e in spec.gaps]
    gap_model = [e.model_id for e in spec.gaps]

    contents = f"""#pragma once
#include <cstdint>

namespace nema_model {{
static constexpr int NODE_COUNT = {node_count};
static constexpr int NODE_STORAGE = NODE_COUNT > 0 ? NODE_COUNT : 1;
static constexpr int CHEM_EDGE_COUNT = {chem_count};
static constexpr int CHEM_EDGE_STORAGE = CHEM_EDGE_COUNT > 0 ? CHEM_EDGE_COUNT : 1;
static constexpr int GAP_EDGE_COUNT = {gap_count};
static constexpr int GAP_EDGE_STORAGE = GAP_EDGE_COUNT > 0 ? GAP_EDGE_COUNT : 1;
static constexpr int LUT_SIZE = 65536;
static constexpr int32_t ACCUM_MIN = {ACCUM_MIN};
static constexpr int32_t ACCUM_MAX = {ACCUM_MAX};

static constexpr int16_t V_INIT[NODE_STORAGE] = {{{_format_c_array(v_init)}}};
static constexpr int64_t INV_TAU_NUM[NODE_STORAGE] = {{{_format_c_array(inv_tau_num)}}};
static constexpr int64_t INV_TAU_DEN[NODE_STORAGE] = {{{_format_c_array(inv_tau_den, default_value=1)}}};

static constexpr uint16_t CHEM_ROW_PTR[NODE_COUNT + 1] = {{{_format_c_array(row_ptr)}}};
static constexpr uint16_t CHEM_PRE_IDX[CHEM_EDGE_STORAGE] = {{{_format_c_array(chem_pre)}}};
static constexpr int64_t CHEM_WEIGHT_NUM[CHEM_EDGE_STORAGE] = {{{_format_c_array(chem_weight_num)}}};
static constexpr int64_t CHEM_WEIGHT_DEN[CHEM_EDGE_STORAGE] = {{{_format_c_array(chem_weight_den, default_value=1)}}};
static constexpr uint8_t CHEM_MODEL_ID[CHEM_EDGE_STORAGE] = {{{_format_c_array(chem_model)}}};
static constexpr uint8_t CHEM_PADDING[CHEM_EDGE_STORAGE] = {{0}};

static constexpr uint16_t GAP_A_IDX[GAP_EDGE_STORAGE] = {{{_format_c_array(gap_a)}}};
static constexpr uint16_t GAP_B_IDX[GAP_EDGE_STORAGE] = {{{_format_c_array(gap_b)}}};
static constexpr int64_t GAP_CONDUCTANCE_NUM[GAP_EDGE_STORAGE] = {{{_format_c_array(gap_num)}}};
static constexpr int64_t GAP_CONDUCTANCE_DEN[GAP_EDGE_STORAGE] = {{{_format_c_array(gap_den, default_value=1)}}};
static constexpr uint8_t GAP_MODEL_ID[GAP_EDGE_STORAGE] = {{{_format_c_array(gap_model)}}};
static constexpr uint8_t GAP_PADDING[GAP_EDGE_STORAGE] = {{0}};
}}  // namespace nema_model

void nema_kernel(
    const int16_t v_in[nema_model::NODE_STORAGE],
    const int16_t tanh_lut[nema_model::LUT_SIZE],
    int16_t v_out[nema_model::NODE_STORAGE]);
"""
    path.write_text(contents, encoding="utf-8")


def _emit_kernel_cpp(path: Path) -> None:
    contents = """#include "nema_kernel.h"

#include <cstdint>

namespace {
inline uint64_t uabs64(int64_t value) {
    return value < 0 ? static_cast<uint64_t>(-(value + 1)) + 1ULL : static_cast<uint64_t>(value);
}

inline int64_t round_div_rne_i64(int64_t numerator, int64_t denominator) {
    if (denominator <= 0) {
        return 0;
    }
    const bool negative = numerator < 0;
    const uint64_t den = static_cast<uint64_t>(denominator);
    const uint64_t mag = uabs64(numerator);
    uint64_t q = mag / den;
    const uint64_t r = mag % den;
    const uint64_t twice_r = r * 2ULL;
    if (twice_r > den || (twice_r == den && (q & 1ULL))) {
        ++q;
    }
    return negative ? -static_cast<int64_t>(q) : static_cast<int64_t>(q);
}

inline int32_t sat_accum_i64(int64_t value) {
    if (value > nema_model::ACCUM_MAX) {
        return nema_model::ACCUM_MAX;
    }
    if (value < nema_model::ACCUM_MIN) {
        return nema_model::ACCUM_MIN;
    }
    return static_cast<int32_t>(value);
}

inline int16_t sat_i16_i64(int64_t value) {
    if (value > 32767) {
        return 32767;
    }
    if (value < -32768) {
        return -32768;
    }
    return static_cast<int16_t>(value);
}

inline int32_t sat_add_accum(int32_t a, int32_t b) {
    return sat_accum_i64(static_cast<int64_t>(a) + static_cast<int64_t>(b));
}

inline int32_t quantize_to_accum(int64_t coeff_num, int64_t coeff_den, int32_t input_raw_q8_8) {
    const int64_t prod = coeff_num * static_cast<int64_t>(input_raw_q8_8);
    return sat_accum_i64(round_div_rne_i64(prod, coeff_den));
}

inline int16_t quantize_to_v(int64_t coeff_num, int64_t coeff_den, int32_t input_raw_q8_8) {
    const int64_t prod = coeff_num * static_cast<int64_t>(input_raw_q8_8);
    return sat_i16_i64(round_div_rne_i64(prod, coeff_den));
}
}  // namespace

void nema_kernel(
    const int16_t v_in[nema_model::NODE_STORAGE],
    const int16_t tanh_lut[nema_model::LUT_SIZE],
    int16_t v_out[nema_model::NODE_STORAGE]) {
    int16_t v_snapshot[nema_model::NODE_STORAGE];
    int16_t a_snapshot[nema_model::NODE_STORAGE];
    int32_t i_chem[nema_model::NODE_STORAGE];
    int32_t i_gap[nema_model::NODE_STORAGE];

    for (int i = 0; i < nema_model::NODE_COUNT; ++i) {
        v_snapshot[i] = v_in[i];
        i_chem[i] = 0;
        i_gap[i] = 0;
    }

    for (int i = 0; i < nema_model::NODE_COUNT; ++i) {
        const uint16_t lut_idx =
            static_cast<uint16_t>(static_cast<int32_t>(v_snapshot[i]) - static_cast<int32_t>(-32768));
        a_snapshot[i] = tanh_lut[lut_idx];
    }

    for (int post = 0; post < nema_model::NODE_COUNT; ++post) {
        const int begin = static_cast<int>(nema_model::CHEM_ROW_PTR[post]);
        const int end = static_cast<int>(nema_model::CHEM_ROW_PTR[post + 1]);
        for (int edge = begin; edge < end; ++edge) {
            const int pre = static_cast<int>(nema_model::CHEM_PRE_IDX[edge]);
            const int32_t msg = quantize_to_accum(
                nema_model::CHEM_WEIGHT_NUM[edge],
                nema_model::CHEM_WEIGHT_DEN[edge],
                static_cast<int32_t>(a_snapshot[pre]));
            i_chem[post] = sat_add_accum(i_chem[post], msg);
        }
    }

    for (int edge = 0; edge < nema_model::GAP_EDGE_COUNT; ++edge) {
        const int a = static_cast<int>(nema_model::GAP_A_IDX[edge]);
        const int b = static_cast<int>(nema_model::GAP_B_IDX[edge]);
        const int32_t dv = static_cast<int32_t>(v_snapshot[b]) - static_cast<int32_t>(v_snapshot[a]);
        const int32_t msg = quantize_to_accum(
            nema_model::GAP_CONDUCTANCE_NUM[edge],
            nema_model::GAP_CONDUCTANCE_DEN[edge],
            dv);
        i_gap[a] = sat_add_accum(i_gap[a], msg);
        i_gap[b] = sat_add_accum(i_gap[b], -msg);
    }

    for (int i = 0; i < nema_model::NODE_COUNT; ++i) {
        const int32_t total_i = sat_add_accum(i_chem[i], i_gap[i]);
        const int16_t delta_v = quantize_to_v(
            nema_model::INV_TAU_NUM[i],
            nema_model::INV_TAU_DEN[i],
            total_i);
        v_out[i] = sat_i16_i64(static_cast<int64_t>(v_snapshot[i]) + static_cast<int64_t>(delta_v));
    }
}
"""
    path.write_text(contents, encoding="utf-8")


def _emit_cpp_ref_main(spec: ModelSpec, path: Path) -> None:
    lut_literal = json.dumps(str(spec.lut_path))
    contents = f"""#include "../hls/nema_kernel.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

namespace {{
constexpr const char* kLutPath = {lut_literal};

inline uint32_t rotr(uint32_t x, uint32_t n) {{
    return (x >> n) | (x << (32U - n));
}}

void sha256_transform(const uint8_t block[64], uint32_t state[8]) {{
    static constexpr uint32_t k[64] = {{
        0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U, 0x3956c25bU, 0x59f111f1U,
        0x923f82a4U, 0xab1c5ed5U, 0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
        0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U, 0xe49b69c1U, 0xefbe4786U,
        0x0fc19dc6U, 0x240ca1ccU, 0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
        0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U, 0xc6e00bf3U, 0xd5a79147U,
        0x06ca6351U, 0x14292967U, 0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
        0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U, 0xa2bfe8a1U, 0xa81a664bU,
        0xc24b8b70U, 0xc76c51a3U, 0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
        0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U, 0x391c0cb3U, 0x4ed8aa4aU,
        0x5b9cca4fU, 0x682e6ff3U, 0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
        0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U,
    }};

    uint32_t w[64] = {{0}};
    for (int i = 0; i < 16; ++i) {{
        w[i] = (static_cast<uint32_t>(block[i * 4 + 0]) << 24U) |
               (static_cast<uint32_t>(block[i * 4 + 1]) << 16U) |
               (static_cast<uint32_t>(block[i * 4 + 2]) << 8U) |
               (static_cast<uint32_t>(block[i * 4 + 3]));
    }}
    for (int i = 16; i < 64; ++i) {{
        const uint32_t s0 = rotr(w[i - 15], 7U) ^ rotr(w[i - 15], 18U) ^ (w[i - 15] >> 3U);
        const uint32_t s1 = rotr(w[i - 2], 17U) ^ rotr(w[i - 2], 19U) ^ (w[i - 2] >> 10U);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }}

    uint32_t a = state[0];
    uint32_t b = state[1];
    uint32_t c = state[2];
    uint32_t d = state[3];
    uint32_t e = state[4];
    uint32_t f = state[5];
    uint32_t g = state[6];
    uint32_t h = state[7];
    for (int i = 0; i < 64; ++i) {{
        const uint32_t s1 = rotr(e, 6U) ^ rotr(e, 11U) ^ rotr(e, 25U);
        const uint32_t ch = (e & f) ^ ((~e) & g);
        const uint32_t temp1 = h + s1 + ch + k[i] + w[i];
        const uint32_t s0 = rotr(a, 2U) ^ rotr(a, 13U) ^ rotr(a, 22U);
        const uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        const uint32_t temp2 = s0 + maj;
        h = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }}

    state[0] += a;
    state[1] += b;
    state[2] += c;
    state[3] += d;
    state[4] += e;
    state[5] += f;
    state[6] += g;
    state[7] += h;
}}

std::string sha256_hex(const uint8_t* data, std::size_t len) {{
    uint32_t state[8] = {{
        0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
        0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U,
    }};

    std::size_t full_blocks = len / 64U;
    for (std::size_t i = 0; i < full_blocks; ++i) {{
        sha256_transform(data + i * 64U, state);
    }}

    uint8_t tail[128] = {{0}};
    const std::size_t rem = len % 64U;
    for (std::size_t i = 0; i < rem; ++i) {{
        tail[i] = data[full_blocks * 64U + i];
    }}
    tail[rem] = 0x80U;

    const uint64_t bit_len = static_cast<uint64_t>(len) * 8ULL;
    const bool one_block = rem < 56U;
    const std::size_t len_offset = one_block ? 56U : 120U;
    tail[len_offset + 0] = static_cast<uint8_t>((bit_len >> 56U) & 0xFFU);
    tail[len_offset + 1] = static_cast<uint8_t>((bit_len >> 48U) & 0xFFU);
    tail[len_offset + 2] = static_cast<uint8_t>((bit_len >> 40U) & 0xFFU);
    tail[len_offset + 3] = static_cast<uint8_t>((bit_len >> 32U) & 0xFFU);
    tail[len_offset + 4] = static_cast<uint8_t>((bit_len >> 24U) & 0xFFU);
    tail[len_offset + 5] = static_cast<uint8_t>((bit_len >> 16U) & 0xFFU);
    tail[len_offset + 6] = static_cast<uint8_t>((bit_len >> 8U) & 0xFFU);
    tail[len_offset + 7] = static_cast<uint8_t>((bit_len >> 0U) & 0xFFU);

    sha256_transform(tail, state);
    if (!one_block) {{
        sha256_transform(tail + 64U, state);
    }}

    std::ostringstream oss;
    oss << std::hex << std::setfill('0');
    for (int i = 0; i < 8; ++i) {{
        oss << std::setw(8) << state[i];
    }}
    return oss.str();
}}

bool load_lut(std::array<int16_t, nema_model::LUT_SIZE>& lut) {{
    std::ifstream in(kLutPath, std::ios::binary);
    if (!in) {{
        return false;
    }}
    std::array<uint8_t, nema_model::LUT_SIZE * 2> raw{{}};
    in.read(reinterpret_cast<char*>(raw.data()), static_cast<std::streamsize>(raw.size()));
    if (in.gcount() != static_cast<std::streamsize>(raw.size())) {{
        return false;
    }}
    for (std::size_t i = 0; i < lut.size(); ++i) {{
        const uint16_t lo = static_cast<uint16_t>(raw[i * 2 + 0]);
        const uint16_t hi = static_cast<uint16_t>(raw[i * 2 + 1]) << 8U;
        lut[i] = static_cast<int16_t>(lo | hi);
    }}
    return true;
}}
}}  // namespace

int main(int argc, char** argv) {{
    int ticks = 8;
    if (argc > 1) {{
        ticks = std::atoi(argv[1]);
    }}
    if (ticks < 0) {{
        std::cerr << "ticks must be >= 0\\n";
        return 2;
    }}

    std::array<int16_t, nema_model::LUT_SIZE> lut{{}};
    if (!load_lut(lut)) {{
        std::cerr << "failed to load LUT from " << kLutPath << "\\n";
        return 3;
    }}

    std::array<int16_t, nema_model::NODE_STORAGE> v_cur{{}};
    std::array<int16_t, nema_model::NODE_STORAGE> v_next{{}};
    for (int i = 0; i < nema_model::NODE_COUNT; ++i) {{
        v_cur[static_cast<std::size_t>(i)] = nema_model::V_INIT[static_cast<std::size_t>(i)];
    }}

    std::array<uint8_t, nema_model::NODE_STORAGE * 2> packed{{}};
    std::cout << "{{\\\"ticks\\\":" << ticks << ",\\\"tickDigestsSha256\\\":[";
    for (int tick = 0; tick < ticks; ++tick) {{
        nema_kernel(v_cur.data(), lut.data(), v_next.data());
        v_cur = v_next;

        for (int i = 0; i < nema_model::NODE_COUNT; ++i) {{
            const uint16_t bits = static_cast<uint16_t>(v_cur[static_cast<std::size_t>(i)]);
            packed[static_cast<std::size_t>(i * 2 + 0)] = static_cast<uint8_t>(bits & 0xFFU);
            packed[static_cast<std::size_t>(i * 2 + 1)] = static_cast<uint8_t>((bits >> 8U) & 0xFFU);
        }}
        const std::string digest = sha256_hex(
            packed.data(),
            static_cast<std::size_t>(nema_model::NODE_COUNT) * 2U);
        if (tick > 0) {{
            std::cout << ",";
        }}
        std::cout << "\\\"" << digest << "\\\"";
    }}
    std::cout << "]}}\\n";
    return 0;
}}
"""
    path.write_text(contents, encoding="utf-8")


def generate_hls_project(
    ir_path: Path,
    outdir: Path,
    *,
    ir_payload_override: dict[str, Any] | None = None,
    ir_sha256_override: str | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """Generate HLS kernel + C++ reference harness for a model IR."""
    if ir_payload_override is None:
        ir_payload, ir_sha256 = load_ir(ir_path)
    else:
        ir_payload = ir_payload_override
        ir_sha256 = ir_sha256_override if ir_sha256_override is not None else "override"

    parse_base_dir = base_dir if base_dir is not None else ir_path.parent
    spec = _parse_spec(ir_payload, base_dir=parse_base_dir)

    model_root = outdir / spec.model_id
    hls_dir = model_root / "hls"
    cpp_ref_dir = model_root / "cpp_ref"
    hls_dir.mkdir(parents=True, exist_ok=True)
    cpp_ref_dir.mkdir(parents=True, exist_ok=True)

    h_path = hls_dir / "nema_kernel.h"
    cpp_path = hls_dir / "nema_kernel.cpp"
    main_path = cpp_ref_dir / "main.cpp"
    _emit_kernel_header(spec, h_path)
    _emit_kernel_cpp(cpp_path)
    _emit_cpp_ref_main(spec, main_path)

    return {
        "ok": True,
        "policy": "nema.codegen.hls.v0.1",
        "ir_sha256": ir_sha256,
        "model_id": spec.model_id,
        "model_root": str(model_root),
        "hls_header": str(h_path),
        "hls_cpp": str(cpp_path),
        "cpp_ref_main": str(main_path),
        "node_count": len(spec.nodes),
        "chemical_edge_count": len(spec.chemicals),
        "gap_edge_count": len(spec.gaps),
        "lut_path": str(spec.lut_path),
    }
