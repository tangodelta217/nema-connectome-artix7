#!/usr/bin/env python3
"""Synchronize status documentation from release/FINAL_STATUS.json."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_STATUS = ROOT / "release" / "FINAL_STATUS.json"

DOC_GATE_STATUS = ROOT / "docs" / "GATE_STATUS.md"
DOC_CLAIMS = ROOT / "docs" / "CLAIMS.md"
ROOT_FINAL_STATUS_JSON = ROOT / "FINAL_STATUS.json"
ROOT_FINAL_STATUS_MD = ROOT / "FINAL_STATUS.md"


def _load_canonical_status() -> dict[str, Any]:
    if not CANONICAL_STATUS.exists():
        raise FileNotFoundError(f"Canonical status file not found: {CANONICAL_STATUS}")
    return json.loads(CANONICAL_STATUS.read_text(encoding="utf-8"))


def _normalized_gates(data: dict[str, Any]) -> dict[str, str]:
    raw = data.get("gates")
    if not isinstance(raw, dict):
        raise ValueError("release/FINAL_STATUS.json must define a 'gates' object")

    gates: dict[str, str] = {}
    for gate, value in raw.items():
        if isinstance(value, dict):
            status = str(value.get("status", "UNKNOWN"))
        else:
            status = str(value)
        gates[str(gate)] = status.upper()
    return gates


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


def _render_gate_status_md(data: dict[str, Any], gates: dict[str, str], synced_at: str) -> str:
    canonical_generated = data.get("generatedAtUtc", "UNKNOWN")
    target_part = data.get("targetPart", "UNKNOWN")
    limits = data.get("limits", [])
    evidence_md = _format_evidence(data.get("evidence"))
    rows = "\n".join(f"| {gate} | `{status}` |" for gate, status in sorted(gates.items()))

    limits_md = "\n".join(f"- {item}" for item in limits) if isinstance(limits, list) and limits else "- (none)"

    return (
        "# Gate Status (Canonical)\n\n"
        "This file is generated from `release/FINAL_STATUS.json`.\n"
        "Do not edit manually. Regenerate with `python tools/sync_status_docs.py`.\n\n"
        "## Canonical Source\n\n"
        f"- File: `release/FINAL_STATUS.json`\n"
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


def _render_claims_md(data: dict[str, Any], gates: dict[str, str], synced_at: str) -> str:
    target_part = data.get("targetPart", "UNKNOWN")
    limits = data.get("limits", [])
    power_estimated_only = bool(data.get("powerEstimatedOnly", False))
    power_measured_on_board = bool(data.get("powerMeasuredOnBoard", False))

    can_claim: list[str] = []
    cannot_claim: list[str] = []

    for gate, status in sorted(gates.items()):
        if status == "CLOSED":
            can_claim.append(f"- Gate `{gate}` is `CLOSED` for target part `{target_part}`.")
        else:
            can_claim.append(f"- Gate `{gate}` is currently `{status}` (not closed).")
            cannot_claim.append(f"- Cannot claim `{gate}` as closed until canonical status is `CLOSED`.")

    if power_estimated_only:
        can_claim.append("- Power and energy are `ESTIMATED_PRE_BOARD_ONLY`.")
    if not power_measured_on_board:
        can_claim.append("- No board measurement is claimed in this release state.")
        cannot_claim.append("- Cannot claim measured-on-board power, energy, or latency.")

    if isinstance(limits, list):
        for item in limits:
            if isinstance(item, str):
                cannot_claim.append(f"- Boundary: {item}")

    if not cannot_claim:
        cannot_claim.append("- No additional claim restrictions were declared.")

    can_claim_md = "\n".join(can_claim)
    cannot_claim_md = "\n".join(cannot_claim)

    return (
        "# Claims Ledger (Canonical)\n\n"
        "This file is generated from `release/FINAL_STATUS.json`.\n"
        "Do not edit manually. Regenerate with `python tools/sync_status_docs.py`.\n\n"
        "## Canonical Source\n\n"
        "- File: `release/FINAL_STATUS.json`\n"
        f"- Synced-at (UTC): `{synced_at}`\n\n"
        "## Canonical Gate Snapshot\n\n"
        "```json\n"
        f"{_snapshot_block(gates)}\n"
        "```\n\n"
        "## Claims We Can Make\n\n"
        f"{can_claim_md}\n\n"
        "## Claims We Cannot Make\n\n"
        f"{cannot_claim_md}\n"
    )


def _render_root_final_status_md(data: dict[str, Any], gates: dict[str, str], synced_at: str) -> str:
    gate_summary = ", ".join(f"{gate}={status}" for gate, status in sorted(gates.items()))
    target_part = data.get("targetPart", "UNKNOWN")
    canonical_generated = data.get("generatedAtUtc", "UNKNOWN")

    return (
        "# Final Status (Mirror)\n\n"
        "This file mirrors `release/FINAL_STATUS.json` and is generated.\n"
        "Canonical source: `release/FINAL_STATUS.json`.\n\n"
        f"- Canonical generated-at: `{canonical_generated}`\n"
        f"- Synced-at (UTC): `{synced_at}`\n"
        f"- Target part: `{target_part}`\n"
        f"- Gates: `{gate_summary}`\n\n"
        "For full machine-readable content, use `release/FINAL_STATUS.json`.\n"
    )


def _expected_outputs(data: dict[str, Any]) -> dict[Path, str]:
    synced_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    gates = _normalized_gates(data)
    return {
        DOC_GATE_STATUS: _render_gate_status_md(data, gates, synced_at),
        DOC_CLAIMS: _render_claims_md(data, gates, synced_at),
        ROOT_FINAL_STATUS_JSON: json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        ROOT_FINAL_STATUS_MD: _render_root_final_status_md(data, gates, synced_at),
    }


def _write_outputs(outputs: dict[Path, str]) -> None:
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _canonicalize_generated_timestamp(content: str) -> str:
    lines = []
    for line in content.splitlines():
        if line.startswith("- Synced-at (UTC): `"):
            lines.append("- Synced-at (UTC): `<DYNAMIC_UTC>`")
        else:
            lines.append(line)
    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


def _check_outputs(outputs: dict[Path, str]) -> list[str]:
    mismatches: list[str] = []
    for path, expected in outputs.items():
        if not path.exists():
            mismatches.append(f"missing file: {path.relative_to(ROOT)}")
            continue
        actual = path.read_text(encoding="utf-8")
        if _canonicalize_generated_timestamp(actual) != _canonicalize_generated_timestamp(expected):
            mismatches.append(f"out of sync: {path.relative_to(ROOT)}")
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write files; fail if generated outputs differ from files on disk.",
    )
    args = parser.parse_args()

    data = _load_canonical_status()
    outputs = _expected_outputs(data)

    if args.check:
        mismatches = _check_outputs(outputs)
        if mismatches:
            print("Status sync check failed:")
            for item in mismatches:
                print(f"- {item}")
            print("Run: python tools/sync_status_docs.py")
            return 1
        print("Status sync check: OK")
        return 0

    _write_outputs(outputs)
    print("Synchronized status docs from release/FINAL_STATUS.json:")
    for path in outputs:
        print(f"- {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
