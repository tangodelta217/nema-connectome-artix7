"""Stable diagnostics primitives for NEMA-DSL v0.1."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


def normalize_path(path: str) -> str:
    """Normalize path for stable rendering and snapshot tests."""
    if not path:
        return "<input>"

    path_obj = Path(path)
    if not path_obj.is_absolute():
        return path

    cwd = Path.cwd()
    try:
        return str(path_obj.relative_to(cwd))
    except ValueError:
        return os.path.relpath(str(path_obj), start=str(cwd))


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: Severity
    path: str
    line: int
    col: int
    message: str
    hint: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "path": normalize_path(self.path),
            "line": self.line,
            "col": self.col,
            "message": self.message,
            "hint": self.hint,
            "note": self.note,
        }

    def format_text(self, no_color: bool = True) -> str:
        # Colors are intentionally disabled for deterministic v0.1 output.
        _ = no_color
        head = (
            f"{normalize_path(self.path)}:{self.line}:{self.col}: "
            f"{self.severity.value} {self.code}: {self.message}"
        )
        lines = [head]
        if self.hint:
            lines.append(f"  hint: {self.hint}")
        if self.note:
            lines.append(f"  note: {self.note}")
        return "\n".join(lines)


def sort_key(diag: Diagnostic) -> tuple[str, int, int, str]:
    return (normalize_path(diag.path), diag.line, diag.col, diag.code)
