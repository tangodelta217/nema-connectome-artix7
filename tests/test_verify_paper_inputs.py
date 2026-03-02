from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_verify_paper_inputs_script_passes() -> None:
    root = _repo_root()
    proc = subprocess.run(
        [sys.executable, "tools/verify_paper_inputs.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Paper input verification: OK" in proc.stdout
