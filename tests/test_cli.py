from __future__ import annotations

import json
from pathlib import Path

from nema.cli import main


def write_ir(path: Path) -> None:
    path.write_text(json.dumps({"graph": {"nodes": []}}), encoding="utf-8")


def test_check_command_ok(tmp_path: Path, capsys) -> None:
    ir = tmp_path / "ir.json"
    write_ir(ir)

    code = main(["check", str(ir)])

    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is True
    assert "ir_sha256" in payload


def test_sim_creates_trace(tmp_path: Path) -> None:
    ir = tmp_path / "ir.json"
    out = tmp_path / "trace.jsonl"
    write_ir(ir)

    code = main(["sim", str(ir), "--ticks", "3", "--out", str(out)])

    assert code == 0
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert first["tick"] == 0


def test_compile_creates_kernel_and_manifest(tmp_path: Path) -> None:
    ir = tmp_path / "ir.json"
    outdir = tmp_path / "build"
    write_ir(ir)

    code = main(["compile", str(ir), "--outdir", str(outdir)])

    assert code == 0
    assert (outdir / "kernel.cpp").exists()
    assert (outdir / "compile_manifest.json").exists()


def test_hwtest_emits_bench_report(tmp_path: Path) -> None:
    ir = tmp_path / "ir.json"
    outdir = tmp_path / "build"
    write_ir(ir)

    code = main(["hwtest", str(ir), "--outdir", str(outdir), "--ticks", "2"])

    assert code == 0
    report_path = outdir / "bench_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["ticks"] == 2


def test_selftest_fixed_ok(capsys) -> None:
    code = main(["selftest", "fixed"])

    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["suite"] == "fixed"
