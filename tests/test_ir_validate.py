from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from nema.ir_validate import IRValidationError, validate_ir


def _base_valid_ir() -> dict:
    return {
        "name": "unit_ir",
        "constraints": {"allowedSpdx": ["MIT", "Apache-2.0"]},
        "license": {"spdxId": "MIT"},
        "graph": {
            "nodes": [
                {"id": "n0", "index": 0, "canonicalOrderId": 0},
                {"id": "n1", "index": 1, "canonicalOrderId": 1},
            ],
            "edges": [
                {
                    "id": "e_chem_0",
                    "kind": "CHEMICAL",
                    "source": "n0",
                    "target": "n1",
                    "directed": True,
                    "conductance": 0.5,
                },
                {
                    "id": "e_gap_0_fwd",
                    "kind": "GAP",
                    "source": "n0",
                    "target": "n1",
                    "directed": True,
                    "conductance": 0.1,
                },
                {
                    "id": "e_gap_0_rev",
                    "kind": "GAP",
                    "source": "n1",
                    "target": "n0",
                    "directed": True,
                    "conductance": 0.1,
                },
            ],
        },
    }


def _write_ir(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _assert_invalid(path: Path, needle: str) -> None:
    with pytest.raises(IRValidationError, match=needle):
        validate_ir(path)


def test_example_b1_small_subgraph_is_valid() -> None:
    report = validate_ir(Path("example_b1_small_subgraph.json"))
    assert report["ok"] is True
    assert report["node_count"] > 0
    assert report["edge_count"] > 0


def test_duplicate_node_id_fails(tmp_path: Path) -> None:
    payload = _base_valid_ir()
    payload["graph"]["nodes"][1]["id"] = payload["graph"]["nodes"][0]["id"]
    ir_path = tmp_path / "dup_node_id.json"
    _write_ir(ir_path, payload)
    _assert_invalid(ir_path, "duplicate node id")


def test_duplicate_node_index_fails(tmp_path: Path) -> None:
    payload = _base_valid_ir()
    payload["graph"]["nodes"][1]["index"] = payload["graph"]["nodes"][0]["index"]
    ir_path = tmp_path / "dup_node_index.json"
    _write_ir(ir_path, payload)
    _assert_invalid(ir_path, "duplicate node index")


def test_duplicate_edge_id_fails(tmp_path: Path) -> None:
    payload = _base_valid_ir()
    payload["graph"]["edges"][1]["id"] = payload["graph"]["edges"][0]["id"]
    ir_path = tmp_path / "dup_edge_id.json"
    _write_ir(ir_path, payload)
    _assert_invalid(ir_path, "duplicate edge id")


def test_edge_reference_missing_node_fails(tmp_path: Path) -> None:
    payload = _base_valid_ir()
    payload["graph"]["edges"][0]["target"] = "missing_node"
    ir_path = tmp_path / "missing_node_ref.json"
    _write_ir(ir_path, payload)
    _assert_invalid(ir_path, "missing target node")


def test_chemical_must_be_directed_fails(tmp_path: Path) -> None:
    payload = _base_valid_ir()
    payload["graph"]["edges"][0]["directed"] = False
    ir_path = tmp_path / "chemical_not_directed.json"
    _write_ir(ir_path, payload)
    _assert_invalid(ir_path, "CHEMICAL must be directed")


def test_gap_directed_edges_must_mirror_fails(tmp_path: Path) -> None:
    payload = _base_valid_ir()
    payload["graph"]["edges"] = [edge for edge in payload["graph"]["edges"] if edge["id"] != "e_gap_0_rev"]
    ir_path = tmp_path / "gap_no_mirror.json"
    _write_ir(ir_path, payload)
    _assert_invalid(ir_path, "GAP edge symmetry violation")


def test_negative_conductance_fails(tmp_path: Path) -> None:
    payload = _base_valid_ir()
    payload["graph"]["edges"][0]["conductance"] = -0.01
    ir_path = tmp_path / "negative_conductance.json"
    _write_ir(ir_path, payload)
    _assert_invalid(ir_path, "negative conductance")


def test_missing_canonical_order_id_fails(tmp_path: Path) -> None:
    payload = _base_valid_ir()
    del payload["graph"]["nodes"][0]["canonicalOrderId"]
    ir_path = tmp_path / "missing_canonical_order_id.json"
    _write_ir(ir_path, payload)
    _assert_invalid(ir_path, "missing canonicalOrderId")


def test_spdx_must_be_allowed_fails(tmp_path: Path) -> None:
    payload = _base_valid_ir()
    payload["license"]["spdxId"] = "GPL-3.0-only"
    ir_path = tmp_path / "spdx_not_allowed.json"
    _write_ir(ir_path, payload)
    _assert_invalid(ir_path, "is not allowed")


def test_graph_external_file_must_exist_fails(tmp_path: Path) -> None:
    payload = _base_valid_ir()
    payload["graph"]["external"] = {
        "path": "missing_external.bin",
        "sha256": "placeholder",
    }
    ir_path = tmp_path / "missing_external_file.json"
    _write_ir(ir_path, payload)
    _assert_invalid(ir_path, "file does not exist")


def test_graph_external_sha256_mismatch_fails(tmp_path: Path) -> None:
    payload = _base_valid_ir()
    external_path = tmp_path / "external_payload.bin"
    external_path.write_bytes(b"nema-external-content")
    payload["graph"]["external"] = {
        "path": external_path.name,
        "sha256": hashlib.sha256(b"not-the-same").hexdigest(),
    }
    ir_path = tmp_path / "external_hash_mismatch.json"
    _write_ir(ir_path, payload)
    _assert_invalid(ir_path, "sha256 mismatch")


def test_graph_external_placeholder_hash_is_allowed(tmp_path: Path) -> None:
    payload = copy.deepcopy(_base_valid_ir())
    external_path = tmp_path / "external_payload.bin"
    external_path.write_bytes(b"nema-external-content")
    payload["graph"]["external"] = {
        "path": external_path.name,
        "sha256": "PLACEHOLDER",
    }
    ir_path = tmp_path / "external_placeholder_hash.json"
    _write_ir(ir_path, payload)

    report = validate_ir(ir_path)
    assert report["ok"] is True
