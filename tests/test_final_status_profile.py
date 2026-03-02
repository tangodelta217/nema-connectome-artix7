from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINAL_STATUS = ROOT / "release" / "FINAL_STATUS.json"
SHA_SUMS = ROOT / "release" / "SHA256SUMS.txt"

PROFILE_PATH_KEY = ("releaseProfile", "path")
EVIDENCE_TABLE_KEYS = (
    "hlsDigestCsv",
    "hlsDigestTex",
    "qorCsv",
    "qorTex",
    "powerCsv",
    "powerTex",
    "metricsCsv",
    "metricsTex",
)
SHA_LINE_RE = re.compile(r"^[0-9a-f]{64}\s{2}(.+)$")


def _load_status() -> dict:
    return json.loads(FINAL_STATUS.read_text(encoding="utf-8"))


def _selected_paths(status: dict) -> dict[str, str]:
    profile = status.get("releaseProfile", {})
    evidence = status.get("evidence", {})
    assert isinstance(profile, dict), "releaseProfile must be an object"
    assert isinstance(evidence, dict), "evidence must be an object"

    out: dict[str, str] = {}
    profile_path = profile.get("path")
    assert isinstance(profile_path, str) and profile_path, (
        "releaseProfile.path must be a non-empty string"
    )
    out["releaseProfile.path"] = profile_path

    for key in EVIDENCE_TABLE_KEYS:
        value = evidence.get(key)
        assert isinstance(value, str) and value, f"evidence.{key} must be a non-empty string"
        out[f"evidence.{key}"] = value
    return out


def _sha_paths() -> set[str]:
    out: set[str] = set()
    for idx, line in enumerate(SHA_SUMS.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        m = SHA_LINE_RE.fullmatch(line.strip())
        assert m is not None, f"invalid SHA256SUMS line {idx}: {line!r}"
        out.add(m.group(1))
    return out


def test_final_status_selected_profile_paths_exist() -> None:
    selected = _selected_paths(_load_status())
    missing = []
    for label, rel_path in selected.items():
        abs_path = ROOT / rel_path
        if not abs_path.exists():
            missing.append(f"{label} -> {rel_path}")
    assert not missing, "release/FINAL_STATUS.json selected paths do not exist: " + ", ".join(
        missing
    )


def test_final_status_selected_profile_paths_are_hashed() -> None:
    selected = _selected_paths(_load_status())
    sha_paths = _sha_paths()
    missing = [f"{label} -> {rel}" for label, rel in selected.items() if rel not in sha_paths]
    assert not missing, (
        "release/FINAL_STATUS.json selected paths missing in SHA256SUMS: " + ", ".join(missing)
    )
