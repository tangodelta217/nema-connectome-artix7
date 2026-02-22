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


def test_dsl_subcommands_return_nyi_exit_code_2() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    commands = [
        ["check", "programs/b1_small.nema.toml"],
        ["compile", "programs/b1_small.nema.toml", "--out", "build/nyi.ir.json"],
        ["hwtest", "programs/b1_small.nema.toml", "--ticks", "1", "--outdir", "build"],
        ["from-ir", "example_b1_small_subgraph.json", "--out", "build/nyi.dsl"],
    ]

    for sub in commands:
        proc = subprocess.run(
            [sys.executable, "-m", "nema", "dsl", *sub],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 2
        payload = json.loads(proc.stdout)
        assert payload["ok"] is False
        assert "NYI" in payload["error"]
