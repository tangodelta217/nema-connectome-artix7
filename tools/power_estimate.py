#!/usr/bin/env python3
"""Boardless post-route power estimation helper.

Generates ESTIMATED_* artifacts only (never MEASURED_ON_BOARD).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CmdResult:
    exitcode: int
    stdout_path: Path
    stderr_path: Path
    command: str


def _run_shell(command: str, out_stdout: Path, out_stderr: Path) -> CmdResult:
    out_stdout.parent.mkdir(parents=True, exist_ok=True)
    out_stderr.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        text=True,
        check=False,
    )
    out_stdout.write_text(proc.stdout or "", encoding="utf-8")
    out_stderr.write_text(proc.stderr or "", encoding="utf-8")
    return CmdResult(proc.returncode, out_stdout, out_stderr, command)


def _parse_power_report(report_path: Path) -> dict[str, Any]:
    if not report_path.exists():
        return {}
    text = report_path.read_text(encoding="utf-8", errors="replace")

    def grab(pattern: str) -> float | None:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    return {
        "totalOnChipPowerW": grab(r"Total On-Chip Power\s*\(W\)\s*\|\s*([0-9.+-Ee]+)"),
        "dynamicPowerW": grab(r"Dynamic\s*\(W\)\s*\|\s*([0-9.+-Ee]+)"),
        "deviceStaticPowerW": grab(r"Device Static\s*\(W\)\s*\|\s*([0-9.+-Ee]+)"),
    }


def _score_amp_plus(outdir: Path) -> tuple[bool | None, Path | None]:
    score_tool = Path("tools/score_milestones.py")
    milestones = Path("milestones_amp_plus_v2.json")
    if not score_tool.exists() or not milestones.exists():
        return None, None

    out_json = outdir / "amp_plus_v2_score_after_power_estimate.json"
    cmd = (
        f"python tools/score_milestones.py --milestones milestones_amp_plus_v2.json "
        f"--out-json {out_json}"
    )
    res = _run_shell(
        cmd,
        outdir / "logs" / "score_milestones.stdout.txt",
        outdir / "logs" / "score_milestones.stderr.txt",
    )
    (outdir / "logs" / "score_milestones.exitcode.txt").write_text(str(res.exitcode), encoding="utf-8")
    if res.exitcode != 0 or not out_json.exists():
        return None, out_json

    data = json.loads(out_json.read_text(encoding="utf-8"))
    amp001_pass: bool | None = None
    for item in data.get("items", []):
        if isinstance(item, dict) and item.get("id") == "AMPPLUS-001":
            amp001_pass = bool(item.get("pass"))
            break
    return amp001_pass, out_json


def generate(outdir: Path, dcp_path: Path) -> None:
    logs = outdir / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    vcd_path = outdir / "activity_b1.vcd"
    power_report_path = outdir / "power_report.rpt"
    tcl_path = outdir / "logs" / "power_estimate_vivado.tcl"
    xsim_tcl_path = outdir / "logs" / "xsim_dump_vcd.tcl"

    # Step 1: try generating VCD from existing post-route snapshot.
    xsim_tcl_path.write_text(
        "\n".join(
            [
                f"open_vcd {vcd_path}",
                "log_vcd [get_objects -r /tb_post_route_min/*]",
                "run 200 ns",
                "close_vcd",
                "quit",
                "",
            ]
        ),
        encoding="utf-8",
    )
    xelab_cmd = (
        "source tools/hw/activate_xilinx.sh >/dev/null 2>&1 || true; "
        "VIVADO_BIN=$(dirname \"$(command -v vivado)\"); "
        "VIVADO_ROOT=$(cd \"$VIVADO_BIN/..\" && pwd); "
        "GLBL=\"$VIVADO_ROOT/data/verilog/src/glbl.v\"; "
        "xelab -prj build/post_route_sim_b1/artifacts/postroute_abs.prj --vlog \"$GLBL\" "
        "glbl tb_post_route_min -L unisims_ver -L simprims_ver -timescale 1ns/1ps "
        "--debug typical -s tb_power_snapshot"
    )
    xelab = _run_shell(xelab_cmd, logs / "xelab.stdout.txt", logs / "xelab.stderr.txt")
    (logs / "xelab.exitcode.txt").write_text(str(xelab.exitcode), encoding="utf-8")

    if xelab.exitcode == 0:
        xsim_cmd = (
            "source tools/hw/activate_xilinx.sh >/dev/null 2>&1 || true; "
            f"xsim tb_power_snapshot -tclbatch {xsim_tcl_path}"
        )
        xsim = _run_shell(xsim_cmd, logs / "xsim.stdout.txt", logs / "xsim.stderr.txt")
        xsim_ec = xsim.exitcode
    else:
        (logs / "xsim.stdout.txt").write_text("", encoding="utf-8")
        (logs / "xsim.stderr.txt").write_text("xsim skipped: xelab failed\n", encoding="utf-8")
        xsim_ec = 127
    (logs / "xsim.exitcode.txt").write_text(str(xsim_ec), encoding="utf-8")

    # Step 2: Vivado report_power with VCD fallback to vectorless.
    tcl_path.write_text(
        "\n".join(
            [
                f"open_checkpoint {{{dcp_path}}}",
                "set nema_method {vectorless}",
                "set nema_toggle_source {VECTORLESS}",
                f"set nema_vcd {{{vcd_path}}}",
                "if {[file exists $nema_vcd]} {",
                "  set vcd_loaded 0",
                "  set strip_candidates [list \"/tb_post_route_min/dut\" \"tb_post_route_min/dut\" \"/tb_post_route_min\" \"tb_post_route_min\"]",
                "  foreach strip $strip_candidates {",
                "    if {[catch {read_vcd -strip_path $strip $nema_vcd} msg]} {",
                "      puts \"NEMA_POWER_INFO: read_vcd_failed strip=$strip msg=$msg\"",
                "    } else {",
                "      set vcd_loaded 1",
                "      puts \"NEMA_POWER_INFO: read_vcd_ok strip=$strip\"",
                "      break",
                "    }",
                "  }",
                "  if {!$vcd_loaded} {",
                "    if {[catch {read_vcd $nema_vcd} msg2]} {",
                "      puts \"NEMA_POWER_INFO: read_vcd_failed_nostrip msg=$msg2\"",
                "    } else {",
                "      set vcd_loaded 1",
                "      puts \"NEMA_POWER_INFO: read_vcd_ok_nostrip\"",
                "    }",
                "  }",
                "  if {$vcd_loaded} {",
                "    set nema_method {vcd}",
                "    set nema_toggle_source {VCD}",
                "  }",
                "}",
                f"report_power -file {{{power_report_path}}}",
                f"set fp [open {{{outdir / 'logs' / 'power_method.txt'}}} w]",
                "puts $fp \"$nema_method,$nema_toggle_source\"",
                "close $fp",
                "exit",
                "",
            ]
        ),
        encoding="utf-8",
    )

    vivado_cmd = (
        "source tools/hw/activate_xilinx.sh >/dev/null 2>&1 || true; "
        f"vivado -mode batch -source {tcl_path}"
    )
    viv = _run_shell(vivado_cmd, logs / "vivado_power.stdout.txt", logs / "vivado_power.stderr.txt")
    (logs / "vivado_power.exitcode.txt").write_text(str(viv.exitcode), encoding="utf-8")

    method = "vectorless"
    toggling_source = "VECTORLESS"
    method_file = logs / "power_method.txt"
    if method_file.exists():
        parts = method_file.read_text(encoding="utf-8", errors="replace").strip().split(",")
        if len(parts) == 2:
            method, toggling_source = parts[0], parts[1]

    label = "ESTIMATED_POST_ROUTE_VCD" if method == "vcd" else "ESTIMATED_POST_ROUTE_VECTORLESS"
    metrics = _parse_power_report(power_report_path)

    amp001_pass, amp_score_path = _score_amp_plus(outdir)

    payload = {
        "generatedAtUtc": now,
        "label": label,
        "method": method,  # vectorless|vcd|saif
        "toggling_source": toggling_source,
        "measuredOnBoard": False,
        "source": {
            "dcp": str(dcp_path),
            "vcd": str(vcd_path) if vcd_path.exists() else None,
            "reportPowerRpt": str(power_report_path) if power_report_path.exists() else None,
        },
        "steps": {
            "xelabExitcode": xelab.exitcode,
            "xsimExitcode": xsim_ec,
            "vivadoPowerExitcode": viv.exitcode,
        },
        "metrics": metrics,
        "ampPlus": {
            "scorePath": str(amp_score_path) if amp_score_path else None,
            "ampplus001Pass": amp001_pass,
            "requiresMeasuredOnBoard": True,
        },
        "notes": [
            "Boardless estimate only. Never MEASURED_ON_BOARD.",
            "AMPPLUS-001 must remain FAIL without build_hw/fpga_measure/power_latency_report.json method=MEASURED_ON_BOARD.",
        ],
    }

    (outdir / "power_estimate.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md_lines = [
        "# Power Estimate (Boardless)",
        "",
        f"- Generated: {now}",
        f"- Label: `{label}`",
        f"- Method: `{method}`",
        f"- toggling_source: `{toggling_source}`",
        "- measuredOnBoard: `False`",
        "",
        "## Inputs",
        f"- DCP: `{dcp_path}`",
        f"- VCD: `{vcd_path}` ({'present' if vcd_path.exists() else 'missing'})",
        f"- report_power output: `{power_report_path}` ({'present' if power_report_path.exists() else 'missing'})",
        "",
        "## Command Status",
        f"- xelab: `{xelab.exitcode}` (`{logs / 'xelab.stdout.txt'}`)",
        f"- xsim: `{xsim_ec}` (`{logs / 'xsim.stdout.txt'}`)",
        f"- vivado report_power: `{viv.exitcode}` (`{logs / 'vivado_power.stdout.txt'}`)",
        "",
        "## Estimated Power Metrics",
        f"- totalOnChipPowerW: `{metrics.get('totalOnChipPowerW')}`",
        f"- dynamicPowerW: `{metrics.get('dynamicPowerW')}`",
        f"- deviceStaticPowerW: `{metrics.get('deviceStaticPowerW')}`",
        "",
        "## AMP+ v2 Safety Check",
        f"- score file: `{amp_score_path}`" if amp_score_path else "- score file: `not generated`",
        f"- AMPPLUS-001 pass: `{amp001_pass}`",
        "- Expected without board: `False` (must require `MEASURED_ON_BOARD`).",
        "",
        "## Guarantee",
        "- This artifact is estimation-only (`ESTIMATED_*`) and does not claim on-board measurement.",
    ]
    (outdir / "power_estimate.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate boardless post-route power estimate")
    parser.add_argument("--outdir", default="build/power_estimate", help="Output directory")
    parser.add_argument(
        "--dcp",
        default="build/post_route_sim_b1/artifacts/nema_kernel_postroute.dcp",
        help="Post-route checkpoint path",
    )
    args = parser.parse_args()

    outdir = Path(args.outdir).resolve()
    dcp_path = Path(args.dcp).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    if not dcp_path.exists():
        raise SystemExit(f"missing dcp: {dcp_path}")

    generate(outdir=outdir, dcp_path=dcp_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
