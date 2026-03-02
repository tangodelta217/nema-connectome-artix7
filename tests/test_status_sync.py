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
SNAPSHOT_RE = re.compile(r"## Canonical Gate Snapshot\s+```json\s+(.*?)\s+```", re.S)


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
