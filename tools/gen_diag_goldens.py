"""Generate golden JSON snapshots for NEMA-DSL diagnostics fixtures."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_check(fixture: Path, *, repo_root: Path) -> dict:
    env = os.environ.copy()
    # Keep fixture behavior stable across environments for NEMA-DSL2401.
    env["NEMA_DSL_FORCE_HW_UNAVAILABLE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "nema", "dsl", "check", str(fixture), "--format", "json"],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        raise RuntimeError(
            f"empty stdout for fixture {fixture.name} (rc={proc.returncode}):\n{proc.stderr}"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"invalid JSON stdout for fixture {fixture.name} (rc={proc.returncode}): {exc}\n{proc.stdout}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected payload for fixture {fixture.name}: not a JSON object")
    return payload


def _run_hwtest_require(fixture: Path, *, repo_root: Path) -> dict:
    env = os.environ.copy()
    env["NEMA_DSL_FORCE_HW_UNAVAILABLE"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "dsl",
            "hwtest",
            str(fixture),
            "--hw",
            "require",
            "--ticks",
            "1",
            "--outdir",
            "build_test",
            "--format",
            "json",
        ],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        raise RuntimeError(
            f"empty stdout for fixture {fixture.name} (rc={proc.returncode}):\n{proc.stderr}"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"invalid JSON stdout for fixture {fixture.name} (rc={proc.returncode}): {exc}\n{proc.stdout}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected payload for fixture {fixture.name}: not a JSON object")
    return payload


def main() -> int:
    repo_root = _repo_root()
    fixtures_dir = repo_root / "tests" / "fixtures" / "diag"
    golden_dir = repo_root / "tests" / "golden" / "diag"
    golden_dir.mkdir(parents=True, exist_ok=True)

    fixtures = sorted(fixtures_dir.glob("*.nema"))
    if not fixtures:
        print("No fixtures found under tests/fixtures/diag")
        return 1

    for fixture in fixtures:
        if fixture.stem == "2401_hw_toolchain_unavailable":
            payload = _run_hwtest_require(fixture, repo_root=repo_root)
        else:
            payload = _run_check(fixture, repo_root=repo_root)
        out_path = golden_dir / f"{fixture.stem}.json"
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"generated {out_path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
