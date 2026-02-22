from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_dsl_hwtoolchain_require_emits_single_error_2401(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fixture = "tests/fixtures/diag/2401_hw_toolchain_unavailable.nema"
    outdir = tmp_path / "build_test"

    env = os.environ.copy()
    env["NEMA_DSL_FORCE_HW_UNAVAILABLE"] = "1"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "dsl",
            "hwtest",
            fixture,
            "--hw",
            "require",
            "--format",
            "json",
            "--ticks",
            "1",
            "--outdir",
            str(outdir),
        ],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    diagnostics = payload["diagnostics"]
    assert len(diagnostics) == 1
    diag = diagnostics[0]
    assert diag["severity"] == "ERROR"
    assert diag["code"] == "NEMA-DSL2401"
