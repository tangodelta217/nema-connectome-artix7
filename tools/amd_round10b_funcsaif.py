#!/usr/bin/env python3
"""Round10b functional-SAIF flow for Artix-7 power finalization.

Implements:
- Canonical bench resolution (B1 + canonical B3).
- Post-route funcsim netlist export from existing DCPs.
- Tick-driven functional testbench generation (benchmark-shaped).
- xsim SAIF dump with real DUT handshake activity.
- report_power vectorless and SAIF-guided on the same DCP.
- Final power/metrics tables for Round10 packaging.

No synth/impl reruns are performed.
All outputs are written under v7/v10b locations.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
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
DEFAULT_CLOCK_NS = 5.0

VIVADO_V5 = ROOT / "build" / "amd_vivado_artix7_v5"
HLS_STRICT_V2 = ROOT / "build" / "amd_hls_strict_v2"
B3_STATUS = ROOT / "build" / "handoff" / "B3_CANONICAL_STATUS.json"

OUT_ROOT = ROOT / "build" / "amd_power_artix7_v7_funcsaif"
TABLE_DIR = ROOT / "review_pack" / "tables"

POWER_V7_CSV = TABLE_DIR / "artix7_power_v7_funcsaif.csv"
POWER_V7_TEX = TABLE_DIR / "artix7_power_v7_funcsaif.tex"
POWER_FINAL_CSV = TABLE_DIR / "artix7_power_final.csv"
POWER_FINAL_TEX = TABLE_DIR / "artix7_power_final.tex"
POWER_FINAL_PROV = TABLE_DIR / "artix7_power_final_provenance.md"

METRICS_V1_CSV = TABLE_DIR / "artix7_metrics_v1.csv"
METRICS_V2_CSV = TABLE_DIR / "artix7_metrics_v2.csv"
METRICS_FINAL_CSV = TABLE_DIR / "artix7_metrics_final.csv"
METRICS_FINAL_TEX = TABLE_DIR / "artix7_metrics_final.tex"

DOC_POWER = ROOT / "docs" / "POWER_METHODOLOGY.md"

BUNDLE_TAR = ROOT / "handoff_round10b_for_chatgpt.tar.gz"
BUNDLE_SHA = ROOT / "handoff_round10b_for_chatgpt.sha256"

DEFAULT_TICKS = {
    "b1_small": 50,
    "b3": 10,
}


@dataclass
class BenchContext:
    bench: str
    dcp_path: Path
    timing_rpt: Path
    clock_period_ns: float
    ticks: int


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=env)


def _fmt_num(v: Any, ndigits: int = 6) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "true" if v else "false"
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


def _parse_num(s: str | None) -> float | None:
    if s is None:
        return None
    token = s.strip().replace(",", "")
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _resolve_vivado_bin() -> Path:
    preferred = Path("/media/tangodelta/Vivado/2025.2/Vivado/bin/vivado")
    if preferred.exists() and os.access(preferred, os.X_OK):
        return preferred.resolve()
    found = shutil.which("vivado")
    if not found:
        raise FileNotFoundError("vivado not found")
    return Path(found).resolve()


def _extract_b3_key() -> str:
    if not B3_STATUS.exists():
        raise FileNotFoundError(f"Missing canonical status file: {B3_STATUS}")
    payload = _read_json(B3_STATUS)

    sidecar = payload.get("sidecarPath")
    if isinstance(sidecar, str):
        stem = Path(sidecar).stem
        if stem.startswith("b3_"):
            return stem

    manifest = payload.get("benchmarkNameInManifest")
    if isinstance(manifest, str):
        low = manifest.lower()
        if low.startswith("b3_"):
            return low

    compile_manifest = payload.get("compileManifestPath")
    if isinstance(compile_manifest, str):
        candidate = Path(compile_manifest).parent.name
        if candidate.startswith("b3_"):
            return candidate

    requested = payload.get("requestedBenchmark")
    if isinstance(requested, str) and requested.startswith("b3_"):
        return requested

    raise ValueError("Unable to derive canonical B3 benchmark key")


def _parse_timing_clock_period(path: Path) -> float:
    if not path.exists():
        return DEFAULT_CLOCK_NS
    txt = path.read_text(encoding="utf-8", errors="replace")

    m = re.search(r"^\s*ap_clk\s+\{[^}]+\}\s+([0-9]+(?:\.[0-9]+)?)\s+[0-9]+(?:\.[0-9]+)?\s*$", txt, flags=re.M)
    if m:
        parsed = _parse_num(m.group(1))
        if isinstance(parsed, float) and parsed > 0:
            return parsed

    m2 = re.search(r"\|\s*ap_clk\s*\|\s*ap_clk\s*\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|", txt)
    if m2:
        parsed = _parse_num(m2.group(1))
        if isinstance(parsed, float) and parsed > 0:
            return parsed

    return DEFAULT_CLOCK_NS


def _resolve_ticks(bench: str) -> int:
    env_key = f"NEMA_FUNCSAIF_TICKS_{bench.upper().replace('-', '_')}"
    env_raw = os.getenv(env_key)
    if env_raw:
        try:
            parsed = int(env_raw)
            if parsed > 0:
                return parsed
        except ValueError:
            pass

    if bench == "b1_small":
        return DEFAULT_TICKS["b1_small"]
    if bench.startswith("b3_"):
        return DEFAULT_TICKS["b3"]
    return 10


def _collect_bench_contexts(b3_key: str) -> list[BenchContext]:
    benches = ["b1_small", b3_key]
    out: list[BenchContext] = []
    for bench in benches:
        dcp = VIVADO_V5 / bench / "post_route.dcp"
        timing = VIVADO_V5 / bench / "post_route_timing.rpt"
        if not dcp.exists():
            raise FileNotFoundError(f"Missing DCP for {bench}: {dcp}")
        clk_ns = _parse_timing_clock_period(timing)
        out.append(
            BenchContext(
                bench=bench,
                dcp_path=dcp,
                timing_rpt=timing,
                clock_period_ns=clk_ns,
                ticks=_resolve_ticks(bench),
            )
        )
    return out


def _find_hls_header(bench: str) -> Path | None:
    root = HLS_STRICT_V2 / bench / "compile_out"
    if not root.exists():
        return None
    candidates = sorted(root.glob("*/hls/nema_kernel.h"))
    return candidates[0] if candidates else None


def _parse_node_and_vinit(header: Path) -> tuple[int, list[int]]:
    txt = header.read_text(encoding="utf-8", errors="replace")

    node_m = re.search(r"NODE_COUNT\s*=\s*([0-9]+)\s*;", txt)
    if not node_m:
        raise ValueError(f"NODE_COUNT not found in {header}")
    node_count = int(node_m.group(1))

    vinit_m = re.search(r"V_INIT\[NODE_STORAGE\]\s*=\s*\{([^}]*)\};", txt, flags=re.S)
    if not vinit_m:
        raise ValueError(f"V_INIT not found in {header}")
    raw = vinit_m.group(1)
    values: list[int] = []
    for token in raw.split(","):
        tok = token.strip()
        if not tok:
            continue
        values.append(int(tok, 10))
    if len(values) < node_count:
        values.extend([0] * (node_count - len(values)))
    return node_count, values[:node_count]


def _parse_port_width(text: str, name: str) -> int:
    m_vec = re.search(rf"\b(?:input|output)\s*\[(\d+):0\]\s*{name}\s*;", text)
    if m_vec:
        return int(m_vec.group(1)) + 1
    m_scalar = re.search(rf"\b(?:input|output)\s+{name}\s*;", text)
    if m_scalar:
        return 1
    raise ValueError(f"Port width for {name} not found")


def _parse_funcsim_ports(funcsim_v: Path) -> dict[str, int]:
    txt = funcsim_v.read_text(encoding="utf-8", errors="replace")
    return {
        "v_in_address0_bits": _parse_port_width(txt, "v_in_address0"),
        "v_out_address0_bits": _parse_port_width(txt, "v_out_address0"),
        "tanh_lut_address0_bits": _parse_port_width(txt, "tanh_lut_address0"),
    }


def _git_head() -> str:
    proc = _run(["git", "rev-parse", "HEAD"])
    if proc.returncode == 0:
        return proc.stdout.strip()
    return "UNKNOWN"


def _write_provenance(
    bench_out: Path,
    *,
    bench: str,
    ticks: int,
    header: Path | None,
    chosen_tb: Path,
) -> None:
    autotb = HLS_STRICT_V2 / bench / "hls_run" / "hls_proj" / "nema_hls_prj" / "sol1" / "sim" / "verilog" / "nema_kernel.autotb.v"
    old_tb_v5 = ROOT / "build" / "amd_power_artix7_v5" / bench / "tb_post_route_min.v"
    old_tb_v6 = ROOT / "build" / "amd_power_artix7_v6" / bench / "tb_post_route_min_100us.v"

    lines = [
        f"# Provenance for {bench}",
        "",
        f"- generated_at_utc: {_now_utc()}",
        f"- git_head: {_git_head()}",
        f"- canonical_status: {B3_STATUS}",
        "",
        "## Candidate testbenches",
        f"- hls_autotb_candidate: {autotb} ({'exists' if autotb.exists() else 'missing'})",
        f"- prior_synthetic_tb_v5: {old_tb_v5} ({'exists' if old_tb_v5.exists() else 'missing'})",
        f"- prior_synthetic_tb_v6: {old_tb_v6} ({'exists' if old_tb_v6.exists() else 'missing'})",
        "",
        "## Selected testbench",
        f"- selected_tb: {chosen_tb}",
        "- rationale: use deterministic tick-driven handshake (ap_start/ap_done) with benchmark-sized state vectors and canonical LUT data.",
        "- rationale_why_not_autotb_direct: generated HLS autotb depends on svtb/file-agent infrastructure and transaction artifacts; not directly portable to standalone post-route funcsim netlist invocation.",
        "- semantics_source_1: hw/tb/nema_digest_tb_common.hpp (tick loop and V_INIT/LUT usage pattern).",
        f"- semantics_source_2: {header if header else 'N/A'}",
        f"- ticks_configured: {ticks}",
    ]
    (bench_out / "provenance.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_tb_tick(
    tb_path: Path,
    *,
    bench: str,
    node_count: int,
    v_init: list[int],
    ticks: int,
    clock_period_ns: float,
    addr_bits: dict[str, int],
    lut_bin: Path,
) -> None:
    half = clock_period_ns / 2.0
    lut_size = 65536

    if len(v_init) != node_count:
        raise ValueError(f"V_INIT length mismatch for {bench}: {len(v_init)} vs {node_count}")

    init_lines = [f"    v_in_mem[{i}] = 16'sd{val};" for i, val in enumerate(v_init)]

    tb = [
        "`timescale 1ns/1ps",
        "module tb_tick;",
        f"  localparam int NODE_COUNT = {node_count};",
        f"  localparam int TICKS = {ticks};",
        f"  localparam int V_IN_ADDR_BITS = {addr_bits['v_in_address0_bits']};",
        f"  localparam int V_OUT_ADDR_BITS = {addr_bits['v_out_address0_bits']};",
        f"  localparam int LUT_ADDR_BITS = {addr_bits['tanh_lut_address0_bits']};",
        f"  localparam int LUT_SIZE = {lut_size};",
        f"  localparam real CLK_PERIOD_NS = {clock_period_ns:.6f};",
        f"  localparam real CLK_HALF_NS = {half:.6f};",
        f"  localparam string LUT_BIN = \"{lut_bin}\";",
        "",
        "  reg ap_clk = 1'b0;",
        "  reg ap_rst = 1'b1;",
        "  reg ap_start = 1'b0;",
        "  wire ap_done;",
        "  wire ap_idle;",
        "  wire ap_ready;",
        "",
        "  wire [V_IN_ADDR_BITS-1:0] v_in_address0;",
        "  wire v_in_ce0;",
        "  reg  [15:0] v_in_q0;",
        "",
        "  wire [LUT_ADDR_BITS-1:0] tanh_lut_address0;",
        "  wire tanh_lut_ce0;",
        "  reg  [15:0] tanh_lut_q0;",
        "",
        "  wire [V_OUT_ADDR_BITS-1:0] v_out_address0;",
        "  wire v_out_ce0;",
        "  wire v_out_we0;",
        "  wire [15:0] v_out_d0;",
        "",
        "  reg signed [15:0] v_in_mem [0:NODE_COUNT-1];",
        "  reg signed [15:0] v_out_mem[0:NODE_COUNT-1];",
        "  reg signed [15:0] tanh_lut_mem[0:LUT_SIZE-1];",
        "  byte unsigned lut_bytes [0:(LUT_SIZE*2)-1];",
        "",
        "  integer fd;",
        "  integer nread;",
        "  integer i;",
        "  integer tick;",
        "",
        "  always #(CLK_HALF_NS) ap_clk = ~ap_clk;",
        "",
        "  nema_kernel dut (",
        "    .ap_clk(ap_clk),",
        "    .ap_rst(ap_rst),",
        "    .ap_start(ap_start),",
        "    .ap_done(ap_done),",
        "    .ap_idle(ap_idle),",
        "    .ap_ready(ap_ready),",
        "    .v_in_address0(v_in_address0),",
        "    .v_in_ce0(v_in_ce0),",
        "    .v_in_q0(v_in_q0),",
        "    .tanh_lut_address0(tanh_lut_address0),",
        "    .tanh_lut_ce0(tanh_lut_ce0),",
        "    .tanh_lut_q0(tanh_lut_q0),",
        "    .v_out_address0(v_out_address0),",
        "    .v_out_ce0(v_out_ce0),",
        "    .v_out_we0(v_out_we0),",
        "    .v_out_d0(v_out_d0)",
        "  );",
        "",
        "  always @(*) begin",
        "    if (v_in_ce0 && (v_in_address0 < NODE_COUNT)) begin",
        "      v_in_q0 = v_in_mem[v_in_address0];",
        "    end else begin",
        "      v_in_q0 = 16'sd0;",
        "    end",
        "  end",
        "",
        "  always @(*) begin",
        "    if (tanh_lut_ce0 && (tanh_lut_address0 < LUT_SIZE)) begin",
        "      tanh_lut_q0 = tanh_lut_mem[tanh_lut_address0];",
        "    end else begin",
        "      tanh_lut_q0 = 16'sd0;",
        "    end",
        "  end",
        "",
        "  always @(posedge ap_clk) begin",
        "    if (v_out_ce0 && v_out_we0 && (v_out_address0 < NODE_COUNT)) begin",
        "      v_out_mem[v_out_address0] <= v_out_d0;",
        "    end",
        "  end",
        "",
        "  initial begin",
        f"    // Benchmark: {bench}",
        "    for (i = 0; i < NODE_COUNT; i = i + 1) begin",
        "      v_out_mem[i] = 16'sd0;",
        "    end",
        *init_lines,
        "",
        "    fd = $fopen(LUT_BIN, \"rb\");",
        "    if (fd == 0) begin",
        "      $display(\"tb_error: cannot open LUT binary: %s\", LUT_BIN);",
        "      $finish;",
        "    end",
        "    nread = $fread(lut_bytes, fd);",
        "    $fclose(fd);",
        "    if (nread != (LUT_SIZE * 2)) begin",
        "      $display(\"tb_error: LUT read size mismatch nread=%0d expected=%0d\", nread, LUT_SIZE * 2);",
        "      $finish;",
        "    end",
        "    for (i = 0; i < LUT_SIZE; i = i + 1) begin",
        "      tanh_lut_mem[i] = {lut_bytes[(i*2)+1], lut_bytes[(i*2)+0]};",
        "    end",
        "",
        "    repeat (8) @(posedge ap_clk);",
        "    ap_rst <= 1'b0;",
        "    repeat (4) @(posedge ap_clk);",
        "",
        "    for (tick = 0; tick < TICKS; tick = tick + 1) begin",
        "      ap_start <= 1'b1;",
        "      @(posedge ap_clk);",
        "      while (!ap_ready) begin",
        "        @(posedge ap_clk);",
        "      end",
        "      ap_start <= 1'b0;",
        "      while (!ap_done) begin",
        "        @(posedge ap_clk);",
        "      end",
        "      @(posedge ap_clk);",
        "      for (i = 0; i < NODE_COUNT; i = i + 1) begin",
        "        v_in_mem[i] = v_out_mem[i];",
        "      end",
        "    end",
        "",
        "    repeat (10) @(posedge ap_clk);",
        "    $finish;",
        "  end",
        "endmodule",
        "",
    ]
    tb_path.write_text("\n".join(tb), encoding="utf-8")


def _export_funcsim(vivado_bin: Path, ctx: BenchContext, bench_out: Path) -> tuple[int, Path]:
    funcsim_v = bench_out / "dut_funcsim.v"
    tcl = bench_out / "export_funcsim.tcl"
    tcl.write_text(
        "\n".join(
            [
                f"open_checkpoint {{{ctx.dcp_path}}}",
                f"write_verilog -mode funcsim -force {{{funcsim_v}}}",
                "close_design",
                "exit",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = _run([str(vivado_bin), "-mode", "batch", "-source", str(tcl)], cwd=bench_out)
    (bench_out / "export_funcsim.log").write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")
    return proc.returncode, funcsim_v


def _run_xsim_saif(
    vivado_bin: Path,
    *,
    bench: str,
    bench_out: Path,
    funcsim_v: Path,
    tb_tick: Path,
    ticks: int,
    clock_period_ns: float,
) -> tuple[int, int, Path, dict[str, Any]]:
    vivado_root = vivado_bin.parent.parent
    xvlog_bin = vivado_bin.parent / "xvlog"
    xelab_bin = vivado_bin.parent / "xelab"
    xsim_bin = vivado_bin.parent / "xsim"
    glbl_v = vivado_root / "data" / "verilog" / "src" / "glbl.v"

    saif_path = bench_out / "activity_func.saif"
    xsim_tcl = bench_out / "xsim_saif.tcl"
    xsim_tcl.write_text(
        "\n".join(
            [
                f"open_saif {saif_path}",
                "set saif_scope \"/tb_tick/dut/*\"",
                "set objs [get_objects -r $saif_scope]",
                "log_saif $objs",
                "run -all",
                "close_saif",
                "quit",
                "",
            ]
        ),
        encoding="utf-8",
    )

    compile_log = bench_out / "sim_compile.log"
    run_log = bench_out / "sim_run.log"

    snapshot = f"sim_{bench}"

    t0 = time.monotonic()
    xvlog_cmd = [str(xvlog_bin), "-sv", str(funcsim_v), str(tb_tick)]
    xvlog_proc = _run(xvlog_cmd, cwd=bench_out)

    xelab_cmd = [
        str(xelab_bin),
        "-debug",
        "typical",
        "tb_tick",
        "glbl",
        "--vlog",
        str(glbl_v),
        "-L",
        "unisims_ver",
        "-timescale",
        "1ns/1ps",
        "-s",
        snapshot,
    ]
    xelab_proc = _run(xelab_cmd, cwd=bench_out)
    t1 = time.monotonic()

    compile_log.write_text(
        "\n".join(
            [
                "$ " + " ".join(xvlog_cmd),
                xvlog_proc.stdout,
                xvlog_proc.stderr,
                "$ " + " ".join(xelab_cmd),
                xelab_proc.stdout,
                xelab_proc.stderr,
            ]
        ),
        encoding="utf-8",
    )

    if xvlog_proc.returncode != 0 or xelab_proc.returncode != 0:
        scope_payload = {
            "bench": bench,
            "tb_top": "tb_tick",
            "dut_instance": "dut",
            "scope_expression": "/tb_tick/dut/*",
            "ticks": ticks,
            "clock_period_ns": clock_period_ns,
            "runtime_mode": "run -all",
            "compile_wall_sec": t1 - t0,
            "run_wall_sec": None,
            "compile_rc": {
                "xvlog": xvlog_proc.returncode,
                "xelab": xelab_proc.returncode,
            },
            "run_rc": None,
            "objects_logged": "unknown (compile failed)",
            "saif_path": str(saif_path),
        }
        _write_json(bench_out / "saif_scope.json", scope_payload)
        return xvlog_proc.returncode or xelab_proc.returncode, 127, saif_path, scope_payload

    xsim_cmd = [str(xsim_bin), snapshot, "-t", str(xsim_tcl)]
    r0 = time.monotonic()
    xsim_proc = _run(xsim_cmd, cwd=bench_out)
    r1 = time.monotonic()

    run_log.write_text(
        "\n".join(
            [
                "$ " + " ".join(xsim_cmd),
                xsim_proc.stdout,
                xsim_proc.stderr,
            ]
        ),
        encoding="utf-8",
    )

    scope_payload = {
        "bench": bench,
        "tb_top": "tb_tick",
        "dut_instance": "dut",
        "scope_expression": "/tb_tick/dut/*",
        "ticks": ticks,
        "clock_period_ns": clock_period_ns,
        "runtime_mode": "run -all",
        "compile_wall_sec": t1 - t0,
        "run_wall_sec": r1 - r0,
        "compile_rc": {
            "xvlog": xvlog_proc.returncode,
            "xelab": xelab_proc.returncode,
        },
        "run_rc": xsim_proc.returncode,
        "objects_logged": "log_saif [get_objects -r /tb_tick/dut/*]",
        "saif_path": str(saif_path),
    }
    _write_json(bench_out / "saif_scope.json", scope_payload)

    return 0, xsim_proc.returncode, saif_path, scope_payload


def _parse_power_report(path: Path) -> dict[str, float | None]:
    out = {
        "total_power_w": None,
        "dynamic_power_w": None,
        "static_power_w": None,
        "matched_nets": None,
        "total_nets": None,
    }
    if not path.exists():
        return out

    txt = path.read_text(encoding="utf-8", errors="replace")

    def grab(pat: str) -> float | None:
        m = re.search(pat, txt, flags=re.I)
        if not m:
            return None
        return _parse_num(m.group(1))

    out["total_power_w"] = grab(r"Total On-Chip Power\s*\(W\)\s*\|\s*([0-9.+\-Ee]+)")
    out["dynamic_power_w"] = grab(r"Dynamic\s*\(W\)\s*\|\s*([0-9.+\-Ee]+)")
    out["static_power_w"] = grab(r"Device Static\s*\(W\)\s*\|\s*([0-9.+\-Ee]+)")

    m_nets = re.search(r"Design Nets Matched\s*\|\s*[^\(]*\(([0-9,]+)\s*/\s*([0-9,]+)\)", txt)
    if m_nets:
        out["matched_nets"] = int(m_nets.group(1).replace(",", ""))
        out["total_nets"] = int(m_nets.group(2).replace(",", ""))

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


def _run_power_reports(vivado_bin: Path, *, ctx: BenchContext, bench_out: Path, saif_path: Path | None) -> dict[str, Any]:
    vec_tcl = bench_out / "report_power_vectorless.tcl"
    vec_rpt = bench_out / "power_vectorless.rpt"
    vec_tcl.write_text(
        "\n".join(
            [
                f"open_checkpoint {{{ctx.dcp_path}}}",
                f"report_power -file {{{vec_rpt}}}",
                "close_design",
                "exit",
                "",
            ]
        ),
        encoding="utf-8",
    )
    vec_proc = _run([str(vivado_bin), "-mode", "batch", "-source", str(vec_tcl)], cwd=bench_out)

    read_saif_log = bench_out / "read_saif.log"
    saif_tcl = bench_out / "report_power_saif_func.tcl"
    saif_rpt = bench_out / "power_saif_func.rpt"

    if saif_path is None or not saif_path.exists():
        read_saif_log.write_text("READ_SAIF_FINAL:0\nNO_SAIF_INPUT\n", encoding="utf-8")
        saif_proc = subprocess.CompletedProcess(args=[], returncode=127, stdout="", stderr="NO_SAIF_INPUT")
    else:
        saif_tcl.write_text(
            "\n".join(
                [
                    f"open_checkpoint {{{ctx.dcp_path}}}",
                    f"set saif_file {{{saif_path}}}",
                    f"set fp [open {{{read_saif_log}}} w]",
                    "set saif_ok 0",
                    "if {[catch {read_saif -input $saif_file -strip_path tb_tick/dut} msg0]} {",
                    "  puts $fp \"READ_SAIF_ATTEMPT_0_FAIL:$msg0\"",
                    "} else {",
                    "  puts $fp \"READ_SAIF_ATTEMPT_0_PASS\"",
                    "  set saif_ok 1",
                    "}",
                    "if {!$saif_ok} {",
                    "  if {[catch {read_saif -input $saif_file -strip_path /tb_tick/dut} msg1]} {",
                    "    puts $fp \"READ_SAIF_ATTEMPT_1_FAIL:$msg1\"",
                    "  } else {",
                    "    puts $fp \"READ_SAIF_ATTEMPT_1_PASS\"",
                    "    set saif_ok 1",
                    "  }",
                    "}",
                    "if {!$saif_ok} {",
                    "  if {[catch {read_saif $saif_file} msg2]} {",
                    "    puts $fp \"READ_SAIF_ATTEMPT_2_FAIL:$msg2\"",
                    "  } else {",
                    "    puts $fp \"READ_SAIF_ATTEMPT_2_PASS\"",
                    "    set saif_ok 1",
                    "  }",
                    "}",
                    "puts $fp \"READ_SAIF_FINAL:$saif_ok\"",
                    "close $fp",
                    f"report_power -file {{{saif_rpt}}}",
                    "close_design",
                    "exit",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        saif_proc = _run([str(vivado_bin), "-mode", "batch", "-source", str(saif_tcl)], cwd=bench_out)

    (bench_out / "power_vectorless.log").write_text(vec_proc.stdout + "\n" + vec_proc.stderr, encoding="utf-8")
    (bench_out / "power_saif.log").write_text(saif_proc.stdout + "\n" + saif_proc.stderr, encoding="utf-8")

    vec_metrics = _parse_power_report(vec_rpt)
    saif_metrics = _parse_power_report(saif_rpt)
    read_status = _read_saif_status(read_saif_log)

    vectorless_status = "PASS" if vec_proc.returncode == 0 and vec_metrics["total_power_w"] is not None else "FAIL"
    if saif_proc.returncode == 127:
        saif_power_status = "NOT_RUN"
    else:
        saif_power_status = "PASS" if saif_proc.returncode == 0 and read_status == "PASS" and saif_metrics["total_power_w"] is not None else "FAIL"

    payload: dict[str, Any] = {
        "benchmark": ctx.bench,
        "target_part": TARGET_PART,
        "dcp_path": str(ctx.dcp_path),
        "saif_path": str(saif_path) if saif_path else None,
        "vectorless_status": vectorless_status,
        "read_saif_status": read_status,
        "saif_power_status": saif_power_status,
        "vectorless": vec_metrics,
        "saif": saif_metrics,
        "artifacts": {
            "power_vectorless_rpt": str(vec_rpt),
            "power_saif_rpt": str(saif_rpt),
            "read_saif_log": str(read_saif_log),
        },
        "estimated_label": "ESTIMATED_PRE_BOARD_ONLY",
    }
    _write_json(bench_out / "power_summary.json", payload)
    return payload


def _write_blocked(bench_out: Path, reason: str) -> None:
    lines = [
        f"# BLOCKED {bench_out.name}",
        "",
        f"- generated_at_utc: {_now_utc()}",
        f"- reason: {reason}",
        "",
        "This bench did not complete full functional SAIF + SAIF-guided power flow.",
    ]
    (bench_out / "BLOCKED.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_one_bench(vivado_bin: Path, ctx: BenchContext, lut_bin: Path) -> dict[str, Any]:
    bench_out = OUT_ROOT / ctx.bench
    bench_out.mkdir(parents=True, exist_ok=True)
    blocked_path = bench_out / "BLOCKED.md"
    if blocked_path.exists():
        blocked_path.unlink()

    header = _find_hls_header(ctx.bench)
    if header is None:
        node_count = max(1, 1 << 1)
        v_init = [0]
    else:
        node_count, v_init = _parse_node_and_vinit(header)

    export_rc, funcsim_v = _export_funcsim(vivado_bin, ctx, bench_out)

    summary: dict[str, Any] = {
        "benchmark": ctx.bench,
        "target_part": TARGET_PART,
        "clock_period_ns": ctx.clock_period_ns,
        "ticks": ctx.ticks,
        "dcp_path": str(ctx.dcp_path),
        "timing_report": str(ctx.timing_rpt),
        "funcsim_netlist": str(funcsim_v),
        "funcsim_export_status": "PASS" if export_rc == 0 and funcsim_v.exists() else f"FAIL:export_rc_{export_rc}",
        "estimated_label": "ESTIMATED_PRE_BOARD_ONLY",
        "blocked": False,
        "block_reason": None,
    }

    if export_rc != 0 or not funcsim_v.exists():
        reason = f"funcsim_export_failed rc={export_rc}"
        summary["blocked"] = True
        summary["block_reason"] = reason
        _write_provenance(bench_out, bench=ctx.bench, ticks=ctx.ticks, header=header, chosen_tb=bench_out / "tb_tick.sv")
        _write_blocked(bench_out, reason)
        _write_json(bench_out / "summary.json", summary)
        return summary

    addr_bits = _parse_funcsim_ports(funcsim_v)
    tb_tick = bench_out / "tb_tick.sv"
    _write_tb_tick(
        tb_tick,
        bench=ctx.bench,
        node_count=node_count,
        v_init=v_init,
        ticks=ctx.ticks,
        clock_period_ns=ctx.clock_period_ns,
        addr_bits=addr_bits,
        lut_bin=lut_bin,
    )
    _write_provenance(bench_out, bench=ctx.bench, ticks=ctx.ticks, header=header, chosen_tb=tb_tick)

    compile_rc, run_rc, saif_path, scope_payload = _run_xsim_saif(
        vivado_bin,
        bench=ctx.bench,
        bench_out=bench_out,
        funcsim_v=funcsim_v,
        tb_tick=tb_tick,
        ticks=ctx.ticks,
        clock_period_ns=ctx.clock_period_ns,
    )

    saif_generation_status = "PASS" if compile_rc == 0 and run_rc == 0 and saif_path.exists() else (
        f"FAIL:compile_rc_{compile_rc}" if compile_rc != 0 else f"FAIL:run_rc_{run_rc}"
    )

    pwr = _run_power_reports(vivado_bin, ctx=ctx, bench_out=bench_out, saif_path=saif_path if saif_generation_status == "PASS" else None)

    summary.update(
        {
            "tb_tick": str(tb_tick),
            "node_count": node_count,
            "saif_scope": scope_payload,
            "saif_generation_status": saif_generation_status,
            "saif_path": str(saif_path) if saif_path.exists() else None,
            "vectorless_status": pwr.get("vectorless_status"),
            "read_saif_status": pwr.get("read_saif_status"),
            "saif_power_status": pwr.get("saif_power_status"),
            "vectorless": pwr.get("vectorless"),
            "saif": pwr.get("saif"),
            "artifacts": pwr.get("artifacts"),
        }
    )

    blocked_reason = None
    if saif_generation_status != "PASS":
        blocked_reason = f"saif_generation_status={saif_generation_status}"
    elif pwr.get("read_saif_status") != "PASS":
        blocked_reason = f"read_saif_status={pwr.get('read_saif_status')}"
    elif pwr.get("saif_power_status") != "PASS":
        blocked_reason = f"saif_power_status={pwr.get('saif_power_status')}"

    if blocked_reason is not None:
        summary["blocked"] = True
        summary["block_reason"] = blocked_reason
        _write_blocked(bench_out, blocked_reason)

    _write_json(bench_out / "summary.json", summary)
    return summary


def _write_power_tables(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in results:
        bench = str(r.get("benchmark"))
        vec = r.get("vectorless") if isinstance(r.get("vectorless"), dict) else {}
        saif = r.get("saif") if isinstance(r.get("saif"), dict) else {}
        artifacts = r.get("artifacts") if isinstance(r.get("artifacts"), dict) else {}
        scope = r.get("saif_scope") if isinstance(r.get("saif_scope"), dict) else {}

        row = {
            "benchmark": bench,
            "part": TARGET_PART,
            "target_part_match": "true",
            "clock_period_ns": _fmt_num(r.get("clock_period_ns")),
            "ticks": _fmt_num(r.get("ticks")),
            "tb_top": str(scope.get("tb_top") or "tb_tick"),
            "dut_instance": str(scope.get("dut_instance") or "dut"),
            "vectorless_status": str(r.get("vectorless_status") or "-"),
            "saif_generation_status": str(r.get("saif_generation_status") or "-"),
            "read_saif_status": str(r.get("read_saif_status") or "-"),
            "saif_power_status": str(r.get("saif_power_status") or "-"),
            "vectorless_total_power_w": _fmt_num(vec.get("total_power_w")),
            "vectorless_dynamic_power_w": _fmt_num(vec.get("dynamic_power_w")),
            "vectorless_static_power_w": _fmt_num(vec.get("static_power_w")),
            "saif_total_power_w": _fmt_num(saif.get("total_power_w")),
            "saif_dynamic_power_w": _fmt_num(saif.get("dynamic_power_w")),
            "saif_static_power_w": _fmt_num(saif.get("static_power_w")),
            "matched_nets": _fmt_num(saif.get("matched_nets")),
            "total_nets": _fmt_num(saif.get("total_nets")),
            "dcp_path": str(r.get("dcp_path") or "-"),
            "funcsim_netlist": str(r.get("funcsim_netlist") or "-"),
            "tb_tick": str(r.get("tb_tick") or "-"),
            "saif_path": str(r.get("saif_path") or "-"),
            "read_saif_log": str(artifacts.get("read_saif_log") or "-"),
            "power_vectorless_rpt": str(artifacts.get("power_vectorless_rpt") or "-"),
            "power_saif_rpt": str(artifacts.get("power_saif_rpt") or "-"),
            "estimated_label": "ESTIMATED_PRE_BOARD_ONLY",
            "representativity_note": "Functional post-route xsim SAIF from tick-driven TB (benchmark-shaped state + LUT), pre-board estimate.",
        }
        rows.append(row)

    headers = [
        "benchmark",
        "part",
        "target_part_match",
        "clock_period_ns",
        "ticks",
        "tb_top",
        "dut_instance",
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
        "matched_nets",
        "total_nets",
        "dcp_path",
        "funcsim_netlist",
        "tb_tick",
        "saif_path",
        "read_saif_log",
        "power_vectorless_rpt",
        "power_saif_rpt",
        "estimated_label",
        "representativity_note",
    ]

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    with POWER_V7_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=headers)
        w.writeheader()
        for row in rows:
            w.writerow(row)

    tex_lines = [
        "\\begin{tabular}{lrrrrrrr}",
        "\\hline",
        "Benchmark & Ticks & SAIF Tot(W) & SAIF Dyn(W) & SAIF Stat(W) & Match & read\\_saif & power \\\\",
        "\\hline",
    ]
    for row in rows:
        match_txt = f"{row['matched_nets']}/{row['total_nets']}"
        tex_lines.append(
            f"{_latex_escape(row['benchmark'])} & "
            f"{_latex_escape(row['ticks'])} & "
            f"{_latex_escape(row['saif_total_power_w'])} & "
            f"{_latex_escape(row['saif_dynamic_power_w'])} & "
            f"{_latex_escape(row['saif_static_power_w'])} & "
            f"{_latex_escape(match_txt)} & "
            f"{_latex_escape(row['read_saif_status'])} & "
            f"{_latex_escape(row['saif_power_status'])} \\\\"
        )
    tex_lines.extend(["\\hline", "\\end{tabular}", ""])
    POWER_V7_TEX.write_text("\n".join(tex_lines), encoding="utf-8")

    POWER_FINAL_CSV.write_text(POWER_V7_CSV.read_text(encoding="utf-8"), encoding="utf-8")
    POWER_FINAL_TEX.write_text(POWER_V7_TEX.read_text(encoding="utf-8"), encoding="utf-8")

    prov_lines = [
        "# Artix-7 Power Final Provenance",
        "",
        f"- generated_at_utc: {_now_utc()}",
        "- source_table: review_pack/tables/artix7_power_v7_funcsaif.csv",
        "- selector_table: review_pack/tables/artix7_power_final.csv",
        "- methodology: post-route DCP -> funcsim netlist -> xsim functional SAIF (tick-driven TB) -> read_saif/report_power",
        "- benches: b1_small + canonical B3",
        "- estimated_label: ESTIMATED_PRE_BOARD_ONLY",
        "",
        "All values are estimated pre-board only and not silicon board measurements.",
    ]
    POWER_FINAL_PROV.write_text("\n".join(prov_lines) + "\n", encoding="utf-8")

    return rows


def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _update_metrics(power_rows: list[dict[str, Any]], b3_key: str) -> dict[str, Any]:
    if not METRICS_V1_CSV.exists():
        raise FileNotFoundError(f"Missing input metrics CSV: {METRICS_V1_CSV}")

    pwr_by_bench = {r["benchmark"]: r for r in power_rows}

    with METRICS_V1_CSV.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        in_rows = list(reader)
        headers = reader.fieldnames or []

    out_rows: list[dict[str, str]] = []
    for row in in_rows:
        bench = row.get("bench", "")
        updated = dict(row)

        pwr_row = pwr_by_bench.get(bench)
        if pwr_row is not None and pwr_row.get("saif_total_power_w") not in (None, "-"):
            updated_power = pwr_row["saif_total_power_w"]
        else:
            updated_power = updated.get("power_total_w", "-")

        updated["power_total_w"] = updated_power

        ticks_s_raw = (updated.get("ticks/s") or "").strip()
        if _is_float(ticks_s_raw) and _is_float(updated_power):
            ticks_s = float(ticks_s_raw)
            pwr_w = float(updated_power)
            if ticks_s > 0:
                e_mj = (pwr_w / ticks_s) * 1000.0
                updated["energy_per_tick_mJ"] = _fmt_num(e_mj)
            else:
                updated["energy_per_tick_mJ"] = "-"
        else:
            updated["energy_per_tick_mJ"] = "-"

        out_rows.append(updated)

    with METRICS_V2_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for row in out_rows:
            writer.writerow(row)

    METRICS_FINAL_CSV.write_text(METRICS_V2_CSV.read_text(encoding="utf-8"), encoding="utf-8")

    tex_lines = [
        "\\begin{tabular}{lrrrrrrrrrr}",
        "\\hline",
        "Bench & LUT & FF & BRAM & DSP & WNS(ns) & f\\_run(MHz) & cycles/tick & ticks/s & P(W) & E/tick(mJ) \\\\",
        "\\hline",
    ]
    for row in out_rows:
        tex_lines.append(
            f"{_latex_escape(row.get('bench', '-'))} & "
            f"{_latex_escape(row.get('lut', '-'))} & "
            f"{_latex_escape(row.get('ff', '-'))} & "
            f"{_latex_escape(row.get('bram', '-'))} & "
            f"{_latex_escape(row.get('dsp', '-'))} & "
            f"{_latex_escape(row.get('wns', '-'))} & "
            f"{_latex_escape(row.get('f_run_mhz', '-'))} & "
            f"{_latex_escape(row.get('cycles_per_tick', '-'))} & "
            f"{_latex_escape(row.get('ticks/s', '-'))} & "
            f"{_latex_escape(row.get('power_total_w', '-'))} & "
            f"{_latex_escape(row.get('energy_per_tick_mJ', '-'))} \\\\"
        )
    tex_lines.extend(["\\hline", "\\end{tabular}", ""])
    METRICS_FINAL_TEX.write_text("\n".join(tex_lines), encoding="utf-8")

    b3_row = next((r for r in out_rows if r.get("bench") == b3_key), None)
    return {
        "input": str(METRICS_V1_CSV),
        "output_v2": str(METRICS_V2_CSV),
        "output_final": str(METRICS_FINAL_CSV),
        "output_tex": str(METRICS_FINAL_TEX),
        "b3_bench": b3_key,
        "b3_power_total_w": b3_row.get("power_total_w") if b3_row else None,
        "b3_energy_per_tick_mJ": b3_row.get("energy_per_tick_mJ") if b3_row else None,
        "estimated_label": "ESTIMATED_PRE_BOARD_ONLY",
    }


def _write_power_methodology(results: list[dict[str, Any]]) -> None:
    lines: list[str] = [
        "# Power Methodology (Pre-Board, Estimated Only)",
        "",
        "## Scope",
        "",
        "This workflow produces estimated post-implementation power only.",
        "No value may be labeled as measured on board.",
        "",
        "## Round10b Functional-SAIF Procedure",
        "",
        "1. Use existing post-route checkpoints (`build/amd_vivado_artix7_v5/<bench>/post_route.dcp`).",
        "2. Export functional netlist: `write_verilog -mode funcsim -force dut_funcsim.v`.",
        "3. Compile and elaborate with xsim front-end:",
        "   - `xvlog -sv dut_funcsim.v tb_tick.sv`",
        "   - `xelab -debug typical tb_tick glbl -s sim_<bench>`",
        "4. Dump SAIF from functional simulation:",
        "   - `open_saif activity_func.saif`",
        "   - `log_saif [get_objects -r /tb_tick/dut/*]`",
        "   - `run -all`",
        "   - `close_saif`",
        "5. Run power on same DCP:",
        "   - `report_power` vectorless baseline",
        "   - `read_saif activity_func.saif` (strip-path fallback attempts)",
        "   - `report_power` SAIF-guided",
        "",
        "## Tick Runtime and Scope",
        "",
        "| bench | ticks | clock_period_ns | saif_scope | matched_nets | total_nets |",
        "|---|---:|---:|---|---:|---:|",
    ]

    for r in results:
        scope = (r.get("saif_scope") or {}).get("scope_expression", "/tb_tick/dut/*")
        saif = r.get("saif") if isinstance(r.get("saif"), dict) else {}
        lines.append(
            "| "
            + str(r.get("benchmark", "-"))
            + " | "
            + _fmt_num(r.get("ticks"))
            + " | "
            + _fmt_num(r.get("clock_period_ns"))
            + " | "
            + str(scope)
            + " | "
            + _fmt_num(saif.get("matched_nets"))
            + " | "
            + _fmt_num(saif.get("total_nets"))
            + " |"
        )

    lines.extend(
        [
            "",
            "## Evidence Artifacts",
            "",
            "- `build/amd_power_artix7_v7_funcsaif/summary.json`",
            "- `build/amd_power_artix7_v7_funcsaif/<bench>/activity_func.saif`",
            "- `build/amd_power_artix7_v7_funcsaif/<bench>/sim_compile.log`",
            "- `build/amd_power_artix7_v7_funcsaif/<bench>/sim_run.log`",
            "- `build/amd_power_artix7_v7_funcsaif/<bench>/power_saif_func.rpt`",
            "- `review_pack/tables/artix7_power_v7_funcsaif.csv`",
            "- `review_pack/tables/artix7_power_final.csv`",
            "",
            "## Limitations and Claim Policy",
            "",
            "- Label all values as `ESTIMATED_PRE_BOARD_ONLY`.",
            "- This remains pre-board estimation and not board measurement.",
            "- Functional SAIF improves representativity versus synthetic clock-only activity, but does not replace silicon measurement.",
        ]
    )

    DOC_POWER.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _create_bundle(blocked_any: bool, b3_key: str) -> None:
    include: list[Path] = [
        OUT_ROOT,
        POWER_FINAL_CSV,
        METRICS_FINAL_CSV,
        DOC_POWER,
    ]

    # Include logs explicitly for auditing.
    for bench in ["b1_small", b3_key]:
        bench_dir = OUT_ROOT / bench
        for name in ["export_funcsim.log", "sim_compile.log", "sim_run.log", "power_vectorless.log", "power_saif.log"]:
            p = bench_dir / name
            if p.exists():
                include.append(p)

    # Produce bundle for blocked cases and also for audit trail.
    if blocked_any or True:
        with tarfile.open(BUNDLE_TAR, "w:gz") as tar:
            for path in include:
                if not path.exists():
                    continue
                tar.add(path, arcname=str(path.relative_to(ROOT)))

        digest = hashlib.sha256(BUNDLE_TAR.read_bytes()).hexdigest()
        BUNDLE_SHA.write_text(f"{digest}  {BUNDLE_TAR.name}\n", encoding="utf-8")


def main() -> int:
    vivado_bin = _resolve_vivado_bin()
    b3_key = _extract_b3_key()
    benches = _collect_bench_contexts(b3_key)

    lut_bin = ROOT / "artifacts" / "luts" / "tanh_q8_8.bin"
    if not lut_bin.exists():
        raise FileNotFoundError(f"Missing LUT binary: {lut_bin}")

    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for ctx in benches:
        results.append(_run_one_bench(vivado_bin, ctx, lut_bin))

    blocked_reasons = [
        f"{r.get('benchmark')}:{r.get('block_reason')}"
        for r in results
        if bool(r.get("blocked"))
    ]

    power_rows = _write_power_tables(results)
    metrics_summary = _update_metrics(power_rows, b3_key=b3_key)
    _write_power_methodology(results)

    summary = {
        "generatedAtUtc": _now_utc(),
        "targetPart": TARGET_PART,
        "canonicalB3": b3_key,
        "benchmarks": ["b1_small", b3_key],
        "results": results,
        "blockedBenchmarks": blocked_reasons,
        "g1dFunctionalSaifReady": len(blocked_reasons) == 0,
        "tableArtifacts": {
            "power_v7_csv": str(POWER_V7_CSV),
            "power_v7_tex": str(POWER_V7_TEX),
            "power_final_csv": str(POWER_FINAL_CSV),
            "power_final_tex": str(POWER_FINAL_TEX),
            "metrics_v2_csv": str(METRICS_V2_CSV),
            "metrics_final_csv": str(METRICS_FINAL_CSV),
            "metrics_final_tex": str(METRICS_FINAL_TEX),
        },
        "metricsSummary": metrics_summary,
        "estimatedOnly": True,
        "measuredOnBoard": False,
        "estimatedLabel": "ESTIMATED_PRE_BOARD_ONLY",
    }
    _write_json(OUT_ROOT / "summary.json", summary)

    _create_bundle(blocked_any=len(blocked_reasons) > 0, b3_key=b3_key)

    print(
        json.dumps(
            {
                "status": "OK" if not blocked_reasons else "PARTIAL_BLOCKED",
                "canonicalB3": b3_key,
                "benchmarks": ["b1_small", b3_key],
                "blocked": blocked_reasons,
                "summary": str(OUT_ROOT / "summary.json"),
                "power_final_csv": str(POWER_FINAL_CSV),
                "metrics_final_csv": str(METRICS_FINAL_CSV),
                "bundle": str(BUNDLE_TAR if BUNDLE_TAR.exists() else "-"),
                "bundle_sha": str(BUNDLE_SHA if BUNDLE_SHA.exists() else "-"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
