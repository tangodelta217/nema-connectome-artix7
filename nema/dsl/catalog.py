"""Diagnostic catalog (single source of truth) for NEMA-DSL v0.1."""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import Diagnostic, Severity


@dataclass(frozen=True)
class _Template:
    message: str
    hint: str | None = None
    note: str | None = None


_CATALOG: dict[str, _Template] = {
    "DSL0001": _Template(
        message="unexpected character '{char}'",
        hint="remove the character or escape it inside a string literal",
    ),
    "DSL0002": _Template(
        message="unterminated string literal",
        hint='close the string with a matching double quote (\")',
    ),
    "DSL0003": _Template(
        message="invalid string escape '\\{escape}'",
        hint=r"use one of: \" \\ \n \t",
    ),
    "DSL0004": _Template(
        message="expected token {expected}, got {actual}",
    ),
    "DSL0005": _Template(
        message="expected value, got {actual}",
    ),
    "DSL0006": _Template(
        message="duplicate key '{key}'",
        hint="keep only one assignment/block for each key at the same object level",
    ),
    "DSL0007": _Template(
        message="expected time unit ns/us/ms/s",
        hint="append one valid unit to the integer literal (example: 15ms)",
    ),
    "DSL0008": _Template(
        message="invalid fixed literal suffix '{suffix}'",
        hint="use signed form TypeId(INT) or unsigned form TypeId(INTu)",
    ),
    "DSL0009": _Template(
        message="failed to read file: {detail}",
    ),
    "DSL0010": _Template(
        message="failed to write file: {detail}",
    ),
    "DSL0011": _Template(
        message="invalid JSON input: {detail}",
    ),
    "DSL0012": _Template(
        message="IR validation failed: {detail}",
    ),
    "DSL0013": _Template(
        message="dsl hwtest requires root field 'modelId'",
        hint="set a non-empty root key: modelId = <IDENT|STRING>;",
    ),
    "DSL0014": _Template(
        message="unknown DSL subcommand '{command}'",
    ),
    "DSL0015": _Template(
        message="{detail}",
    ),
}


def _render_template(template: str | None, kwargs: dict[str, object]) -> str | None:
    if template is None:
        return None
    return template.format(**kwargs)


def make_diag(
    code: str,
    severity: Severity,
    path: str,
    line: int,
    col: int,
    **kwargs: object,
) -> Diagnostic:
    template = _CATALOG.get(code)
    if template is None:
        raise ValueError(f"unknown diagnostic code: {code}")

    message = _render_template(template.message, kwargs)
    hint = _render_template(template.hint, kwargs)
    note = _render_template(template.note, kwargs)
    return Diagnostic(
        code=code,
        severity=severity,
        path=path,
        line=line,
        col=col,
        message=message or "",
        hint=hint,
        note=note,
    )


def known_codes() -> list[str]:
    return sorted(_CATALOG.keys())
