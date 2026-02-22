from __future__ import annotations

from pathlib import Path


def test_spec_md_exists() -> None:
    assert Path("spec.md").is_file(), "missing required normative file: ./spec.md"


def test_nema_ir_proto_exists() -> None:
    assert Path("nema_ir.proto").is_file(), "missing required normative file: ./nema_ir.proto"


def test_spec_header_contains_v0_1() -> None:
    spec_path = Path("spec.md")
    assert spec_path.is_file(), "missing required normative file: ./spec.md"
    lines = spec_path.read_text(encoding="utf-8").splitlines()
    header = next((line for line in lines if line.strip()), "")
    assert "v0.1" in header.lower(), "spec.md header must contain 'v0.1'"
