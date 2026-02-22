from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_dsl_check_ok_for_b1_and_b3_programs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    programs = [
        "programs/b1_small.nema",
        "programs/b3_kernel_302.nema",
    ]

    for program in programs:
        proc = subprocess.run(
            [sys.executable, "-m", "nema", "dsl", "check", program],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
