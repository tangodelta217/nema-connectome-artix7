from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_dsl_help_lists_planned_subcommands() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "nema", "dsl", "--help"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    output = proc.stdout
    assert "compile" in output
    assert "check" in output
    assert "hwtest" in output
    assert "from-ir" in output


def test_dsl_compile_smoke_outputs_json(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    dsl_path = tmp_path / "smoke.nema"
    dsl_path.write_text("root { value = 1; };", encoding="utf-8")
    out_path = tmp_path / "out.json"

    proc = subprocess.run(
        [sys.executable, "-m", "nema", "dsl", "compile", str(dsl_path), "--out", str(out_path)],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert out_path.exists()


def test_dsl_from_ir_smoke_outputs_source(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    out_path = tmp_path / "from_ir.nema"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "dsl",
            "from-ir",
            "example_b1_small_subgraph.json",
            "--out",
            str(out_path),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert out_path.exists()
