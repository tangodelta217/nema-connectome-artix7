"""DSL error types and helpers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .catalog import make_diag
from .diagnostics import Diagnostic, Severity


class DslError(Exception):
    """DSL exception carrying a structured diagnostic."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "NEMA-DSL9001",
        severity: Severity = Severity.ERROR,
        path: str = "<input>",
        line: int | None = None,
        col: int | None = None,
        start: int | None = None,
        end: int | None = None,
        hint: str | None = None,
        note: str | None = None,
        diagnostic: Diagnostic | None = None,
    ) -> None:
        resolved_line = 1 if line is None else line
        resolved_col = 1 if col is None else col
        if diagnostic is None:
            diagnostic = Diagnostic(
                code=code,
                severity=severity,
                path=path,
                line=resolved_line,
                col=resolved_col,
                message=message,
                hint=hint,
                note=note,
            )
        self.diagnostic = diagnostic
        self.message = diagnostic.message
        self.line = diagnostic.line
        self.col = diagnostic.col
        self.start = start
        self.end = end
        super().__init__(self.__str__())

    def __str__(self) -> str:
        return self.diagnostic.format_text(no_color=True)


def _resolve_location(token_or_loc: Any) -> tuple[str, int, int, int | None, int | None]:
    if token_or_loc is None:
        return ("<input>", 1, 1, None, None)

    if isinstance(token_or_loc, tuple):
        if len(token_or_loc) >= 3:
            path, line, col = token_or_loc[0], token_or_loc[1], token_or_loc[2]
            return (str(path), int(line), int(col), None, None)
        if len(token_or_loc) == 2:
            line, col = token_or_loc
            return ("<input>", int(line), int(col), None, None)

    if isinstance(token_or_loc, dict):
        return (
            str(token_or_loc.get("path", "<input>")),
            int(token_or_loc.get("line", 1)),
            int(token_or_loc.get("col", 1)),
            token_or_loc.get("start"),
            token_or_loc.get("end"),
        )

    return (
        str(getattr(token_or_loc, "path", "<input>")),
        int(getattr(token_or_loc, "line", 1)),
        int(getattr(token_or_loc, "col", 1)),
        getattr(token_or_loc, "start", None),
        getattr(token_or_loc, "end", None),
    )


def raise_error(
    code: str,
    token_or_loc: Any,
    message: str,
    hint: str | None = None,
    note: str | None = None,
) -> None:
    path, line, col, start, end = _resolve_location(token_or_loc)
    diag = make_diag(
        code=code,
        severity=Severity.ERROR,
        path=path,
        line=line,
        col=col,
        detail=message,
        got=message,
        expected=message,
        field=message,
        type_id=message,
        key=message,
        value=message,
        spdx_id=message,
        mode=message,
    )
    if hint is not None:
        diag = replace(diag, hint=hint)
    if note is not None:
        diag = replace(diag, note=note)
    raise DslError(
        message=diag.message,
        diagnostic=diag,
        start=start,
        end=end,
    )
