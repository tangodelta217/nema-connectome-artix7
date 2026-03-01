from __future__ import annotations

import json
from pathlib import Path

from nema.cli import main


def test_connectome_ingest_and_verify_json_bundle(tmp_path: Path, capsys) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    nodes_csv = repo_root / "tests/fixtures/connectome_ingest/nodes.csv"
    edges_csv = repo_root / "tests/fixtures/connectome_ingest/edges.csv"
    out_bundle = tmp_path / "bundle.json"

    code = main(
        [
            "connectome",
            "ingest",
            "--nodes",
            str(nodes_csv),
            "--edges",
            str(edges_csv),
            "--out",
            str(out_bundle),
            "--subgraph-id",
            "unit_subgraph",
            "--license-spdx",
            "MIT",
            "--source-url",
            "https://example.org/unit/connectome",
            "--source-sha256",
            "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "--retrieved-at",
            "2026-02-24T00:00:00Z",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert out_bundle.exists()

    bundle = json.loads(out_bundle.read_text(encoding="utf-8"))
    assert bundle["schemaVersion"] == "0.1"
    assert bundle["formatId"] == "nema.connectome.bundle.v0.1"
    assert bundle["license"]["spdxId"] == "MIT"
    assert bundle["provenance"]["sourceUrls"] == ["https://example.org/unit/connectome"]
    assert bundle["counts"]["nodeCount"] == 4
    assert bundle["counts"]["chemicalEdgeCount"] == 2
    assert bundle["counts"]["gapEdgeCount"] == 1
    gap_edges = [edge for edge in bundle["graph"]["edges"] if edge["kind"] == "GAP"]
    assert len(gap_edges) == 1
    assert gap_edges[0]["directed"] is False
    assert gap_edges[0]["source"] <= gap_edges[0]["target"]

    verify_code = main(["connectome", "verify", str(out_bundle)])
    assert verify_code == 0
    verify_payload = json.loads(capsys.readouterr().out)
    assert verify_payload["ok"] is True
    assert verify_payload["mismatches"] == []


def test_connectome_verify_detects_invalid_reference(tmp_path: Path, capsys) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source_bundle = repo_root / "connectomes/test_bundle.json"
    bad_bundle = tmp_path / "bad_bundle.json"
    payload = json.loads(source_bundle.read_text(encoding="utf-8"))
    payload["graph"]["edges"][0]["source"] = "n_missing"
    bad_bundle.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    code = main(["connectome", "verify", str(bad_bundle)])
    assert code == 1
    report = json.loads(capsys.readouterr().out)
    fields = {item["field"] for item in report["mismatches"]}
    assert "graph.edges[0].source" in fields


def test_connectome_verify_repo_fixture(capsys) -> None:
    code = main(["connectome", "verify", "connectomes/test_bundle.json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
