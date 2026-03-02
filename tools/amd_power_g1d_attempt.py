#!/usr/bin/env python3
"""Attempt G1d boardless power evidence with vectorless + SAIF-guided paths.

Outputs:
- build/amd_power/<bench>/*
- build/amd_power/summary.json
- review_pack/tables/artix7_power.csv
- review_pack/tables/artix7_power.tex

Notes:
- Estimation-only (never on-board measured).
- Keeps gate honesty: does not close G1d on missing SAIF / part mismatch.
"""

from __future__ import annotations

import csv
import json
import math
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "build" / "amd_power"
TABLE_DIR = ROOT / "review_pack" / "tables"
TARGET_PART = "xc7a200t-1sbg484c"
DEFAULT_CLOCK_NS = 5.0


@dataclass(frozen=True)
class BenchSpec:
    key: str
    path_hint: str
    requires_saif: bool


BENCHES = [
    BenchSpec("b1_small", "example_b1_small_subgraph", True),
    BenchSpec("b3_varshney_exec_expanded_gap_279_7284", "B3_kernel_302_7500", True),
]


def _run(cmd: str, *, stdout_path: Path, stderr_path: Path) -> int:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True)
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    return proc.returncode


def _json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_latest_bench_report(path_hint: str) -> Path | None:
    candidates = []
    for p in ROOT.glob("build/**/bench_report.json"):
        sp = str(p)
        if path_hint in sp:
            candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _parse_power_report(path: Path) -> dict[str, float | None]:
    out = {"totalOnChipPowerW": None, "dynamicPowerW": None, "deviceStaticPowerW": None}
    if not path.exists():
        return out
    txt = path.read_text(encoding="utf-8", errors="replace")

    def grab(pattern: str) -> float | None:
        m = re.search(pattern, txt, flags=re.IGNORECASE)
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None

    out["totalOnChipPowerW"] = grab(r"Total On-Chip Power\s*\(W\)\s*\|\s*([0-9.+Ee-]+)")
    out["dynamicPowerW"] = grab(r"Dynamic\s*\(W\)\s*\|\s*([0-9.+Ee-]+)")
    out["deviceStaticPowerW"] = grab(r"Device Static\s*\(W\)\s*\|\s*([0-9.+Ee-]+)")
    return out


def _fmax_mhz(clock_ns: float | None, wns_ns: float | None) -> float | None:
    if clock_ns is None or wns_ns is None:
        return None
    denom = clock_ns - wns_ns
    if denom <= 0:
        return None
    return 1000.0 / denom


def _energy_per_tick_nj(total_power_w: float | None, ii: float | None, fmax_mhz: float | None) -> float | None:
    if total_power_w is None or ii is None or fmax_mhz is None:
        return None
    if ii <= 0 or fmax_mhz <= 0:
        return None
    ticks_per_sec = (fmax_mhz * 1_000_000.0) / ii
    if ticks_per_sec <= 0:
        return None
    return (total_power_w / ticks_per_sec) * 1e9


def _extract_vivado_meta(bench_report: dict[str, Any]) -> tuple[str | None, float | None, float | None, float | None]:
    hw = bench_report.get("hardware") or {}
    viv = hw.get("vivado") or {}
    qor = hw.get("qor") or {}
    part = viv.get("part") if isinstance(viv.get("part"), str) else None
    wns = viv.get("wns")
    ii = qor.get("ii")
    clock_ns = DEFAULT_CLOCK_NS
    # clockInfoNs appears in some reports
    if isinstance(viv.get("clockInfoNs"), (int, float)):
        clock_ns = float(viv["clockInfoNs"])
    return part, (float(wns) if isinstance(wns, (int, float)) else None), (float(ii) if isinstance(ii, (int, float)) else None), float(clock_ns)


def _b1_existing_dcp() -> Path | None:
    p = ROOT / "build" / "post_route_sim_b1" / "artifacts" / "nema_kernel_postroute.dcp"
    return p if p.exists() else None


