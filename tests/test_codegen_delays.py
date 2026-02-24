from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _compile_ir(repo_root: Path, ir_path: Path, outdir: Path) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "compile",
            str(ir_path),
            "--outdir",
            str(outdir),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


def test_delay_codegen_emits_ring_buffer_and_delay_fields(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    ir_path = repo_root / "example_b6_delay_small.json"
    report = _compile_ir(repo_root, ir_path, tmp_path / "out")

    header = Path(report["hls_header"]).read_text(encoding="utf-8")
    cpp = Path(report["hls_cpp"]).read_text(encoding="utf-8")

    assert "static constexpr int DELAY_MAX = 2;" in header
    assert "static constexpr int DELAY_RING_SIZE = DELAY_MAX + 1;" in header
    assert "static constexpr uint16_t CHEM_DELAY_TICKS" in header
    assert "static constexpr uint16_t GAP_DELAY_TICKS" in header

    assert "delay_v_ring" in cpp
    assert "delay_a_ring" in cpp
    assert "CHEM_DELAY_TICKS" in cpp
    assert "GAP_DELAY_TICKS" in cpp
    assert "delay_cursor" in cpp
