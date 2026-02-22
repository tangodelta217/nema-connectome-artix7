"""NEMA-DSL lexer for v0.1 scaffold grammar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import DslError


@dataclass(frozen=True)
class Token:
    kind: str
    value: Any
    line: int
    col: int
    start: int
    end: int


_PUNCT_TOKENS = {
    "{": "LBRACE",
    "}": "RBRACE",
    "[": "LBRACKET",
    "]": "RBRACKET",
    "(": "LPAREN",
    ")": "RPAREN",
    ",": "COMMA",
    ";": "SEMI",
    "=": "EQUAL",
}

_STRING_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "n": "\n",
    "t": "\t",
}


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_ident_part(ch: str) -> bool:
    return ch.isalnum() or ch in {"_", ".", "-", "/"}


def lex(text: str) -> list[Token]:
    """Tokenize DSL text into a flat token stream."""
    i = 0
    n = len(text)
    line = 1
    col = 1
    tokens: list[Token] = []

    def error(message: str, *, err_line: int, err_col: int, start: int, end: int | None = None) -> DslError:
        return DslError(
            message,
            line=err_line,
            col=err_col,
            start=start,
            end=(start if end is None else end),
        )

    def push(kind: str, value: Any, tok_line: int, tok_col: int, start: int, end: int) -> None:
        tokens.append(Token(kind=kind, value=value, line=tok_line, col=tok_col, start=start, end=end))

    def advance() -> str:
        nonlocal i, line, col
        ch = text[i]
        i += 1
        if ch == "\n":
            line += 1
            col = 1
        else:
            col += 1
        return ch

    while i < n:
        ch = text[i]

        if ch in {" ", "\t", "\r", "\n"}:
            advance()
            continue

        if ch == "#":
            while i < n and text[i] != "\n":
                advance()
            continue

        if ch == "/" and (i + 1) < n and text[i + 1] == "/":
            advance()
            advance()
            while i < n and text[i] != "\n":
                advance()
            continue

        if ch in _PUNCT_TOKENS:
            start = i
            tok_line, tok_col = line, col
            kind = _PUNCT_TOKENS[ch]
            advance()
            push(kind, ch, tok_line, tok_col, start, i)
            continue

        if ch == '"':
            start = i
            tok_line, tok_col = line, col
            advance()  # opening quote
            parts: list[str] = []
            terminated = False
            while i < n:
                cur = text[i]
                if cur == '"':
                    advance()
                    terminated = True
                    break
                if cur == "\\":
                    esc_pos = i
                    advance()
                    if i >= n:
                        raise error(
                            "unterminated string literal",
                            err_line=tok_line,
                            err_col=tok_col,
                            start=start,
                            end=esc_pos + 1,
                        )
                    esc_ch = text[i]
                    mapped = _STRING_ESCAPES.get(esc_ch)
                    if mapped is None:
                        raise error(
                            f"invalid string escape '\\{esc_ch}'",
                            err_line=line,
                            err_col=col,
                            start=i,
                            end=i + 1,
                        )
                    advance()
                    parts.append(mapped)
                    continue
                if cur == "\n":
                    raise error(
                        "unterminated string literal",
                        err_line=tok_line,
                        err_col=tok_col,
                        start=start,
                        end=i,
                    )
                parts.append(cur)
                advance()
            if not terminated:
                raise error(
                    "unterminated string literal",
                    err_line=tok_line,
                    err_col=tok_col,
                    start=start,
                    end=i,
                )
            push("STRING", "".join(parts), tok_line, tok_col, start, i)
            continue

        if ch == "-" and (i + 1) < n and text[i + 1].isdigit():
            start = i
            tok_line, tok_col = line, col
            advance()
            while i < n and text[i].isdigit():
                advance()
            is_float = False
            if i < n and text[i] == "." and (i + 1) < n and text[i + 1].isdigit():
                is_float = True
                advance()
                while i < n and text[i].isdigit():
                    advance()
            raw = text[start:i]
            if is_float:
                push("FLOAT", float(raw), tok_line, tok_col, start, i)
            else:
                push("INT", int(raw), tok_line, tok_col, start, i)
            continue

        if ch.isdigit():
            start = i
            tok_line, tok_col = line, col
            while i < n and text[i].isdigit():
                advance()
            is_float = False
            if i < n and text[i] == "." and (i + 1) < n and text[i + 1].isdigit():
                is_float = True
                advance()
                while i < n and text[i].isdigit():
                    advance()
            raw = text[start:i]
            if is_float:
                push("FLOAT", float(raw), tok_line, tok_col, start, i)
            else:
                push("INT", int(raw), tok_line, tok_col, start, i)
            continue

        if _is_ident_start(ch):
            start = i
            tok_line, tok_col = line, col
            advance()
            while i < n and _is_ident_part(text[i]):
                advance()
            raw = text[start:i]
            if raw == "true":
                push("BOOL", True, tok_line, tok_col, start, i)
            elif raw == "false":
                push("BOOL", False, tok_line, tok_col, start, i)
            elif raw == "null":
                push("NULL", None, tok_line, tok_col, start, i)
            else:
                push("IDENT", raw, tok_line, tok_col, start, i)
            continue

        raise error(
            f"unexpected character '{ch}'",
            err_line=line,
            err_col=col,
            start=i,
            end=i + 1,
        )

    push("EOF", None, line, col, i, i)
    return tokens