def _generate_dcp_from_run_tcl(bench_out: Path, run_tcl: Path, logs_dir: Path) -> tuple[int, Path]:
    run_tcl_copy = bench_out / "run_vivado_power_export.tcl"
    txt = run_tcl.read_text(encoding="utf-8", errors="replace")
    lines = txt.splitlines()
    while lines and lines[-1].strip() == "":
        lines.pop()
    if lines and lines[-1].strip() == "exit":
        lines.pop()

    dcp = bench_out / "post_route.dcp"
    util_rpt = bench_out / "post_route_utilization.rpt"
    timing_rpt = bench_out / "post_route_timing.rpt"
    power_vec_rpt = bench_out / "power_vectorless.rpt"
    opcond_rpt = bench_out / "operating_conditions.rpt"

    lines.extend(
        [
            f"write_checkpoint -force {{{dcp}}}",
            f"report_utilization -file {{{util_rpt}}}",
            f"report_timing_summary -file {{{timing_rpt}}} -delay_type max -max_paths 10",
            f"report_power -file {{{power_vec_rpt}}}",
            f"catch {{ report_operating_conditions -file {{{opcond_rpt}}} }}",
            "exit",
        ]
    )
    run_tcl_copy.write_text("\n".join(lines) + "\n", encoding="utf-8")

    cmd = (
        "set -euo pipefail; "
        "source tools/hw/activate_xilinx.sh >/dev/null 2>&1; "
        f"vivado -mode batch -source {shlex.quote(str(run_tcl_copy))}"
    )
    rc = _run(cmd, stdout_path=logs_dir / "vivado_power_export.stdout.log", stderr_path=logs_dir / "vivado_power_export.stderr.log")
    return rc, dcp


def _attempt_saif_b1(bench_out: Path, logs_dir: Path) -> tuple[str, Path | None]:
    # Uses existing post-route simulation assets from build/post_route_sim_b1.
    artifacts = ROOT / "build" / "post_route_sim_b1" / "artifacts"
    prj = artifacts / "postroute_abs.prj"
    if not prj.exists():
        return "NOT_AVAILABLE:missing_postroute_abs_prj", None

    saif_path = bench_out / "activity.saif"
    xsim_tcl = bench_out / "xsim_dump_saif.tcl"
    xsim_tcl.write_text(
        "\n".join(
            [
                f"open_saif {saif_path}",
                "log_saif [get_objects -r /tb_post_route_min/*]",
                "run 200 ns",
                "close_saif",
                "quit",
                "",
            ]
        ),
        encoding="utf-8",
    )

    xelab_cmd = (
        "set -euo pipefail; "
        "source tools/hw/activate_xilinx.sh >/dev/null 2>&1; "
        'VIVADO_BIN=$(dirname "$(command -v vivado)"); '
        'VIVADO_ROOT=$(cd "$VIVADO_BIN/.." && pwd); '
        'GLBL="$VIVADO_ROOT/data/verilog/src/glbl.v"; '
        f"xelab -prj {shlex.quote(str(prj))} --vlog \"$GLBL\" glbl tb_post_route_min "
        "-L unisims_ver -L simprims_ver -timescale 1ns/1ps --debug typical -s tb_saif_snapshot"
    )
    xelab_rc = _run(xelab_cmd, stdout_path=logs_dir / "xelab_saif.stdout.log", stderr_path=logs_dir / "xelab_saif.stderr.log")
    (logs_dir / "xelab_saif.exitcode.txt").write_text(str(xelab_rc), encoding="utf-8")
    if xelab_rc != 0:
        return f"FAIL:xelab_rc_{xelab_rc}", None

    xsim_cmd = (
        "set -euo pipefail; "
        "source tools/hw/activate_xilinx.sh >/dev/null 2>&1; "
        f"xsim tb_saif_snapshot -tclbatch {shlex.quote(str(xsim_tcl))}"
    )
    xsim_rc = _run(xsim_cmd, stdout_path=logs_dir / "xsim_saif.stdout.log", stderr_path=logs_dir / "xsim_saif.stderr.log")
    (logs_dir / "xsim_saif.exitcode.txt").write_text(str(xsim_rc), encoding="utf-8")
    if xsim_rc != 0:
        return f"FAIL:xsim_rc_{xsim_rc}", None

    if not saif_path.exists():
        return "FAIL:saif_not_emitted", None
    return "PASS", saif_path


