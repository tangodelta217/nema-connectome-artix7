#!/usr/bin/env python3
"""Recompute controlled SHA-256 entries and update release/SHA256SUMS.txt."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA_FILE = ROOT / "release" / "SHA256SUMS.txt"

# Only these controlled files are recalculated by this tool.
CONTROLLED_ALLOWLIST = (
    "paper/paper.pdf",
    "release/artifact_bundle_final.tar.gz",
    "review_pack/tables/artix7_hls_digest_summary.csv",
    "review_pack/tables/artix7_hls_digest_summary_strict.csv",
    "review_pack/tables/artix7_hls_digest_summary_strict_v2.csv",
    "review_pack/tables/artix7_metrics_final.csv",
    "review_pack/tables/artix7_metrics_v1.csv",
    "review_pack/tables/artix7_power.csv",
    "review_pack/tables/artix7_power_v4.csv",
    "review_pack/tables/artix7_power_v5.csv",
    "review_pack/tables/artix7_power_v6.csv",
    "review_pack/tables/artix7_power_v7_funcsaif.csv",
    "review_pack/tables/artix7_qor.csv",
    "review_pack/tables/artix7_qor_v4.csv",
    "review_pack/tables/artix7_qor_v5.csv",
    "review_pack/tables/artix7_qor_v6.csv",
)

CONTROLLED_PREFIXES = ("paper/", "review_pack/tables/", "release/")
LINE_RE = re.compile(r"^([0-9a-f]{64})\s{2}(.+)$")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_allowlist(rel_path: str) -> None:
    if not rel_path.startswith(CONTROLLED_PREFIXES):
        raise ValueError(f"allowlist entry outside controlled roots: {rel_path}")
    if rel_path == "release/SHA256SUMS.txt":
        raise ValueError("release/SHA256SUMS.txt cannot hash itself")


def _read_sha_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    if not path.exists():
        return entries
    for idx, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        match = LINE_RE.match(line)
        if not match:
            raise ValueError(f"invalid SHA256SUMS line {idx}: {raw_line!r}")
        digest, rel = match.groups()
        if rel in entries:
            raise ValueError(f"duplicate SHA256SUMS path on line {idx}: {rel}")
        entries[rel] = digest
    return entries


def _compute_controlled_entries() -> dict[str, str]:
    computed: dict[str, str] = {}
    for rel in sorted(CONTROLLED_ALLOWLIST):
        _validate_allowlist(rel)
        path = ROOT / rel
        if not path.is_file():
            raise FileNotFoundError(f"missing allowlisted path: {rel}")
        computed[rel] = _sha256(path)
    return computed


def _format_manifest(entries: dict[str, str]) -> str:
    lines = [f"{entries[rel]}  {rel}" for rel in sorted(entries)]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update release/SHA256SUMS.txt for controlled allowlisted paths."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write files; fail if the manifest is not up to date",
    )
    args = parser.parse_args()

    current = _read_sha_manifest(SHA_FILE)
    computed = _compute_controlled_entries()
    merged = dict(current)
    merged.update(computed)
    rendered = _format_manifest(merged)

    existing_text = SHA_FILE.read_text(encoding="utf-8") if SHA_FILE.exists() else ""
    if args.check:
        if existing_text != rendered:
            print("SHA256SUMS drift detected. Run: python tools/update_sha256sums.py")
            return 1
        print("SHA256SUMS is up to date.")
        return 0

    SHA_FILE.write_text(rendered, encoding="utf-8")
    print(f"updated {SHA_FILE.relative_to(ROOT)} with {len(computed)} controlled entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
