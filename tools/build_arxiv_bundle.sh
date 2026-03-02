#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAIN_REL="${ARXIV_MAIN_REL:-paper/paper.tex}"
STAGE_DIR="$ROOT/build/arxiv_bundle_stage"
OUT_TAR="$ROOT/build/arxiv_bundle.tar.gz"
REQ_LIST="$ROOT/build/arxiv_bundle.required_files.txt"
CONTENTS_LIST="$ROOT/build/arxiv_bundle.contents.txt"
LATEX_LOG="$ROOT/build/arxiv_bundle_latexmk.log"

mkdir -p "$ROOT/build"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"

python3 - "$ROOT" "$MAIN_REL" "$STAGE_DIR" "$REQ_LIST" <<'PY'
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
main_rel = Path(sys.argv[2])
stage = Path(sys.argv[3]).resolve()
req_list_path = Path(sys.argv[4]).resolve()

main_abs = (root / main_rel).resolve()
if not main_abs.exists():
    raise SystemExit(f"missing canonical paper file: {main_rel}")
main_dir = main_abs.parent

try:
    main_abs.relative_to(root)
except ValueError as exc:
    raise SystemExit(f"canonical paper escapes repo root: {main_abs}") from exc

input_re = re.compile(r"\\(?:input|include)\{([^}]+)\}")
graphics_re = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
bib_re = re.compile(r"\\bibliography\{([^}]+)\}")
pkg_re = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}")

tex_queue: list[Path] = [main_abs]
seen_tex: set[Path] = set()
required_abs: set[Path] = set()


def strip_comments(text: str) -> str:
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


def ensure_inside_repo(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"dependency escapes repo root: {resolved}") from exc
    return resolved


def resolve_tex_ref(base_dir: Path, ref: str) -> Path:
    ref = ref.strip()
    if not ref:
        raise SystemExit("empty \\input or \\include reference")
    raw = Path(ref)
    if raw.is_absolute():
        raise SystemExit(f"absolute TeX input path is forbidden: {ref}")
    candidates: list[Path] = []
    for anchor in (base_dir, main_dir):
        c = ensure_inside_repo(anchor / raw)
        if c.suffix == "":
            c = c.with_suffix(".tex")
        if c not in candidates:
            candidates.append(c)
    found = next((c for c in candidates if c.exists()), None)
    if found is None:
        tried = ", ".join(str(c) for c in candidates)
        raise SystemExit(f"missing TeX input dependency for '{ref}'; tried: {tried}")
    return found


def resolve_graphics_ref(base_dir: Path, ref: str) -> Path:
    ref = ref.strip()
    if not ref:
        raise SystemExit("empty \\includegraphics reference")
    raw = Path(ref)
    if raw.is_absolute():
        raise SystemExit(f"absolute graphics path is forbidden: {ref}")

    base_candidates: list[Path] = []
    for anchor in (base_dir, main_dir):
        c = ensure_inside_repo(anchor / raw)
        if c not in base_candidates:
            base_candidates.append(c)

    tried: list[Path] = []
    for base in base_candidates:
        if base.suffix:
            tried.append(base)
            if base.exists():
                return base
            continue
        for ext in (".pdf", ".png", ".jpg", ".jpeg", ".eps"):
            c = base.with_suffix(ext)
            tried.append(c)
            if c.exists():
                return c
        tried.append(base)
        if base.exists():
            return base

    tried_list = ", ".join(str(p) for p in tried)
    raise SystemExit(f"missing graphics dependency for {ref}; tried: {tried_list}")


def maybe_local_package(path_dir: Path, pkg_ref: str) -> Path | None:
    pkg_ref = pkg_ref.strip()
    if not pkg_ref:
        return None
    pkg_path = Path(pkg_ref)
    if pkg_path.is_absolute():
        raise SystemExit(f"absolute style path is forbidden: {pkg_ref}")
    candidates: list[Path] = []
    for anchor in (path_dir, main_dir, root):
        c = ensure_inside_repo(anchor / pkg_path)
        if c.suffix == "":
            c = c.with_suffix(".sty")
        if c not in candidates:
            candidates.append(c)
    for c in candidates:
        if c.exists():
            return c
    return None


while tex_queue:
    tex_path = tex_queue.pop()
    if tex_path in seen_tex:
        continue
    seen_tex.add(tex_path)
    required_abs.add(tex_path)

    text = strip_comments(tex_path.read_text(encoding="utf-8", errors="replace"))
    parent = tex_path.parent

    for group in input_re.findall(text):
        for ref in [x.strip() for x in group.split(",") if x.strip()]:
            dep = resolve_tex_ref(parent, ref)
            required_abs.add(dep)
            tex_queue.append(dep)

    for ref in graphics_re.findall(text):
        dep = resolve_graphics_ref(parent, ref)
        required_abs.add(dep)

    for group in bib_re.findall(text):
        for bib_ref in [x.strip() for x in group.split(",") if x.strip()]:
            found = None
            for anchor in (parent, main_dir):
                bib_candidate = ensure_inside_repo(anchor / bib_ref)
                candidates = [bib_candidate] if bib_candidate.suffix else [
                    bib_candidate.with_suffix(".bib"),
                    bib_candidate.with_suffix(".bbl"),
                ]
                found = next((c for c in candidates if c.exists()), None)
                if found is not None:
                    break
            if found is None:
                raise SystemExit(f"missing bibliography dependency for reference: {bib_ref}")
            required_abs.add(found)

    for group in pkg_re.findall(text):
        for pkg in [x.strip() for x in group.split(",") if x.strip()]:
            local_style = maybe_local_package(parent, pkg)
            if local_style is not None:
                required_abs.add(local_style)

