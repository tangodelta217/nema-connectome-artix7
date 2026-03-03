#!/usr/bin/env python3
"""Download and verify large release assets from GitHub Releases."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "release" / "EXTERNAL_ASSETS_SHA256SUMS.txt"
DEFAULT_OUTDIR = ROOT / "build" / "release_assets"
DEFAULT_REPO = "tangodelta217/nema-connectome-artix7"
DEFAULT_TAG = "v0.1.0"
LINE_RE = re.compile(r"^([0-9a-f]{64})\s{2}([A-Za-z0-9._-]+)$")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest(path: Path) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for idx, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        match = LINE_RE.fullmatch(line)
        if not match:
            raise ValueError(f"invalid line {idx} in {path}: {raw!r}")
        digest, name = match.groups()
        items.append((name, digest))
    return items


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as resp:  # nosec B310
        if resp.status != 200:
            raise RuntimeError(f"unexpected HTTP status {resp.status} for {url}")
        with tmp.open("wb") as out:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    tmp.replace(dest)


def _verify_local(items: list[tuple[str, str]], outdir: Path) -> int:
    missing = []
    mismatch = []
    for name, expected in items:
        path = outdir / name
        if not path.exists():
            missing.append(name)
            continue
        got = _sha256(path)
        if got != expected:
            mismatch.append((name, expected, got))

    if missing or mismatch:
        print("Release asset verification failed:")
        for name in missing:
            print(f"- missing: {name}")
        for name, expected, got in mismatch:
            print(f"- sha mismatch: {name}")
            print(f"  expected: {expected}")
            print(f"  got:      {got}")
        return 1

    print(f"Release assets OK: {len(items)} files verified in {outdir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub repository owner/name")
    parser.add_argument("--tag", default=DEFAULT_TAG, help="Release tag to download from")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="SHA256 manifest file")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR, help="Destination directory")
    parser.add_argument("--check", action="store_true", help="Verify existing files only (no download)")
    args = parser.parse_args()

    manifest = args.manifest.resolve()
    outdir = args.outdir.resolve()
    if not manifest.exists():
        print(f"missing manifest: {manifest}", file=sys.stderr)
        return 2

    items = _load_manifest(manifest)
    if args.check:
        return _verify_local(items, outdir)

    outdir.mkdir(parents=True, exist_ok=True)
    base = f"https://github.com/{args.repo}/releases/download/{args.tag}"
    for name, expected in items:
        dst = outdir / name
        if dst.exists() and _sha256(dst) == expected:
            print(f"ok: {name} (cached)")
            continue
        url = f"{base}/{name}"
        try:
            print(f"download: {name}")
            _download(url, dst)
        except urllib.error.URLError as exc:
            print(f"download failed for {name}: {exc}", file=sys.stderr)
            return 3
        got = _sha256(dst)
        if got != expected:
            print(f"sha mismatch after download: {name}", file=sys.stderr)
            print(f"expected: {expected}", file=sys.stderr)
            print(f"got:      {got}", file=sys.stderr)
            return 4
        print(f"ok: {name}")

    print(f"done: {len(items)} assets in {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
