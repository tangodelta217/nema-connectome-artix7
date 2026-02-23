from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nema.ir_canonical import canonicalize_ir


def _run_compile(repo_root: Path, dsl_path: Path, out_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "dsl",
            "compile",
            str(dsl_path),
            "--out",
            str(out_path),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_programs_b1_b3_keep_canonical_ir_shape(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cases = [
        ("programs/b1_small.nema", "example_b1_small_subgraph.json"),
        ("programs/b3_kernel_302.nema", "example_b3_kernel_302.json"),
    ]

    for idx, (dsl_rel, ir_rel) in enumerate(cases):
        out_path = tmp_path / f"compiled_{idx}.json"
        _run_compile(repo_root, repo_root / dsl_rel, out_path)

        compiled = json.loads(out_path.read_text(encoding="utf-8"))
        reference = json.loads((repo_root / ir_rel).read_text(encoding="utf-8"))
        # B1 fixture omits modelId in JSON, while the checked-in DSL keeps it explicit.
        if "modelId" in compiled and "modelId" not in reference:
            reference["modelId"] = compiled["modelId"]
        assert canonicalize_ir(compiled) == canonicalize_ir(reference)


def test_cli_check_remaps_parse_error_to_included_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.nema.inc"
    bad.write_text("foo = ;\n", encoding="utf-8")
    main = tmp_path / "main.nema"
    main.write_text('include "bad.nema.inc";\nbar = 1;\n', encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "dsl",
            "check",
            str(main),
            "--format",
            "json",
            "--no-color",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    diag = payload["diagnostics"][0]
    assert diag["code"] == "NEMA-DSL1101"
    assert diag["path"].endswith("bad.nema.inc")
    assert diag["line"] == 1
    assert diag["col"] == 7
