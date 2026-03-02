#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE_DIR="${1:-$ROOT/build/arxiv_bundle_stage}"
MAIN_REL="${2:-${ARXIV_MAIN_REL:-paper/paper.tex}}"
LATEX_LOG="${3:-$ROOT/build/arxiv_bundle_latexmk.log}"

README_PATH="$STAGE_DIR/00README.XXX"
MAIN_PATH="$STAGE_DIR/$MAIN_REL"

if [ ! -d "$STAGE_DIR" ]; then
  echo "ERROR: preflight stage directory missing: $STAGE_DIR"
  exit 1
fi
if [ ! -f "$README_PATH" ]; then
  echo "ERROR: required file missing in stage: 00README.XXX"
  exit 1
fi
if [ ! -f "$MAIN_PATH" ]; then
  echo "ERROR: main TeX missing in stage: $MAIN_REL"
  exit 1
fi

python3 - "$MAIN_PATH" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

main_path = Path(sys.argv[1])
text = main_path.read_text(encoding="utf-8", errors="replace")

lines: list[str] = []
for line in text.splitlines():
    idx = line.find("%")
    if idx >= 0:
        lines.append(line[:idx])
    else:
        lines.append(line)
clean = "\n".join(lines)

if "\\documentclass" not in clean:
    raise SystemExit(f"missing \\documentclass in staged main TeX: {main_path}")
PY

if command -v latexmk >/dev/null 2>&1; then
  echo "Running LaTeX preflight compile (non-interactive): $MAIN_REL"
  if ! (cd "$STAGE_DIR" && latexmk -cd -pdf -interaction=nonstopmode -halt-on-error "$MAIN_REL" > "$LATEX_LOG" 2>&1); then
    echo "ERROR: latexmk preflight failed. See $LATEX_LOG"
    exit 1
  fi

  # Keep bundle source-only after preflight compile.
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
else
  echo "latexmk not available; structural preflight checks passed (00README.XXX + \\documentclass)."
fi
