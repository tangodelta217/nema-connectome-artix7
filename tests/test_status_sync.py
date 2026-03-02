from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "release" / "FINAL_STATUS.json"
GATE_STATUS_DOC = ROOT / "docs" / "GATE_STATUS.md"
CLAIMS_DOC = ROOT / "docs" / "CLAIMS.md"
SHA_MANIFEST = ROOT / "release" / "SHA256SUMS.txt"
SNAPSHOT_RE = re.compile(r"## Canonical Gate Snapshot\s+```json\s+(.*?)\s+```", re.S)
SHA_LINE_RE = re.compile(r"^[0-9a-f]{64}\s{2}(.+)$")
HASH_REQUIRED_PREFIXES = ("paper/", "review_pack/tables/", "datasets/raw/", "release/")
HASH_OPTIONAL = {"release/SHA256SUMS.txt"}


def _normalized_gates(data: dict[str, Any]) -> dict[str, str]:
    raw = data.get("gates", {})
    out: dict[str, str] = {}
    for gate, value in raw.items():
        if isinstance(value, dict):
            status = str(value.get("status", "UNKNOWN"))
        else:
            status = str(value)
        out[str(gate)] = status.upper()
    return out


def _extract_gate_snapshot(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    m = SNAPSHOT_RE.search(text)
    assert m is not None, f"missing canonical gate snapshot in {path}"
    parsed = json.loads(m.group(1))
    assert isinstance(parsed, dict), f"snapshot in {path} must be a JSON object"
    return {str(k): str(v).upper() for k, v in parsed.items()}


def _canonical_gates() -> dict[str, str]:
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    return _normalized_gates(data)


def _collect_string_paths(value: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(value, dict):
        for child in value.values():
            out.update(_collect_string_paths(child))
        return out
    if isinstance(value, list):
        for child in value:
            out.update(_collect_string_paths(child))
        return out
    if isinstance(value, str):
        if value.startswith(("http://", "https://", "/")):
            return out
        if "/" in value:
            out.add(value)
    return out


def _sha_manifest_paths() -> set[str]:
    paths: set[str] = set()
    for idx, line in enumerate(SHA_MANIFEST.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        m = SHA_LINE_RE.fullmatch(line.strip())
        assert m is not None, f"invalid SHA256SUMS line {idx}: {line!r}"
        paths.add(m.group(1))
    return paths


def test_gate_status_doc_matches_canonical_release_status() -> None:
    assert _extract_gate_snapshot(GATE_STATUS_DOC) == _canonical_gates()


def test_claims_doc_matches_canonical_release_status() -> None:
    assert _extract_gate_snapshot(CLAIMS_DOC) == _canonical_gates()


def test_sync_status_docs_check_mode_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "tools/sync_status_docs.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_final_status_referenced_artifacts_are_present_in_sha256sums() -> None:
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    referenced = _collect_string_paths(data)
    hashed = _sha_manifest_paths()

    required = sorted(
        path
        for path in referenced
        if path.startswith(HASH_REQUIRED_PREFIXES) and path not in HASH_OPTIONAL
    )
    missing = [path for path in required if path not in hashed]
    assert not missing, (
        "release/FINAL_STATUS.json references artifacts missing in release/SHA256SUMS.txt: "
        + ", ".join(missing)
    )
