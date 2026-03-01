#!/usr/bin/env python3
"""Compatibility wrapper for legacy review-pack command.

Delegates to the canonical existing entrypoint.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    target = repo / "tools" / "paperA" / "build_review_pack_v3.py"
    if not target.exists():
        sys.stderr.write(
            "MISSING_CANONICAL_SOURCE: expected tools/paperA/build_review_pack_v3.py\n"
        )
        return 2
    proc = subprocess.run([sys.executable, str(target)], cwd=repo)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
