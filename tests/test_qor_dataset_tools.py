from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_qor_dataset_csv_snapshot(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    out_csv = tmp_path / "qor_dataset.csv"

    proc = subprocess.run(
        [
            sys.executable,
            "tools/qor_dataset.py",
            "--root",
            "tests/fixtures/qor_dataset/reports",
            "--out",
            str(out_csv),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["reportsFound"] == 4

    expected = (repo_root / "tests/golden/qor_dataset_fixture.csv").read_text(encoding="utf-8").replace("\r\n", "\n")
    actual = out_csv.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == expected


def test_cost_model_fit_metrics_snapshot(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    csv_path = tmp_path / "qor_dataset.csv"

    build_proc = subprocess.run(
        [
            sys.executable,
            "tools/qor_dataset.py",
            "--root",
            "tests/fixtures/qor_dataset/reports",
            "--out",
            str(csv_path),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert build_proc.returncode == 0, build_proc.stderr

    fit_proc = subprocess.run(
        [
            sys.executable,
            "tools/cost_model_fit.py",
            "--csv",
            str(csv_path),
            "--min-points",
            "3",
            "--mean-rel-error-max",
            "0.1",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert fit_proc.returncode == 0, fit_proc.stderr
    payload = json.loads(fit_proc.stdout)

    actual_subset = {
        "ok": payload["ok"],
        "fit": {
            "modelVersion": payload["fit"]["modelVersion"],
            "minPointsRequired": payload["fit"]["minPointsRequired"],
            "pointsWithActualQor": payload["fit"]["pointsWithActualQor"],
            "kRequirementMet": payload["fit"]["kRequirementMet"],
            "coefficients": payload["fit"]["coefficients"],
            "meanRelativeError": payload["fit"]["meanRelativeError"],
            "maxRelativeError": payload["fit"]["maxRelativeError"],
            "withinThreshold": payload["fit"]["withinThreshold"],
            "ok": payload["fit"]["ok"],
        },
    }

    expected = json.loads((repo_root / "tests/golden/cost_model_fit_fixture.json").read_text(encoding="utf-8"))
    assert actual_subset == expected
