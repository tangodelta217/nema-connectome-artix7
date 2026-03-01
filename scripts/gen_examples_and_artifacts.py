#!/usr/bin/env python3
"""Compatibility wrapper for legacy smoke command.

Runs deterministic, existing generation entrypoints available in this repo.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> dict:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    return {
        "cmd": cmd,
        "exitCode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    tasks: list[dict] = []

    # 1) Existing deterministic diagnostics artifact generator.
    tasks.append(run([sys.executable, "tools/gen_diag_goldens.py"], repo))

    # 2) Generate compile artifacts for canonical examples.
    outdir = repo / "build" / "examples_and_artifacts"
    outdir.mkdir(parents=True, exist_ok=True)
    tasks.append(
        run(
            [
                sys.executable,
                "-m",
                "nema",
                "compile",
                "example_b1_small_subgraph.json",
                "--outdir",
                str(outdir / "b1"),
            ],
            repo,
        )
    )
    tasks.append(
        run(
            [
                sys.executable,
                "-m",
                "nema",
                "compile",
                "example_b3_kernel_302.json",
                "--outdir",
                str(outdir / "b3"),
            ],
            repo,
        )
    )

    summary = {
        "ok": all(t["exitCode"] == 0 for t in tasks),
        "tasks": tasks,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
