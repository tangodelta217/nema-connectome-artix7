"""Lower a typechecked NEMA DSL program to canonical IR JSON dict."""

from __future__ import annotations

from typing import Any

from .parse_toml import DSLProgram
from .typecheck import CheckedProgram, typecheck_program


def _emit_graph(checked: CheckedProgram) -> dict[str, Any]:
    graph: dict[str, Any] = {"nodes": [], "edges": []}
    if checked.graph.dt is not None:
        graph["dt"] = checked.graph.dt
    if checked.graph.tau_m is not None:
        graph["tauM"] = checked.graph.tau_m

    if checked.graph.stats is not None:
        graph["stats"] = {
            "nodeCount": checked.graph.stats.node_count,
            "chemicalEdgeCount": checked.graph.stats.chemical_edge_count,
            "gapEdgeCount": checked.graph.stats.gap_edge_count,
        }

    if checked.graph.external is not None:
        graph["external"] = {
            "uri": checked.graph.external.uri,
            "path": checked.graph.external.path,
            "subgraphId": checked.graph.external.subgraph_id,
            "formatId": checked.graph.external.format_id,
            "sha256": checked.graph.external.sha256,
        }

    sorted_nodes = sorted(
        checked.graph.nodes,
        key=lambda node: (node.index, node.node_id),
    )
    for node in sorted_nodes:
        node_obj: dict[str, Any] = {
            "id": node.node_id,
            "index": node.index,
            "canonicalOrderId": node.canonical_order_id,
        }
        if node.v_init_raw is not None:
            node_obj["vInitRaw"] = node.v_init_raw
        if node.tau_m is not None:
            node_obj["tauM"] = node.tau_m
        graph["nodes"].append(node_obj)

    sorted_edges = sorted(
        checked.graph.edges,
        key=lambda edge: (edge.edge_id, edge.kind, edge.source, edge.target),
    )
    for edge in sorted_edges:
        edge_obj: dict[str, Any] = {
            "id": edge.edge_id,
            "kind": edge.kind,
            "source": edge.source,
            "target": edge.target,
            "directed": edge.directed,
            "conductance": edge.conductance,
        }
        if edge.weight is not None:
            edge_obj["weight"] = edge.weight
        if edge.model_id is not None:
            edge_obj["modelId"] = edge.model_id
        graph["edges"].append(edge_obj)

    return graph


def lower_checked_program_to_ir(checked: CheckedProgram) -> dict[str, Any]:
    """Lower an already typechecked DSL program to canonical IR JSON."""
    ir: dict[str, Any] = {
        "name": checked.module.name,
        "constraints": {
            "allowedSpdx": list(checked.module.allowed_spdx),
        },
        "license": {
            "spdxId": checked.module.license_spdx,
        },
        "graph": _emit_graph(checked),
        "tanhLut": {
            "policy": checked.compile.tanh_lut_policy,
            "artifact": checked.compile.tanh_lut_artifact,
            "inputType": checked.qformats.lut_input,
            "outputType": checked.qformats.lut_output,
            "checksumSha256": checked.compile.tanh_lut_checksum_sha256,
        },
    }

    if checked.module.model_id is not None:
        ir["modelId"] = checked.module.model_id
    if checked.module.kernel_id is not None:
        ir["kernelId"] = checked.module.kernel_id

    return ir


def lower_to_ir(program: DSLProgram) -> dict[str, Any]:
    """Typecheck and lower parsed DSL to IR JSON dict."""
    checked = typecheck_program(program)
    return lower_checked_program_to_ir(checked)
