"""IR loading and lightweight invariant checks for scaffold commands."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class IRValidationError(ValueError):
    """Raised when an IR file fails invariant checks."""


def load_ir(path: Path) -> tuple[dict, str]:
    """Load an IR JSON file and return (payload, sha256)."""
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise IRValidationError(f"invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise IRValidationError("top-level JSON value must be an object")
    if not payload:
        raise IRValidationError("top-level JSON object must not be empty")

    return payload, digest


def validate_ir(path: Path) -> dict:
    """Return a validation report for basic scaffold invariants."""
    payload, digest = load_ir(path)
    return {
        "ok": True,
        "ir_sha256": digest,
        "invariants_checked": [
            "json_parseable",
            "top_level_is_object",
            "top_level_not_empty",
        ],
        "top_level_keys": sorted(payload.keys()),
    }
