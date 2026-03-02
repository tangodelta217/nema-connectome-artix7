#!/usr/bin/env python3
"""Check that artifacts referenced by release/FINAL_STATUS.json are hashed."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUS = ROOT / "release" / "FINAL_STATUS.json"
DEFAULT_SHA = ROOT / "release" / "SHA256SUMS.txt"

SHA_LINE_RE = re.compile(r"^[0-9a-f]{64}\s{2}(.+)$")
PATH_TOKEN_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def _collect_referenced_paths(value: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(value, dict):
        for child in value.values():
            out.update(_collect_referenced_paths(child))
        return out
    if isinstance(value, list):
        for child in value:
            out.update(_collect_referenced_paths(child))
        return out
    if isinstance(value, str):
        token = value.strip()
        if "/" not in token:
            return out
        if token.startswith(("http://", "https://", "/")):
            return out
        if not PATH_TOKEN_RE.fullmatch(token):
            return out
        out.add(token)
    return out


def _load_sha_paths(path: Path) -> set[str]:
    out: set[str] = set()
    for idx, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        match = SHA_LINE_RE.fullmatch(line)
        if not match:
            raise ValueError(f"invalid SHA256SUMS line {idx}: {raw!r}")
        out.add(match.group(1))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--final-status",
        type=Path,
        default=DEFAULT_STATUS,
        help="path to release FINAL_STATUS JSON (default: release/FINAL_STATUS.json)",
    )
    parser.add_argument(
        "--sha256sums",
        type=Path,
        default=DEFAULT_SHA,
        help="path to SHA256SUMS manifest (default: release/SHA256SUMS.txt)",
    )
    args = parser.parse_args()

    status_path = args.final_status.resolve()
    sha_path = args.sha256sums.resolve()

    if not status_path.exists():
        print(f"release integrity check failed: missing final status file: {status_path}")
        return 1
    if not sha_path.exists():
        print(f"release integrity check failed: missing SHA256SUMS file: {sha_path}")
        return 1

    status_obj = _load_json(status_path)
    referenced = sorted(_collect_referenced_paths(status_obj))
    hashed = _load_sha_paths(sha_path)

    sha_rel = sha_path.relative_to(ROOT).as_posix() if sha_path.is_relative_to(ROOT) else sha_path.as_posix()

    missing = []
    for rel in referenced:
        if rel == sha_rel:
            continue
        if rel not in hashed:
            abs_path = (ROOT / rel).resolve()
            exists = abs_path.exists()
            where = "exists" if exists else "missing on disk"
            missing.append((rel, where))

    if missing:
        print("Release integrity check failed:")
        print("Missing SHA256 entries for artifacts referenced by FINAL_STATUS:")
        for rel, where in missing:
            print(f"- {rel} ({where})")
        print("")
        print("Action:")
        print("1) Add hashes to release/SHA256SUMS.txt, for example:")
        for rel, _ in missing:
            print(f"   sha256sum {rel}")
        print("2) Re-run: python tools/check_release_integrity.py")
        return 1

    print(f"Release integrity check: OK ({len(referenced)} referenced artifacts hashed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
