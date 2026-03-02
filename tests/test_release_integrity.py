from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_check_release_integrity_script_passes() -> None:
    root = _repo_root()
    proc = subprocess.run(
        [sys.executable, "tools/check_release_integrity.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Release integrity check: OK" in proc.stdout


def test_check_release_integrity_reports_missing_entries_actionably(tmp_path: Path) -> None:
    status = tmp_path / "FINAL_STATUS.json"
    status.write_text(
        """
{
  "evidence": {
    "powerCsv": "review_pack/tables/example_power.csv",
    "metricsCsv": "review_pack/tables/example_metrics.csv"
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    sha = tmp_path / "SHA256SUMS.txt"
    sha.write_text(
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  review_pack/tables/example_power.csv\n",
        encoding="utf-8",
    )

    root = _repo_root()
    proc = subprocess.run(
        [
            sys.executable,
            "tools/check_release_integrity.py",
            "--final-status",
            str(status),
            "--sha256sums",
            str(sha),
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "Missing SHA256 entries for artifacts referenced by FINAL_STATUS:" in proc.stdout
    assert "review_pack/tables/example_metrics.csv" in proc.stdout
    assert "Action:" in proc.stdout
