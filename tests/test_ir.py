from __future__ import annotations

import json
from pathlib import Path

import pytest

from nema.ir import IRValidationError, load_ir, validate_ir


def write_valid_ir(path: Path) -> None:
    payload = {
        "constraints": {"allowedSpdx": ["MIT"]},
        "license": {"spdxId": "MIT"},
        "graph": {
            "nodes": [
                {"id": "n0", "index": 0, "canonicalOrderId": 0},
                {"id": "n1", "index": 1, "canonicalOrderId": 1},
            ],
            "edges": [
                {
                    "id": "e0",
                    "kind": "CHEMICAL",
                    "source": "n0",
                    "target": "n1",
                    "directed": True,
                    "conductance": 1.0,
                }
            ],
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_validate_ir_ok(tmp_path: Path) -> None:
    ir = tmp_path / "ok.json"
    write_valid_ir(ir)

    report = validate_ir(ir)

    assert report["ok"] is True
    assert "ir_sha256" in report


def test_validate_ir_rejects_non_object(tmp_path: Path) -> None:
    ir = tmp_path / "bad.json"
    ir.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(IRValidationError):
        load_ir(ir)


def test_validate_ir_rejects_empty_object(tmp_path: Path) -> None:
    ir = tmp_path / "empty.json"
    ir.write_text("{}", encoding="utf-8")

    with pytest.raises(IRValidationError):
        load_ir(ir)
