from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _write_report(
    path: Path,
    *,
    model_id: str,
    target_id: str,
    node_count: int,
    chemical_edge_count: int,
    gap_edge_count: int,
    edge_count_total: int,
    digest_ok: bool,
) -> None:
    payload = {
        "modelId": model_id,
        "bench": {"targetId": target_id},
        "ok": digest_ok,
        "correctness": {"digestMatch": {"ok": digest_ok}},
        "config": {
            "graph": {
                "nodeCount": node_count,
                "chemicalEdgeCount": chemical_edge_count,
                "gapEdgeCount": gap_edge_count,
                "edgeCountTotal": edge_count_total,
            }
        },
        "provenance": {"syntheticUsed": True, "externalVerified": False},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_audit_min_go(tmp_path: Path) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    root = tmp_path / "build"
    _write_report(
        root / "B1" / "bench_report.json",
        model_id="example_b1_small_subgraph",
        target_id="B1/CE/2-1",
        node_count=2,
        chemical_edge_count=1,
        gap_edge_count=1,
        edge_count_total=3,
        digest_ok=True,
    )
    _write_report(
        root / "B3" / "bench_report.json",
        model_id="B3_kernel_302_7500",
        target_id="B3/CE/302-7500",
        node_count=302,
        chemical_edge_count=7500,
        gap_edge_count=0,
        edge_count_total=7500,
        digest_ok=True,
    )

    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "tools/audit_min.py", "--path", str(root)],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["decision"] == "GO"
    assert payload["benchReportsScanned"] == 2
    assert payload["dslReady"]["ok"] is True
    assert payload["criteria"]["dslProgramsPresent"] is True
    assert payload["criteria"]["dslCompileAndCheckOk"] is True
    assert payload["criteria"]["benchVerifyOk"] is True


def test_audit_min_no_go_without_b3(tmp_path: Path) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    root = tmp_path / "build"
    _write_report(
        root / "B1" / "bench_report.json",
        model_id="example_b1_small_subgraph",
        target_id="B1/CE/2-1",
        node_count=2,
        chemical_edge_count=1,
        gap_edge_count=1,
        edge_count_total=3,
        digest_ok=True,
    )

    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "tools/audit_min.py", "--path", str(root)],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["decision"] == "NO-GO"
    assert any("B3 302/7500" in reason for reason in payload["reasons"])
    assert payload["criteria"]["b3Evidence302_7500"] is False
