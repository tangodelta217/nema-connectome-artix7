#!/usr/bin/env python3
"""Run real Vivado implementation attempts for Artix-7 G1c evidence.

Outputs:
- build/amd_vivado/summary.json
- review_pack/tables/artix7_qor.csv
- review_pack/tables/artix7_qor.tex
"""

from __future__ import annotations

import csv
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BenchCfg:
    name: str
    mandatory: bool
    note: str | None = None


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "build" / "amd_vivado"
TABLE_DIR = ROOT / "review_pack" / "tables"
TARGET_PART = "xc7a200t-1sbg484c"
CLOCK_NS = 5.0

BENCHES: list[BenchCfg] = [
    BenchCfg("b1_small", mandatory=True),
    BenchCfg(
        "b3_varshney_exec_expanded_gap_279_7284",
        mandatory=True,
        note="repository currently aliases this benchmark to B3 kernel baseline assets",
    ),
    BenchCfg("b2_mid_64_1024", mandatory=False),
    BenchCfg("b6_delay_small", mandatory=False),
]


def _run_shell(cmd: str, *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-lc", cmd], cwd=cwd, text=True, capture_output=True)


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def _tool_versions() -> dict[str, Any]:
    if not (ROOT / "tools" / "hw" / "activate_xilinx.sh").exists():
        return {"available": False, "reason": "tools/hw/activate_xilinx.sh missing"}
    cmd = (
        "set -euo pipefail; "
        "source tools/hw/activate_xilinx.sh >/dev/null 2>&1; "
        "echo VIVADO=$(command -v vivado || true); "
        "vivado -version | head -n 8"
    )
    p = _run_shell(cmd, cwd=ROOT)
    return {
        "available": p.returncode == 0,
        "exitCode": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
    }


def _probe_requested_part() -> dict[str, Any]:
    """Probe part availability once to avoid N Vivado launches when part is missing."""
    logs_dir = OUT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    if not (ROOT / "tools" / "hw" / "activate_xilinx.sh").exists():
        result = {
            "probeRan": False,
            "requestedPart": TARGET_PART,
            "available": False,
            "reason": "tools/hw/activate_xilinx.sh missing",
            "sampleAvailableParts": [],
            "exitCode": None,
        }
        (OUT_ROOT / "part_probe.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return result

    tcl_script = logs_dir / "part_probe.tcl"
    tcl_script.write_text(
        "\n".join(
            [
                f"set requested_part \"{TARGET_PART}\"",
                "set parts [lsort [get_parts]]",
                "set has_requested [expr {[lsearch -exact $parts $requested_part] >= 0}]",
                "puts \"NEMA_PART_CHECK requested=$requested_part\"",
                "puts \"NEMA_PART_COUNT [llength $parts]\"",
                "puts \"NEMA_PART_AVAILABLE $has_requested\"",
                "puts \"NEMA_PART_SAMPLE [join [lrange $parts 0 9] ,]\"",
                "exit",
                "",
            ]
        ),
        encoding="utf-8",
    )

    cmd = (
        "set -euo pipefail; "
        "source tools/hw/activate_xilinx.sh >/dev/null 2>&1; "
        f"vivado -mode batch -source {shlex.quote(str(tcl_script))}"
    )
    proc = _run_shell(cmd, cwd=ROOT)
    (logs_dir / "part_probe.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (logs_dir / "part_probe.stderr.log").write_text(proc.stderr, encoding="utf-8")

    sample: list[str] = []
    count: int | None = None
    available = False
    for line in proc.stdout.splitlines():
        if line.startswith("NEMA_PART_AVAILABLE "):
            value = line.split(" ", 1)[1].strip()
            available = value in {"1", "true", "True"}
        elif line.startswith("NEMA_PART_COUNT "):
            raw = line.split(" ", 1)[1].strip()
            try:
                count = int(raw)
            except ValueError:
                count = None
        elif line.startswith("NEMA_PART_SAMPLE "):
            raw = line.split(" ", 1)[1].strip()
            sample = [part for part in raw.split(",") if part]

    result = {
        "probeRan": True,
        "requestedPart": TARGET_PART,
        "available": bool(proc.returncode == 0 and available),
        "sampleAvailableParts": sample,
        "availableCount": count,
        "exitCode": proc.returncode,
        "stdoutLog": str(logs_dir / "part_probe.stdout.log"),
        "stderrLog": str(logs_dir / "part_probe.stderr.log"),
    }
    if not result["available"]:
        result["reason"] = (
            f"requested_part_unavailable:{TARGET_PART}"
            if proc.returncode == 0
            else f"probe_failed_exit_{proc.returncode}"
        )

    (OUT_ROOT / "part_probe.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def _parse_float(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _parse_util_report(path: Path) -> dict[str, float | None]:
    if not path.exists():
        return {"lut": None, "ff": None, "bram": None, "dsp": None}
    txt = path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "lut": r"\|\s*CLB LUTs\s*\|\s*([0-9.]+)\s*\|",
        "ff": r"\|\s*Registers\s*\|\s*([0-9.]+)\s*\|",
        "bram": r"\|\s*Block RAM Tile\s*\|\s*([0-9.]+)\s*\|",
        "dsp": r"\|\s*DSP Slices\s*\|\s*([0-9.]+)\s*\|",
    }
    out: dict[str, float | None] = {}
    for key, pat in patterns.items():
        m = re.search(pat, txt)
        out[key] = _parse_float(m.group(1) if m else None)
    return out


def _parse_timing_report(path: Path) -> dict[str, float | None]:
    out: dict[str, float | None] = {
        "wns": None,
        "tns": None,
        "clock_period_ns": None,
        "clock_freq_mhz": None,
    }
    if not path.exists():
        return out
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    # Design timing summary first numeric row after "WNS(ns)..."
    for idx, line in enumerate(lines):
        if "WNS(ns)" in line and "TNS(ns)" in line:
            for j in range(idx + 1, min(idx + 10, len(lines))):
                m = re.match(r"^\s*([+-]?[0-9]+(?:\.[0-9]+)?)\s+([+-]?[0-9]+(?:\.[0-9]+)?)\s+", lines[j])
                if m:
                    out["wns"] = _parse_float(m.group(1))
                    out["tns"] = _parse_float(m.group(2))
                    break
            if out["wns"] is not None:
                break

    # Clock summary row (prefer ap_clk)
    for line in lines:
        m = re.match(
            r"^\s*ap_clk\s+\{[^}]+\}\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)",
            line,
        )
        if m:
            out["clock_period_ns"] = _parse_float(m.group(1))
            out["clock_freq_mhz"] = _parse_float(m.group(2))
            break

    return out


def _fmax_est(clock_period_ns: float | None, wns: float | None) -> float | None:
    if clock_period_ns is None or wns is None:
        return None
    achieved = clock_period_ns - wns
    if achieved <= 0.0:
        return None
    return 1000.0 / achieved


def _fmt(x: float | None) -> str:
    if x is None:
        return "-"
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.3f}"


def _to_jsonable_num(x: float | None) -> float | int | None:
    if x is None:
        return None
    if abs(x - round(x)) < 1e-9:
        return int(round(x))
    return float(x)


def _detect_b3_alias(bench: str) -> bool:
    if bench != "b3_varshney_exec_expanded_gap_279_7284":
        return False
    hls_summary = ROOT / "build" / "amd_hls" / bench / "run_artix7_hls.summary.json"
    if not hls_summary.exists():
        return True
    payload = json.loads(hls_summary.read_text(encoding="utf-8"))
    ir_path = str(payload.get("irPath") or "")
    # If dedicated varshney IR does not exist, this remains aliased.
    return "example_b3_kernel_302.json" in ir_path


def run_one(cfg: BenchCfg) -> dict[str, Any]:
    outdir = OUT_ROOT / cfg.name
    outdir.mkdir(parents=True, exist_ok=True)
    logs_dir = outdir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    hls_root = ROOT / "build" / "amd_hls" / cfg.name
    if not hls_root.exists():
        return {
            "benchmark": cfg.name,
            "mandatory": cfg.mandatory,
            "attempted": False,
            "implOk": False,
            "reason": f"missing_hls_root:{hls_root}",
            "part": None,
            "partMatchRequested": False,
            "lut": None,
            "ff": None,
            "bram": None,
            "dsp": None,
            "wns": None,
            "tns": None,
            "clockPeriodNs": CLOCK_NS,
            "fmaxEstMhz": None,
            "outputs": {},
            "note": cfg.note,
        }

    cmd = [
        sys.executable,
        "scripts/amd/run_artix7_impl.py",
        "--benchmark",
        cfg.name,
        "--hls-root",
        str(hls_root),
        "--part",
        TARGET_PART,
        "--clock-ns",
        str(CLOCK_NS),
        "--outdir",
        str(OUT_ROOT),
        "--activate-xilinx",
    ]
    proc = _run(cmd, cwd=ROOT)
    (logs_dir / "runner.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (logs_dir / "runner.stderr.log").write_text(proc.stderr, encoding="utf-8")

    run_summary_path = outdir / "run_artix7_impl.summary.json"
    vivado_status_path = outdir / "vivado_status.json"
    run_summary = {}
    vivado_status = {}
    if run_summary_path.exists():
        run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
    if vivado_status_path.exists():
        vivado_status = json.loads(vivado_status_path.read_text(encoding="utf-8"))

    outputs = {
        "postSynthDcp": str(outdir / "post_synth.dcp"),
        "postRouteDcp": str(outdir / "post_route.dcp"),
        "postSynthUtilization": str(outdir / "post_synth_utilization.rpt"),
        "postRouteUtilization": str(outdir / "post_route_utilization.rpt"),
        "postSynthTiming": str(outdir / "post_synth_timing.rpt"),
        "postRouteTiming": str(outdir / "post_route_timing.rpt"),
        "operatingConditions": str(outdir / "operating_conditions.rpt"),
        "vivadoLog": str(outdir / "vivado.log"),
    }

    util = _parse_util_report(Path(outputs["postRouteUtilization"]))
    timing = _parse_timing_report(Path(outputs["postRouteTiming"]))
    clock_period = timing.get("clock_period_ns") or CLOCK_NS
    wns = timing.get("wns")
    tns = timing.get("tns")
    fmax = _fmax_est(clock_period, wns)

    part = str(vivado_status.get("part")) if isinstance(vivado_status.get("part"), str) else None
    part_match = part == TARGET_PART

    required_exists = all(Path(p).exists() for p in outputs.values())
    impl_ok = bool(
        proc.returncode == 0
        and run_summary.get("ok") is True
        and vivado_status.get("impl_ok") is True
        and required_exists
        and wns is not None
    )
    reason = "ok" if impl_ok else "vivado_impl_failed_or_incomplete"

    alias = _detect_b3_alias(cfg.name)
    note = cfg.note
    if alias:
        alias_note = "benchmark assets aliased to B3 kernel baseline (no dedicated varshney manifest/IR)"
        note = f"{note}; {alias_note}" if note else alias_note

    return {
        "benchmark": cfg.name,
        "mandatory": cfg.mandatory,
        "attempted": True,
        "runnerExitCode": proc.returncode,
        "implOk": impl_ok,
        "reason": reason,
        "part": part,
        "partMatchRequested": part_match,
        "lut": util.get("lut"),
        "ff": util.get("ff"),
        "bram": util.get("bram"),
        "dsp": util.get("dsp"),
        "wns": wns,
        "tns": tns,
        "clockPeriodNs": clock_period,
        "fmaxEstMhz": fmax,
        "outputs": outputs,
        "runSummaryPath": str(run_summary_path),
        "vivadoStatusPath": str(vivado_status_path),
        "note": note,
        "benchmarkIdentityCanonical": not alias,
    }


def _write_tables(rows: list[dict[str, Any]]) -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = TABLE_DIR / "artix7_qor.csv"
    tex_path = TABLE_DIR / "artix7_qor.tex"

    headers = [
        "benchmark",
        "mandatory",
        "attempted",
        "impl_ok",
        "part",
        "part_match_requested",
        "lut",
        "ff",
        "bram",
        "dsp",
        "wns",
        "tns",
        "clock_period_ns",
        "fmax_est_mhz",
        "reason",
        "note",
        "post_route_timing",
        "post_route_utilization",
        "vivado_log",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for r in rows:
            writer.writerow(
                [
                    r["benchmark"],
                    str(bool(r["mandatory"])).lower(),
                    str(bool(r["attempted"])).lower(),
                    str(bool(r["implOk"])).lower(),
                    r.get("part") or "-",
                    str(bool(r.get("partMatchRequested"))).lower(),
                    _fmt(r.get("lut")),
                    _fmt(r.get("ff")),
                    _fmt(r.get("bram")),
                    _fmt(r.get("dsp")),
                    _fmt(r.get("wns")),
                    _fmt(r.get("tns")),
                    _fmt(r.get("clockPeriodNs")),
                    _fmt(r.get("fmaxEstMhz")),
                    r.get("reason") or "-",
                    (r.get("note") or "-").replace("\n", " "),
                    r.get("outputs", {}).get("postRouteTiming", "-"),
                    r.get("outputs", {}).get("postRouteUtilization", "-"),
                    r.get("outputs", {}).get("vivadoLog", "-"),
                ]
            )

    def esc(s: str) -> str:
        return (
            s.replace("\\", "\\textbackslash{}")
            .replace("_", "\\_")
            .replace("%", "\\%")
            .replace("&", "\\&")
            .replace("#", "\\#")
        )

    tex_lines = [
        "\\begin{tabular}{lrrrrrrrrrr}",
        "\\hline",
        "Benchmark & ImplOK & LUT & FF & BRAM & DSP & WNS(ns) & TNS(ns) & Period(ns) & Fmax(MHz) & Part \\\\",
        "\\hline",
    ]
    for r in rows:
        tex_lines.append(
            f"{esc(r['benchmark'])} & "
            f"{'yes' if r['implOk'] else 'no'} & "
            f"{_fmt(r.get('lut'))} & "
            f"{_fmt(r.get('ff'))} & "
            f"{_fmt(r.get('bram'))} & "
            f"{_fmt(r.get('dsp'))} & "
            f"{_fmt(r.get('wns'))} & "
            f"{_fmt(r.get('tns'))} & "
            f"{_fmt(r.get('clockPeriodNs'))} & "
            f"{_fmt(r.get('fmaxEstMhz'))} & "
            f"{esc(r.get('part') or '-')} \\\\"
        )
    tex_lines.extend(["\\hline", "\\end{tabular}", ""])
    tex_path.write_text("\n".join(tex_lines), encoding="utf-8")


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "logs").mkdir(parents=True, exist_ok=True)

    tool_versions = _tool_versions()
    (OUT_ROOT / "tool_versions.json").write_text(
        json.dumps(tool_versions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if not tool_versions.get("available"):
        (OUT_ROOT / "UNAVAILABLE.md").write_text(
            "Vivado unavailable for G1c run.\n"
            f"Reason: {tool_versions.get('reason', 'probe failed')}\n",
            encoding="utf-8",
        )
        return 2

    part_probe = _probe_requested_part()
    if not part_probe.get("available"):
        rows = []
        reason = str(part_probe.get("reason") or f"requested_part_unavailable:{TARGET_PART}")
        sample = ",".join(part_probe.get("sampleAvailableParts") or [])
        note_suffix = f"; sample_available_parts={sample}" if sample else ""
        for cfg in BENCHES:
            alias = _detect_b3_alias(cfg.name)
            note = cfg.note
            if alias:
                alias_note = "benchmark assets aliased to B3 kernel baseline (no dedicated varshney manifest/IR)"
                note = f"{note}; {alias_note}" if note else alias_note
            if note_suffix:
                note = f"{note}{note_suffix}" if note else note_suffix.lstrip("; ")
            rows.append(
                {
                    "benchmark": cfg.name,
                    "mandatory": cfg.mandatory,
                    "attempted": False,
                    "runnerExitCode": None,
                    "implOk": False,
                    "reason": reason,
                    "part": None,
                    "partMatchRequested": False,
                    "lut": None,
                    "ff": None,
                    "bram": None,
                    "dsp": None,
                    "wns": None,
                    "tns": None,
                    "clockPeriodNs": CLOCK_NS,
                    "fmaxEstMhz": None,
                    "outputs": {},
                    "runSummaryPath": None,
                    "vivadoStatusPath": None,
                    "note": note,
                    "benchmarkIdentityCanonical": not alias,
                }
            )

        _write_tables(rows)

        mandatory = [r for r in rows if r["mandatory"]]
        mandatory_ok = False
        b3_identity_ok = all(
            r["benchmark"] != "b3_varshney_exec_expanded_gap_279_7284" or r["benchmarkIdentityCanonical"]
            for r in mandatory
        )
        summary = {
            "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
            "targetPart": TARGET_PART,
            "clockNs": CLOCK_NS,
            "toolVersionsPath": str(OUT_ROOT / "tool_versions.json"),
            "partProbe": part_probe,
            "results": rows,
            "mandatoryBenchmarks": [r["benchmark"] for r in mandatory],
            "mandatoryImplAllOk": mandatory_ok,
            "b3BenchmarkIdentityCanonical": b3_identity_ok,
            "g1cClosureRecommended": False,
            "notes": [
                "G1c closure requires real Vivado implementation reports for required benchmarks.",
                "Vivado part precheck failed or requested part unavailable; skipped per-benchmark runs.",
                "B3 varshney benchmark identity remains non-canonical if fallback assets are used.",
            ],
            "tableArtifacts": {
                "csv": str(TABLE_DIR / "artix7_qor.csv"),
                "tex": str(TABLE_DIR / "artix7_qor.tex"),
            },
        }
        (OUT_ROOT / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    rows: list[dict[str, Any]] = []
    for cfg in BENCHES:
        rows.append(run_one(cfg))

    _write_tables(rows)

    mandatory = [r for r in rows if r["mandatory"]]
    mandatory_ok = all(
        r["implOk"] and r["partMatchRequested"] and r.get("wns") is not None for r in mandatory
    )
    b3_identity_ok = all(
        r["benchmark"] != "b3_varshney_exec_expanded_gap_279_7284" or r["benchmarkIdentityCanonical"]
        for r in mandatory
    )
    g1c_closure_recommended = bool(mandatory_ok and b3_identity_ok)

    summary = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "targetPart": TARGET_PART,
        "clockNs": CLOCK_NS,
        "toolVersionsPath": str(OUT_ROOT / "tool_versions.json"),
        "partProbe": part_probe,
        "results": [
            {
                **r,
                "lut": _to_jsonable_num(r.get("lut")),
                "ff": _to_jsonable_num(r.get("ff")),
                "bram": _to_jsonable_num(r.get("bram")),
                "dsp": _to_jsonable_num(r.get("dsp")),
                "wns": _to_jsonable_num(r.get("wns")),
                "tns": _to_jsonable_num(r.get("tns")),
                "clockPeriodNs": _to_jsonable_num(r.get("clockPeriodNs")),
                "fmaxEstMhz": _to_jsonable_num(r.get("fmaxEstMhz")),
            }
            for r in rows
        ],
        "mandatoryBenchmarks": [r["benchmark"] for r in mandatory],
        "mandatoryImplAllOk": mandatory_ok,
        "b3BenchmarkIdentityCanonical": b3_identity_ok,
        "g1cClosureRecommended": g1c_closure_recommended,
        "notes": [
            "G1c closure requires real Vivado implementation reports for required benchmarks.",
            "B3 varshney benchmark identity remains non-canonical if fallback assets are used.",
        ],
        "tableArtifacts": {
            "csv": str(TABLE_DIR / "artix7_qor.csv"),
            "tex": str(TABLE_DIR / "artix7_qor.tex"),
        },
    }
    (OUT_ROOT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
