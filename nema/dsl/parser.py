"""Recursive-descent parser for NEMA-DSL v0.1 scaffold grammar."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import DslError
from .lexer import Token, lex


@dataclass(frozen=True)
class TimeLit:
    value: int
    unit: str


@dataclass(frozen=True)
class FixedLit:
    type_id: str
    raw: int
    unsigned: bool


_TIME_UNITS = {"ns", "us", "ms", "s"}


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _cur(self) -> Token:
        return self.tokens[self.pos]

    def _peek(self, offset: int = 1) -> Token:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def _advance(self) -> Token:
        tok = self._cur()
        if tok.kind != "EOF":
            self.pos += 1
        return tok

    def _error(self, message: str, *, token: Token | None = None) -> DslError:
        tok = self._cur() if token is None else token
        return DslError(message, line=tok.line, col=tok.col, start=tok.start, end=tok.end)

    def _expect(self, kind: str) -> Token:
        tok = self._cur()
        if tok.kind != kind:
            raise self._error(f"expected token {kind}, got {tok.kind}", token=tok)
        return self._advance()

    def _parse_key(self) -> str:
        tok = self._cur()
        if tok.kind in {"IDENT", "STRING"}:
            self._advance()
            return str(tok.value)
        raise self._error(f"expected token IDENT, got {tok.kind}", token=tok)

    def parse_program(self) -> dict[str, Any]:
        root = self._parse_statements(until_kind="EOF")
        self._expect("EOF")
        return root

    def _parse_statements(self, *, until_kind: str) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        while self._cur().kind != until_kind:
            tok = self._cur()
            if tok.kind == "SEMI":
                self._advance()
                continue

            key = self._parse_key()
            sep = self._cur()
            if sep.kind == "EQUAL":
                self._advance()
                value = self._parse_value()
                self._expect("SEMI")
                if key in obj:
                    raise self._error(f"duplicate key '{key}'", token=sep)
                obj[key] = value
                continue

            if sep.kind == "LBRACE":
                value = self._parse_object()
                if self._cur().kind == "SEMI":
                    self._advance()
                if key in obj:
                    raise self._error(f"duplicate key '{key}'", token=sep)
                obj[key] = value
                continue

            raise self._error(f"expected token EQUAL, got {sep.kind}", token=sep)

        return obj

    def _parse_object(self) -> dict[str, Any]:
        self._expect("LBRACE")
        body = self._parse_statements(until_kind="RBRACE")
        self._expect("RBRACE")
        return body

    def _parse_list(self) -> list[Any]:
        self._expect("LBRACKET")
        values: list[Any] = []
        if self._cur().kind == "RBRACKET":
            self._advance()
            return values

        while True:
            values.append(self._parse_value())
            if self._cur().kind != "COMMA":
                break
            self._advance()
            if self._cur().kind == "RBRACKET":
                break
        self._expect("RBRACKET")
        return values

    def _parse_time_literal(self, int_token: Token) -> TimeLit:
        unit_tok = self._cur()
        if unit_tok.kind != "IDENT":
            raise self._error(f"expected token IDENT, got {unit_tok.kind}", token=unit_tok)
        unit = str(unit_tok.value)
        if unit not in _TIME_UNITS:
            raise self._error(
                "expected time unit ns/us/ms/s",
                token=unit_tok,
            )
        self._advance()
        return TimeLit(value=int(int_token.value), unit=unit)

    def _parse_fixed_literal(self, type_token: Token) -> FixedLit:
        self._expect("LPAREN")
        raw_token = self._expect("INT")
        unsigned = False
        if self._cur().kind == "IDENT" and self._cur().value == "u":
            unsigned = True
            self._advance()
        self._expect("RPAREN")
        return FixedLit(type_id=str(type_token.value), raw=int(raw_token.value), unsigned=unsigned)

    def _parse_typed_object(self, tag_token: Token) -> dict[str, Any]:
        body = self._parse_object()
        out = dict(body)
        out["__tag__"] = str(tag_token.value)
        return out

    def _parse_value(self) -> Any:
        tok = self._cur()

        if tok.kind == "LBRACE":
            return self._parse_object()
        if tok.kind == "LBRACKET":
            return self._parse_list()
        if tok.kind == "STRING":
            self._advance()
            return tok.value
        if tok.kind == "BOOL":
            self._advance()
            return bool(tok.value)
        if tok.kind == "NULL":
            self._advance()
            return None
        if tok.kind == "INT":
            self._advance()
            if self._cur().kind == "IDENT" and str(self._cur().value) in _TIME_UNITS:
                return self._parse_time_literal(tok)
            return int(tok.value)
        if tok.kind == "IDENT":
            self._advance()
            if self._cur().kind == "LPAREN":
                return self._parse_fixed_literal(tok)
            if self._cur().kind == "LBRACE":
                return self._parse_typed_object(tok)
            return str(tok.value)

        raise self._error(f"expected value, got {tok.kind}", token=tok)


def parse(source: str) -> dict[str, Any]:
    """Parse NEMA-DSL text into a root object (dict)."""
    parser = _Parser(lex(source))
    return parser.parse_program()
