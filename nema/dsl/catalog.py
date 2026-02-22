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
    "NEMA-DSL1001": _Template(
        message="unterminated string",
        hint='close the string with a matching double quote (\")',
    ),
    "NEMA-DSL1002": _Template(
        message="invalid escape",
        hint=r"use one of: \" \\ \n \t",
    ),
    "NEMA-DSL1101": _Template(
        message="unexpected token",
        hint="check token order and block delimiters",
        note="expected: {expected}; got: {actual}",
    ),
    "NEMA-DSL1102": _Template(
        message="missing semicolon",
        hint="terminate assignments with ';'",
    ),
    "NEMA-DSL1103": _Template(
        message="duplicate key in same object",
        hint="keep only one assignment/block per key within a single object",
        note="duplicate key: {key}",
    ),
    "NEMA-DSL2001": _Template(
        message="missing required top-level field",
        hint="add required root field '{field}'",
        note="missing field: {field}",
    ),
    "NEMA-DSL2002": _Template(
        message='unsupported irVersion (expected "0.1")',
        hint='set irVersion = "0.1"',
        note="got: {got}",
    ),
    "NEMA-DSL2101": _Template(
        message="graph must define exactly one of {{inline, external}}",
        hint="define either graph.inline or graph.external, but not both",
    ),
    "NEMA-DSL2201": _Template(
        message="external.sha256 placeholder",
        hint="replace placeholder with real sha256:<digest>",
        note="mode: {mode}",
    ),
    "NEMA-DSL2202": _Template(
        message="external artifact missing or sha mismatch",
        hint="provide an existing external artifact and matching sha256",
        note="{detail}",
    ),
    "NEMA-DSL2301": _Template(
        message="qformats.*TypeId references unknown typeId",
        hint="define referenced typeId in typeTable",
        note="{field} -> {type_id}",
    ),
    "NEMA-DSL2302": _Template(
        message="schedule policy/snapshotRule mismatch (must be nema.tick.v0.1 and snapshotRule=true)",
        hint="set schedule.policy = nema.tick.v0.1 and schedule.snapshotRule = true",
    ),
    "NEMA-DSL2303": _Template(
        message="non-negative conductance violated",
        hint="set conductance >= 0",
        note="value: {value}",
    ),
    "NEMA-DSL2304": _Template(
        message="license.spdxId not in constraints.allowedSpdx",
        hint="add license.spdxId to constraints.allowedSpdx or change spdxId",
        note="spdxId: {spdx_id}",
    ),
    "NEMA-DSL2401": _Template(
        message="HW toolchain unavailable (vitis_hls/vivado)",
        hint="install vitis_hls/vivado or run software-only mode",
    ),
    "NEMA-DSL2501": _Template(
        message="include loop detected",
        hint="remove cyclic include chain",
        note="{detail}",
    ),
    "NEMA-DSL2502": _Template(
        message="include directives must appear at top of file",
        hint='move include statements before any non-comment statement',
    ),
    "NEMA-DSL2503": _Template(
        message="undefined const reference",
        hint="define const NAME before use",
        note="name: {name}",
    ),
    "NEMA-DSL2504": _Template(
        message="duplicate const definition",
        hint="keep a single const NAME definition",
        note="name: {name}",
    ),
    "NEMA-DSL2999": _Template(
        message="IR validation failed",
        hint="fix semantic issues before IR validation",
        note="{detail}",
    ),
    "NEMA-DSL9001": _Template(
        message="{detail}",
    ),
    "NEMA-DSL9002": _Template(
        message="failed to read file",
        hint="{detail}",
    ),
    "NEMA-DSL9003": _Template(
        message="failed to write file",
        hint="{detail}",
    ),
    "NEMA-DSL9004": _Template(
        message="unknown DSL subcommand",
        note="{command}",
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
