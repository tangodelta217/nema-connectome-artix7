"""Deterministic connectome ingest + verify for JSON bundle artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .connectome_bundle import (
    BUNDLE_FORMAT_ID,
    ConnectomeBundleError,
    is_valid_sha256_hex,
    normalize_sha256_token,
    verify_bundle_directory,
)

JSON_BUNDLE_SCHEMA_VERSION = "0.1"


def _as_bool(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"1", "true", "yes", "y"}:
            return True
        if token in {"0", "false", "no", "n"}:
            return False
    return default


def _as_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise ConnectomeBundleError(f"{field} must be integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        token = value.strip()
        if token and (token.isdigit() or (token.startswith("-") and token[1:].isdigit())):
            return int(token)
    raise ConnectomeBundleError(f"{field} must be integer")


def _as_float(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise ConnectomeBundleError(f"{field} must be numeric")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        token = value.strip()
        if token:
            try:
                return float(token)
            except ValueError as exc:
                raise ConnectomeBundleError(f"{field} must be numeric") from exc
    raise ConnectomeBundleError(f"{field} must be numeric")


def _sha256_hex(raw: bytes) -> str:
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def _sha256_token(value: str) -> str:
    return f"sha256:{value}"


def _canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _section_hash(obj: Any) -> str:
    return _sha256_token(_sha256_hex(_canonical_bytes(obj)))


def _normalize_url_list(urls: list[str] | None) -> list[str]:
    if not urls:
        return []
    out = [item.strip() for item in urls if isinstance(item, str) and item.strip()]
    return sorted(set(out))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ConnectomeBundleError(f"missing file: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ConnectomeBundleError(f"{path} has no CSV header")
        rows: list[dict[str, str]] = []
        for row in reader:
            clean: dict[str, str] = {}
            for key, value in row.items():
                if key is None:
                    continue
                clean[key] = "" if value is None else str(value)
            rows.append(clean)
    return rows


def _node_from_csv(row: dict[str, str], *, row_idx: int) -> dict[str, Any]:
    node_id = row.get("id", "").strip()
    if not node_id:
        raise ConnectomeBundleError(f"nodes.csv row {row_idx + 1} missing id")
    index_raw = row.get("index", "").strip()
    canonical_raw = row.get("canonicalOrderId", "").strip()
    v_init_raw = row.get("vInitRaw", "").strip()
    tau_raw = row.get("tauM", "").strip()

    index = _as_int(index_raw, field=f"nodes[{row_idx}].index") if index_raw else row_idx
    canonical = _as_int(canonical_raw, field=f"nodes[{row_idx}].canonicalOrderId") if canonical_raw else index
    v_init = _as_int(v_init_raw, field=f"nodes[{row_idx}].vInitRaw") if v_init_raw else 0
    tau = _as_float(tau_raw, field=f"nodes[{row_idx}].tauM") if tau_raw else 2.0
    if tau <= 0:
        raise ConnectomeBundleError(f"nodes[{row_idx}].tauM must be > 0")

    node: dict[str, Any] = {
        "id": node_id,
        "index": index,
        "canonicalOrderId": canonical,
        "vInitRaw": v_init,
        "tauM": tau,
    }
    for key in ("name", "role"):
        value = row.get(key, "").strip()
        if value:
            node[key] = value
    params = row.get("params", "").strip()
    if params:
        try:
            node["params"] = json.loads(params)
        except json.JSONDecodeError:
            node["params"] = params
    return node


def _edge_from_csv(row: dict[str, str], *, row_idx: int) -> dict[str, Any]:
    src = row.get("src", row.get("source", "")).strip()
    dst = row.get("dst", row.get("target", "")).strip()
    if not src or not dst:
        raise ConnectomeBundleError(f"edges.csv row {row_idx + 1} missing src/dst")

    kind_raw = row.get("type", row.get("kind", "CHEMICAL")).strip().upper() or "CHEMICAL"
    if kind_raw not in {"CHEMICAL", "GAP"}:
        raise ConnectomeBundleError(f"edges.csv row {row_idx + 1} unsupported kind '{kind_raw}'")

    edge_id = row.get("id", "").strip() or f"e_{kind_raw.lower()}_{row_idx:06d}"
    conductance_raw = row.get("conductance", "").strip()
    if conductance_raw:
        conductance = _as_float(conductance_raw, field=f"edges[{row_idx}].conductance")
    else:
        weight_raw = row.get("weight", "").strip()
        if not weight_raw:
            raise ConnectomeBundleError(f"edges.csv row {row_idx + 1} missing conductance/weight")
        conductance = abs(_as_float(weight_raw, field=f"edges[{row_idx}].weight"))
    if conductance < 0:
        raise ConnectomeBundleError(f"edges[{row_idx}].conductance must be >= 0")

    edge: dict[str, Any] = {
        "id": edge_id,
        "kind": kind_raw,
        "source": src,
        "target": dst,
        "directed": _as_bool(row.get("directed", ""), default=True),
        "conductance": conductance,
    }
    weight_raw = row.get("weight", "").strip()
    if weight_raw:
        edge["weight"] = _as_float(weight_raw, field=f"edges[{row_idx}].weight")
    model_id = row.get("modelId", "").strip()
    if model_id:
        edge["modelId"] = model_id
    return edge


def _stable_node_sort_key(node: dict[str, Any]) -> tuple[int, int, str]:
    return (
        int(node.get("canonicalOrderId", 0)),
        int(node.get("index", 0)),
        str(node.get("id", "")),
    )


def _stable_edge_sort_key(edge: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(edge.get("kind", "")),
        str(edge.get("source", "")),
        str(edge.get("target", "")),
        str(edge.get("id", "")),
    )


def _canonicalize_graph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    node_ids: set[str] = set()
    node_indices: set[int] = set()
    normalized_nodes: list[dict[str, Any]] = []
    for raw in sorted(nodes, key=_stable_node_sort_key):
        node_id = str(raw.get("id", "")).strip()
        if not node_id:
            raise ConnectomeBundleError("node id must be non-empty")
        if node_id in node_ids:
            raise ConnectomeBundleError(f"duplicate node id '{node_id}'")
        index = _as_int(raw.get("index"), field=f"node[{node_id}].index")
        canonical = _as_int(raw.get("canonicalOrderId"), field=f"node[{node_id}].canonicalOrderId")
        v_init = _as_int(raw.get("vInitRaw", 0), field=f"node[{node_id}].vInitRaw")
        tau = _as_float(raw.get("tauM", 2.0), field=f"node[{node_id}].tauM")
        if index < 0 or canonical < 0:
            raise ConnectomeBundleError(f"node '{node_id}' index/canonicalOrderId must be >= 0")
        if index in node_indices:
            raise ConnectomeBundleError(f"duplicate node index {index}")
        if tau <= 0:
            raise ConnectomeBundleError(f"node '{node_id}' tauM must be > 0")
        node_indices.add(index)
        node_ids.add(node_id)
        node_obj: dict[str, Any] = {
            "id": node_id,
            "index": index,
            "canonicalOrderId": canonical,
            "vInitRaw": v_init,
            "tauM": tau,
        }
        for key in ("name", "role"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                node_obj[key] = value.strip()
        params = raw.get("params")
        if params is not None:
            node_obj["params"] = params
        normalized_nodes.append(node_obj)

    edge_ids: set[str] = set()
    canonical_chemical: list[dict[str, Any]] = []
    gap_map: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for idx, raw in enumerate(edges):
        edge_id = str(raw.get("id", f"edge_{idx:06d}"))
        if edge_id in edge_ids:
            raise ConnectomeBundleError(f"duplicate edge id '{edge_id}'")
        edge_ids.add(edge_id)

        kind = str(raw.get("kind", raw.get("type", ""))).upper().strip()
        if kind not in {"CHEMICAL", "GAP"}:
            raise ConnectomeBundleError(f"edge '{edge_id}' unsupported kind '{kind}'")
        source = str(raw.get("source", raw.get("src", ""))).strip()
        target = str(raw.get("target", raw.get("dst", ""))).strip()
        if source not in node_ids:
            raise ConnectomeBundleError(f"edge '{edge_id}' references missing source node '{source}'")
        if target not in node_ids:
            raise ConnectomeBundleError(f"edge '{edge_id}' references missing target node '{target}'")
        conductance = _as_float(raw.get("conductance"), field=f"edge[{edge_id}].conductance")
        if conductance < 0:
            raise ConnectomeBundleError(f"edge '{edge_id}' has negative conductance")
        model_id = raw.get("modelId")
        model_id_str = str(model_id) if isinstance(model_id, str) and model_id else ""

        if kind == "CHEMICAL":
            edge_obj: dict[str, Any] = {
                "id": edge_id,
                "kind": "CHEMICAL",
                "source": source,
                "target": target,
                "directed": True,
                "conductance": conductance,
            }
            weight = raw.get("weight")
            if weight is not None:
                edge_obj["weight"] = _as_float(weight, field=f"edge[{edge_id}].weight")
            if model_id_str:
                edge_obj["modelId"] = model_id_str
            canonical_chemical.append(edge_obj)
            continue

        # GAP canonicalization (single undirected canonical edge per pair+conductance+modelId).
        a, b = sorted((source, target))
        cond_key = f"{conductance:.16g}"
        gap_key = (a, b, cond_key, model_id_str)
        if gap_key not in gap_map:
            gap_edge: dict[str, Any] = {
                "id": "",
                "kind": "GAP",
                "source": a,
                "target": b,
                "directed": False,
                "conductance": conductance,
            }
            if model_id_str:
                gap_edge["modelId"] = model_id_str
            gap_map[gap_key] = gap_edge

    canonical_gap = [gap_map[key] for key in sorted(gap_map.keys())]
    for idx, edge in enumerate(canonical_gap):
        edge["id"] = f"gap_{idx:06d}"

    normalized_edges = sorted([*canonical_chemical, *canonical_gap], key=_stable_edge_sort_key)
    return {
        "nodes": normalized_nodes,
        "edges": normalized_edges,
    }


def _graph_counts(graph: dict[str, Any]) -> dict[str, int]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    chemical = 0
    gap = 0
    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            kind = str(edge.get("kind", edge.get("type", ""))).upper()
            if kind == "CHEMICAL":
                chemical += 1
            elif kind == "GAP":
                gap += 1
    return {
        "nodeCount": len(nodes) if isinstance(nodes, list) else 0,
        "chemicalEdgeCount": chemical,
        "gapEdgeCount": gap,
        "gapDirectedCount": 0,
        "edgeCountTotal": (len(edges) if isinstance(edges, list) else 0),
    }


def _section_hashes(*, graph: dict[str, Any], metadata_payload: dict[str, Any]) -> dict[str, str]:
    sections = {
        "nodes": _section_hash(graph["nodes"]),
        "edges": _section_hash(graph["edges"]),
        "graph": _section_hash({"nodes": graph["nodes"], "edges": graph["edges"]}),
        "metadata": _section_hash(metadata_payload),
    }
    bundle_payload = {
        "formatId": BUNDLE_FORMAT_ID,
        "schemaVersion": metadata_payload.get("schemaVersion"),
        "subgraphId": metadata_payload.get("subgraphId"),
        "sections": sections,
    }
    return {
        "algorithm": "sha256",
        "sections": sections,
        "bundle": _section_hash(bundle_payload),
    }


def ingest_connectome_bundle_json(
    *,
    nodes_csv: Path,
    edges_csv: Path,
    out_path: Path,
    subgraph_id: str = "default",
    license_spdx: str = "MIT",
    source_urls: list[str] | None = None,
    source_sha256: str | None = None,
    retrieved_at: str = "1970-01-01T00:00:00Z",
    schema_version: str = JSON_BUNDLE_SCHEMA_VERSION,
) -> dict[str, Any]:
    if not subgraph_id.strip():
        raise ConnectomeBundleError("subgraph_id must be non-empty")
    if not license_spdx.strip():
        raise ConnectomeBundleError("license_spdx must be non-empty")
    if not schema_version.strip():
        raise ConnectomeBundleError("schema_version must be non-empty")
    if not isinstance(retrieved_at, str) or not retrieved_at.strip():
        raise ConnectomeBundleError("retrieved_at must be non-empty")

    source_sha_token = None
    if isinstance(source_sha256, str) and source_sha256.strip():
        normalized = normalize_sha256_token(source_sha256)
        if not is_valid_sha256_hex(normalized):
            raise ConnectomeBundleError("source_sha256 must be a valid sha256 token")
        source_sha_token = _sha256_token(normalized)

    raw_nodes = _read_csv(nodes_csv)
    raw_edges = _read_csv(edges_csv)
    parsed_nodes = [_node_from_csv(row, row_idx=idx) for idx, row in enumerate(raw_nodes)]
    parsed_edges = [_edge_from_csv(row, row_idx=idx) for idx, row in enumerate(raw_edges)]
    graph = _canonicalize_graph(parsed_nodes, parsed_edges)
    counts = _graph_counts(graph)

    provenance: dict[str, Any] = {
        "sourceUrls": _normalize_url_list(source_urls),
        "retrievedAt": retrieved_at.strip(),
    }
    if source_sha_token is not None:
        provenance["sourceSha256"] = source_sha_token

    metadata_payload = {
        "schemaVersion": schema_version.strip(),
        "formatId": BUNDLE_FORMAT_ID,
        "subgraphId": subgraph_id.strip(),
        "license": {"spdxId": license_spdx.strip()},
        "provenance": provenance,
        "counts": counts,
    }
    checksums = _section_hashes(graph=graph, metadata_payload=metadata_payload)

    bundle = {
        **metadata_payload,
        "graph": graph,
        "checksums": checksums,
    }

    resolved_out = out_path.resolve()
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "bundlePath": str(resolved_out),
        "formatId": BUNDLE_FORMAT_ID,
        "schemaVersion": schema_version.strip(),
        "subgraphId": subgraph_id.strip(),
        "counts": counts,
        "checksums": checksums,
    }


def _validate_json_bundle(bundle: dict[str, Any], *, bundle_path: Path) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []

    schema_version = bundle.get("schemaVersion")
    if schema_version != JSON_BUNDLE_SCHEMA_VERSION:
        mismatches.append(
            {
                "field": "schemaVersion",
                "expected": JSON_BUNDLE_SCHEMA_VERSION,
                "actual": schema_version,
            }
        )

    format_id = bundle.get("formatId")
    if format_id != BUNDLE_FORMAT_ID:
        mismatches.append({"field": "formatId", "expected": BUNDLE_FORMAT_ID, "actual": format_id})

    license_obj = bundle.get("license")
    spdx = license_obj.get("spdxId") if isinstance(license_obj, dict) else None
    if not isinstance(spdx, str) or not spdx.strip():
        mismatches.append({"field": "license.spdxId", "detail": "missing or empty"})

    provenance = bundle.get("provenance")
    if not isinstance(provenance, dict):
        mismatches.append({"field": "provenance", "detail": "missing object"})
        provenance = {}
    else:
        urls = provenance.get("sourceUrls")
        if not isinstance(urls, list):
            mismatches.append({"field": "provenance.sourceUrls", "detail": "must be array"})
        retrieved_at = provenance.get("retrievedAt")
        if not isinstance(retrieved_at, str) or not retrieved_at.strip():
            mismatches.append({"field": "provenance.retrievedAt", "detail": "missing or empty"})
        source_sha = provenance.get("sourceSha256")
        if source_sha is not None:
            if not isinstance(source_sha, str) or not is_valid_sha256_hex(normalize_sha256_token(source_sha)):
                mismatches.append({"field": "provenance.sourceSha256", "detail": "invalid sha256 token"})

    graph_raw = bundle.get("graph")
    if not isinstance(graph_raw, dict):
        mismatches.append({"field": "graph", "detail": "missing object"})
        graph_raw = {"nodes": [], "edges": []}
    nodes = graph_raw.get("nodes")
    edges = graph_raw.get("edges")
    if not isinstance(nodes, list):
        mismatches.append({"field": "graph.nodes", "detail": "must be array"})
        nodes = []
    if not isinstance(edges, list):
        mismatches.append({"field": "graph.edges", "detail": "must be array"})
        edges = []

    node_ids: set[str] = set()
    node_indices: set[int] = set()
    normalized_nodes: list[dict[str, Any]] = []
    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            mismatches.append({"field": f"graph.nodes[{idx}]", "detail": "must be object"})
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            mismatches.append({"field": f"graph.nodes[{idx}].id", "detail": "missing or empty"})
            continue
        if node_id in node_ids:
            mismatches.append({"field": f"graph.nodes[{idx}].id", "detail": f"duplicate id '{node_id}'"})
            continue
        try:
            node_index = _as_int(node.get("index"), field=f"graph.nodes[{idx}].index")
            canonical = _as_int(node.get("canonicalOrderId"), field=f"graph.nodes[{idx}].canonicalOrderId")
            v_init = _as_int(node.get("vInitRaw", 0), field=f"graph.nodes[{idx}].vInitRaw")
            tau = _as_float(node.get("tauM", 2.0), field=f"graph.nodes[{idx}].tauM")
        except ConnectomeBundleError as exc:
            mismatches.append({"field": f"graph.nodes[{idx}]", "detail": str(exc)})
            continue
        if node_index < 0 or canonical < 0:
            mismatches.append({"field": f"graph.nodes[{idx}]", "detail": "index/canonicalOrderId must be >= 0"})
            continue
        if node_index in node_indices:
            mismatches.append({"field": f"graph.nodes[{idx}].index", "detail": f"duplicate index {node_index}"})
            continue
        if tau <= 0:
            mismatches.append({"field": f"graph.nodes[{idx}].tauM", "detail": "must be > 0"})
            continue
        node_ids.add(node_id)
        node_indices.add(node_index)
        normalized_nodes.append(
            {
                "id": node_id,
                "index": node_index,
                "canonicalOrderId": canonical,
                "vInitRaw": v_init,
                "tauM": tau,
                **({"name": node["name"]} if isinstance(node.get("name"), str) and node.get("name") else {}),
                **({"role": node["role"]} if isinstance(node.get("role"), str) and node.get("role") else {}),
                **({"params": node["params"]} if "params" in node else {}),
            }
        )

    edge_ids: set[str] = set()
    canonical_gap_keys: set[tuple[str, str, str, str]] = set()
    normalized_edges: list[dict[str, Any]] = []
    for idx, edge in enumerate(edges):
        if not isinstance(edge, dict):
            mismatches.append({"field": f"graph.edges[{idx}]", "detail": "must be object"})
            continue
        edge_id = edge.get("id")
        if not isinstance(edge_id, str) or not edge_id:
            mismatches.append({"field": f"graph.edges[{idx}].id", "detail": "missing or empty"})
            continue
        if edge_id in edge_ids:
            mismatches.append({"field": f"graph.edges[{idx}].id", "detail": f"duplicate id '{edge_id}'"})
            continue
        edge_ids.add(edge_id)

        kind = str(edge.get("kind", edge.get("type", ""))).upper()
        if kind not in {"CHEMICAL", "GAP"}:
            mismatches.append({"field": f"graph.edges[{idx}].kind", "detail": f"unsupported kind '{kind}'"})
            continue
        src = str(edge.get("source", edge.get("src", ""))).strip()
        dst = str(edge.get("target", edge.get("dst", ""))).strip()
        if src not in node_ids:
            mismatches.append({"field": f"graph.edges[{idx}].source", "detail": f"missing node '{src}'"})
        if dst not in node_ids:
            mismatches.append({"field": f"graph.edges[{idx}].target", "detail": f"missing node '{dst}'"})
        try:
            conductance = _as_float(edge.get("conductance"), field=f"graph.edges[{idx}].conductance")
        except ConnectomeBundleError as exc:
            mismatches.append({"field": f"graph.edges[{idx}].conductance", "detail": str(exc)})
            continue
        if conductance < 0:
            mismatches.append({"field": f"graph.edges[{idx}].conductance", "detail": "must be >= 0"})
            continue
        directed = _as_bool(edge.get("directed", True), default=True)

        if kind == "CHEMICAL" and directed is not True:
            mismatches.append({"field": f"graph.edges[{idx}].directed", "detail": "CHEMICAL must be directed=true"})
        if kind == "GAP":
            if directed is not False:
                mismatches.append({"field": f"graph.edges[{idx}].directed", "detail": "GAP must be directed=false"})
            if src > dst:
                mismatches.append(
                    {"field": f"graph.edges[{idx}].source/target", "detail": "GAP endpoints must be canonical (source<=target)"}
                )
            model_id = edge.get("modelId")
            model_id_str = model_id if isinstance(model_id, str) else ""
            key = (src, dst, f"{conductance:.16g}", model_id_str)
            if key in canonical_gap_keys:
                mismatches.append({"field": f"graph.edges[{idx}]", "detail": "duplicate canonical GAP edge"})
            canonical_gap_keys.add(key)

        normalized: dict[str, Any] = {
            "id": edge_id,
            "kind": kind,
            "source": src,
            "target": dst,
            "directed": directed,
            "conductance": conductance,
        }
        if "weight" in edge:
            try:
                normalized["weight"] = _as_float(edge.get("weight"), field=f"graph.edges[{idx}].weight")
            except ConnectomeBundleError:
                pass
        if isinstance(edge.get("modelId"), str) and edge.get("modelId"):
            normalized["modelId"] = edge["modelId"]
        normalized_edges.append(normalized)

    sorted_graph = {
        "nodes": sorted(normalized_nodes, key=_stable_node_sort_key),
        "edges": sorted(normalized_edges, key=_stable_edge_sort_key),
    }
    computed_counts = _graph_counts(sorted_graph)

    counts_obj = bundle.get("counts")
    if not isinstance(counts_obj, dict):
        mismatches.append({"field": "counts", "detail": "missing object"})
        counts_obj = {}
    for key, actual_value in computed_counts.items():
        expected_value = counts_obj.get(key)
        if expected_value != actual_value:
            mismatches.append(
                {
                    "field": f"counts.{key}",
                    "expected": actual_value,
                    "actual": expected_value,
                }
            )

    metadata_payload = {
        "schemaVersion": bundle.get("schemaVersion"),
        "formatId": bundle.get("formatId"),
        "subgraphId": bundle.get("subgraphId"),
        "license": bundle.get("license"),
        "provenance": bundle.get("provenance"),
        "counts": bundle.get("counts"),
    }
    computed_checksums = _section_hashes(graph=sorted_graph, metadata_payload=metadata_payload)

    checksums = bundle.get("checksums")
    if not isinstance(checksums, dict):
        mismatches.append({"field": "checksums", "detail": "missing object"})
        checksums = {}
    sections = checksums.get("sections")
    if not isinstance(sections, dict):
        mismatches.append({"field": "checksums.sections", "detail": "missing object"})
        sections = {}

    for key in ("nodes", "edges", "graph", "metadata"):
        expected = sections.get(key)
        actual = computed_checksums["sections"][key]
        if not isinstance(expected, str) or normalize_sha256_token(expected) != normalize_sha256_token(actual):
            mismatches.append({"field": f"checksums.sections.{key}", "expected": actual, "actual": expected})

    bundle_expected = checksums.get("bundle")
    bundle_actual = computed_checksums["bundle"]
    if not isinstance(bundle_expected, str) or normalize_sha256_token(bundle_expected) != normalize_sha256_token(bundle_actual):
        mismatches.append({"field": "checksums.bundle", "expected": bundle_actual, "actual": bundle_expected})

    return {
        "ok": len(mismatches) == 0,
        "bundlePath": str(bundle_path),
        "formatId": bundle.get("formatId"),
        "schemaVersion": bundle.get("schemaVersion"),
        "subgraphId": bundle.get("subgraphId"),
        "computed": {
            "counts": computed_counts,
            "checksums": computed_checksums,
        },
        "mismatches": mismatches,
    }


def verify_connectome_bundle_json(bundle_path: Path) -> dict[str, Any]:
    if not bundle_path.exists():
        return {
            "ok": False,
            "bundlePath": str(bundle_path),
            "mismatches": [{"field": "bundle", "detail": f"file not found: {bundle_path}"}],
        }
    try:
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "bundlePath": str(bundle_path),
            "mismatches": [{"field": "bundle", "detail": f"invalid JSON: {exc}"}],
        }
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "bundlePath": str(bundle_path),
            "mismatches": [{"field": "bundle", "detail": "bundle JSON must be an object"}],
        }
    return _validate_json_bundle(payload, bundle_path=bundle_path)


def verify_connectome_artifact(path: Path) -> dict[str, Any]:
    if path.is_dir():
        return verify_bundle_directory(path)
    return verify_connectome_bundle_json(path)
