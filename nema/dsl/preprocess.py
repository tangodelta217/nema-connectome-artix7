"""NEMA-DSL v0.2 textual preprocessor (include + const)."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .catalog import make_diag
from .diagnostics import Diagnostic, Severity
from .errors import DslError

PREPROCESSED_PATH = "<preprocessed>"

_INCLUDE_RE = re.compile(r'^\s*include\s+"([^"]+)"\s*;\s*(?:(?://|#).*)?$')
_CONST_RE = re.compile(r"^\s*const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*;\s*(?:(?://|#).*)?$")
_PLACEHOLDER_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_ESCAPE_DECODE = {
    '"': '"',
    "\\": "\\",
    "n": "\n",
    "t": "\t",
}
_ESCAPE_ENCODE = {
    "\n": r"\n",
    "\t": r"\t",
    "\\": r"\\",
    '"': r"\"",
}


@dataclass(frozen=True)
class _ConstValue:
    raw: str
    string_embed: str
    defined_path: str
    defined_line: int


@dataclass(frozen=True)
class _LineOrigin:
    source_path: str
    source_line: int
    source_line_len: int
    col_map: tuple[int, ...]


@dataclass(frozen=True)
class SourceMap:
    lines: tuple[_LineOrigin, ...]

    def map(self, line: int, col: int) -> tuple[str, int, int]:
        if not self.lines:
            return (PREPROCESSED_PATH, 1, 1)

        if line < 1:
            idx = 0
        elif line > len(self.lines):
            idx = len(self.lines) - 1
        else:
            idx = line - 1
        origin = self.lines[idx]

        if col < 1:
            mapped_col = 1
        elif origin.col_map:
            max_col = len(origin.col_map)
            mapped_col = origin.col_map[min(col, max_col) - 1]
        else:
            mapped_col = min(max(col, 1), origin.source_line_len + 1)

        if mapped_col < 1:
            mapped_col = 1
        return (origin.source_path, origin.source_line, mapped_col)

    def remap_diagnostic(self, diagnostic: Diagnostic) -> Diagnostic:
        if diagnostic.path != PREPROCESSED_PATH:
            return diagnostic
        path, line, col = self.map(diagnostic.line, diagnostic.col)
        return replace(diagnostic, path=path, line=line, col=col)

    def remap_locs(self, locs: dict[str, dict[str, int]]) -> dict[str, dict[str, Any]]:
        remapped: dict[str, dict[str, Any]] = {}
        for key, raw in locs.items():
            if not isinstance(raw, dict):
                continue
            line = raw.get("line")
            col = raw.get("col")
            if not isinstance(line, int) or not isinstance(col, int):
                continue
            mapped_path, mapped_line, mapped_col = self.map(line, col)
            remapped[key] = {"path": mapped_path, "line": mapped_line, "col": mapped_col}
        return remapped


@dataclass(frozen=True)
class PreprocessResult:
    text: str
    source_map: SourceMap
    dependencies: tuple[str, ...]

    def remap_error(self, exc: DslError) -> DslError:
        mapped = self.source_map.remap_diagnostic(exc.diagnostic)
        if mapped == exc.diagnostic:
            return exc
        return DslError(
            mapped.message,
            diagnostic=mapped,
            start=exc.start,
            end=exc.end,
        )


def _encode_for_string(decoded: str) -> str:
    parts: list[str] = []
    for ch in decoded:
        parts.append(_ESCAPE_ENCODE.get(ch, ch))
    return "".join(parts)


def _decode_string_literal(raw: str) -> str | None:
    if len(raw) < 2 or raw[0] != '"' or raw[-1] != '"':
        return None
    body = raw[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        i += 1
        if i >= len(body):
            return None
        esc = body[i]
        mapped = _ESCAPE_DECODE.get(esc)
        if mapped is None:
            return None
        out.append(mapped)
        i += 1
    return "".join(out)


def _is_comment_or_blank(line: str) -> bool:
    stripped = line.strip()
    return stripped == "" or stripped.startswith("#") or stripped.startswith("//")


def _diag(
    *,
    code: str,
    path: Path,
    line: int,
    col: int,
    detail: str | None = None,
    name: str | None = None,
) -> Diagnostic:
    kwargs: dict[str, object] = {}
    if detail is not None:
        kwargs["detail"] = detail
    if name is not None:
        kwargs["name"] = name
    return make_diag(
        code=code,
        severity=Severity.ERROR,
        path=str(path),
        line=line,
        col=col,
        **kwargs,
    )


def _substitute_text(
    text: str,
    *,
    consts: dict[str, _ConstValue],
    path: Path,
    line_no: int,
    start_col: int = 1,
) -> tuple[str, list[int]]:
    out_chars: list[str] = []
    col_map: list[int] = []
    i = 0
    source_col = start_col
    in_string = False
    escaped = False

    while i < len(text):
        ch = text[i]
        if ch == "$" and (i + 1) < len(text) and text[i + 1] == "{":
            match = _PLACEHOLDER_RE.match(text[i:])
            if match is None:
                # Leave malformed placeholder untouched for downstream parser errors.
                out_chars.append(ch)
                col_map.append(source_col)
                i += 1
                source_col += 1
                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == '"':
                        in_string = False
                elif ch == '"':
                    in_string = True
                continue

            name = match.group(1)
            const_value = consts.get(name)
            if const_value is None:
                raise DslError(
                    "undefined const reference",
                    diagnostic=_diag(
                        code="NEMA-DSL2503",
                        path=path,
                        line=line_no,
                        col=source_col,
                        name=name,
                    ),
                )

            replacement = const_value.string_embed if in_string else const_value.raw
            placeholder_len = len(match.group(0))
            for _ in replacement:
                out_chars.append(_)
                col_map.append(source_col)
            i += placeholder_len
            source_col += placeholder_len
            continue

        out_chars.append(ch)
        col_map.append(source_col)
        i += 1
        source_col += 1

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True

    return "".join(out_chars), col_map


def preprocess_file(path: Path) -> PreprocessResult:
    """Expand include + const directives into a deterministic source blob."""
    entry = path.resolve()
    consts: dict[str, _ConstValue] = {}
    dependencies: list[str] = []
    out_lines: list[str] = []
    origins: list[_LineOrigin] = []

    def process_file(file_path: Path, stack: list[Path]) -> None:
        if file_path in stack:
            chain = " -> ".join(item.name for item in [*stack, file_path])
            raise DslError(
                "include loop detected",
                diagnostic=_diag(
                    code="NEMA-DSL2501",
                    path=stack[-1],
                    line=1,
                    col=1,
                    detail=chain,
                ),
            )

        try:
            raw = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DslError(
                "failed to read file",
                diagnostic=make_diag(
                    code="NEMA-DSL9002",
                    severity=Severity.ERROR,
                    path=str(file_path),
                    line=1,
                    col=1,
                    detail=str(exc),
                ),
            ) from exc

        dependencies.append(str(file_path))
        lines = raw.splitlines()
        include_phase = True
        next_stack = [*stack, file_path]

        for idx, line in enumerate(lines, start=1):
            include_match = _INCLUDE_RE.match(line)
            if include_match:
                if not include_phase:
                    raise DslError(
                        "include directives must appear at top of file",
                        diagnostic=_diag(
                            code="NEMA-DSL2502",
                            path=file_path,
                            line=idx,
                            col=line.find("include") + 1 if "include" in line else 1,
                        ),
                    )

                rel = include_match.group(1)
                include_path = (file_path.parent / rel).resolve()
                if include_path in next_stack:
                    chain = " -> ".join(item.name for item in [*next_stack, include_path])
                    raise DslError(
                        "include loop detected",
                        diagnostic=_diag(
                            code="NEMA-DSL2501",
                            path=file_path,
                            line=idx,
                            col=line.find("include") + 1 if "include" in line else 1,
                            detail=chain,
                        ),
                    )
                process_file(include_path, next_stack)
                continue

            if not _is_comment_or_blank(line):
                include_phase = False

            const_match = _CONST_RE.match(line)
            if const_match:
                name = const_match.group(1)
                raw_value = const_match.group(2)
                value_col = line.find(raw_value) + 1 if raw_value else line.find("=") + 1
                substituted, _ = _substitute_text(
                    raw_value,
                    consts=consts,
                    path=file_path,
                    line_no=idx,
                    start_col=value_col,
                )
                if name in consts:
                    raise DslError(
                        "duplicate const definition",
                        diagnostic=_diag(
                            code="NEMA-DSL2504",
                            path=file_path,
                            line=idx,
                            col=line.find(name) + 1 if name in line else 1,
                            name=name,
                        ),
                    )
                decoded = _decode_string_literal(substituted.strip())
                string_embed = _encode_for_string(decoded) if decoded is not None else substituted.strip()
                consts[name] = _ConstValue(
                    raw=substituted.strip(),
                    string_embed=string_embed,
                    defined_path=str(file_path),
                    defined_line=idx,
                )
                continue

            substituted_line, col_map = _substitute_text(
                line,
                consts=consts,
                path=file_path,
                line_no=idx,
                start_col=1,
            )
            out_lines.append(substituted_line)
            origins.append(
                _LineOrigin(
                    source_path=str(file_path),
                    source_line=idx,
                    source_line_len=len(line),
                    col_map=tuple(col_map),
                )
            )

    process_file(entry, [])
    text = "\n".join(out_lines) + ("\n" if out_lines else "")
    return PreprocessResult(
        text=text,
        source_map=SourceMap(lines=tuple(origins)),
        dependencies=tuple(dependencies),
    )
