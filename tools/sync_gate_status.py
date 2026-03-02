#!/usr/bin/env python3
"""Synchronize docs/GATE_STATUS.md from release/FINAL_STATUS.json."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_STATUS = ROOT / "release" / "FINAL_STATUS.json"
DOC_GATE_STATUS = ROOT / "docs" / "GATE_STATUS.md"


def _load_canonical_status() -> dict[str, Any]:
    if not CANONICAL_STATUS.exists():
        raise FileNotFoundError(f"Canonical status file not found: {CANONICAL_STATUS}")
    data = json.loads(CANONICAL_STATUS.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("release/FINAL_STATUS.json must be a JSON object")
    return data


def _normalized_gates(data: dict[str, Any]) -> dict[str, str]:
    raw = data.get("gates")
    if not isinstance(raw, dict):
        raise ValueError("release/FINAL_STATUS.json must define a 'gates' object")
    out: dict[str, str] = {}
    for gate, value in raw.items():
        if isinstance(value, dict):
            status = str(value.get("status", "UNKNOWN"))
        else:
            status = str(value)
        out[str(gate)] = status.upper()
    return out


def _snapshot_block(gates: dict[str, str]) -> str:
    return json.dumps(gates, indent=2, sort_keys=True, ensure_ascii=False)


def _format_evidence(evidence: Any) -> str:
    if not isinstance(evidence, dict) or not evidence:
        return "- (none)"
    lines: list[str] = []
    for key in sorted(evidence):
        value = evidence[key]
        if isinstance(value, list):
            joined = ", ".join(f"`{item}`" for item in value)
            lines.append(f"- `{key}`: {joined}")
        else:
            lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines)


def _render(data: dict[str, Any], synced_at: str) -> str:
    canonical_generated = data.get("generatedAtUtc", "UNKNOWN")
    target_part = data.get("targetPart", "UNKNOWN")
    gates = _normalized_gates(data)
    evidence_md = _format_evidence(data.get("evidence"))
    limits = data.get("limits", [])
    limits_md = (
        "\n".join(f"- {item}" for item in limits)
        if isinstance(limits, list) and limits
        else "- (none)"
    )
    rows = "\n".join(f"| {gate} | `{status}` |" for gate, status in sorted(gates.items()))

    return (
        "# Gate Status (Canonical)\n\n"
        "This file is generated from `release/FINAL_STATUS.json`.\n"
        "Do not edit manually. Regenerate with `python tools/sync_status_docs.py`.\n\n"
        "## Canonical Source\n\n"
        "- File: `release/FINAL_STATUS.json`\n"
        f"- Canonical generated-at: `{canonical_generated}`\n"
        f"- Synced-at (UTC): `{synced_at}`\n"
        f"- Target part: `{target_part}`\n\n"
        "## Gate Summary\n\n"
        "| Gate | Status |\n"
        "|---|---|\n"
        f"{rows}\n\n"
        "## Canonical Gate Snapshot\n\n"
        "```json\n"
        f"{_snapshot_block(gates)}\n"
        "```\n\n"
        "## Evidence Anchors\n\n"
        f"{evidence_md}\n\n"
        "## Limits\n\n"
        f"{limits_md}\n"
    )


def _canonicalize_synced_at(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith("- Synced-at (UTC): `"):
            lines.append("- Synced-at (UTC): `<DYNAMIC_UTC>`")
        else:
            lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if docs/GATE_STATUS.md is out of sync"
    )
    args = parser.parse_args()

    data = _load_canonical_status()
    synced_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    expected = _render(data, synced_at)

    if args.check:
        if not DOC_GATE_STATUS.exists():
            print(f"missing file: {DOC_GATE_STATUS.relative_to(ROOT)}")
            return 1
        actual = DOC_GATE_STATUS.read_text(encoding="utf-8")
        if _canonicalize_synced_at(actual) != _canonicalize_synced_at(expected):
            print("gate status sync check failed: docs/GATE_STATUS.md is out of sync")
            print("Run: python tools/sync_gate_status.py")
            return 1
        print("gate status sync check: OK")
        return 0

    DOC_GATE_STATUS.parent.mkdir(parents=True, exist_ok=True)
    DOC_GATE_STATUS.write_text(expected, encoding="utf-8")
    print(
        f"synchronized {DOC_GATE_STATUS.relative_to(ROOT)} from {CANONICAL_STATUS.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
