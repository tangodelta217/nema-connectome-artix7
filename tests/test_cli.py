from __future__ import annotations

import json
from pathlib import Path

from nema.cli import main


def write_ir(path: Path) -> None:
    lut_path = Path("artifacts/luts/tanh_q8_8.bin").resolve()
    payload = {
        "constraints": {"allowedSpdx": ["MIT"]},
        "license": {"spdxId": "MIT"},
        "graph": {
            "nodes": [
                {"id": "n0", "index": 0, "canonicalOrderId": 0, "vInitRaw": 128, "tauM": 2.0},
                {"id": "n1", "index": 1, "canonicalOrderId": 1, "vInitRaw": -64, "tauM": 3.0},
            ],
            "edges": [
                {
                    "id": "e0",
                    "kind": "CHEMICAL",
                    "source": "n0",
                    "target": "n1",
                    "directed": True,
                    "conductance": 0.1,
                }
            ],
            "dt": 1.0,
        },
        "tanhLut": {
            "policy": "nema.tanh_lut.v0.1",
            "artifact": str(lut_path),
            "inputType": "Q8.8",
            "outputType": "Q8.8",
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


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
    assert (tmp_path / "digest.json").exists()


def test_compile_creates_kernel_and_manifest(tmp_path: Path) -> None:
    ir = tmp_path / "ir.json"
    outdir = tmp_path / "build"
    write_ir(ir)

    code = main(["compile", str(ir), "--outdir", str(outdir)])

    assert code == 0
    # Inspect generated model directory by searching for compile_manifest.json
    manifests = list(outdir.glob("*/compile_manifest.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    assert Path(artifacts["hls_header"]).exists()
    assert Path(artifacts["hls_cpp"]).exists()
    assert Path(artifacts["cpp_ref_main"]).exists()


def test_dump_csr_creates_json(tmp_path: Path) -> None:
    ir = tmp_path / "ir.json"
    out = tmp_path / "csr_dump.json"
    write_ir(ir)

    code = main(["dump-csr", str(ir), "--out", str(out)])

    assert code == 0
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert "chemical_csr" in payload
    assert "row_ptr_u16" in payload["chemical_csr"]


def test_hwtest_emits_bench_report(tmp_path: Path) -> None:
    ir = tmp_path / "ir.json"
    outdir = tmp_path / "build"
    write_ir(ir)

    code = main(["hwtest", str(ir), "--outdir", str(outdir), "--ticks", "2"])

    assert code == 0
    reports = list(outdir.glob("*/bench_report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["ticks"] == 2
    assert "correctness" in report


def test_selftest_fixed_ok(capsys) -> None:
    code = main(["selftest", "fixed"])

    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["suite"] == "fixed"
