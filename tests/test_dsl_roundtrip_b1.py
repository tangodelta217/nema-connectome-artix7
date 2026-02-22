from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_dsl_roundtrip_b1_from_ir_to_compile(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    ir_path = repo_root / "example_b1_small_subgraph.json"
    dsl_path = tmp_path / "b1.nema"
    ir2_path = tmp_path / "b1_roundtrip.json"

    from_ir_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "dsl",
            "from-ir",
            str(ir_path),
            "--out",
            str(dsl_path),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert from_ir_proc.returncode == 0

    compile_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "dsl",
            "compile",
            str(dsl_path),
            "--out",
            str(ir2_path),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert compile_proc.returncode == 0

    ir = json.loads(ir_path.read_text(encoding="utf-8"))
    ir2 = json.loads(ir2_path.read_text(encoding="utf-8"))
    assert ir2 == ir
