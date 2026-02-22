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
LocationMap = dict[str, dict[str, int]]


def _join_path(prefix: str, key: str) -> str:
    if not prefix:
        return key
    return f"{prefix}.{key}"


def _index_path(prefix: str, index: int) -> str:
    if not prefix:
        return f"[{index}]"
    return f"{prefix}[{index}]"


class _Parser:
    def __init__(self, tokens: list[Token], *, source_path: str = "<input>") -> None:
        self.tokens = tokens
        self.pos = 0
        self.source_path = source_path
        self.locs: LocationMap = {}

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

    def _record_loc(self, field_path: str, token: Token) -> None:
        if not field_path:
            return
        if field_path in self.locs:
            return
        self.locs[field_path] = {"line": token.line, "col": token.col}

    def _error(self, message: str, *, token: Token | None = None) -> DslError:
        tok = self._cur() if token is None else token
        return DslError(
            message,
            line=tok.line,
            col=tok.col,
            start=tok.start,
            end=tok.end,
            path=self.source_path,
        )

    def _expect(self, kind: str) -> Token:
        tok = self._cur()
        if tok.kind != kind:
            raise self._error(f"expected token {kind}, got {tok.kind}", token=tok)
        return self._advance()

    def _parse_key(self) -> tuple[str, Token]:
        tok = self._cur()
        if tok.kind in {"IDENT", "STRING"}:
            self._advance()
            return str(tok.value), tok
        raise self._error(f"expected token IDENT, got {tok.kind}", token=tok)

    def parse_program(self) -> dict[str, Any]:
        root = self._parse_statements(until_kind="EOF", prefix="")
        self._expect("EOF")
        return root

    def _parse_statements(self, *, until_kind: str, prefix: str) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        while self._cur().kind != until_kind:
            tok = self._cur()
            if tok.kind == "SEMI":
                self._advance()
                continue

            key, key_tok = self._parse_key()
            field_path = _join_path(prefix, key)
            self._record_loc(field_path, key_tok)
            sep = self._cur()
            if sep.kind == "EQUAL":
                self._advance()
                value = self._parse_value(context_path=field_path)
                self._expect("SEMI")
                if key in obj:
                    raise self._error(f"duplicate key '{key}'", token=sep)
                obj[key] = value
                continue

            if sep.kind == "LBRACE":
                value = self._parse_object(context_path=field_path)
                if self._cur().kind == "SEMI":
                    self._advance()
                if key in obj:
                    raise self._error(f"duplicate key '{key}'", token=sep)
                obj[key] = value
                continue

            raise self._error(f"expected token EQUAL, got {sep.kind}", token=sep)

        return obj

    def _parse_object(self, *, context_path: str) -> dict[str, Any]:
        self._expect("LBRACE")
        body = self._parse_statements(until_kind="RBRACE", prefix=context_path)
        self._expect("RBRACE")
        return body

    def _parse_list(self, *, context_path: str) -> list[Any]:
        self._expect("LBRACKET")
        values: list[Any] = []
        if self._cur().kind == "RBRACKET":
            self._advance()
            return values

        idx = 0
        while True:
            item_tok = self._cur()
            item_path = _index_path(context_path, idx)
            self._record_loc(item_path, item_tok)
            values.append(self._parse_value(context_path=item_path))
            idx += 1
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

    def _parse_typed_object(self, tag_token: Token, *, context_path: str) -> dict[str, Any]:
        body = self._parse_object(context_path=context_path)
        out = dict(body)
        out["__tag__"] = str(tag_token.value)
        return out

    def _parse_value(self, *, context_path: str) -> Any:
        tok = self._cur()

        if tok.kind == "LBRACE":
            return self._parse_object(context_path=context_path)
        if tok.kind == "LBRACKET":
            return self._parse_list(context_path=context_path)
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
        if tok.kind == "FLOAT":
            self._advance()
            return float(tok.value)
        if tok.kind == "IDENT":
            self._advance()
            if self._cur().kind == "LPAREN":
                return self._parse_fixed_literal(tok)
            if self._cur().kind == "LBRACE":
                return self._parse_typed_object(tok, context_path=context_path)
            return str(tok.value)

        raise self._error(f"expected value, got {tok.kind}", token=tok)


def parse(source: str) -> dict[str, Any]:
    """Parse NEMA-DSL text into a root object (dict)."""
    root, _ = parse_with_locs(source, "<input>")
    return root


def parse_with_locs(source: str, path: str) -> tuple[dict[str, Any], LocationMap]:
    """Parse NEMA-DSL and return (AST object, field location map)."""
    parser = _Parser(lex(source), source_path=path)
    root = parser.parse_program()
    return root, dict(parser.locs)
