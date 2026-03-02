#!/usr/bin/env python3
"""Structural preflight checks for an arXiv source bundle directory."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE_DIR = ROOT / "build" / "arxiv_bundle_stage"
DEFAULT_MAIN_REL = Path(os.environ.get("ARXIV_MAIN_REL", "paper/paper.tex"))

README_NAME = "00README.XXX"
INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")


def _strip_comments(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        i = 0
        while i < len(line):
            if line[i] == "%" and (i == 0 or line[i - 1] != "\\"):
                line = line[:i]
                break
            i += 1
        out.append(line)
    return "\n".join(out)


def _ensure_inside(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise SystemExit(f"path escapes bundle: {resolved}")
    return resolved


def _parse_toplevelfile(readme_path: Path) -> str:
    text = readme_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("toplevelfile:"):
            value = stripped.split(":", maxsplit=1)[1].strip()
            if not value:
                raise SystemExit(f"empty toplevelfile in {readme_path}")
            return value
    raise SystemExit(f"missing 'toplevelfile:' in {readme_path}")


def _resolve_tex_ref(bundle_dir: Path, tex_parent: Path, main_dir: Path, ref: str) -> Path:
    token = ref.strip()
    if not token:
        raise SystemExit("empty \\input/\\include reference")
    candidate_raw = Path(token)
    if candidate_raw.is_absolute():
        raise SystemExit(f"absolute \\input/\\include path is forbidden: {token}")

    candidates: list[Path] = []
    for anchor in (tex_parent, main_dir):
        c = _ensure_inside(anchor / candidate_raw, bundle_dir)
        if c.suffix == "":
            c = c.with_suffix(".tex")
        if c not in candidates:
            candidates.append(c)
    found = next((c for c in candidates if c.exists()), None)
    if found is None:
        tried = ", ".join(str(c.relative_to(bundle_dir)) for c in candidates)
        raise SystemExit(f"missing \\input/\\include target '{token}' (tried: {tried})")
    return found


def _check_inputs_exist(bundle_dir: Path, main_rel: Path) -> int:
    main_path = _ensure_inside(bundle_dir / main_rel, bundle_dir)
    if not main_path.exists():
        raise SystemExit(f"missing main TeX in bundle: {main_rel.as_posix()}")

    main_text = _strip_comments(main_path.read_text(encoding="utf-8", errors="replace"))
    if "\\documentclass" not in main_text:
        raise SystemExit(f"missing \\documentclass in main TeX: {main_rel.as_posix()}")

    seen: set[Path] = set()
    stack: list[Path] = [main_path]
    main_dir = main_path.parent

    while stack:
        tex_path = stack.pop()
        if tex_path in seen:
            continue
        seen.add(tex_path)
        text = _strip_comments(tex_path.read_text(encoding="utf-8", errors="replace"))
        for group in INPUT_RE.findall(text):
            for raw in [x.strip() for x in group.split(",") if x.strip()]:
                dep = _resolve_tex_ref(bundle_dir, tex_path.parent, main_dir, raw)
                stack.append(dep)

    return len(seen)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=DEFAULT_BUNDLE_DIR,
        help="bundle/stage directory containing 00README.XXX and TeX sources",
    )
    parser.add_argument(
        "--main-rel",
        type=Path,
        default=DEFAULT_MAIN_REL,
        help="main TeX relative path expected in bundle and 00README.XXX",
    )
    args = parser.parse_args()

    bundle_dir = args.bundle_dir.resolve()
    main_rel = Path(args.main_rel.as_posix())

    if not bundle_dir.exists():
        raise SystemExit(f"bundle directory does not exist: {bundle_dir}")
    if main_rel.is_absolute():
        raise SystemExit(f"--main-rel must be relative, got: {main_rel}")

    readme_path = bundle_dir / README_NAME
    if not readme_path.exists():
        raise SystemExit(f"missing required file in bundle: {README_NAME}")

    top_level = _parse_toplevelfile(readme_path)
    expected = main_rel.as_posix()
    if top_level != expected:
        raise SystemExit(
            "00README.XXX toplevelfile mismatch: "
            f"expected '{expected}', found '{top_level}'"
        )

    checked = _check_inputs_exist(bundle_dir, main_rel)
    print(
        "arXiv preflight OK: "
        f"main={expected}, readme=toplevelfile, tex_dependency_closure={checked}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
