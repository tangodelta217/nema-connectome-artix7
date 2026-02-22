from __future__ import annotations

import json

from nema.dsl.diagnostics import Diagnostic, Severity, sort_key


def test_diagnostics_text_render_and_sort_order_are_stable() -> None:
    first = Diagnostic(
        code="DSL0004",
        severity=Severity.ERROR,
        path="programs/b3_kernel_302.nema",
        line=9,
        col=13,
        message="expected token SEMI, got IDENT",
        hint="add ';' after the assignment",
        note="parser stopped at next statement boundary",
    )
    second = Diagnostic(
        code="DSLW0001",
        severity=Severity.WARNING,
        path="programs/b1_small.nema",
        line=1,
        col=1,
        message="deprecated field alias",
        hint="use canonical field names",
        note=None,
    )

    ordered = sorted([first, second], key=sort_key)
    assert [diag.path for diag in ordered] == [
        "programs/b1_small.nema",
        "programs/b3_kernel_302.nema",
    ]

    assert ordered[0].format_text(no_color=True) == (
        "programs/b1_small.nema:1:1: WARNING DSLW0001: deprecated field alias\n"
        "  hint: use canonical field names"
    )
    assert ordered[1].format_text(no_color=True) == (
        "programs/b3_kernel_302.nema:9:13: ERROR DSL0004: expected token SEMI, got IDENT\n"
        "  hint: add ';' after the assignment\n"
        "  note: parser stopped at next statement boundary"
    )


def test_diagnostics_json_render_is_stable() -> None:
    diagnostics = [
        Diagnostic(
            code="DSL0001",
            severity=Severity.ERROR,
            path="programs/b1_small.nema",
            line=3,
            col=7,
            message="unexpected character '@'",
            hint="remove the character or quote it in a string",
            note=None,
        ),
        Diagnostic(
            code="DSL0002",
            severity=Severity.ERROR,
            path="programs/b1_small.nema",
            line=4,
            col=9,
            message="unterminated string literal",
            hint='close the string with a matching quote (\")',
            note="string started at line 4, col 9",
        ),
    ]
    payload = {"ok": False, "diagnostics": [diag.to_dict() for diag in diagnostics]}
    rendered = json.dumps(payload, indent=2, sort_keys=True)

    assert rendered == (
        '{\n'
        '  "diagnostics": [\n'
        "    {\n"
        '      "code": "DSL0001",\n'
        '      "col": 7,\n'
        '      "hint": "remove the character or quote it in a string",\n'
        '      "line": 3,\n'
        '      "message": "unexpected character \'@\'",\n'
        '      "note": null,\n'
        '      "path": "programs/b1_small.nema",\n'
        '      "severity": "ERROR"\n'
        "    },\n"
        "    {\n"
        '      "code": "DSL0002",\n'
        '      "col": 9,\n'
        '      "hint": "close the string with a matching quote (\\")",\n'
        '      "line": 4,\n'
        '      "message": "unterminated string literal",\n'
        '      "note": "string started at line 4, col 9",\n'
        '      "path": "programs/b1_small.nema",\n'
        '      "severity": "ERROR"\n'
        "    }\n"
        "  ],\n"
        '  "ok": false\n'
        "}"
    )
