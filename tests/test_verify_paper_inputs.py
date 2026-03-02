from __future__ import annotations

import re
import runpy
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_verify_paper_inputs_script_passes() -> None:
    root = _repo_root()
    proc = subprocess.run(
        [sys.executable, "tools/verify_paper_inputs.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Paper input verification: OK" in proc.stdout


def test_verify_paper_inputs_referenced_tables_are_hashed() -> None:
    root = _repo_root()
    verify_script = root / "tools" / "verify_paper_inputs.py"
    sha_manifest = root / "release" / "SHA256SUMS.txt"

    namespace = runpy.run_path(str(verify_script))
    required_artifacts = namespace.get("REQUIRED_ARTIFACTS", [])
    assert isinstance(required_artifacts, list), "REQUIRED_ARTIFACTS must be a list"

    referenced_csvs: set[str] = set()
    for artifact in required_artifacts:
        path = Path(artifact)
        rel = path.relative_to(root) if path.is_absolute() else path
        rel_str = rel.as_posix()
        if rel_str.startswith("review_pack/tables/") and rel_str.endswith(".csv"):
            referenced_csvs.add(rel_str)
    assert referenced_csvs, (
        "expected at least one review_pack CSV reference in verify_paper_inputs.py"
    )

    listed_paths: set[str] = set()
    for idx, line in enumerate(sha_manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        match = re.fullmatch(r"[0-9a-f]{64}\s{2}(.+)", line.strip())
        assert match is not None, f"invalid SHA256SUMS line {idx}: {line!r}"
        listed_paths.add(match.group(1).strip())

    missing = sorted(path for path in referenced_csvs if path not in listed_paths)
    assert not missing, (
        "tools/verify_paper_inputs.py references table CSVs missing in "
        f"release/SHA256SUMS.txt: {', '.join(missing)}"
    )
