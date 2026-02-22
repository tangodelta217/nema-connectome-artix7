"""DSL error types."""

from __future__ import annotations


class DslError(Exception):
    """Base DSL error carrying optional line/column source location."""

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        col: int | None = None,
        start: int | None = None,
        end: int | None = None,
    ) -> None:
        self.message = message
        self.line = line
        self.col = col
        self.start = start
        self.end = end
        super().__init__(self.__str__())

    def __str__(self) -> str:
        if self.line is None and self.col is None:
            return self.message
        if self.line is None:
            return f"{self.message} (col {self.col})"
        if self.col is None:
            return f"{self.message} (line {self.line})"
        return f"{self.message} (line {self.line}, col {self.col})"
