from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_hw_report(
    path: Path,
    *,
    benchmark_id: str,
    seed: int,
    n_count: int,
    e_count: int,
    cycles: int,
) -> None:
    payload = {
        "modelId": f"{benchmark_id.lower()}_model_s{seed}",
        "bench": {"targetId": f"{benchmark_id}/CE/{n_count}-{e_count}"},
        "ok": True,
        "correctness": {"digestMatch": {"ok": True}},
        "config": {
            "graph": {
                "nodeCount": n_count,
                "chemicalEdgeCount": e_count,
                "gapEdgeCount": 0,
                "edgeCountTotal": e_count,
            },
            "schedule": {"synapseLanes": 1, "neuronLanes": 1},
            "qformats": {"voltage": "Q8.8"},
        },
        "provenance": {"syntheticUsed": False, "externalVerified": True, "seed": seed},
        "hardware": {
            "toolchain": {"available": True},
            "csim": {"ok": True},
            "csynth": {"ok": True},
            "cosim": {"attempted": False, "ok": None},
            "reports": {"files": ["hw_reports/syn/report/csynth.rpt"]},
            "qor": {
                "utilization": {"lut": 100, "ff": 200, "bram": 1, "dsp": 1},
                "ii": cycles,
                "latencyCycles": cycles,
                "timingOrLatency": {"ii": cycles, "latencyCycles": cycles},
                "sourceReports": ["hw_reports/syn/report/csynth.rpt"],
            },
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _run_audit_min_hardware(root: Path, *, max_err: float) -> dict:
    repo_root = Path(__file__).resolve().parents[1]
    isolated_repo = root / "_isolated_repo"
    isolated_repo.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            sys.executable,
            "tools/audit_min.py",
            "--mode",
            "hardware",
            "--path",
            str(root),
            "--repo-root",
            str(isolated_repo),
            "--workdir",
            str(root / "_work"),
            "--cost-split-by",
            "seed",
            "--cost-test-fraction",
            "0.5",
            "--cost-split-seed",
            "0",
            "--cost-min-points",
            "3",
            "--cost-mean-rel-error-max",
            str(max_err),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.stdout.strip(), proc.stderr
    return json.loads(proc.stdout)


def test_audit_min_cost_crossval_threshold_passes_for_linear_data(tmp_path: Path) -> None:
    root = tmp_path / "reports_ok"
    linear_samples = [
        ("B1", 101, 10, 100),
        ("B1", 101, 20, 40),
        ("B2", 202, 40, 80),
        ("B2", 202, 30, 60),
        ("B3", 303, 302, 7500),
        ("B3", 303, 302, 7500),
        ("B4", 404, 25, 70),
        ("B4", 404, 60, 10),
    ]
    for idx, (benchmark_id, seed, n_count, e_count) in enumerate(linear_samples):
        cycles = 20 + 2 * n_count + e_count
        _write_hw_report(
            root / f"r{idx}" / "bench_report.json",
            benchmark_id=benchmark_id,
            seed=seed,
            n_count=n_count,
            e_count=e_count,
            cycles=cycles,
        )

    payload = _run_audit_min_hardware(root, max_err=0.05)
    assert payload["criteria"]["hardwareCostModelMinPoints"] is True
    assert payload["criteria"]["hardwareCostModelMeanErrorWithinThreshold"] is True
    assert payload["costModel"]["splitBy"] == "seed"
    mean_test = payload["costModel"]["meanRelativeErrorTest"]
    assert isinstance(mean_test, float)
    assert mean_test <= 1e-9


def test_audit_min_cost_crossval_threshold_fails_for_non_generalizing_data(tmp_path: Path) -> None:
    root = tmp_path / "reports_bad"
    nonlinear_samples = [
        ("B1", 101, 10, 100),
        ("B1", 101, 20, 40),
        ("B2", 202, 40, 80),
        ("B2", 202, 30, 60),
        ("B3", 303, 302, 7500),
        ("B3", 303, 302, 7500),
        ("B4", 404, 25, 70),
        ("B4", 404, 60, 10),
    ]
    for idx, (benchmark_id, seed, n_count, e_count) in enumerate(nonlinear_samples):
        cycles = n_count * n_count + e_count
        _write_hw_report(
            root / f"r{idx}" / "bench_report.json",
            benchmark_id=benchmark_id,
            seed=seed,
            n_count=n_count,
            e_count=e_count,
            cycles=cycles,
        )

    payload = _run_audit_min_hardware(root, max_err=0.05)
    assert payload["criteria"]["hardwareCostModelMinPoints"] is True
    assert payload["criteria"]["hardwareCostModelMeanErrorWithinThreshold"] is False
    mean_test = payload["costModel"]["meanRelativeErrorTest"]
    assert isinstance(mean_test, float)
    assert mean_test > 0.05
