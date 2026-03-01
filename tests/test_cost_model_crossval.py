from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from nema.qor_model import fit_cost_model


def _linear_rows() -> list[dict[str, object]]:
    # y = 20 + 2*(N/P_N) + 1*(E/P_S)
    rows: list[dict[str, object]] = []
    samples = [
        ("B1", 101, 10, 100),
        ("B1", 101, 20, 40),
        ("B2", 202, 40, 80),
        ("B2", 202, 30, 60),
        ("B3", 303, 15, 30),
        ("B3", 303, 50, 20),
        ("B5", 404, 25, 70),
        ("B5", 404, 60, 10),
    ]
    for benchmark, seed, n_count, e_count in samples:
        latency = 20 + 2 * n_count + e_count
        rows.append(
            {
                "N": n_count,
                "E": e_count,
                "qformat": "Q8.8",
                "P_N": 1,
                "P_S": 1,
                "ii": latency,
                "latency": latency,
                "lut": 100,
                "ff": 200,
                "bram": 1,
                "dsp": 1,
                "benchmarkId": benchmark,
                "seed": seed,
                "modelId": f"{benchmark.lower()}_s{seed}",
                "_reportPath": f"/tmp/{benchmark.lower()}_{seed}.json",
                "_modelId": f"{benchmark.lower()}_s{seed}",
            }
        )
    return rows


def test_fit_cost_model_crossval_by_seed_has_train_and_test_metrics() -> None:
    payload = fit_cost_model(
        _linear_rows(),
        min_points=3,
        mean_relative_error_max=0.05,
        split_by="seed",
        test_fraction=0.25,
        split_seed=7,
    )

    assert payload["fitSolved"] is True
    assert payload["kRequirementMet"] is True
    assert payload["splitBy"] == "seed"
    assert payload["train"]["points"] >= 3
    assert payload["test"]["points"] >= 1
    assert payload["datasetStats"]["benchmarkCount"] == 4
    assert payload["datasetStats"]["seedCount"] == 4
    assert payload["meanRelativeError_train"] == 0.0
    assert payload["meanRelativeError_test"] == 0.0
    assert payload["test"]["withinThreshold"] is True
    assert payload["withinThreshold"] is True
    assert payload["ok"] is True


def test_fit_cost_model_crossval_test_error_flags_non_generalizing_data() -> None:
    rows = _linear_rows()
    for row in rows:
        n_count = int(row["N"])
        e_count = int(row["E"])
        row["latency"] = n_count * n_count + e_count
        row["ii"] = row["latency"]

    payload = fit_cost_model(
        rows,
        min_points=3,
        mean_relative_error_max=0.05,
        split_by="benchmark",
        test_fraction=0.25,
        split_seed=0,
    )

    assert payload["fitSolved"] is True
    assert payload["kRequirementMet"] is True
    assert isinstance(payload["meanRelativeError_test"], float)
    assert payload["meanRelativeError_test"] > 0.05
    assert payload["test"]["withinThreshold"] is False
    assert payload["withinThreshold"] is False
    assert payload["ok"] is False


def test_cost_model_fit_cli_emits_train_test_metrics(tmp_path: Path) -> None:
    csv_path = tmp_path / "dataset.csv"
    fieldnames = [
        "N",
        "E",
        "qformat",
        "P_N",
        "P_S",
        "ii",
        "latency",
        "lut",
        "ff",
        "bram",
        "dsp",
        "benchmarkId",
        "seed",
        "modelId",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in _linear_rows():
            writer.writerow({key: row.get(key) for key in fieldnames})

    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [
            sys.executable,
            "tools/cost_model_fit.py",
            "--csv",
            str(csv_path),
            "--split-by",
            "benchmark",
            "--test-fraction",
            "0.25",
            "--split-seed",
            "0",
            "--min-points",
            "3",
            "--mean-rel-error-max",
            "0.05",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    fit = payload["fit"]
    assert fit["splitBy"] == "benchmark"
    assert fit["train"]["points"] >= 3
    assert fit["test"]["points"] >= 1
    assert fit["meanRelativeError_test"] == 0.0
    assert fit["ok"] is True
