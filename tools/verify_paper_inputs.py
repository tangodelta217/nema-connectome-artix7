#!/usr/bin/env python3
"""Verify that paper table inputs are present and pinned to expected artifacts.

This script is designed to fail fast in CI if paper input wiring drifts.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER_TEX = ROOT / "paper" / "paper.tex"
TEX_INPUT_PATTERN = re.compile(r"\\input\{([^}]+)\}")

# Expected table targets and hashes chosen to preserve Round10b numbers.
EXPECTED_TABLE_TARGETS: dict[str, tuple[str, str]] = {
    "paper/tables/artix7_hls_digest_summary.tex": (
        "review_pack/tables/artix7_hls_digest_summary_strict_v2.tex",
        "619fa26b52bfad35287fec27bd6ace7acc68869897f9363a48b8f47f0a8df18f",
    ),
    "paper/tables/artix7_qor.tex": (
        "review_pack/tables/artix7_qor_v6.tex",
        "09792fd32fe7741b7c8827f985c96e9f75d96241285b32efbb12ccf3b36fdba3",
    ),
    "paper/tables/artix7_power.tex": (
        "review_pack/tables/artix7_power_v7_funcsaif.tex",
        "ed75ff8a02a68322d1d2a627533808c8db0f1a875405ce41003a7a9cf2ba3cd6",
    ),
    "paper/tables/artix7_metrics.tex": (
        "review_pack/tables/artix7_metrics_final.tex",
        "4c963b17fbe84feed569f3e7ef3f2570ccfe7af56dc99297064e82bbd7a425d9",
    ),
}

REQUIRED_ARTIFACTS = [
    ROOT / "release" / "SHA256SUMS.txt",
    ROOT / "release" / "FINAL_STATUS.json",
    ROOT / "review_pack" / "tables" / "artix7_hls_digest_summary_strict_v2.csv",
    ROOT / "review_pack" / "tables" / "artix7_qor_v6.csv",
    ROOT / "review_pack" / "tables" / "artix7_power_v7_funcsaif.csv",
    ROOT / "review_pack" / "tables" / "artix7_metrics_final.csv",
]


def _strip_tex_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        idx = line.find("%")
        if idx >= 0:
            lines.append(line[:idx])
        else:
            lines.append(line)
    return "\n".join(lines)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _err(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []

    if not PAPER_TEX.exists():
        _err(errors, f"missing paper file: {PAPER_TEX}")
        print("\n".join(errors))
        return 1

    paper_text = PAPER_TEX.read_text(encoding="utf-8", errors="replace")

    if "release_round10b" in paper_text:
        _err(errors, "paper/paper.tex still references release_round10b (forbidden dependency)")

    clean = _strip_tex_comments(paper_text)
    inputs = TEX_INPUT_PATTERN.findall(clean)
    if not inputs:
        _err(errors, "no \\input{...} entries found in paper/paper.tex")

    input_abs_paths: list[Path] = []
    for input_path in inputs:
        if not input_path.startswith("tables/"):
            _err(errors, f"unexpected input path (expected tables/...): {input_path}")
            continue
        resolved = (PAPER_TEX.parent / input_path).resolve()
        input_abs_paths.append(resolved)
        if not resolved.exists():
            _err(errors, f"missing input file referenced by paper: {input_path} -> {resolved}")

    for wrapper_rel, (target_rel, expected_hash) in EXPECTED_TABLE_TARGETS.items():
        wrapper = ROOT / wrapper_rel
        target = ROOT / target_rel

        if not wrapper.exists():
            _err(errors, f"missing wrapper table file: {wrapper_rel}")
            continue
        if not target.exists():
            _err(errors, f"missing target table file: {target_rel}")
            continue

        wrapper_text = _strip_tex_comments(wrapper.read_text(encoding="utf-8", errors="replace"))
        m = TEX_INPUT_PATTERN.search(wrapper_text)
        if not m:
            _err(errors, f"wrapper missing \\input target: {wrapper_rel}")
            continue

        # TeX resolves nested \input paths relative to the main paper directory.
        wrapper_target_abs = (PAPER_TEX.parent / m.group(1)).resolve()
        if wrapper_target_abs != target.resolve():
            _err(
                errors,
                f"wrapper target mismatch: {wrapper_rel} -> {wrapper_target_abs} (expected {target.resolve()})",
            )

        actual_hash = _sha256(target)
        if actual_hash != expected_hash:
            _err(
                errors,
                "TODO: table numerical content mismatch with pinned canonical digest: "
                f"{target_rel} expected {expected_hash} got {actual_hash}",
            )

    for artifact in REQUIRED_ARTIFACTS:
        if not artifact.exists():
            _err(errors, f"missing required artifact input: {artifact.relative_to(ROOT)}")

    if errors:
        print("Paper input verification failed:\n")
        for item in errors:
            print(f"- {item}")
        return 1

    print("Paper input verification: OK")
    for p in sorted(input_abs_paths):
        try:
            rel = p.relative_to(ROOT)
        except ValueError:
            rel = p
        print(f"- input exists: {rel}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
