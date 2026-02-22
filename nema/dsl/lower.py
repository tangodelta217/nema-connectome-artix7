"""NEMA-DSL lowering scaffold (NYI)."""

from __future__ import annotations

from .errors import DslError


def lower_to_ir(_ast: object) -> dict:
    """Lower typed AST to IR JSON dict. Not implemented in scaffold phase."""
    raise DslError("NYI: NEMA-DSL lower v0.1 scaffold")
