#!/usr/bin/env python3
"""Run deterministic Vivado implementation + power estimation (boardless)."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from pathlib import Path


def _run(cmd: list[str], *, cwd: Path, activate: bool) -> subprocess.CompletedProcess[str]:
    if activate and Path("tools/hw/activate_xilinx.sh").exists():
        cmd_text = " ".join(shlex.quote(part) for part in cmd)
        wrapped = f"source tools/hw/activate_xilinx.sh >/dev/null 2>&1; {cmd_text}"
        return subprocess.run(
            ["bash", "-lc", wrapped],
            cwd=cwd,
            text=True,
            capture_output=True,
        )
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def _find_solution_dir(root: Path) -> Path:
    candidates = [
        root / "hls_run" / "hls_proj" / "nema_hls_prj" / "sol1",
        root / "hls_proj" / "nema_hls_prj" / "sol1",
        root / "nema_hls_prj" / "sol1",
        root / "nema_hwtest" / "sol1",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    dynamic = sorted(root.glob("**/sol1"))
    for candidate in dynamic:
        if (candidate / "syn").exists() or (candidate / "impl").exists():
            return candidate.resolve()
    raise FileNotFoundError(f"cannot find HLS solution dir under {root}")


def _choose_rtl_glob(sol: Path) -> str:
    syn_verilog = sol / "syn" / "verilog" / "*.v"
    impl_verilog = sol / "impl" / "verilog" / "*.v"
    sim_verilog = sol / "sim" / "verilog" / "*.v"
    for pattern in (syn_verilog, impl_verilog, sim_verilog):
        if list(pattern.parent.glob(pattern.name)):
            return str(pattern)
    return str(syn_verilog)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Vivado implementation for pre-board Artix-7 flow")
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--hls-root", type=Path, required=True, help="root directory with HLS outputs")
    parser.add_argument("--top", default="nema_kernel")
    parser.add_argument("--tb", default="")
    parser.add_argument("--clock-ns", type=float, default=5.0)
    parser.add_argument("--part", default="xc7a200t-1sbg484c")
    parser.add_argument("--outdir", type=Path, default=Path("build/artix7_impl"))
    parser.add_argument("--activate-xilinx", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    os.chdir(repo_root)

    hls_root = (repo_root / args.hls_root).resolve()
    if not hls_root.exists():
        raise FileNotFoundError(f"hls root not found: {hls_root}")

    solution_dir = _find_solution_dir(hls_root)
    rtl_glob = _choose_rtl_glob(solution_dir)
    xci_glob = str(solution_dir / "impl" / "ip" / "hdl" / "ip" / "**" / "*.xci")
    xdc_glob = str(solution_dir / "impl" / "ip" / "constraints" / "*.xdc")

    outdir = (repo_root / args.outdir / args.benchmark).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    logs_dir = outdir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    tcl_script = (repo_root / "scripts/amd/vivado_artix7_impl_power.tcl").resolve()
    cmd = [
        "vivado",
        "-mode",
        "batch",
        "-source",
        str(tcl_script),
        "-tclargs",
        "--benchmark",
        args.benchmark,
        "--top",
        args.top,
        "--tb",
        args.tb,
        "--clock-ns",
        f"{args.clock_ns:.6f}",
        "--part",
        args.part,
        "--outdir",
        str(outdir),
        "--rtl-glob",
        rtl_glob,
        "--xci-glob",
        xci_glob,
        "--xdc-glob",
        xdc_glob,
    ]

    rc = None
    stdout = ""
    stderr = ""
    if not args.dry_run:
        proc = _run(cmd, cwd=repo_root, activate=args.activate_xilinx)
        rc = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
        (logs_dir / "vivado.stdout.log").write_text(stdout, encoding="utf-8")
        (logs_dir / "vivado.stderr.log").write_text(stderr, encoding="utf-8")
        (outdir / "vivado.log").write_text(
            stdout + ("\n" if stdout and not stdout.endswith("\n") else "") + stderr,
            encoding="utf-8",
        )

    summary = {
        "ok": bool(args.dry_run or (rc == 0)),
        "dryRun": args.dry_run,
        "benchmark": args.benchmark,
        "hlsRoot": str(hls_root),
        "solutionDir": str(solution_dir),
        "rtlGlob": rtl_glob,
        "xciGlob": xci_glob,
        "xdcGlob": xdc_glob,
        "part": args.part,
        "clockNs": args.clock_ns,
        "command": cmd,
        "exitCode": rc,
        "outdir": str(outdir),
        "requiredArtifacts": {
            "postSynthDcp": str(outdir / "post_synth.dcp"),
            "postRouteDcp": str(outdir / "post_route.dcp"),
            "postSynthUtilization": str(outdir / "post_synth_utilization.rpt"),
            "postRouteUtilization": str(outdir / "post_route_utilization.rpt"),
            "postSynthTiming": str(outdir / "post_synth_timing.rpt"),
            "postRouteTiming": str(outdir / "post_route_timing.rpt"),
            "operatingConditions": str(outdir / "operating_conditions.rpt"),
            "vivadoLog": str(outdir / "vivado.log"),
        },
    }
    (outdir / "run_artix7_impl.summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (outdir / "run_artix7_impl.command.txt").write_text(" ".join(cmd) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else (rc or 1)


if __name__ == "__main__":
    raise SystemExit(main())
