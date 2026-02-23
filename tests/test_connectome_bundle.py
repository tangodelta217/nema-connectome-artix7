from __future__ import annotations

import json
from pathlib import Path

from nema.cli import main


def _write_source_csvs(tmp_path: Path) -> tuple[Path, Path]:
    nodes = tmp_path / "nodes.csv"
    edges = tmp_path / "edges.csv"
    nodes.write_text(
        "\n".join(
            [
                "id,name,role,index,canonicalOrderId,vInitRaw,tauM",
                "n0,ADAL,sensory,0,0,-64,2",
                "n1,ADAR,sensory,1,1,-32,2",
                "n2,ADEL,inter,2,2,0,3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    edges.write_text(
        "\n".join(
            [
                "id,src,dst,type,directed,conductance,weight",
                "e0,n0,n2,CHEMICAL,true,0.015625,0.015625",
                "e1,n1,n2,CHEMICAL,true,0.01171875,0.01171875",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return nodes, edges


def test_connectome_bundle_build_and_verify(tmp_path: Path, capsys) -> None:
    nodes_csv, edges_csv = _write_source_csvs(tmp_path)
    out_bundle = tmp_path / "bundle"

    build_code = main(
        [
            "connectome",
            "bundle",
            "build",
            "--nodes",
            str(nodes_csv),
            "--edges",
            str(edges_csv),
            "--out",
            str(out_bundle),
            "--source",
            "unit-test",
            "--license",
            "MIT",
            "--subgraph-id",
            "unit_subgraph",
        ]
    )
    assert build_code == 0
    build_payload = json.loads(capsys.readouterr().out)
    assert build_payload["ok"] is True
    assert (out_bundle / "nodes.csv").exists()
    assert (out_bundle / "edges.csv").exists()
    assert (out_bundle / "metadata.json").exists()

    verify_code = main(["connectome", "bundle", "verify", str(out_bundle)])
    assert verify_code == 0
    verify_payload = json.loads(capsys.readouterr().out)
    assert verify_payload["ok"] is True
    assert verify_payload["mismatches"] == []


def test_connectome_bundle_verify_detects_sha_mismatch(tmp_path: Path, capsys) -> None:
    nodes_csv, edges_csv = _write_source_csvs(tmp_path)
    out_bundle = tmp_path / "bundle"
    assert (
        main(
            [
                "connectome",
                "bundle",
                "build",
                "--nodes",
                str(nodes_csv),
                "--edges",
                str(edges_csv),
                "--out",
                str(out_bundle),
            ]
        )
        == 0
    )
    capsys.readouterr()

    metadata_path = out_bundle / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["sha256"]["bundle"] = "0" * 64
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    verify_code = main(["connectome", "bundle", "verify", str(out_bundle)])
    assert verify_code == 1
    payload = json.loads(capsys.readouterr().out)
    fields = {item["field"] for item in payload["mismatches"]}
    assert "metadata.sha256.bundle" in fields


def test_connectome_bundle_verify_detects_count_mismatch(tmp_path: Path, capsys) -> None:
    nodes_csv, edges_csv = _write_source_csvs(tmp_path)
    out_bundle = tmp_path / "bundle"
    assert (
        main(
            [
                "connectome",
                "bundle",
                "build",
                "--nodes",
                str(nodes_csv),
                "--edges",
                str(edges_csv),
                "--out",
                str(out_bundle),
            ]
        )
        == 0
    )
    capsys.readouterr()

    metadata_path = out_bundle / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["counts"]["nodeCount"] = 999
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    verify_code = main(["connectome", "bundle", "verify", str(out_bundle)])
    assert verify_code == 1
    payload = json.loads(capsys.readouterr().out)
    fields = {item["field"] for item in payload["mismatches"]}
    assert "metadata.counts.nodeCount" in fields

