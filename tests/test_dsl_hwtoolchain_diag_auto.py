from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_dsl_hwtoolchain_auto_warning_when_unavailable(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fixture = "tests/fixtures/diag/2401_hw_toolchain_unavailable.nema"
    outdir = tmp_path / "build_test"

    env = os.environ.copy()
    # Force software-only path to keep default pytest deterministic and fast.
    env["NEMA_DSL_FORCE_HW_UNAVAILABLE"] = "1"
    env["NEMA_HWTEST_DISABLE_VITIS"] = "1"
    env["NEMA_HWTEST_DISABLE_VIVADO"] = "1"

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "dsl",
            "hwtest",
            fixture,
            "--hw",
            "auto",
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

    payload = json.loads(proc.stdout)
    diagnostics = payload.get("diagnostics", [])
    has_2401 = any(diag.get("code") == "NEMA-DSL2401" for diag in diagnostics)

    assert payload.get("hwToolchainAvailable") is False
    assert has_2401 is True
    severities = [diag.get("severity") for diag in diagnostics if diag.get("code") == "NEMA-DSL2401"]
    assert severities == ["WARNING"]
