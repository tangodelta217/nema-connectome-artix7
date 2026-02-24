from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_combo(root: Path, *, combo: str, syn: int, neu: int, kernel_tag: str) -> Path:
    model_root = root / combo / "model_x"
    bench_path = model_root / "bench_report.json"
    kernel_path = model_root / "hls" / "nema_kernel.cpp"
    kernel_path.parent.mkdir(parents=True, exist_ok=True)
    kernel_path.write_text(f"// kernel {kernel_tag}\n", encoding="utf-8")
    bench_payload = {
        "config": {"schedule": {"synapseLanes": syn, "neuronLanes": neu}},
    }
    bench_path.write_text(json.dumps(bench_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return bench_path


def test_knob_sanity_detects_hash_diversity_and_unique_paths(tmp_path: Path) -> None:
    bench_a = _write_combo(tmp_path, combo="syn1_neu1", syn=1, neu=1, kernel_tag="A")
    bench_b = _write_combo(tmp_path, combo="syn8_neu4", syn=8, neu=4, kernel_tag="B")
    sweep_payload = {
        "results": [
            {
                "comboId": "syn1_neu1",
                "synapseLanes": 1,
                "neuronLanes": 1,
                "benchReportPath": str(bench_a),
            },
            {
                "comboId": "syn8_neu4",
                "synapseLanes": 8,
                "neuronLanes": 4,
                "benchReportPath": str(bench_b),
            },
        ]
    }
    sweep_path = tmp_path / "sweep_results.json"
    sweep_path.write_text(json.dumps(sweep_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    out_json = tmp_path / "knob.json"
    out_md = tmp_path / "knob.md"
    proc = subprocess.run(
        [
            sys.executable,
            "tools/knob_sanity.py",
            "--sweep-results",
            str(sweep_path),
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(out_json.read_text(encoding="utf-8"))
    assert summary["ok"] is True
    assert summary["counts"]["rows"] == 2
    assert summary["counts"]["uniqueBenchReportPaths"] == 2
    assert summary["counts"]["uniqueKernelHashes"] == 2
    assert summary["criteria"]["benchReportPathsUnique"] is True
    assert summary["criteria"]["kernelHashDiversity"] is True
    assert summary["criteria"]["benchScheduleMatchesSweep"] is True
