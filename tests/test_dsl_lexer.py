from __future__ import annotations

import pytest

from nema.dsl.errors import DslError
from nema.dsl.lexer import lex


def test_lex_mixed_comments_and_tokens() -> None:
    text = """
# hash comment
root { // slash comment
  enabled = true;
  count = -12;
  items = [1, 2, null]; # trailing hash
}
"""

    tokens = lex(text)
    kinds = [token.kind for token in tokens]
    values = [token.value for token in tokens]

    assert kinds == [
        "IDENT",
        "LBRACE",
        "IDENT",
        "EQUAL",
        "BOOL",
        "SEMI",
        "IDENT",
        "EQUAL",
        "INT",
        "SEMI",
        "IDENT",
        "EQUAL",
        "LBRACKET",
        "INT",
        "COMMA",
        "INT",
        "COMMA",
        "NULL",
        "RBRACKET",
        "SEMI",
        "RBRACE",
        "EOF",
    ]
    assert values[0] == "root"
    assert values[4] is True
    assert values[8] == -12
    assert values[13] == 1
    assert values[15] == 2
    assert values[17] is None


def test_lex_string_with_escapes() -> None:
    tokens = lex('msg = "a\\n\\t\\"\\\\b";')

    assert [tok.kind for tok in tokens] == ["IDENT", "EQUAL", "STRING", "SEMI", "EOF"]
    assert tokens[2].value == 'a\n\t"\\b'


def test_lex_unterminated_string_reports_line_col() -> None:
    text = 'a = "unterminated\nnext = 1;'

    with pytest.raises(DslError) as exc_info:
        lex(text)

    err = exc_info.value
    assert "unterminated string literal" in str(err)
    assert err.line == 1
    assert err.col == 5
