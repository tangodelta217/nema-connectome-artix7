#!/usr/bin/env python3
"""Attempt G1b closure with real AMD Vitis HLS evidence."""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BenchCfg:
    name: str
    manifest: Path | None
    ir: Path
    ticks: int
    note: str | None = None


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "build" / "amd_hls"
TRACE_ROOT = ROOT / "artifacts" / "traces"
TABLE_DIR = ROOT / "review_pack" / "tables"


BENCHES: list[BenchCfg] = [
    BenchCfg("b1_small", Path("benches/B1_small/manifest.json"), Path("example_b1_small_subgraph.json"), 20),
    BenchCfg("b2_mid_64_1024", Path("benches/B2_mid/manifest.json"), Path("example_b2_mid_scale.json"), 20),
    BenchCfg(
        "b3_varshney_exec_expanded_gap_279_7284",
        Path("benches/B3_kernel_302_7500/manifest.json"),
        Path("example_b3_kernel_302.json"),
        20,
        note="repo does not include dedicated varshney manifest/IR; executed with B3_kernel_302_7500 baseline assets",
    ),
    BenchCfg("b6_delay_small", Path("benches/B6_delay_small/manifest.json"), Path("example_b6_delay_small.json"), 20),
]


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=env)
    return proc


def _run_shell(cmd: str, *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-lc", cmd], cwd=cwd, text=True, capture_output=True)


def _load_manifest(manifest: Path) -> tuple[list[str], int]:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    expected = payload.get("expectedDigests")
    ticks = payload.get("ticks")
    if not isinstance(expected, list) or any(not isinstance(x, str) for x in expected):
        raise ValueError(f"invalid expectedDigests in {manifest}")
    if not isinstance(ticks, int):
        raise ValueError(f"invalid ticks in {manifest}")
    return expected, ticks


_DIGEST_LINE = re.compile(r"tick=(?P<tick>\d+)\s+digest=(?P<digest>[0-9a-f]{64})")


def _parse_digest_pairs(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for line in text.splitlines():
        m = _DIGEST_LINE.search(line)
        if not m:
            continue
        out.append((int(m.group("tick")), m.group("digest")))
    return out


def _extract_last_tb_run_digests(text: str) -> list[str]:
    runs: list[list[str]] = []
    cur: list[tuple[int, str]] = []
    for line in text.splitlines():
        if "tb_begin" in line:
            cur = []
            continue
        m = _DIGEST_LINE.search(line)
        if m:
            cur.append((int(m.group("tick")), m.group("digest")))
            continue
        if "tb_end" in line and cur:
            cur.sort(key=lambda x: x[0])
            runs.append([digest for _, digest in cur])
            cur = []
    if runs:
        return runs[-1]
    # Fallback: take first occurrence per tick from full stream.
    first_by_tick: dict[int, str] = {}
    for tick, digest in _parse_digest_pairs(text):
        if tick not in first_by_tick:
            first_by_tick[tick] = digest
    return [first_by_tick[k] for k in sorted(first_by_tick.keys())]


def _write_trace(path: Path, digests: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"tick": idx, "digestSha256": digest}) for idx, digest in enumerate(digests)]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _tool_versions() -> dict[str, Any]:
    activate = ROOT / "tools" / "hw" / "activate_xilinx.sh"
    if not activate.exists():
        return {"available": False, "reason": "tools/hw/activate_xilinx.sh missing"}
    env_cmd = (
        "set -euo pipefail; "
        "source tools/hw/activate_xilinx.sh >/dev/null 2>&1; "
        "echo VIVADO=$(command -v vivado || true); "
        "echo VITIS_HLS=$(command -v vitis_hls || true); "
        "vivado -version | head -n 8; "
        "vitis_hls -version | head -n 12"
    )
    p = _run_shell(env_cmd, cwd=ROOT)
    return {
        "available": p.returncode == 0,
        "exitCode": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
    }


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def run_one(cfg: BenchCfg) -> dict[str, Any]:
    bench_root = OUT_ROOT / cfg.name
    bench_root.mkdir(parents=True, exist_ok=True)
    logs_dir = bench_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    manifest_expected: list[str] | None = None
    manifest_ticks: int | None = None
    if cfg.manifest is not None:
        manifest_path = (ROOT / cfg.manifest).resolve()
        if manifest_path.exists():
            manifest_expected, manifest_ticks = _load_manifest(manifest_path)

    ticks = manifest_ticks if isinstance(manifest_ticks, int) else cfg.ticks

    # Golden sim (always generated for objective compare).
    golden_trace = TRACE_ROOT / f"{cfg.name}.trace.jsonl"
    golden_digest_json = bench_root / "golden.digest.json"
    sim_cmd = [
        sys.executable,
        "-m",
        "nema",
        "sim",
        str((ROOT / cfg.ir).resolve()),
        "--ticks",
        str(ticks),
        "--out",
        str(golden_trace),
        "--digest-out",
        str(golden_digest_json),
    ]
    sim_proc = _run(sim_cmd, cwd=ROOT)
    (logs_dir / "golden_sim.stdout.log").write_text(sim_proc.stdout, encoding="utf-8")
    (logs_dir / "golden_sim.stderr.log").write_text(sim_proc.stderr, encoding="utf-8")
    golden_digests: list[str] = []
    if sim_proc.returncode == 0 and golden_digest_json.exists():
        payload = json.loads(golden_digest_json.read_text(encoding="utf-8"))
        raw = payload.get("tickDigestsSha256", [])
        if isinstance(raw, list):
            golden_digests = [str(x) for x in raw]

    # HLS run
    hls_cmd = [
        sys.executable,
        "scripts/amd/run_artix7_hls.py",
        "--benchmark",
        cfg.name,
        "--ir",
        str(cfg.ir),
        "--outdir",
        str(OUT_ROOT),
        "--part",
        "xc7a200t-1sbg484c",
        "--clock-ns",
        "5.0",
        "--cosim",
        "on",
        "--activate-xilinx",
    ]
    hls_proc = _run(hls_cmd, cwd=ROOT)
    (logs_dir / "runner.stdout.log").write_text(hls_proc.stdout, encoding="utf-8")
    (logs_dir / "runner.stderr.log").write_text(hls_proc.stderr, encoding="utf-8")

    runner_summary_path = bench_root / "run_artix7_hls.summary.json"
    runner_summary = (
        json.loads(runner_summary_path.read_text(encoding="utf-8"))
        if runner_summary_path.exists()
        else {}
    )

    # Locate HLS logs.
    sol = bench_root / "hls_run" / "hls_proj" / "nema_hls_prj" / "sol1"
    csim_src = _first_existing([sol / "csim" / "report" / "nema_kernel_csim.log"])
    csynth_src = _first_existing([sol / "syn" / "report" / "csynth.rpt", sol / "syn" / "report" / "nema_kernel_csynth.rpt"])
    cosim_src = _first_existing(
        [
            logs_dir / "vitis_hls.stdout.log",
            sol / "sim" / "report" / "verilog" / "nema_kernel.log",
            sol / "sim" / "verilog" / "xsim.log",
        ]
    )

    csim_dst = bench_root / "csim.log"
    csynth_dst = bench_root / "csynth.log"
    cosim_dst = bench_root / "cosim.log"
    if csim_src is not None:
        shutil.copyfile(csim_src, csim_dst)
    else:
        csim_dst.write_text("", encoding="utf-8")
    if csynth_src is not None:
        shutil.copyfile(csynth_src, csynth_dst)
    else:
        csynth_dst.write_text("", encoding="utf-8")
    if cosim_src is not None:
        shutil.copyfile(cosim_src, cosim_dst)
    else:
        cosim_dst.write_text("", encoding="utf-8")

    csim_text = csim_dst.read_text(encoding="utf-8", errors="replace")
    cosim_text = cosim_dst.read_text(encoding="utf-8", errors="replace")
    csim_digests = _extract_last_tb_run_digests(csim_text)
    cosim_digests = _extract_last_tb_run_digests(cosim_text)

    csim_trace = TRACE_ROOT / f"{cfg.name}.amd_csim.trace.jsonl"
    cosim_trace = TRACE_ROOT / f"{cfg.name}.amd_cosim.trace.jsonl"
    _write_trace(csim_trace, csim_digests)
    _write_trace(cosim_trace, cosim_digests)

    manifest_match = None
    if manifest_expected is not None:
        manifest_match = (manifest_expected == golden_digests)

    cmp_payload: dict[str, Any] = {
        "benchmark": cfg.name,
        "note": cfg.note,
        "ticksExpected": ticks,
        "manifestPath": str((ROOT / cfg.manifest).resolve()) if cfg.manifest is not None else None,
        "runnerExitCode": hls_proc.returncode,
        "runnerOk": bool(runner_summary.get("ok") is True),
        "runnerSummary": runner_summary,
        "golden": {
            "tracePath": str(golden_trace),
            "digestPath": str(golden_digest_json),
            "tickCount": len(golden_digests),
            "finalDigest": golden_digests[-1] if golden_digests else None,
            "simExitCode": sim_proc.returncode,
            "matchesManifestExpected": manifest_match,
        },
        "csim": {
            "logPath": str(csim_dst),
            "sourcePath": str(csim_src) if csim_src is not None else None,
            "tracePath": str(csim_trace),
            "tickCount": len(csim_digests),
            "finalDigest": csim_digests[-1] if csim_digests else None,
            "status": "pass" if "tb_end" in csim_text and "status=PASS" in csim_text else "unknown",
        },
        "cosim": {
            "logPath": str(cosim_dst),
            "sourcePath": str(cosim_src) if cosim_src is not None else None,
            "tracePath": str(cosim_trace),
            "tickCount": len(cosim_digests),
            "finalDigest": cosim_digests[-1] if cosim_digests else None,
            "status": "pass" if "PASS" in cosim_text else "unknown",
        },
    }
    cmp_payload["match"] = {
        "golden_eq_csim_per_tick": bool(golden_digests and golden_digests == csim_digests),
        "golden_eq_cosim_per_tick": bool(golden_digests and golden_digests == cosim_digests),
        "csim_eq_cosim_per_tick": bool(csim_digests and csim_digests == cosim_digests),
    }
    cmp_payload["g1bEligible"] = (
        cmp_payload["match"]["golden_eq_csim_per_tick"]
        and cmp_payload["match"]["golden_eq_cosim_per_tick"]
        and cmp_payload["match"]["csim_eq_cosim_per_tick"]
        and cmp_payload["csim"]["status"] == "pass"
        and cmp_payload["cosim"]["status"] == "pass"
    )

    (bench_root / "digest_compare.json").write_text(
        json.dumps(cmp_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return cmp_payload


def _write_tables(rows: list[dict[str, Any]]) -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = TABLE_DIR / "artix7_hls_digest_summary.csv"
    tex_path = TABLE_DIR / "artix7_hls_digest_summary.tex"
    fields = [
        "benchmark",
        "ticksExpected",
        "goldenTickCount",
        "csimTickCount",
        "cosimTickCount",
        "goldenEqCsim",
        "goldenEqCosim",
        "csimEqCosim",
        "runnerExitCode",
        "g1bEligible",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(
                {
                    "benchmark": row["benchmark"],
                    "ticksExpected": row["ticksExpected"],
                    "goldenTickCount": row["golden"]["tickCount"],
                    "csimTickCount": row["csim"]["tickCount"],
                    "cosimTickCount": row["cosim"]["tickCount"],
                    "goldenEqCsim": row["match"]["golden_eq_csim_per_tick"],
                    "goldenEqCosim": row["match"]["golden_eq_cosim_per_tick"],
                    "csimEqCosim": row["match"]["csim_eq_cosim_per_tick"],
                    "runnerExitCode": row["runnerExitCode"],
                    "g1bEligible": row["g1bEligible"],
                }
            )

    lines = [
        r"\begin{tabular}{lrrrrrrrrr}",
        r"\hline",
        r"bench & ticks & gold & csim & cosim & g=csim & g=cosim & csim=cosim & runner & eligible \\",
        r"\hline",
    ]
    for row in rows:
        lines.append(
            "{} & {} & {} & {} & {} & {} & {} & {} & {} & {} \\\\".format(
                row["benchmark"].replace("_", r"\_"),
                row["ticksExpected"],
                row["golden"]["tickCount"],
                row["csim"]["tickCount"],
                row["cosim"]["tickCount"],
                "Y" if row["match"]["golden_eq_csim_per_tick"] else "N",
                "Y" if row["match"]["golden_eq_cosim_per_tick"] else "N",
                "Y" if row["match"]["csim_eq_cosim_per_tick"] else "N",
                row["runnerExitCode"],
                "Y" if row["g1bEligible"] else "N",
            )
        )
    lines.extend([r"\hline", r"\end{tabular}"])
    tex_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    TRACE_ROOT.mkdir(parents=True, exist_ok=True)

    tool_meta = _tool_versions()
    tool_file = OUT_ROOT / "tool_versions.json"
    tool_file.write_text(json.dumps(tool_meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not tool_meta.get("available", False):
        unavailable = OUT_ROOT / "UNAVAILABLE.md"
        unavailable.write_text(
            "# AMD HLS Unavailable\n\n"
            f"- Reason: tool probe failed (exit={tool_meta.get('exitCode')})\n"
            f"- stderr:\n```\n{tool_meta.get('stderr','')}\n```\n",
            encoding="utf-8",
        )
        return 0

    rows: list[dict[str, Any]] = []
    for cfg in BENCHES:
        try:
            row = run_one(cfg)
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            bench_root = OUT_ROOT / cfg.name
            bench_root.mkdir(parents=True, exist_ok=True)
            payload = {
                "benchmark": cfg.name,
                "error": str(exc),
                "g1bEligible": False,
            }
            (bench_root / "digest_compare.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            rows.append(payload)

    summary = {
        "benchmarks": rows,
        "toolVersionsPath": str(tool_file),
    }
    (OUT_ROOT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_tables(rows=[r for r in rows if "golden" in r])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
