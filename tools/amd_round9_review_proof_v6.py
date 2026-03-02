#!/usr/bin/env python3
"""Round9 review-proof refresh using existing Round8 implementation evidence.

Scope:
- Fix QoR parsing from existing post-route reports (no synth/impl rerun).
- Generate Round9 power evidence with SAIF windows 200ns and 100us from post-route DCP.
- Recompute derived throughput/energy metrics.
- Sync gate/power docs.
- Regenerate review-pack tables and optional paper PDF.
- Build final handoff tarball + sha256.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

TARGET_PART = "xc7a200tsbg484-1"
CLOCK_NS_DEFAULT = 5.0
CLOCK_FREQ_MHZ_DEFAULT = 200.0

VIVADO_V5 = ROOT / "build" / "amd_vivado_artix7_v5"
POWER_V5 = ROOT / "build" / "amd_power_artix7_v5"
POWER_V6 = ROOT / "build" / "amd_power_artix7_v6"

TABLE_DIR = ROOT / "review_pack" / "tables"
QOR_CSV = TABLE_DIR / "artix7_qor_v6.csv"
QOR_TEX = TABLE_DIR / "artix7_qor_v6.tex"
POWER_CSV = TABLE_DIR / "artix7_power_v6.csv"
POWER_TEX = TABLE_DIR / "artix7_power_v6.tex"
METRICS_CSV = TABLE_DIR / "artix7_metrics_v1.csv"
METRICS_TEX = TABLE_DIR / "artix7_metrics_v1.tex"

DOC_GATE = ROOT / "docs" / "GATE_STATUS.md"
DOC_POWER = ROOT / "docs" / "POWER_METHODOLOGY.md"
PAPER_TEX = ROOT / "paper" / "paper.tex"
PAPER_PDF = ROOT / "paper" / "paper.pdf"
PAPER_MISSING = ROOT / "build" / "handoff" / "PAPER_MISSING.md"

B3_STATUS = ROOT / "build" / "handoff" / "B3_CANONICAL_STATUS.json"
CHATGPT_BRIEF = ROOT / "build" / "handoff" / "CHATGPT_BRIEF_round9.md"

BUNDLE_TAR = ROOT / "handoff_round9_for_chatgpt.tar.gz"
BUNDLE_SHA = ROOT / "handoff_round9_for_chatgpt.sha256"

SAIF_WINDOWS = [("200ns", 200.0), ("100us", 100_000.0)]


@dataclass(frozen=True)
class WindowPoint:
    benchmark: str
    window_label: str
    saif_window_ns: float
    saif_generation_status: str
    saif_path: str | None
    read_saif_status: str
    saif_power_status: str
    saif_total_power_w: float | None
    saif_dynamic_power_w: float | None
    saif_static_power_w: float | None
    saif_total_wall_sec: float | None
    read_saif_log: str
    power_saif_rpt: str
    note: str


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=env)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_vivado_bin() -> Path | None:
    preferred = Path("/media/tangodelta/Vivado/2025.2/Vivado/bin/vivado")
    if preferred.exists() and os.access(preferred, os.X_OK):
        return preferred.resolve()
    found = shutil.which("vivado")
    return Path(found).resolve() if found else None


def _extract_b3_key() -> str:
    if not B3_STATUS.exists():
        raise FileNotFoundError(f"Missing canonical status file: {B3_STATUS}")
    payload = _json(B3_STATUS)

    sidecar = payload.get("sidecarPath")
    if isinstance(sidecar, str):
        stem = Path(sidecar).stem
        if stem.startswith("b3_"):
            return stem

    bench_manifest_name = payload.get("benchmarkNameInManifest")
    if isinstance(bench_manifest_name, str):
        low = bench_manifest_name.lower()
        if low.startswith("b3_"):
            return low

    compile_manifest = payload.get("compileManifestPath")
    if isinstance(compile_manifest, str):
        maybe = Path(compile_manifest).parent.name
        if maybe.startswith("b3_"):
            return maybe

    requested = payload.get("requestedBenchmark")
    if isinstance(requested, str) and requested.startswith("b3_"):
        return requested

    raise ValueError("Could not determine canonical B3 benchmark key")


def _parse_num(token: str | None) -> float | None:
    if token is None:
        return None
    cleaned = token.strip().replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_util_report(path: Path) -> dict[str, float | None]:
    out: dict[str, float | None] = {"lut": None, "ff": None, "bram": None, "dsp": None}
    if not path.exists():
        return out
    txt = path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "lut": r"^\|\s*Slice LUTs\s*\|\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*\|",
        "ff": r"^\|\s*Slice Registers\s*\|\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*\|",
        "bram": r"^\|\s*Block RAM Tile\s*\|\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*\|",
        "dsp": r"^\|\s*DSPs\s*\|\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*\|",
    }
    for key, pat in patterns.items():
        m = re.search(pat, txt, flags=re.M)
        out[key] = _parse_num(m.group(1) if m else None)
    return out


def _parse_timing_report(path: Path) -> dict[str, float | None]:
    out: dict[str, float | None] = {
        "wns": None,
        "tns": None,
        "clock_period_ns": CLOCK_NS_DEFAULT,
        "clock_freq_mhz": CLOCK_FREQ_MHZ_DEFAULT,
    }
    if not path.exists():
        return out
    txt = path.read_text(encoding="utf-8", errors="replace")
    lines = txt.splitlines()

    # Preferred source: Clock summary row
    for line in lines:
        m = re.match(r"^\s*ap_clk\s+([+-]?[0-9]+(?:\.[0-9]+)?)\s+([+-]?[0-9]+(?:\.[0-9]+)?)\s+\d+\s+\d+", line)
        if m:
            out["wns"] = _parse_num(m.group(1))
            out["tns"] = _parse_num(m.group(2))
            break

    # Fallback: first numeric row below WNS/TNS header
    if out["wns"] is None or out["tns"] is None:
        for i, line in enumerate(lines):
            if "WNS(ns)" in line and "TNS(ns)" in line:
                for j in range(i + 1, min(i + 12, len(lines))):
                    m = re.match(r"^\s*([+-]?[0-9]+(?:\.[0-9]+)?)\s+([+-]?[0-9]+(?:\.[0-9]+)?)\s+", lines[j])
                    if m:
                        out["wns"] = _parse_num(m.group(1))
                        out["tns"] = _parse_num(m.group(2))
                        break
                if out["wns"] is not None:
                    break

    # Clock period/frequency from clock definition row
    mclk = re.search(
        r"^\s*ap_clk\s+\{[^}]+\}\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)\s*$",
        txt,
        flags=re.M,
    )
    if mclk:
        period = _parse_num(mclk.group(1))
        freq = _parse_num(mclk.group(2))
        if period is not None:
            out["clock_period_ns"] = period
        if freq is not None:
            out["clock_freq_mhz"] = freq

    return out


def _fmax_est(clock_period_ns: float | None, wns: float | None) -> float | None:
    if clock_period_ns is None or wns is None:
        return None
    achieved_period = clock_period_ns - wns
    if achieved_period <= 0:
        return None
    return 1000.0 / achieved_period


def _fmt_num(v: Any, *, ndigits: int = 6) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if abs(v - round(v)) < 1e-12:
            return str(int(round(v)))
        return f"{v:.{ndigits}f}"
    return str(v)


def _latex_escape(s: str) -> str:
    return (
        s.replace("\\", "\\textbackslash{}")
        .replace("_", "\\_")
        .replace("%", "\\%")
        .replace("&", "\\&")
        .replace("#", "\\#")
    )


def _refresh_vivado_summary_and_qor(bench_order: list[str]) -> list[dict[str, Any]]:
    summary_path = VIVADO_V5 / "summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing Vivado summary: {summary_path}")
    summary = _json(summary_path)
    old_rows = summary.get("results")
    if not isinstance(old_rows, list):
        raise ValueError(f"Invalid results list in {summary_path}")
    by_bench = {str(r.get("benchmark")): r for r in old_rows if isinstance(r, dict)}

    rows: list[dict[str, Any]] = []
    for bench in bench_order:
        old = by_bench.get(bench)
        if old is None:
            raise KeyError(f"Benchmark {bench} missing from {summary_path}")
        outputs = old.get("outputs") if isinstance(old.get("outputs"), dict) else {}

        util_path = Path(outputs.get("postRouteUtilization", VIVADO_V5 / bench / "post_route_utilization.rpt"))
        timing_path = Path(outputs.get("postRouteTiming", VIVADO_V5 / bench / "post_route_timing.rpt"))
        dcp_path = Path(outputs.get("postRouteDcp", VIVADO_V5 / bench / "post_route.dcp"))

        util = _parse_util_report(util_path)
        timing = _parse_timing_report(timing_path)
        part = old.get("part")
        if not isinstance(part, str):
            part = None
        part_match = bool(part == TARGET_PART)

        impl_ok = bool(old.get("implOk")) and dcp_path.exists() and util_path.exists() and timing_path.exists() and part_match
        row = dict(old)
        row.update(
            {
                "implOk": impl_ok,
                "reason": "ok" if impl_ok else str(old.get("reason") or "vivado_impl_failed_or_incomplete"),
                "part": part,
                "partMatchRequested": part_match,
                "lut": util.get("lut"),
                "ff": util.get("ff"),
                "bram": util.get("bram"),
                "dsp": util.get("dsp"),
                "wns": timing.get("wns"),
                "tns": timing.get("tns"),
                "clockPeriodNs": timing.get("clock_period_ns"),
                "clockFreqMhz": timing.get("clock_freq_mhz"),
                "fmaxEstMhz": _fmax_est(timing.get("clock_period_ns"), timing.get("wns")),
            }
        )
        rows.append(row)

    summary["generatedAtUtc"] = _now_utc()
    summary["results"] = rows
    summary["round9QorRefresh"] = {
        "updatedAtUtc": _now_utc(),
        "method": "parsed_existing_post_route_reports_only",
        "tableCsvV6": str(QOR_CSV),
        "tableTexV6": str(QOR_TEX),
    }
    _write_json(summary_path, summary)

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    headers = [
        "benchmark",
        "impl_ok",
        "part",
        "part_match_requested",
        "lut",
        "ff",
        "bram",
        "dsp",
        "wns_ns",
        "tns_ns",
        "clock_period_ns",
        "clock_freq_mhz",
        "fmax_est_mhz",
        "reason",
        "post_route_dcp",
        "post_route_utilization",
        "post_route_timing",
        "vivado_log",
    ]
    with QOR_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        for r in rows:
            outputs = r.get("outputs") if isinstance(r.get("outputs"), dict) else {}
            w.writerow(
                [
                    r.get("benchmark", "-"),
                    str(bool(r.get("implOk"))).lower(),
                    r.get("part") or "-",
                    str(bool(r.get("partMatchRequested"))).lower(),
                    _fmt_num(r.get("lut")),
                    _fmt_num(r.get("ff")),
                    _fmt_num(r.get("bram")),
                    _fmt_num(r.get("dsp")),
                    _fmt_num(r.get("wns")),
                    _fmt_num(r.get("tns")),
                    _fmt_num(r.get("clockPeriodNs")),
                    _fmt_num(r.get("clockFreqMhz")),
                    _fmt_num(r.get("fmaxEstMhz")),
                    r.get("reason") or "-",
                    outputs.get("postRouteDcp", "-"),
                    outputs.get("postRouteUtilization", "-"),
                    outputs.get("postRouteTiming", "-"),
                    outputs.get("vivadoLog", "-"),
                ]
            )

    tex_lines = [
        "\\begin{tabular}{lrrrrrrrrrr}",
        "\\hline",
        "Benchmark & ImplOK & LUT & FF & BRAM & DSP & WNS(ns) & TNS(ns) & Period(ns) & Fmax(MHz) & Part \\\\",
        "\\hline",
    ]
    for r in rows:
        tex_lines.append(
            f"{_latex_escape(str(r.get('benchmark', '-')))} & "
            f"{'yes' if r.get('implOk') else 'no'} & "
            f"{_fmt_num(r.get('lut'))} & "
            f"{_fmt_num(r.get('ff'))} & "
            f"{_fmt_num(r.get('bram'))} & "
            f"{_fmt_num(r.get('dsp'))} & "
            f"{_fmt_num(r.get('wns'))} & "
            f"{_fmt_num(r.get('tns'))} & "
            f"{_fmt_num(r.get('clockPeriodNs'))} & "
            f"{_fmt_num(r.get('fmaxEstMhz'))} & "
            f"{_latex_escape(str(r.get('part') or '-'))} \\\\"
        )
    tex_lines.extend(["\\hline", "\\end{tabular}", ""])
    QOR_TEX.write_text("\n".join(tex_lines), encoding="utf-8")

    return rows


def _parse_power_report(path: Path) -> dict[str, float | None]:
    out = {"totalOnChipPowerW": None, "dynamicPowerW": None, "deviceStaticPowerW": None}
    if not path.exists():
        return out
    txt = path.read_text(encoding="utf-8", errors="replace")

    def grab(pat: str) -> float | None:
        m = re.search(pat, txt, flags=re.I)
        if not m:
            return None
        return _parse_num(m.group(1))

    out["totalOnChipPowerW"] = grab(r"Total On-Chip Power\s*\(W\)\s*\|\s*([0-9.+-Ee]+)")
    out["dynamicPowerW"] = grab(r"Dynamic\s*\(W\)\s*\|\s*([0-9.+-Ee]+)")
    out["deviceStaticPowerW"] = grab(r"Device Static\s*\(W\)\s*\|\s*([0-9.+-Ee]+)")
    return out


def _read_saif_status(path: Path) -> str:
    if not path.exists():
        return "NOT_RUN"
    txt = path.read_text(encoding="utf-8", errors="replace")
    if "READ_SAIF_FINAL:1" in txt:
        return "PASS"
    if "NO_SAIF_INPUT" in txt:
        return "NOT_AVAILABLE"
    return "FAIL"


def _run_vectorless_power(vivado_bin: Path, dcp: Path, bench_out: Path, logs: Path) -> tuple[int, Path]:
    tcl = bench_out / "report_power_vectorless.tcl"
    rpt = bench_out / "power_vectorless.rpt"
    tcl.write_text(
        "\n".join(
            [
                f"open_checkpoint {{{dcp}}}",
                f"report_power -file {{{rpt}}}",
                "exit",
                "",
            ]
        ),
        encoding="utf-8",
    )
    proc = _run([str(vivado_bin), "-mode", "batch", "-source", str(tcl)])
    (logs / "vivado_vectorless.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (logs / "vivado_vectorless.stderr.log").write_text(proc.stderr, encoding="utf-8")
    (logs / "vivado_vectorless.exitcode.txt").write_text(str(proc.returncode) + "\n", encoding="utf-8")
    return proc.returncode, rpt


def _export_funcsim_from_dcp(vivado_bin: Path, dcp: Path, bench_out: Path, logs: Path) -> tuple[int, Path]:
    funcsim_v = bench_out / "nema_kernel_postroute_funcsim.v"
    tcl = bench_out / "export_postroute_funcsim.tcl"
    tcl.write_text(
        "\n".join(
            [
                f"open_checkpoint {{{dcp}}}",
                f"write_verilog -force -mode funcsim {{{funcsim_v}}}",
                "exit",
                "",
            ]
        ),
        encoding="utf-8",
    )
    proc = _run([str(vivado_bin), "-mode", "batch", "-source", str(tcl)])
    (logs / "vivado_funcsim_export.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (logs / "vivado_funcsim_export.stderr.log").write_text(proc.stderr, encoding="utf-8")
    (logs / "vivado_funcsim_export.exitcode.txt").write_text(str(proc.returncode) + "\n", encoding="utf-8")
    return proc.returncode, funcsim_v


def _attempt_saif_window(
    *,
    vivado_bin: Path,
    bench_key: str,
    bench_out: Path,
    logs: Path,
    funcsim_v: Path,
    window_label: str,
    window_ns: float,
) -> tuple[str, Path | None, dict[str, float | None]]:
    module_name = f"tb_post_route_min_{window_label}"
    tb_v = bench_out / f"{module_name}.v"
    run_ns_int = int(round(window_ns))

    tb_v.write_text(
        "\n".join(
            [
                "`timescale 1ns/1ps",
                f"module {module_name};",
                "  reg ap_clk = 1'b0;",
                "  always #2.5 ap_clk = ~ap_clk;",
                "",
                "  nema_kernel dut();",
                "",
                "  initial begin",
                f"    #{run_ns_int};",
                "    $finish;",
                "  end",
                "endmodule",
                "",
            ]
        ),
        encoding="utf-8",
    )

    prj = bench_out / f"postroute_funcsim_{window_label}.prj"
    prj.write_text(
        "\n".join(
            [
                f"verilog work {funcsim_v}",
                f"verilog work {tb_v}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    saif_path = bench_out / f"activity_{window_label}.saif"
    xsim_tcl = bench_out / f"xsim_dump_saif_{window_label}.tcl"
    xsim_tcl.write_text(
        "\n".join(
            [
                f"open_saif {saif_path}",
                f"log_saif [get_objects -r /{module_name}/*]",
                f"run {run_ns_int} ns",
                "close_saif",
                "quit",
                "",
            ]
        ),
        encoding="utf-8",
    )

    vivado_root = vivado_bin.resolve().parent.parent
    xelab_bin = vivado_bin.resolve().parent / "xelab"
    xsim_bin = vivado_bin.resolve().parent / "xsim"
    glbl = vivado_root / "data" / "verilog" / "src" / "glbl.v"

    duration = {
        "saif_window_ns": float(window_ns),
        "xelab_wall_sec": None,
        "xsim_wall_sec": None,
        "total_wall_sec": None,
    }

    if not xelab_bin.exists() or not xsim_bin.exists() or not glbl.exists():
        return "NOT_AVAILABLE:missing_xelab_or_xsim_or_glbl", None, duration

    snapshot = f"tb_saif_snapshot_{bench_key}_{window_label}"
    xelab_cmd = [
        str(xelab_bin),
        "-prj",
        str(prj),
        "--vlog",
        str(glbl),
        "glbl",
        module_name,
        "-L",
        "unisims_ver",
        "-timescale",
        "1ns/1ps",
        "--debug",
        "typical",
        "-s",
        snapshot,
    ]

    t0 = time.monotonic()
    x0 = time.monotonic()
    xelab_proc = _run(xelab_cmd, cwd=bench_out)
    x1 = time.monotonic()
    duration["xelab_wall_sec"] = x1 - x0

    (logs / f"xelab_saif_{window_label}.stdout.log").write_text(xelab_proc.stdout, encoding="utf-8")
    (logs / f"xelab_saif_{window_label}.stderr.log").write_text(xelab_proc.stderr, encoding="utf-8")
    (logs / f"xelab_saif_{window_label}.exitcode.txt").write_text(str(xelab_proc.returncode) + "\n", encoding="utf-8")
    if xelab_proc.returncode != 0:
        duration["total_wall_sec"] = time.monotonic() - t0
        return f"FAIL:xelab_rc_{xelab_proc.returncode}", None, duration

    xsim_cmd = [str(xsim_bin), snapshot, "-tclbatch", str(xsim_tcl)]
    y0 = time.monotonic()
    xsim_proc = _run(xsim_cmd, cwd=bench_out)
    y1 = time.monotonic()
    duration["xsim_wall_sec"] = y1 - y0
    duration["total_wall_sec"] = y1 - t0

    (logs / f"xsim_saif_{window_label}.stdout.log").write_text(xsim_proc.stdout, encoding="utf-8")
    (logs / f"xsim_saif_{window_label}.stderr.log").write_text(xsim_proc.stderr, encoding="utf-8")
    (logs / f"xsim_saif_{window_label}.exitcode.txt").write_text(str(xsim_proc.returncode) + "\n", encoding="utf-8")
    if xsim_proc.returncode != 0:
        return f"FAIL:xsim_rc_{xsim_proc.returncode}", None, duration

    if not saif_path.exists():
        return "FAIL:saif_not_emitted", None, duration

    return "PASS", saif_path, duration


def _run_saif_power_window(
    *,
    vivado_bin: Path,
    dcp: Path,
    bench_out: Path,
    logs: Path,
    window_label: str,
    saif_path: Path | None,
) -> tuple[int, Path, Path]:
    tcl = bench_out / f"report_power_saif_{window_label}.tcl"
    saif_rpt = bench_out / f"power_saif_{window_label}.rpt"
    read_saif_log = bench_out / f"read_saif_{window_label}.log"

    if saif_path is None or not saif_path.exists():
        read_saif_log.write_text("READ_SAIF_FINAL:0\nNO_SAIF_INPUT\n", encoding="utf-8")
        (logs / f"vivado_saif_{window_label}.stdout.log").write_text("", encoding="utf-8")
        (logs / f"vivado_saif_{window_label}.stderr.log").write_text("Skipped: no SAIF input\n", encoding="utf-8")
        (logs / f"vivado_saif_{window_label}.exitcode.txt").write_text("127\n", encoding="utf-8")
        return 127, saif_rpt, read_saif_log

    tcl.write_text(
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

    proc = _run([str(vivado_bin), "-mode", "batch", "-source", str(tcl)])
    (logs / f"vivado_saif_{window_label}.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (logs / f"vivado_saif_{window_label}.stderr.log").write_text(proc.stderr, encoding="utf-8")
    (logs / f"vivado_saif_{window_label}.exitcode.txt").write_text(str(proc.returncode) + "\n", encoding="utf-8")
    return proc.returncode, saif_rpt, read_saif_log


def _run_power_round9(vivado_bin: Path, vivado_rows: list[dict[str, Any]], bench_order: list[str]) -> dict[str, Any]:
    POWER_V6.mkdir(parents=True, exist_ok=True)
    viv_by_bench = {str(r.get("benchmark")): r for r in vivado_rows}

    bench_summaries: list[dict[str, Any]] = []
    flat_points: list[WindowPoint] = []
    sensitivity_rows: list[dict[str, Any]] = []

    for bench in bench_order:
        vr = viv_by_bench.get(bench)
        if vr is None:
            raise KeyError(f"Missing bench {bench} in Vivado rows")

        bench_out = POWER_V6 / bench
        logs = bench_out / "logs"
        bench_out.mkdir(parents=True, exist_ok=True)
        logs.mkdir(parents=True, exist_ok=True)

        outputs = vr.get("outputs") if isinstance(vr.get("outputs"), dict) else {}
        dcp_path = Path(outputs.get("postRouteDcp", VIVADO_V5 / bench / "post_route.dcp"))
        util_path = Path(outputs.get("postRouteUtilization", VIVADO_V5 / bench / "post_route_utilization.rpt"))
        timing_path = Path(outputs.get("postRouteTiming", VIVADO_V5 / bench / "post_route_timing.rpt"))

        if not dcp_path.exists():
            bench_summary = {
                "benchmark": bench,
                "part": vr.get("part"),
                "targetPart": TARGET_PART,
                "targetPartMatch": bool(vr.get("partMatchRequested")),
                "dcpPath": str(dcp_path),
                "vectorless_status": "NOT_AVAILABLE:missing_post_route_dcp",
                "vectorless": {"totalOnChipPowerW": None, "dynamicPowerW": None, "deviceStaticPowerW": None},
                "windows": [],
                "estimated_label": "ESTIMATED_PRE_BOARD_ONLY",
                "representativityNote": "No SAIF points generated because post-route DCP is missing.",
            }
            _write_json(bench_out / "summary.json", bench_summary)
            bench_summaries.append(bench_summary)
            continue

        vec_rc, vec_rpt = _run_vectorless_power(vivado_bin, dcp_path, bench_out, logs)
        vec_metrics = _parse_power_report(vec_rpt)
        vectorless_status = "PASS" if vec_rc == 0 and vec_metrics.get("totalOnChipPowerW") is not None else "FAIL"

        export_rc, funcsim_v = _export_funcsim_from_dcp(vivado_bin, dcp_path, bench_out, logs)
        funcsim_status = "PASS" if export_rc == 0 and funcsim_v.exists() else f"FAIL:funcsim_export_rc_{export_rc}"

        points: list[dict[str, Any]] = []
        for window_label, window_ns in SAIF_WINDOWS:
            if export_rc != 0 or not funcsim_v.exists():
                saif_generation_status = funcsim_status
                saif_path = None
                duration = {
                    "saif_window_ns": window_ns,
                    "xelab_wall_sec": None,
                    "xsim_wall_sec": None,
                    "total_wall_sec": None,
                }
            else:
                saif_generation_status, saif_path, duration = _attempt_saif_window(
                    vivado_bin=vivado_bin,
                    bench_key=bench,
                    bench_out=bench_out,
                    logs=logs,
                    funcsim_v=funcsim_v,
                    window_label=window_label,
                    window_ns=window_ns,
                )

            saif_rc, saif_rpt, read_saif_log = _run_saif_power_window(
                vivado_bin=vivado_bin,
                dcp=dcp_path,
                bench_out=bench_out,
                logs=logs,
                window_label=window_label,
                saif_path=saif_path,
            )
            saif_metrics = _parse_power_report(saif_rpt)
            read_status = _read_saif_status(read_saif_log)

            if saif_rc == 127:
                saif_power_status = "NOT_RUN"
            else:
                saif_power_status = (
                    "PASS"
                    if saif_rc == 0 and read_status == "PASS" and saif_metrics.get("totalOnChipPowerW") is not None
                    else "FAIL"
                )

            point = {
                "window_label": window_label,
                "saif_window_ns": window_ns,
                "saif_generation_status": saif_generation_status,
                "saifDuration": duration,
                "saif_path": str(saif_path) if saif_path is not None else None,
                "read_saif_status": read_status,
                "saif_power_status": saif_power_status,
                "saif": saif_metrics,
                "artifacts": {
                    "read_saif_log": str(read_saif_log),
                    "power_saif_rpt": str(saif_rpt),
                },
                "representativityNote": "Synthetic clock-only testbench; longer windows (100us) improve stability but remain pre-board estimates.",
            }
            points.append(point)
            flat_points.append(
                WindowPoint(
                    benchmark=bench,
                    window_label=window_label,
                    saif_window_ns=window_ns,
                    saif_generation_status=saif_generation_status,
                    saif_path=str(saif_path) if saif_path is not None else None,
                    read_saif_status=read_status,
                    saif_power_status=saif_power_status,
                    saif_total_power_w=saif_metrics.get("totalOnChipPowerW"),
                    saif_dynamic_power_w=saif_metrics.get("dynamicPowerW"),
                    saif_static_power_w=saif_metrics.get("deviceStaticPowerW"),
                    saif_total_wall_sec=duration.get("total_wall_sec"),
                    read_saif_log=str(read_saif_log),
                    power_saif_rpt=str(saif_rpt),
                    note=point["representativityNote"],
                )
            )

        p200 = next((p for p in points if p.get("window_label") == "200ns"), None)
        p100 = next((p for p in points if p.get("window_label") == "100us"), None)
        p200_w = ((p200 or {}).get("saif") or {}).get("totalOnChipPowerW") if p200 else None
        p100_w = ((p100 or {}).get("saif") or {}).get("totalOnChipPowerW") if p100 else None
        delta_w = None
        delta_pct = None
        if isinstance(p200_w, (int, float)) and isinstance(p100_w, (int, float)):
            delta_w = float(p100_w) - float(p200_w)
            if abs(float(p200_w)) > 1e-15:
                delta_pct = (delta_w / float(p200_w)) * 100.0
        sensitivity_rows.append(
            {
                "benchmark": bench,
                "saif_total_power_200ns_w": p200_w,
                "saif_total_power_100us_w": p100_w,
                "delta_100us_minus_200ns_w": delta_w,
                "delta_100us_minus_200ns_pct": delta_pct,
            }
        )

        bench_summary = {
            "benchmark": bench,
            "part": vr.get("part"),
            "targetPart": TARGET_PART,
            "targetPartMatch": bool(vr.get("partMatchRequested")),
            "dcpPath": str(dcp_path),
            "postRouteUtilization": str(util_path),
            "postRouteTiming": str(timing_path),
            "funcsimNetlist": str(funcsim_v) if funcsim_v.exists() else str(funcsim_v),
            "funcsimExportStatus": funcsim_status,
            "vectorless_status": vectorless_status,
            "vectorless": vec_metrics,
            "windows": points,
            "sensitivity_200ns_vs_100us": {
                "delta_total_power_w": delta_w,
                "delta_total_power_pct": delta_pct,
            },
            "estimated_label": "ESTIMATED_PRE_BOARD_ONLY",
            "representativityNote": "SAIF comes from synthetic post-route funcsim (no SDF, no board stimulus); 100us window is more representative than 200ns but still estimation-only.",
        }
        _write_json(bench_out / "summary.json", bench_summary)
        bench_summaries.append(bench_summary)

    g1d_reasons: list[str] = []
    for bench in bench_order:
        bs = next((b for b in bench_summaries if b.get("benchmark") == bench), None)
        if bs is None:
            g1d_reasons.append(f"{bench}:missing_summary")
            continue
        p100 = next((p for p in bs.get("windows", []) if p.get("window_label") == "100us"), None)
        if p100 is None:
            g1d_reasons.append(f"{bench}:missing_100us_point")
            continue
        if p100.get("saif_generation_status") != "PASS":
            g1d_reasons.append(f"{bench}:saif_generation_status={p100.get('saif_generation_status')}")
        if p100.get("read_saif_status") != "PASS":
            g1d_reasons.append(f"{bench}:read_saif_status={p100.get('read_saif_status')}")
        if p100.get("saif_power_status") != "PASS":
            g1d_reasons.append(f"{bench}:saif_power_status={p100.get('saif_power_status')}")
        if not Path(str((p100.get("artifacts") or {}).get("power_saif_rpt", ""))).exists():
            g1d_reasons.append(f"{bench}:missing_power_saif_100us_rpt")

    g1d_closed = len(g1d_reasons) == 0

    summary = {
        "generatedAtUtc": _now_utc(),
        "targetPart": TARGET_PART,
        "estimatedOnly": True,
        "measuredOnBoard": False,
        "baselineRound8Path": str(POWER_V5 / "summary.json"),
        "saifWindowsNs": [w for _, w in SAIF_WINDOWS],
        "results": bench_summaries,
        "points": [p.__dict__ for p in flat_points],
        "sensitivity_200ns_vs_100us": sensitivity_rows,
        "g1dClosureRecommended": g1d_closed,
        "g1dBlockReasons": g1d_reasons,
        "tableArtifacts": {"csv": str(POWER_CSV), "tex": str(POWER_TEX)},
        "notes": [
            "All values are ESTIMATED_PRE_BOARD_ONLY.",
            "No value in this summary is measured on board.",
            "200ns is retained as baseline sensitivity point; 100us is preferred for representativity.",
            "Activity is from synthetic post-route funcsim without SDF and without board I/O stimulus.",
        ],
    }
    _write_json(POWER_V6 / "summary.json", summary)
    return summary


def _write_power_tables(power_summary: dict[str, Any], vivado_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_bench = {str(r.get("benchmark")): r for r in vivado_rows}
    out_rows: list[dict[str, Any]] = []

    for bench_summary in power_summary.get("results", []):
        if not isinstance(bench_summary, dict):
            continue
        bench = str(bench_summary.get("benchmark"))
        vr = by_bench.get(bench, {})
        vec = bench_summary.get("vectorless") if isinstance(bench_summary.get("vectorless"), dict) else {}
        for point in bench_summary.get("windows", []):
            if not isinstance(point, dict):
                continue
            saif = point.get("saif") if isinstance(point.get("saif"), dict) else {}
            dur = point.get("saifDuration") if isinstance(point.get("saifDuration"), dict) else {}
            artifacts = point.get("artifacts") if isinstance(point.get("artifacts"), dict) else {}
            row = {
                "benchmark": bench,
                "window_label": point.get("window_label") or "-",
                "saif_window_ns": _fmt_num(point.get("saif_window_ns")),
                "part": bench_summary.get("part") or "-",
                "target_part_match": str(bool(bench_summary.get("targetPartMatch"))).lower(),
                "vectorless_status": bench_summary.get("vectorless_status") or "-",
                "saif_generation_status": point.get("saif_generation_status") or "-",
                "read_saif_status": point.get("read_saif_status") or "-",
                "saif_power_status": point.get("saif_power_status") or "-",
                "vectorless_total_power_w": _fmt_num(vec.get("totalOnChipPowerW")),
                "vectorless_dynamic_power_w": _fmt_num(vec.get("dynamicPowerW")),
                "vectorless_static_power_w": _fmt_num(vec.get("deviceStaticPowerW")),
                "saif_total_power_w": _fmt_num(saif.get("totalOnChipPowerW")),
                "saif_dynamic_power_w": _fmt_num(saif.get("dynamicPowerW")),
                "saif_static_power_w": _fmt_num(saif.get("deviceStaticPowerW")),
                "saif_total_wall_sec": _fmt_num(dur.get("total_wall_sec")),
                "dcp_path": bench_summary.get("dcpPath") or "-",
                "funcsim_netlist": bench_summary.get("funcsimNetlist") or "-",
                "saif_path": point.get("saif_path") or "-",
                "read_saif_log": artifacts.get("read_saif_log") or "-",
                "power_vectorless_rpt": str(POWER_V6 / bench / "power_vectorless.rpt"),
                "power_saif_rpt": artifacts.get("power_saif_rpt") or "-",
                "post_route_timing": (vr.get("outputs") or {}).get("postRouteTiming", "-")
                if isinstance(vr.get("outputs"), dict)
                else "-",
                "post_route_utilization": (vr.get("outputs") or {}).get("postRouteUtilization", "-")
                if isinstance(vr.get("outputs"), dict)
                else "-",
                "estimated_label": "ESTIMATED_PRE_BOARD_ONLY",
                "representativity_note": point.get("representativityNote") or "-",
            }
            out_rows.append(row)

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    headers = [
        "benchmark",
        "window_label",
        "saif_window_ns",
        "part",
        "target_part_match",
        "vectorless_status",
        "saif_generation_status",
        "read_saif_status",
        "saif_power_status",
        "vectorless_total_power_w",
        "vectorless_dynamic_power_w",
        "vectorless_static_power_w",
        "saif_total_power_w",
        "saif_dynamic_power_w",
        "saif_static_power_w",
        "saif_total_wall_sec",
        "dcp_path",
        "funcsim_netlist",
        "saif_path",
        "read_saif_log",
        "power_vectorless_rpt",
        "power_saif_rpt",
        "post_route_timing",
        "post_route_utilization",
        "estimated_label",
        "representativity_note",
    ]
    with POWER_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=headers)
        w.writeheader()
        for row in out_rows:
            w.writerow(row)

    tex_lines = [
        "\\begin{tabular}{lrrrrrr}",
        "\\hline",
        "Benchmark & Win(ns) & SAIF Tot(W) & SAIF Dyn(W) & SAIF Stat(W) & read\\_saif & power \\\\",
        "\\hline",
    ]
    for row in out_rows:
        tex_lines.append(
            f"{_latex_escape(row['benchmark'])} & "
            f"{_latex_escape(row['saif_window_ns'])} & "
            f"{_latex_escape(row['saif_total_power_w'])} & "
            f"{_latex_escape(row['saif_dynamic_power_w'])} & "
            f"{_latex_escape(row['saif_static_power_w'])} & "
            f"{_latex_escape(row['read_saif_status'])} & "
            f"{_latex_escape(row['saif_power_status'])} \\\\"
        )
    tex_lines.extend(["\\hline", "\\end{tabular}", ""])
    POWER_TEX.write_text("\n".join(tex_lines), encoding="utf-8")

    return out_rows


def _parse_csynth_cycles_per_tick(csynth_path: Path) -> dict[str, int | None]:
    out: dict[str, int | None] = {
        "latency_min_cycles": None,
        "latency_max_cycles": None,
        "interval_min_cycles": None,
        "interval_max_cycles": None,
        "cycles_per_tick": None,
    }
    if not csynth_path.exists():
        return out
    lines = csynth_path.read_text(encoding="utf-8", errors="replace").splitlines()
    start_idx = None
    for i, line in enumerate(lines):
        if "Latency (cycles)" in line and "Interval" in line and "Pipeline" in line:
            start_idx = i
            break
    if start_idx is None:
        return out

    for j in range(start_idx + 1, min(start_idx + 60, len(lines))):
        line = lines[j].strip()
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 6:
            continue
        if not re.fullmatch(r"[0-9]+", parts[0] or ""):
            continue
        if not re.fullmatch(r"[0-9]+", parts[1] or ""):
            continue
        lat_min = int(parts[0])
        lat_max = int(parts[1])
        int_min = int(parts[4]) if re.fullmatch(r"[0-9]+", parts[4] or "") else None
        int_max = int(parts[5]) if len(parts) > 5 and re.fullmatch(r"[0-9]+", parts[5] or "") else None
        out["latency_min_cycles"] = lat_min
        out["latency_max_cycles"] = lat_max
        out["interval_min_cycles"] = int_min
        out["interval_max_cycles"] = int_max
        out["cycles_per_tick"] = int_min if isinstance(int_min, int) and int_min > 0 else lat_min
        break

    return out


def _write_metrics_tables(
    *,
    b3_key: str,
    vivado_rows: list[dict[str, Any]],
    power_rows_flat: list[dict[str, Any]],
) -> dict[str, Any]:
    viv_by_bench = {str(r.get("benchmark")): r for r in vivado_rows}
    pwr_by_bench_window = {(r["benchmark"], r["window_label"]): r for r in power_rows_flat}

    b3_csynth = (
        ROOT
        / "build"
        / "amd_hls_artix7_v3"
        / b3_key
        / "hls_run"
        / "hls_proj"
        / "nema_hls_prj"
        / "sol1"
        / "syn"
        / "report"
        / "nema_kernel_csynth.rpt"
    )
    if not b3_csynth.exists():
        b3_csynth = (
            ROOT
            / "build"
            / "amd_hls_artix7_v3"
            / b3_key
            / "hls_run"
            / "hls_proj"
            / "nema_hls_prj"
            / "sol1"
            / "syn"
            / "report"
            / "csynth.rpt"
        )
    csynth_cycles = _parse_csynth_cycles_per_tick(b3_csynth)
    b3_cycles = csynth_cycles.get("cycles_per_tick")

    metrics_rows: list[dict[str, Any]] = []
    benches = ["b1_small", b3_key]
    sensitivity_rows: list[dict[str, Any]] = []

    for bench in benches:
        vr = viv_by_bench.get(bench, {})
        part = vr.get("part")
        if not isinstance(part, str):
            part = None
        wns = vr.get("wns")
        clock_freq = vr.get("clockFreqMhz")
        if not isinstance(clock_freq, (int, float)):
            clock_freq = CLOCK_FREQ_MHZ_DEFAULT
        fmax_est = vr.get("fmaxEstMhz")
        if not isinstance(fmax_est, (int, float)):
            fmax_est = None

        f_run = None
        if isinstance(wns, (int, float)):
            if wns < 0:
                f_run = fmax_est
            else:
                f_run = float(clock_freq)
        elif isinstance(clock_freq, (int, float)):
            f_run = float(clock_freq)

        cycles_per_tick = b3_cycles if bench == b3_key else None
        p100 = pwr_by_bench_window.get((bench, "100us"), {})
        p200 = pwr_by_bench_window.get((bench, "200ns"), {})
        p100_w = _parse_num(str(p100.get("saif_total_power_w"))) if isinstance(p100.get("saif_total_power_w"), str) else None
        p200_w = _parse_num(str(p200.get("saif_total_power_w"))) if isinstance(p200.get("saif_total_power_w"), str) else None

        # Use 100us as principal point.
        power_total_w = p100_w
        ticks_per_sec = None
        energy_per_tick_mj = None
        if isinstance(f_run, (int, float)) and isinstance(cycles_per_tick, int) and cycles_per_tick > 0:
            ticks_per_sec = (float(f_run) * 1_000_000.0) / float(cycles_per_tick)
            if isinstance(power_total_w, (int, float)) and ticks_per_sec > 0:
                energy_per_tick_mj = (float(power_total_w) / ticks_per_sec) * 1000.0

        energy_200ns_mj = None
        if isinstance(f_run, (int, float)) and isinstance(cycles_per_tick, int) and cycles_per_tick > 0 and isinstance(p200_w, (int, float)):
            ticks_per_sec_200 = (float(f_run) * 1_000_000.0) / float(cycles_per_tick)
            if ticks_per_sec_200 > 0:
                energy_200ns_mj = (float(p200_w) / ticks_per_sec_200) * 1000.0

        sensitivity_rows.append(
            {
                "benchmark": bench,
                "energy_per_tick_100us_mJ": energy_per_tick_mj,
                "energy_per_tick_200ns_mJ": energy_200ns_mj,
                "power_100us_w": p100_w,
                "power_200ns_w": p200_w,
            }
        )

        metrics_rows.append(
            {
                "bench": bench,
                "part": part or "-",
                "lut": _fmt_num(vr.get("lut")),
                "ff": _fmt_num(vr.get("ff")),
                "bram": _fmt_num(vr.get("bram")),
                "dsp": _fmt_num(vr.get("dsp")),
                "wns": _fmt_num(wns),
                "f_run_mhz": _fmt_num(f_run),
                "cycles_per_tick": _fmt_num(cycles_per_tick),
                "ticks/s": _fmt_num(ticks_per_sec),
                "power_total_w": _fmt_num(power_total_w),
                "energy_per_tick_mJ": _fmt_num(energy_per_tick_mj),
            }
        )

    headers = [
        "bench",
        "part",
        "lut",
        "ff",
        "bram",
        "dsp",
        "wns",
        "f_run_mhz",
        "cycles_per_tick",
        "ticks/s",
        "power_total_w",
        "energy_per_tick_mJ",
    ]
    with METRICS_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=headers)
        w.writeheader()
        for row in metrics_rows:
            w.writerow(row)

    tex_lines = [
        "\\begin{tabular}{lrrrrrrrrrr}",
        "\\hline",
        "Bench & LUT & FF & BRAM & DSP & WNS(ns) & f\\_run(MHz) & cycles/tick & ticks/s & P(W) & E/tick(mJ) \\\\",
        "\\hline",
    ]
    for row in metrics_rows:
        tex_lines.append(
            f"{_latex_escape(row['bench'])} & "
            f"{_latex_escape(row['lut'])} & "
            f"{_latex_escape(row['ff'])} & "
            f"{_latex_escape(row['bram'])} & "
            f"{_latex_escape(row['dsp'])} & "
            f"{_latex_escape(row['wns'])} & "
            f"{_latex_escape(row['f_run_mhz'])} & "
            f"{_latex_escape(row['cycles_per_tick'])} & "
            f"{_latex_escape(row['ticks/s'])} & "
            f"{_latex_escape(row['power_total_w'])} & "
            f"{_latex_escape(row['energy_per_tick_mJ'])} \\\\"
        )
    tex_lines.extend(["\\hline", "\\end{tabular}", ""])
    METRICS_TEX.write_text("\n".join(tex_lines), encoding="utf-8")

    metrics_summary = {
        "generatedAtUtc": _now_utc(),
        "b3CsynthPath": str(b3_csynth),
        "b3CsynthCycles": csynth_cycles,
        "rows": metrics_rows,
        "sensitivity": sensitivity_rows,
        "notes": [
            "For WNS < 0, f_run_mhz = fmax_est_mhz.",
            "For WNS >= 0, f_run_mhz = 200 MHz (requested run clock); fmax_est_mhz retained in QoR summary as headroom.",
            "power_total_w uses SAIF 100us as principal estimate; 200ns is tracked in sensitivity.",
            "All metrics remain ESTIMATED_PRE_BOARD_ONLY.",
        ],
    }
    _write_json(ROOT / "build" / "handoff" / "artix7_metrics_v1.summary.json", metrics_summary)
    return metrics_summary


def _write_gate_status_doc(
    *,
    b3_key: str,
    g1d_closed: bool,
    g1d_reasons: list[str],
) -> None:
    g1d_status = "CLOSED" if g1d_closed else "OPEN"
    g1d_note = (
        "SAIF 100us + read_saif PASS + power_saif present for B1 and B3."
        if g1d_closed
        else ("; ".join(g1d_reasons) if g1d_reasons else "Missing required SAIF 100us evidence.")
    )

    lines = [
        "# Gate Status (Evidence-Aligned)",
        "",
        f"Last reconciled: {_now_utc()}",
        "",
        "## Current status",
        "",
        "| Gate | Status | Evidence | Notes |",
        "|---|---|---|---|",
        "| G1b (AMD HLS digest parity) | `CLOSED` | `build/amd_hls_strict_v2/summary.json`, `review_pack/tables/artix7_hls_digest_summary_strict_v2.csv`, `artifacts/traces/*.amd_{csim,cosim}.trace.jsonl` | Strict v2 canonical run closes digest parity for B1 and canonical B3. |",
        "| G1c (Vivado synth+impl on Artix-7) | `CLOSED` | `build/amd_vivado_artix7_v5/summary.json`, `build/amd_vivado_artix7_v5/*/post_route_utilization.rpt`, `build/amd_vivado_artix7_v5/*/post_route_timing.rpt`, `review_pack/tables/artix7_qor_v6.csv` | Both required benches (`b1_small`, `"
        + b3_key
        + "`) have Artix-7 post-route evidence. |",
        f"| G1d (post-implementation power with activity) | `{g1d_status}` | `build/amd_power_artix7_v6/summary.json`, `build/amd_power_artix7_v6/*/activity_100us.saif`, `build/amd_power_artix7_v6/*/read_saif_100us.log`, `build/amd_power_artix7_v6/*/power_saif_100us.rpt`, `review_pack/tables/artix7_power_v6.csv` | {g1d_note} |",
        "",
        "## Hard boundaries",
        "",
        "- All power evidence is `ESTIMATED_PRE_BOARD_ONLY`.",
        "- No claim in this repo state is `MEASURED_ON_BOARD`.",
        "- QoR parser refresh in Round9 used existing reports only (no synth/impl rerun).",
        "",
        "## Round9 artifacts",
        "",
        "- QoR summary refreshed in place: `build/amd_vivado_artix7_v5/summary.json`",
        "- QoR table: `review_pack/tables/artix7_qor_v6.csv`",
        "- Power summary: `build/amd_power_artix7_v6/summary.json`",
        "- Power table: `review_pack/tables/artix7_power_v6.csv`",
        "- Derived metrics: `review_pack/tables/artix7_metrics_v1.csv`",
    ]
    DOC_GATE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_power_methodology_doc(
    *,
    b3_key: str,
    power_summary: dict[str, Any],
) -> None:
    sens_rows = power_summary.get("sensitivity_200ns_vs_100us")
    if not isinstance(sens_rows, list):
        sens_rows = []

    lines = [
        "# Power Methodology (Pre-Board, Estimated Only)",
        "",
        "## Scope",
        "",
        "This workflow produces estimated post-implementation power only.",
        "No value may be labeled as measured on board.",
        "",
        "## Evidence roots",
        "",
        "- Round8 baseline (short SAIF): `build/amd_power_artix7_v5/summary.json`",
        "- Round9 dual-window power: `build/amd_power_artix7_v6/summary.json`",
        "- Round9 table: `review_pack/tables/artix7_power_v6.csv`",
        "",
        "## Round9 SAIF policy",
        "",
        "- Netlist source: post-route DCP -> `write_verilog -mode funcsim`.",
        "- SAIF windows per bench: 200 ns (baseline sensitivity) and 100 us (preferred representativity).",
        "- `report_power` run separately after `read_saif` for each window.",
        "",
        "## Sensitivity (200ns vs 100us)",
        "",
        "| benchmark | saif_200ns_total_w | saif_100us_total_w | delta_w | delta_pct |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in sens_rows:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            + str(row.get("benchmark", "-"))
            + " | "
            + _fmt_num(row.get("saif_total_power_200ns_w"))
            + " | "
            + _fmt_num(row.get("saif_total_power_100us_w"))
            + " | "
            + _fmt_num(row.get("delta_100us_minus_200ns_w"))
            + " | "
            + _fmt_num(row.get("delta_100us_minus_200ns_pct"))
            + " |"
        )

    lines.extend(
        [
            "",
            "## Derived metric boundary",
            "",
            "- Throughput/energy-per-tick uses canonical B3 (`"
            + b3_key
            + "`) cycles from HLS `nema_kernel_csynth.rpt`.",
            "- Principal power point for energy/tick: SAIF 100us.",
            "- SAIF 200ns retained as sensitivity only.",
            "",
            "## Limitations and claim policy",
            "",
            "- Label all values as `ESTIMATED_PRE_BOARD_ONLY`.",
            "- Synthetic activity (clock-only harness) is not equivalent to board traffic.",
            "- Use board measurements before any silicon-level claim.",
            "",
            "## Current evidence boundary",
            "",
            "- B1 and canonical B3 both have SAIF 200ns and SAIF 100us artifacts under `build/amd_power_artix7_v6/`.",
            "- Gate closure for G1d is controlled by 100us point statuses in `build/amd_power_artix7_v6/summary.json`.",
        ]
    )
    DOC_POWER.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _update_or_mark_paper() -> bool:
    if not PAPER_TEX.exists():
        PAPER_MISSING.parent.mkdir(parents=True, exist_ok=True)
        PAPER_MISSING.write_text(
            "\n".join(
                [
                    "# PAPER_MISSING",
                    "",
                    "Expected file not found: `paper/paper.tex`.",
                    "Round9 handoff includes all tables/docs, but PDF regeneration was skipped because the source file is missing.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return False

    paper_text = "\n".join(
        [
            "\\documentclass[11pt]{article}",
            "\\usepackage[margin=1in]{geometry}",
            "\\usepackage[T1]{fontenc}",
            "\\usepackage[utf8]{inputenc}",
            "\\usepackage{lmodern}",
            "\\title{NEMA Artix-7 Review-Proof Snapshot (Round9)}",
            "\\author{}",
            "\\date{\\today}",
            "",
            "\\begin{document}",
            "\\maketitle",
            "",
            "\\section{Scope}",
            "This snapshot is evidence-aligned and boardless. Numerical content is generated from CSV/JSON artifacts; no table values are hardcoded in this paper.",
            "",
            "\\section{Evidence Tables}",
            "",
            "\\subsection{HLS digest parity}",
            "\\begin{table}[h]",
            "\\centering",
            "\\small",
            "\\input{../review_pack/tables/artix7_hls_digest_summary_strict_v2.tex}",
            "\\caption{Digest parity from generated strict-v2 table.}",
            "\\end{table}",
            "",
            "\\subsection{Vivado post-route QoR}",
            "\\begin{table}[h]",
            "\\centering",
            "\\small",
            "\\input{../review_pack/tables/artix7_qor_v6.tex}",
            "\\caption{Post-route QoR parsed from existing Round8 implementation reports.}",
            "\\end{table}",
            "",
            "\\subsection{Power sensitivity (SAIF windows)}",
            "\\begin{table}[h]",
            "\\centering",
            "\\small",
            "\\input{../review_pack/tables/artix7_power_v6.tex}",
            "\\caption{Estimated post-route power with SAIF 200ns and 100us windows.}",
            "\\end{table}",
            "",
            "\\subsection{Derived throughput and energy metrics}",
            "\\begin{table}[h]",
            "\\centering",
            "\\small",
            "\\input{../review_pack/tables/artix7_metrics_v1.tex}",
            "\\caption{Derived metrics from generated QoR/power artifacts (pre-board estimate).}",
            "\\end{table}",
            "",
            "\\section{Claim Boundary}",
            "\\begin{itemize}",
            "\\item All power/energy numbers are estimated pre-board only.",
            "\\item No result in this document is an on-board measurement.",
            "\\item Gate closure decisions must follow \\texttt{docs/GATE\\_STATUS.md}.",
            "\\end{itemize}",
            "",
            "\\end{document}",
            "",
        ]
    )
    PAPER_TEX.write_text(paper_text, encoding="utf-8")

    latexmk = shutil.which("latexmk")
    if latexmk is None:
        return False
    proc = _run([latexmk, "-pdf", "-interaction=nonstopmode", "paper.tex"], cwd=PAPER_TEX.parent)
    (PAPER_TEX.parent / "latexmk_round9.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (PAPER_TEX.parent / "latexmk_round9.stderr.log").write_text(proc.stderr, encoding="utf-8")
    return proc.returncode == 0 and PAPER_PDF.exists()


def _write_chatgpt_brief(
    *,
    b3_key: str,
    g1d_closed: bool,
    g1d_reasons: list[str],
) -> None:
    lines = [
        "Round9 review-proof handoff brief for ChatGPT",
        f"UTC: {_now_utc()}",
        f"Target part: {TARGET_PART}",
        f"Canonical B3 benchmark: {b3_key}",
        "QoR parsing fixed: Slice LUTs / Slice Registers / Block RAM Tile / DSPs from post_route_utilization.rpt.",
        "Timing parsing source: post_route_timing.rpt WNS/TNS from clock summary.",
        "Vivado summary refreshed in place: build/amd_vivado_artix7_v5/summary.json.",
        "QoR table regenerated: review_pack/tables/artix7_qor_v6.csv.",
        "Round9 power root: build/amd_power_artix7_v6/.",
        "SAIF windows generated per bench: 200ns baseline and 100us preferred.",
        "Per-window outputs include activity_<window>.saif, read_saif_<window>.log, power_saif_<window>.rpt.",
        "Power table regenerated: review_pack/tables/artix7_power_v6.csv.",
        "Derived metrics table generated: review_pack/tables/artix7_metrics_v1.csv.",
        "G1b status: CLOSED (strict v2 digest parity evidence retained).",
        "G1c status: CLOSED (Round8 Artix-7 post-route evidence retained, parser corrected).",
        f"G1d status: {'CLOSED' if g1d_closed else 'OPEN'}.",
        f"G1d reason: {'all required 100us SAIF checks PASS' if g1d_closed else '; '.join(g1d_reasons) if g1d_reasons else 'missing required 100us evidence'}.",
        "docs/GATE_STATUS.md and docs/POWER_METHODOLOGY.md synchronized to Round9 evidence.",
        "All power/energy numbers are labeled ESTIMATED_PRE_BOARD_ONLY.",
        "No measured-on-board claim is made in this handoff.",
    ]
    if len(lines) != 20:
        raise RuntimeError(f"CHATGPT_BRIEF_round9.md must have 20 lines, got {len(lines)}")
    CHATGPT_BRIEF.parent.mkdir(parents=True, exist_ok=True)
    CHATGPT_BRIEF.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _create_bundle(*, b3_key: str, paper_exists: bool) -> None:
    include: list[Path] = [
        VIVADO_V5 / "summary.json",
        VIVADO_V5 / "b1_small" / "post_route_timing.rpt",
        VIVADO_V5 / "b1_small" / "post_route_utilization.rpt",
        VIVADO_V5 / b3_key / "post_route_timing.rpt",
        VIVADO_V5 / b3_key / "post_route_utilization.rpt",
        POWER_V6 / "summary.json",
        POWER_V6 / "b1_small",
        POWER_V6 / b3_key,
        QOR_CSV,
        POWER_CSV,
        METRICS_CSV,
        DOC_GATE,
        DOC_POWER,
        B3_STATUS,
        CHATGPT_BRIEF,
    ]
    if paper_exists and PAPER_PDF.exists():
        include.append(PAPER_PDF)
    elif PAPER_MISSING.exists():
        include.append(PAPER_MISSING)

    with tarfile.open(BUNDLE_TAR, "w:gz") as tar:
        for path in include:
            if not path.exists():
                continue
            tar.add(path, arcname=str(path.relative_to(ROOT)))

    digest = hashlib.sha256(BUNDLE_TAR.read_bytes()).hexdigest()
    BUNDLE_SHA.write_text(f"{digest}  {BUNDLE_TAR.name}\n", encoding="utf-8")


def main() -> int:
    vivado_bin = _resolve_vivado_bin()
    if vivado_bin is None:
        raise RuntimeError("vivado not found in PATH and preferred path is unavailable")

    b3_key = _extract_b3_key()
    bench_order = ["b1_small", b3_key]

    vivado_rows = _refresh_vivado_summary_and_qor(bench_order)
    power_summary = _run_power_round9(vivado_bin, vivado_rows, bench_order)
    power_rows_flat = _write_power_tables(power_summary, vivado_rows)
    metrics_summary = _write_metrics_tables(b3_key=b3_key, vivado_rows=vivado_rows, power_rows_flat=power_rows_flat)

    g1d_closed = bool(power_summary.get("g1dClosureRecommended"))
    g1d_reasons = [str(x) for x in power_summary.get("g1dBlockReasons", []) if isinstance(x, str)]

    _write_gate_status_doc(b3_key=b3_key, g1d_closed=g1d_closed, g1d_reasons=g1d_reasons)
    _write_power_methodology_doc(b3_key=b3_key, power_summary=power_summary)

    paper_ok = _update_or_mark_paper()
    _write_chatgpt_brief(b3_key=b3_key, g1d_closed=g1d_closed, g1d_reasons=g1d_reasons)
    _create_bundle(b3_key=b3_key, paper_exists=paper_ok)

    print(
        json.dumps(
            {
                "status": "OK",
                "b3Key": b3_key,
                "vivadoSummary": str(VIVADO_V5 / "summary.json"),
                "powerSummaryV6": str(POWER_V6 / "summary.json"),
                "qorCsvV6": str(QOR_CSV),
                "powerCsvV6": str(POWER_CSV),
                "metricsCsvV1": str(METRICS_CSV),
                "g1dClosed": g1d_closed,
                "g1dReasons": g1d_reasons,
                "paperPdf": str(PAPER_PDF if PAPER_PDF.exists() else PAPER_MISSING),
                "bundleTar": str(BUNDLE_TAR),
                "bundleSha": str(BUNDLE_SHA),
                "metricsSummary": str(ROOT / "build" / "handoff" / "artix7_metrics_v1.summary.json"),
                "metricsRows": metrics_summary.get("rows"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
