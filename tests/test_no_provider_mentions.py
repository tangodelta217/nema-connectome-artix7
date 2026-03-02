from __future__ import annotations

import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_no_provider_mentions_in_tracked_text_files() -> None:
    root = _repo_root()
    allowed_paths: set[str] = set()
    forbidden = "co" + "dex"

    proc = subprocess.run(
        ["git", "grep", "-n", "-I", "-i", forbidden, "--", "."],
        cwd=root,
        capture_output=True,
        text=True,
    )

    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    filtered = []
    for line in lines:
        path = line.split(":", maxsplit=1)[0]
        if path not in allowed_paths:
            filtered.append(line)

    assert not filtered, (
        f"Found forbidden '{forbidden}' mentions in tracked files:\n"
        + "\n".join(filtered)
        + "\nUse neutral terms like 'handoff', 'agent', or 'automation'."
    )