# Include main-adjacent .bbl if present to help arXiv fallback mode.
main_bbl = main_abs.with_suffix(".bbl")
if main_bbl.exists():
    required_abs.add(main_bbl)

rel_paths: list[str] = []
for src in sorted(required_abs):
    rel = src.relative_to(root).as_posix()
    rel_paths.append(rel)
    dst = stage / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

req_list_path.write_text("\n".join(sorted(set(rel_paths))) + "\n", encoding="utf-8")
print(f"staged {len(set(rel_paths))} source dependencies")
PY

cat > "$STAGE_DIR/00README.XXX" <<EOF
This archive was generated by tools/build_arxiv_bundle.sh.
toplevelfile: $MAIN_REL
EOF

echo "00README.XXX" >> "$REQ_LIST"
sort -u -o "$REQ_LIST" "$REQ_LIST"

# Hard fail on stale release-round paths or machine-local absolute paths.
if grep -RInE 'release_round10b|/home/|/Users/|file://|~/' \
  --include='*.tex' --include='*.bib' --include='*.bbl' --include='*.sty' "$STAGE_DIR"; then
  echo "ERROR: forbidden path pattern found in staged arXiv sources."
  exit 1
fi
if grep -RInE '[A-Za-z]:\\\\' \
  --include='*.tex' --include='*.bib' --include='*.bbl' --include='*.sty' "$STAGE_DIR"; then
  echo "ERROR: Windows local absolute path found in staged arXiv sources."
  exit 1
fi

# Dependency closure check inside staged tree.
python3 - "$STAGE_DIR" "$MAIN_REL" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

stage = Path(sys.argv[1]).resolve()
main_rel = Path(sys.argv[2])
main_path = stage / main_rel
main_dir = main_path.parent

if not main_path.exists():
    raise SystemExit(f"missing top-level file in stage: {main_rel}")

input_re = re.compile(r"\\(?:input|include)\{([^}]+)\}")
seen: set[Path] = set()
stack: list[Path] = [main_path]

def strip_comments(text: str) -> str:
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

while stack:
    tex = stack.pop()
    if tex in seen:
        continue
    seen.add(tex)
    text = strip_comments(tex.read_text(encoding="utf-8", errors="replace"))
    for group in input_re.findall(text):
        for raw in [x.strip() for x in group.split(",") if x.strip()]:
            candidates = []
            for anchor in (tex.parent, main_dir):
                dep = (anchor / raw).resolve()
                if dep.suffix == "":
                    dep = dep.with_suffix(".tex")
                if dep not in candidates:
                    candidates.append(dep)
            found = next((c for c in candidates if c.exists()), None)
            if found is None:
                raise SystemExit(f"staged dependency missing for {tex.relative_to(stage)}: {raw}")
            stack.append(found)

print(f"dependency closure check OK ({len(seen)} TeX files)")
PY

if command -v latexmk >/dev/null 2>&1; then
  echo "Running optional local compile preflight (latexmk)."
  if ! (cd "$STAGE_DIR" && latexmk -cd -pdf -interaction=nonstopmode -halt-on-error "$MAIN_REL" > "$LATEX_LOG" 2>&1); then
    echo "ERROR: latexmk preflight failed. See $LATEX_LOG"
    exit 1
  fi
  # Keep bundle source-only: remove generated LaTeX products from staging.
  find "$STAGE_DIR" -type f \( \
    -name '*.aux' -o \
    -name '*.log' -o \
    -name '*.out' -o \
    -name '*.fls' -o \
    -name '*.fdb_latexmk' -o \
    -name '*.blg' -o \
    -name '*.synctex.gz' -o \
    -name '*.pdf' \
  \) -delete
fi

tar -czf "$OUT_TAR" -C "$STAGE_DIR" .
tar -tzf "$OUT_TAR" | sed 's#^\./##' | sed '/^$/d' | sed '/\/$/d' | sort -u > "$CONTENTS_LIST"

if ! grep -Fxq "$MAIN_REL" "$CONTENTS_LIST"; then
  echo "ERROR: tarball missing toplevel file: $MAIN_REL"
  exit 1
fi
if ! grep -Fxq "00README.XXX" "$CONTENTS_LIST"; then
  echo "ERROR: tarball missing 00README.XXX"
  exit 1
fi

while IFS= read -r rel; do
  [ -z "$rel" ] && continue
  if ! grep -Fxq "$rel" "$CONTENTS_LIST"; then
    echo "ERROR: tarball missing required source dependency: $rel"
    exit 1
  fi
done < "$REQ_LIST"

python3 - "$CONTENTS_LIST" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

contents_path = Path(sys.argv[1])
entries = [line.strip() for line in contents_path.read_text(encoding="utf-8").splitlines() if line.strip()]
entry_set = set(entries)
errors: list[str] = []

banned_exts = {
    ".aux",
    ".log",
    ".out",
    ".fls",
    ".fdb_latexmk",
    ".blg",
}

for rel in entries:
    p = Path(rel)
    if rel.endswith(".synctex.gz"):
        errors.append(rel)
        continue
    if p.suffix.lower() in banned_exts:
        errors.append(rel)
        continue
    if p.suffix.lower() == ".pdf":
        # Ban generated PDF siblings (e.g., paper/paper.pdf), but allow source figures.
        if p.with_suffix(".tex").as_posix() in entry_set:
            errors.append(rel)

if errors:
    print("forbidden generated artifacts in arXiv tarball:")
    for item in errors:
        print(f"- {item}")
    raise SystemExit(1)
PY

echo "arXiv bundle created: $OUT_TAR"
echo "required file list: $REQ_LIST"
echo "tarball contents list: $CONTENTS_LIST"
