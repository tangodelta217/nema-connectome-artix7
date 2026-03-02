from __future__ import annotations

import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_no_provider_mentions_in_commit_history() -> None:
    root = _repo_root()
    forbidden = "co" + "dex"
    proc = subprocess.run(
        ["git", "log", "--pretty=%H%x09%s%x09%b", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    bad_lines = [
        line
        for line in proc.stdout.splitlines()
        if forbidden.lower() in line.lower()
    ]
    assert not bad_lines, (
        f"Found forbidden '{forbidden}' mention in commit history:\n"
        + "\n".join(bad_lines[:20])
    )