def _run_vivado_power_from_dcp(
    *,
    dcp: Path,
    bench_out: Path,
    logs_dir: Path,
    saif_path: Path | None,
) -> tuple[int, int]:
    vec_tcl = bench_out / "report_power_vectorless.tcl"
    vec_rpt = bench_out / "power_vectorless.rpt"
    vec_tcl.write_text(
        "\n".join(
            [
                f"open_checkpoint {{{dcp}}}",
                f"report_power -file {{{vec_rpt}}}",
                "exit",
                "",
            ]
        ),
        encoding="utf-8",
    )

    vec_cmd = (
        "set -euo pipefail; "
        "source tools/hw/activate_xilinx.sh >/dev/null 2>&1; "
        f"vivado -mode batch -source {shlex.quote(str(vec_tcl))}"
    )
    vec_rc = _run(vec_cmd, stdout_path=logs_dir / "vivado_vectorless.stdout.log", stderr_path=logs_dir / "vivado_vectorless.stderr.log")
    (logs_dir / "vivado_vectorless.exitcode.txt").write_text(str(vec_rc), encoding="utf-8")

    saif_tcl = bench_out / "report_power_saif.tcl"
    saif_rpt = bench_out / "power_saif.rpt"
    read_saif_log = bench_out / "read_saif.log"

    if saif_path and saif_path.exists():
        saif_tcl.write_text(
            "\n".join(
                [
                    f"open_checkpoint {{{dcp}}}",
                    f"set saif_file {{{saif_path}}}",
                    "set saif_ok 0",
                    f"set fp [open {{{read_saif_log}}} w]",
                    "if {[catch {read_saif $saif_file} msg]} {",
                    "  puts $fp \"READ_SAIF_ATTEMPT_1_FAIL:$msg\"",
                    "} else {",
                    "  puts $fp \"READ_SAIF_ATTEMPT_1_PASS\"",
                    "  set saif_ok 1",
                    "}",
                    "if {!$saif_ok} {",
                    "  if {[catch {read_saif -input $saif_file} msg2]} {",
                    "    puts $fp \"READ_SAIF_ATTEMPT_2_FAIL:$msg2\"",
                    "  } else {",
                    "    puts $fp \"READ_SAIF_ATTEMPT_2_PASS\"",
                    "    set saif_ok 1",
                    "  }",
                    "}",
                    "puts $fp \"READ_SAIF_FINAL:$saif_ok\"",
                    "close $fp",
                    f"report_power -file {{{saif_rpt}}}",
                    "exit",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        saif_cmd = (
            "set -euo pipefail; "
            "source tools/hw/activate_xilinx.sh >/dev/null 2>&1; "
            f"vivado -mode batch -source {shlex.quote(str(saif_tcl))}"
        )
        saif_rc = _run(saif_cmd, stdout_path=logs_dir / "vivado_saif.stdout.log", stderr_path=logs_dir / "vivado_saif.stderr.log")
    else:
        read_saif_log.write_text("READ_SAIF_FINAL:0\nNO_SAIF_INPUT\n", encoding="utf-8")
        (logs_dir / "vivado_saif.stdout.log").write_text("", encoding="utf-8")
        (logs_dir / "vivado_saif.stderr.log").write_text("Skipped: no SAIF input\n", encoding="utf-8")
        saif_rc = 127

    (logs_dir / "vivado_saif.exitcode.txt").write_text(str(saif_rc), encoding="utf-8")
    return vec_rc, saif_rc


def _read_saif_status(read_saif_log: Path) -> str:
    if not read_saif_log.exists():
        return "NOT_RUN"
    txt = read_saif_log.read_text(encoding="utf-8", errors="replace")
    if "READ_SAIF_FINAL:1" in txt:
        return "PASS"
    if "NO_SAIF_INPUT" in txt:
        return "NOT_AVAILABLE"
    return "FAIL"


def _format_num(x: float | None, nd: int = 6) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "-"
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def _to_tex(rows: list[dict[str, Any]], out_path: Path) -> None:
    def esc(s: str) -> str:
        return s.replace("_", "\\_").replace("%", "\\%").replace("&", "\\&").replace("#", "\\#")

    lines = [
        "\\begin{tabular}{lcccccc}",
        "\\hline",
        "Benchmark & Part & VecTot(W) & SAIFTot(W) & VecE/tick(nJ) & SAIFE/tick(nJ) & SAIF \\\\",
        "\\hline",
    ]
    for r in rows:
        lines.append(
            f"{esc(r['benchmark'])} & {esc(r['part'] or '-')} & "
            f"{esc(r['vectorless_total_power_w'])} & {esc(r['saif_total_power_w'])} & "
            f"{esc(r['vectorless_energy_per_tick_nj'])} & {esc(r['saif_energy_per_tick_nj'])} & "
            f"{esc(r['read_saif_status'])} \\\\" 
        )
    lines.extend(["\\hline", "\\end{tabular}", ""])
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _run_one(spec: BenchSpec) -> dict[str, Any]:
    bench_out = OUT_ROOT / spec.key
    logs_dir = bench_out / "logs"
    bench_out.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    bench_report_path = _find_latest_bench_report(spec.path_hint)
    bench_report = _json_load(bench_report_path) if bench_report_path and bench_report_path.exists() else {}
    part, wns, ii, clock_ns = _extract_vivado_meta(bench_report)
    fmax = _fmax_mhz(clock_ns, wns)

    dcp_source = None
    dcp_path: Path | None = None

    if spec.key == "b1_small":
        dcp = _b1_existing_dcp()
        if dcp:
            dcp_source = "existing_post_route_sim_b1"
            dcp_path = dcp

    if dcp_path is None:
        run_tcl = None
        proj_dir = ((bench_report.get("hardware") or {}).get("vivado") or {}).get("projectDir")
        if isinstance(proj_dir, str):
            cand = Path(proj_dir) / "run_vivado.tcl"
            if cand.exists():
                run_tcl = cand
        if run_tcl is None:
            # fallback known path for b3
            known = ROOT / "build" / "pre_board_20260228T132542Z" / "runs" / "b3_hw" / "B3_kernel_302_7500" / "hls_proj" / "vivado_batch" / "run_vivado.tcl"
            if known.exists() and spec.key.startswith("b3"):
                run_tcl = known

        if run_tcl is not None:
            dcp_source = f"rerun_from_tcl:{run_tcl}"
            rc, generated = _generate_dcp_from_run_tcl(bench_out, run_tcl, logs_dir)
            (logs_dir / "rerun_vivado.exitcode.txt").write_text(str(rc), encoding="utf-8")
            if rc == 0 and generated.exists():
                dcp_path = generated

    if dcp_path is None or not dcp_path.exists():
        return {
            "benchmark": spec.key,
            "bench_report_path": str(bench_report_path) if bench_report_path else None,
            "dcp_path": None,
            "dcp_source": dcp_source,
            "part": part,
            "target_part": TARGET_PART,
            "target_part_match": part == TARGET_PART,
            "clock_ns": clock_ns,
            "wns_ns": wns,
            "ii_cycles": ii,
            "fmax_est_mhz": fmax,
            "vectorless_status": "NOT_AVAILABLE",
            "saif_generation_status": "NOT_AVAILABLE",
            "read_saif_status": "NOT_RUN",
            "saif_power_status": "NOT_RUN",
            "vectorless": {"totalOnChipPowerW": None, "dynamicPowerW": None, "deviceStaticPowerW": None},
            "saif": {"totalOnChipPowerW": None, "dynamicPowerW": None, "deviceStaticPowerW": None},
            "vectorless_energy_per_tick_nj": None,
            "saif_energy_per_tick_nj": None,
            "reason": "missing_post_route_dcp",
            "estimated_label": "ESTIMATED_PRE_BOARD_ONLY",
        }

    saif_path: Path | None = None
    if spec.key == "b1_small":
        saif_generation_status, saif_path = _attempt_saif_b1(bench_out, logs_dir)
    else:
        saif_generation_status = "NOT_AVAILABLE:no_timing_sim_harness"

    vec_rc, saif_rc = _run_vivado_power_from_dcp(dcp=dcp_path, bench_out=bench_out, logs_dir=logs_dir, saif_path=saif_path)

    vec_metrics = _parse_power_report(bench_out / "power_vectorless.rpt")
    saif_metrics = _parse_power_report(bench_out / "power_saif.rpt")
    read_saif_status = _read_saif_status(bench_out / "read_saif.log")

    vectorless_status = "PASS" if vec_rc == 0 and vec_metrics.get("totalOnChipPowerW") is not None else "FAIL"
    saif_power_status = "PASS" if saif_rc == 0 and saif_metrics.get("totalOnChipPowerW") is not None else "FAIL"
    if saif_rc == 127:
        saif_power_status = "NOT_RUN"

    vec_e = _energy_per_tick_nj(vec_metrics.get("totalOnChipPowerW"), ii, fmax)
    saif_e = _energy_per_tick_nj(saif_metrics.get("totalOnChipPowerW"), ii, fmax)

    return {
        "benchmark": spec.key,
        "bench_report_path": str(bench_report_path) if bench_report_path else None,
        "dcp_path": str(dcp_path),
        "dcp_source": dcp_source,
        "part": part,
        "target_part": TARGET_PART,
        "target_part_match": part == TARGET_PART,
        "clock_ns": clock_ns,
        "wns_ns": wns,
        "ii_cycles": ii,
        "fmax_est_mhz": fmax,
        "vectorless_status": vectorless_status,
        "saif_generation_status": saif_generation_status,
        "read_saif_status": read_saif_status,
        "saif_power_status": saif_power_status,
        "vectorless": vec_metrics,
        "saif": saif_metrics,
        "vectorless_energy_per_tick_nj": vec_e,
        "saif_energy_per_tick_nj": saif_e,
        "reason": "ok" if vectorless_status == "PASS" else "vectorless_failed",
        "estimated_label": "ESTIMATED_PRE_BOARD_ONLY",
        "artifacts": {
            "saif": str(saif_path) if saif_path else None,
            "read_saif_log": str(bench_out / "read_saif.log"),
            "power_vectorless_rpt": str(bench_out / "power_vectorless.rpt"),
            "power_saif_rpt": str(bench_out / "power_saif.rpt"),
        },
    }


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for spec in BENCHES:
        rows.append(_run_one(spec))

    for row in rows:
        bench = row["benchmark"]
        (OUT_ROOT / bench / "summary.json").write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    csv_rows = []
    for r in rows:
        csv_rows.append(
            {
                "benchmark": r["benchmark"],
                "part": r["part"] or "-",
                "target_part": r["target_part"],
                "target_part_match": str(bool(r["target_part_match"])).lower(),
                "vectorless_status": r["vectorless_status"],
                "saif_generation_status": r["saif_generation_status"],
                "read_saif_status": r["read_saif_status"],
                "saif_power_status": r["saif_power_status"],
                "vectorless_total_power_w": _format_num(r["vectorless"].get("totalOnChipPowerW")),
                "vectorless_dynamic_power_w": _format_num(r["vectorless"].get("dynamicPowerW")),
                "vectorless_static_power_w": _format_num(r["vectorless"].get("deviceStaticPowerW")),
                "saif_total_power_w": _format_num(r["saif"].get("totalOnChipPowerW")),
                "saif_dynamic_power_w": _format_num(r["saif"].get("dynamicPowerW")),
                "saif_static_power_w": _format_num(r["saif"].get("deviceStaticPowerW")),
                "ii_cycles": _format_num(r.get("ii_cycles"), nd=3),
                "fmax_est_mhz": _format_num(r.get("fmax_est_mhz"), nd=6),
                "vectorless_energy_per_tick_nj": _format_num(r.get("vectorless_energy_per_tick_nj"), nd=6),
                "saif_energy_per_tick_nj": _format_num(r.get("saif_energy_per_tick_nj"), nd=6),
                "bench_report_path": r.get("bench_report_path") or "-",
                "dcp_path": r.get("dcp_path") or "-",
                "saif_path": r["artifacts"].get("saif") or "-",
                "read_saif_log": r["artifacts"].get("read_saif_log") or "-",
                "power_vectorless_rpt": r["artifacts"].get("power_vectorless_rpt") or "-",
                "power_saif_rpt": r["artifacts"].get("power_saif_rpt") or "-",
                "estimated_label": r.get("estimated_label"),
                "reason": r.get("reason"),
            }
        )

    csv_path = TABLE_DIR / "artix7_power.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)

    tex_path = TABLE_DIR / "artix7_power.tex"
    _to_tex(csv_rows, tex_path)

    # Sensitivity (if viable): compare vectorless vs SAIF total power deltas.
    sensitivity = []
    for r in rows:
        vec = r["vectorless"].get("totalOnChipPowerW")
        saif = r["saif"].get("totalOnChipPowerW")
        if isinstance(vec, (int, float)) and isinstance(saif, (int, float)) and vec > 0:
            sensitivity.append(
                {
                    "benchmark": r["benchmark"],
                    "deltaW": saif - vec,
                    "deltaPct": ((saif - vec) / vec) * 100.0,
                }
            )

    g1d_close = False
    # Contract-honest closure requires both benches with SAIF-guided post-impl evidence and target-part match.
    if len(rows) == 2:
        g1d_close = all(
            r["vectorless_status"] == "PASS"
            and r["saif_power_status"] == "PASS"
            and r["read_saif_status"] == "PASS"
            and bool(r["target_part_match"])
            for r in rows
        )

    summary = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "targetPart": TARGET_PART,
        "estimatedOnly": True,
        "measuredOnBoard": False,
        "results": rows,
        "sensitivity": sensitivity,
        "g1dClosureRecommended": g1d_close,
        "tables": {"csv": str(csv_path), "tex": str(tex_path)},
        "notes": [
            "All values are ESTIMATED_PRE_BOARD_ONLY (never MEASURED_ON_BOARD).",
            "Vectorless and SAIF-guided power are reported separately.",
            "If SAIF generation/mapping fails, G1d stays OPEN and vectorless remains exploratory evidence.",
        ],
    }
    (OUT_ROOT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
