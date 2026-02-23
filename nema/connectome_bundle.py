"""Connectome bundle v0.1 helpers (build/verify/load)."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

BUNDLE_FORMAT_ID = "nema.connectome.bundle.v0.1"
NODES_CSV = "nodes.csv"
EDGES_CSV = "edges.csv"
METADATA_JSON = "metadata.json"


class ConnectomeBundleError(ValueError):
    """Raised when a connectome bundle is invalid."""


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def normalize_sha256_token(value: str) -> str:
    token = value.strip().lower()
    if token.startswith("sha256:"):
        token = token[len("sha256:") :]
    return token


def is_placeholder_sha256(value: str) -> bool:
    token = normalize_sha256_token(value)
    if not token:
        return True
    return (
        "placeholder" in token
        or "replace" in token
        or token in {"todo", "tbd", "none", "unknown", "na", "n/a"}
        or token == "0" * 64
    )


def is_valid_sha256_hex(value: str) -> bool:
    token = normalize_sha256_token(value)
    return len(token) == 64 and all(ch in "0123456789abcdef" for ch in token)


def bundle_digest_from_file_hashes(*, nodes_sha256: str, edges_sha256: str) -> str:
    payload = {
        "edgesCsvSha256": edges_sha256,
        "formatId": BUNDLE_FORMAT_ID,
        "nodesCsvSha256": nodes_sha256,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(canonical)


def _parse_int(raw: str, *, field: str) -> int:
    token = raw.strip()
    if not token:
        raise ConnectomeBundleError(f"invalid empty integer for {field}")
    try:
        value = int(token)
    except ValueError as exc:
        raise ConnectomeBundleError(f"invalid integer for {field}: {raw}") from exc
    return value


def _parse_float(raw: str, *, field: str) -> float:
    token = raw.strip()
    if not token:
        raise ConnectomeBundleError(f"invalid empty float for {field}")
    try:
        value = float(token)
    except ValueError as exc:
        raise ConnectomeBundleError(f"invalid float for {field}: {raw}") from exc
    return value


def _parse_bool(raw: str, *, default: bool = True) -> bool:
    token = raw.strip().lower()
    if not token:
        return default
    if token in {"1", "true", "yes", "y"}:
        return True
    if token in {"0", "false", "no", "n"}:
        return False
    return default


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ConnectomeBundleError(f"missing file: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ConnectomeBundleError(f"{path} has no CSV header")
        rows: list[dict[str, str]] = []
        for row in reader:
            out: dict[str, str] = {}
            for key, value in row.items():
                if key is None:
                    continue
                out[key] = "" if value is None else str(value)
            rows.append(out)
    return rows


def _node_from_row(row: dict[str, str], row_index: int) -> dict[str, Any]:
    node_id = row.get("id", "").strip()
    if not node_id:
        raise ConnectomeBundleError(f"nodes.csv row {row_index + 1} missing id")

    index_raw = row.get("index", "").strip()
    index = _parse_int(index_raw, field=f"nodes[{row_index}].index") if index_raw else row_index
    canonical_raw = row.get("canonicalOrderId", "").strip()
    canonical = _parse_int(canonical_raw, field=f"nodes[{row_index}].canonicalOrderId") if canonical_raw else index
    v_init_raw = row.get("vInitRaw", "").strip()
    v_init = _parse_int(v_init_raw, field=f"nodes[{row_index}].vInitRaw") if v_init_raw else 0
    tau_raw = row.get("tauM", "").strip()
    tau = _parse_float(tau_raw, field=f"nodes[{row_index}].tauM") if tau_raw else 2.0
    if tau <= 0:
        raise ConnectomeBundleError(f"nodes.csv row {row_index + 1} has non-positive tauM")

    node: dict[str, Any] = {
        "id": node_id,
        "index": index,
        "canonicalOrderId": canonical,
        "vInitRaw": v_init,
        "tauM": tau,
    }
    for key in ("name", "role"):
        raw = row.get(key, "").strip()
        if raw:
            node[key] = raw
    params = row.get("params", "").strip()
    if params:
        try:
            node["params"] = json.loads(params)
        except json.JSONDecodeError:
            node["params"] = params
    return node


def _edge_from_row(row: dict[str, str], row_index: int) -> dict[str, Any]:
    src = row.get("src", row.get("source", "")).strip()
    dst = row.get("dst", row.get("target", "")).strip()
    if not src or not dst:
        raise ConnectomeBundleError(f"edges.csv row {row_index + 1} missing src/dst")

    kind_raw = row.get("type", row.get("kind", "CHEMICAL")).strip().upper() or "CHEMICAL"
    if kind_raw not in {"CHEMICAL", "GAP"}:
        raise ConnectomeBundleError(f"edges.csv row {row_index + 1} has unsupported type '{kind_raw}'")
    edge_id = row.get("id", "").strip() or f"e_{kind_raw.lower()}_{row_index:06d}"

    conductance_raw = row.get("conductance", "").strip()
    if conductance_raw:
        conductance = _parse_float(conductance_raw, field=f"edges[{row_index}].conductance")
    else:
        weight_raw = row.get("weight", "").strip()
        if not weight_raw:
            raise ConnectomeBundleError(f"edges.csv row {row_index + 1} missing conductance/weight")
        conductance = abs(_parse_float(weight_raw, field=f"edges[{row_index}].weight"))

    if conductance < 0:
        raise ConnectomeBundleError(f"edges.csv row {row_index + 1} has negative conductance")

    edge: dict[str, Any] = {
        "id": edge_id,
        "kind": kind_raw,
        "source": src,
        "target": dst,
        "directed": _parse_bool(row.get("directed", ""), default=True),
        "conductance": conductance,
    }
    weight_raw = row.get("weight", "").strip()
    if weight_raw:
        edge["weight"] = _parse_float(weight_raw, field=f"edges[{row_index}].weight")
    model_id = row.get("modelId", "").strip()
    if model_id:
        edge["modelId"] = model_id
    return edge


def _load_graph_from_csv(*, nodes_csv: Path, edges_csv: Path) -> dict[str, Any]:
    node_rows = _read_csv(nodes_csv)
    edge_rows = _read_csv(edges_csv)

    nodes = [_node_from_row(row, idx) for idx, row in enumerate(node_rows)]
    edges = [_edge_from_row(row, idx) for idx, row in enumerate(edge_rows)]
    return {"nodes": nodes, "edges": edges}


def _graph_counts(graph: dict[str, Any]) -> dict[str, int]:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_count = len(nodes) if isinstance(nodes, list) else 0
    edge_count_total = len(edges) if isinstance(edges, list) else 0
    chemical = 0
    gap_directed = 0
    gap_pairs: set[tuple[str, str, str]] = set()

    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            kind = str(edge.get("kind", edge.get("type", ""))).upper()
            if kind == "CHEMICAL":
                chemical += 1
                continue
            if kind == "GAP":
                gap_directed += 1
                src = str(edge.get("source", edge.get("src", "")))
                dst = str(edge.get("target", edge.get("dst", "")))
                a, b = sorted((src, dst))
                gap_pairs.add((a, b, str(edge.get("conductance", ""))))

    return {
        "nodeCount": node_count,
        "chemicalEdgeCount": chemical,
        "gapEdgeCount": len(gap_pairs),
        "gapDirectedCount": gap_directed,
        "edgeCountTotal": edge_count_total,
    }


def bundle_file_hashes(bundle_dir: Path) -> dict[str, str]:
    nodes_path = bundle_dir / NODES_CSV
    edges_path = bundle_dir / EDGES_CSV
    if not nodes_path.exists():
        raise ConnectomeBundleError(f"bundle missing {NODES_CSV}: {bundle_dir}")
    if not edges_path.exists():
        raise ConnectomeBundleError(f"bundle missing {EDGES_CSV}: {bundle_dir}")

    nodes_sha = sha256_file(nodes_path)
    edges_sha = sha256_file(edges_path)
    bundle_sha = bundle_digest_from_file_hashes(nodes_sha256=nodes_sha, edges_sha256=edges_sha)
    return {
        "nodesCsv": nodes_sha,
        "edgesCsv": edges_sha,
        "bundle": bundle_sha,
    }


def external_artifact_sha256(path: Path) -> str:
    if path.is_dir():
        return bundle_file_hashes(path)["bundle"]
    if not path.exists():
        raise ConnectomeBundleError(f"artifact not found: {path}")
    return sha256_file(path)


def load_bundle_directory(bundle_dir: Path) -> dict[str, Any]:
    if not bundle_dir.is_dir():
        raise ConnectomeBundleError(f"bundle directory not found: {bundle_dir}")

    graph = _load_graph_from_csv(nodes_csv=bundle_dir / NODES_CSV, edges_csv=bundle_dir / EDGES_CSV)
    counts = _graph_counts(graph)
    sha256 = bundle_file_hashes(bundle_dir)

    metadata_path = bundle_dir / METADATA_JSON
    metadata: dict[str, Any] | None = None
    if metadata_path.exists():
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConnectomeBundleError(f"invalid metadata.json: {exc}") from exc
        if not isinstance(raw, dict):
            raise ConnectomeBundleError("metadata.json must be an object")
        metadata = raw

    format_id = metadata.get("formatId") if isinstance(metadata, dict) else None
    if not isinstance(format_id, str) or not format_id:
        format_id = BUNDLE_FORMAT_ID
    subgraph_id = metadata.get("subgraphId") if isinstance(metadata, dict) else None
    if not isinstance(subgraph_id, str) or not subgraph_id:
        subgraph_id = "default"

    return {
        "formatId": format_id,
        "subgraphId": subgraph_id,
        "graph": graph,
        "stats": {
            "nodeCount": counts["nodeCount"],
            "chemicalEdgeCount": counts["chemicalEdgeCount"],
            "gapEdgeCount": counts["gapEdgeCount"],
        },
        "counts": counts,
        "sha256": sha256,
        "metadata": metadata,
    }


def verify_bundle_directory(bundle_dir: Path) -> dict[str, Any]:
    try:
        loaded = load_bundle_directory(bundle_dir)
    except ConnectomeBundleError as exc:
        return {
            "ok": False,
            "bundlePath": str(bundle_dir),
            "error": str(exc),
            "mismatches": [{"field": "bundle", "detail": str(exc)}],
        }

    metadata = loaded.get("metadata")
    mismatches: list[dict[str, Any]] = []
    if not isinstance(metadata, dict):
        mismatches.append({"field": "metadata.json", "detail": "missing metadata.json"})
    else:
        if metadata.get("formatId") != BUNDLE_FORMAT_ID:
            mismatches.append(
                {
                    "field": "metadata.formatId",
                    "expected": BUNDLE_FORMAT_ID,
                    "actual": metadata.get("formatId"),
                }
            )

        expected_sha = metadata.get("sha256")
        if not isinstance(expected_sha, dict):
            mismatches.append({"field": "metadata.sha256", "detail": "missing sha256 object"})
        else:
            for key in ("nodesCsv", "edgesCsv", "bundle"):
                expected = expected_sha.get(key)
                actual = loaded["sha256"][key]
                if expected != actual:
                    mismatches.append(
                        {
                            "field": f"metadata.sha256.{key}",
                            "expected": expected,
                            "actual": actual,
                        }
                    )

        expected_counts = metadata.get("counts")
        if not isinstance(expected_counts, dict):
            mismatches.append({"field": "metadata.counts", "detail": "missing counts object"})
        else:
            for key in ("nodeCount", "chemicalEdgeCount", "gapEdgeCount", "edgeCountTotal"):
                expected = expected_counts.get(key)
                actual = loaded["counts"][key]
                if expected != actual:
                    mismatches.append(
                        {
                            "field": f"metadata.counts.{key}",
                            "expected": expected,
                            "actual": actual,
                        }
                    )

    return {
        "ok": len(mismatches) == 0,
        "bundlePath": str(bundle_dir),
        "formatId": loaded["formatId"],
        "subgraphId": loaded["subgraphId"],
        "computed": {
            "sha256": loaded["sha256"],
            "counts": loaded["counts"],
        },
        "mismatches": mismatches,
    }


def _stable_node_sort_key(node: dict[str, Any]) -> tuple[int, int, str]:
    return (
        int(node.get("canonicalOrderId", 0)),
        int(node.get("index", 0)),
        str(node.get("id", "")),
    )


def _stable_edge_sort_key(edge: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(edge.get("source", "")),
        str(edge.get("target", "")),
        str(edge.get("kind", "")),
        str(edge.get("id", "")),
    )


def _write_nodes_csv(path: Path, nodes: list[dict[str, Any]]) -> None:
    fieldnames = ["id", "index", "canonicalOrderId", "vInitRaw", "tauM", "name", "role", "params"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for node in sorted(nodes, key=_stable_node_sort_key):
            params = node.get("params")
            if isinstance(params, (dict, list)):
                params_value = json.dumps(params, sort_keys=True, separators=(",", ":"))
            elif params is None:
                params_value = ""
            else:
                params_value = str(params)
            writer.writerow(
                {
                    "id": str(node.get("id", "")),
                    "index": str(int(node.get("index", 0))),
                    "canonicalOrderId": str(int(node.get("canonicalOrderId", 0))),
                    "vInitRaw": str(int(node.get("vInitRaw", 0))),
                    "tauM": str(float(node.get("tauM", 2.0))),
                    "name": str(node.get("name", "")),
                    "role": str(node.get("role", "")),
                    "params": params_value,
                }
            )


def _write_edges_csv(path: Path, edges: list[dict[str, Any]]) -> None:
    fieldnames = ["id", "src", "dst", "type", "directed", "conductance", "weight", "modelId"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for edge in sorted(edges, key=_stable_edge_sort_key):
            writer.writerow(
                {
                    "id": str(edge.get("id", "")),
                    "src": str(edge.get("source", "")),
                    "dst": str(edge.get("target", "")),
                    "type": str(edge.get("kind", "")),
                    "directed": "true" if bool(edge.get("directed", True)) else "false",
                    "conductance": str(float(edge.get("conductance", 0.0))),
                    "weight": "" if "weight" not in edge else str(float(edge.get("weight", 0.0))),
                    "modelId": str(edge.get("modelId", "")),
                }
            )


def build_bundle_directory(
    *,
    nodes_csv: Path,
    edges_csv: Path,
    out_dir: Path,
    source: str = "UNKNOWN",
    license_id: str = "UNKNOWN",
    subgraph_id: str = "default",
) -> dict[str, Any]:
    graph = _load_graph_from_csv(nodes_csv=nodes_csv, edges_csv=edges_csv)
    out_dir.mkdir(parents=True, exist_ok=True)

    nodes_out = out_dir / NODES_CSV
    edges_out = out_dir / EDGES_CSV
    metadata_out = out_dir / METADATA_JSON

    _write_nodes_csv(nodes_out, graph["nodes"])
    _write_edges_csv(edges_out, graph["edges"])

    loaded = load_bundle_directory(out_dir)
    metadata = {
        "formatId": BUNDLE_FORMAT_ID,
        "source": source,
        "license": license_id,
        "subgraphId": subgraph_id,
        "files": {
            "nodes": NODES_CSV,
            "edges": EDGES_CSV,
        },
        "sha256": loaded["sha256"],
        "counts": loaded["counts"],
    }
    metadata_out.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "formatId": BUNDLE_FORMAT_ID,
        "bundlePath": str(out_dir),
        "subgraphId": subgraph_id,
        "metadataPath": str(metadata_out),
        "sha256": loaded["sha256"],
        "counts": loaded["counts"],
        "source": source,
        "license": license_id,
    }

