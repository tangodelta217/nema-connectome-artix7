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


def test_audit_min_go_with_dsl_ready_checks(tmp_path: Path) -> None:
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
        [sys.executable, "tools/audit_min.py", "--path", str(root), "--mode", "software"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["decision"] == "GO"
    assert payload["benchReportsScanned"] == 2
    assert payload["mode"] == "software"
    assert payload["software_ok"] is True
    assert payload["dsl"]["ok"] is True
    assert payload["dsl"]["programs_present"] is True
    assert payload["dsl"]["check_ok"] is True
    assert payload["dsl"]["hwtest_ok"] is True
    assert payload["criteria"]["dslProgramsPresent"] is True
    assert payload["criteria"]["dslCheckOk"] is True
    assert payload["criteria"]["dslHwtestOk"] is True
    assert payload["criteria"]["benchVerifyOk"] is True
    assert payload["reasons"] == []


def test_audit_min_hardware_mode_no_go_without_toolchain(tmp_path: Path) -> None:
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
        [sys.executable, "tools/audit_min.py", "--path", str(root), "--mode", "hardware"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["decision"] == "NO-GO"
    assert payload["mode"] == "hardware"
    assert payload["hardware_ok"] is False
    assert payload["criteria"]["hardwareToolchainAvailable"] is False
    assert any("HW toolchain unavailable" in reason for reason in payload["reasons"])


def test_audit_min_ignores_legacy_non_relevant_reports(tmp_path: Path) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    root = tmp_path / "build"
    legacy_payload = {
        "modelId": "legacy_302",
        "ok": True,
        "correctness": {"digestMatch": {"ok": True}},
        "config": {"graph": {"nodeCount": 3}},
    }
    legacy_path = root / "legacy" / "bench_report.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(json.dumps(legacy_payload, indent=2), encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "tools/audit_min.py", "--path", str(root), "--mode", "software"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["decision"] == "GO"
    assert payload["mode"] == "software"
    ignored = payload.get("ignoredReports", [])
    assert any("legacy/bench_report.json" in path for path in ignored)
    assert payload["criteria"]["graphCountsNormalized"] is True


def test_audit_min_hardware_g2_true_with_qor_or_report_listed(tmp_path: Path) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    root = tmp_path / "build"
    report_path = root / "B3" / "bench_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "modelId": "B3_kernel_302_7500",
        "bench": {"targetId": "B3/CE/302-7500"},
        "ok": True,
        "correctness": {"digestMatch": {"ok": True}},
        "config": {
            "graph": {
                "nodeCount": 302,
                "chemicalEdgeCount": 7500,
                "gapEdgeCount": 0,
                "edgeCountTotal": 7500,
            }
        },
        "provenance": {"syntheticUsed": False, "externalVerified": True},
        "hardware": {
            "toolchain": {"available": True},
            "csim": {"ok": True},
            "csynth": {"ok": True},
            "cosim": None,
            "reports": {"files": ["hw_reports/syn/report/csynth.rpt"]},
            "qor": {
                "utilization": {"lut": 10, "ff": None, "bram": None, "dsp": None},
                "timingOrLatency": {"ii": None, "latencyCycles": None},
                "sourceReports": ["hw_reports/syn/report/csynth.rpt"],
            },
        },
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "tools/audit_min.py", "--path", str(root), "--mode", "hardware"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    parsed = json.loads(proc.stdout)
    assert parsed["criteria"]["hardwareEvidenceG2"] is True
