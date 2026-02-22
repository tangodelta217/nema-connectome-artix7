from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_dsl_diag_snapshots_match_goldens() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fixtures_dir = repo_root / "tests" / "fixtures" / "diag"
    goldens_dir = repo_root / "tests" / "golden" / "diag"

    fixtures = sorted(fixtures_dir.glob("*.nema"))
    assert fixtures, "no diagnostics fixtures found"

    env = os.environ.copy()
    env["NEMA_DSL_FORCE_HW_UNAVAILABLE"] = "1"

    for fixture in fixtures:
        rel_fixture = fixture.relative_to(repo_root).as_posix()
        proc = subprocess.run(
            [sys.executable, "-m", "nema", "dsl", "check", rel_fixture, "--format", "json"],
            cwd=repo_root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.stdout.strip(), f"empty stdout for {rel_fixture}"
        actual = json.loads(proc.stdout)

        golden_path = goldens_dir / f"{fixture.stem}.json"
        assert golden_path.exists(), f"missing golden snapshot: {golden_path}"
        expected = json.loads(golden_path.read_text(encoding="utf-8"))
        assert actual == expected, f"diagnostic snapshot mismatch for {rel_fixture}"
