from __future__ import annotations

import json
from pathlib import Path

import pytest

from nema.ir import IRValidationError, validate_ir


def test_validate_ir_ok(tmp_path: Path) -> None:
    ir = tmp_path / "ok.json"
    ir.write_text(json.dumps({"graph": {}}), encoding="utf-8")

    report = validate_ir(ir)

    assert report["ok"] is True
    assert "ir_sha256" in report


def test_validate_ir_rejects_non_object(tmp_path: Path) -> None:
    ir = tmp_path / "bad.json"
    ir.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(IRValidationError):
        validate_ir(ir)


def test_validate_ir_rejects_empty_object(tmp_path: Path) -> None:
    ir = tmp_path / "empty.json"
    ir.write_text("{}", encoding="utf-8")

    with pytest.raises(IRValidationError):
        validate_ir(ir)
