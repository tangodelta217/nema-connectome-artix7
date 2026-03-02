#!/usr/bin/env python3
"""Round8 flow: forced Artix-7 HLS(B3) + Vivado impl/power + handoff bundle."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

TARGET_PART = "xc7a200tsbg484-1"
CLOCK_NS = 5.0
SAIF_WINDOW_NS = 200.0
PREFERRED_XILINX_BASE = Path("/media/tangodelta/Vivado/2025.2")
PREFERRED_VIVADO_BIN = PREFERRED_XILINX_BASE / "Vivado" / "bin" / "vivado"

ENV_JSON = ROOT / "build" / "round8_env.json"
HLS_OUT_ROOT = ROOT / "build" / "amd_hls_artix7_v3"
VIVADO_OUT = ROOT / "build" / "amd_vivado_artix7_v5"
POWER_OUT = ROOT / "build" / "amd_power_artix7_v5"

TABLE_DIR = ROOT / "review_pack" / "tables"
QOR_CSV = TABLE_DIR / "artix7_qor_v5.csv"
POWER_CSV = TABLE_DIR / "artix7_power_v5.csv"

DOC_GATE = ROOT / "docs" / "GATE_STATUS.md"
DOC_POWER = ROOT / "docs" / "POWER_METHODOLOGY.md"

B3_STATUS = ROOT / "build" / "handoff" / "B3_CANONICAL_STATUS.json"
CHATGPT_BRIEF = ROOT / "build" / "handoff" / "CHATGPT_BRIEF_round8.md"

BUNDLE_TAR = ROOT / "handoff_round8_for_chatgpt.tar.gz"
BUNDLE_SHA = ROOT / "handoff_round8_for_chatgpt.sha256"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run(cmd: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=env)


def _resolve_bin(name: str) -> Path | None:
    found = shutil.which(name)
    if not found:
        return None
    return Path(found).resolve()


def _resolve_vivado_bin() -> Path | None:
    if PREFERRED_VIVADO_BIN.exists() and os.access(PREFERRED_VIVADO_BIN, os.X_OK):
        return PREFERRED_VIVADO_BIN.resolve()
    return _resolve_bin("vivado")


def _collect_env(vivado_bin: Path | None, vitis_hls_bin: Path | None) -> dict[str, Any]:
    which_vivado = _run(["bash", "-lc", "which vivado || true"])
    which_vitis_hls = _run(["bash", "-lc", "which vitis_hls || true"])
    uname = _run(["uname", "-a"])

    vivado_ver_stdout = ""
    vivado_ver_stderr = ""
    vivado_ver_rc: int | None = None
    if vivado_bin is not None:
        p = _run([str(vivado_bin), "-version"])
        vivado_ver_stdout = p.stdout
        vivado_ver_stderr = p.stderr
        vivado_ver_rc = p.returncode

    vitis_ver_stdout = ""
    vitis_ver_stderr = ""
    vitis_ver_rc: int | None = None
    if vitis_hls_bin is not None:
        p = _run([str(vitis_hls_bin), "-version"])
        vitis_ver_stdout = p.stdout
        vitis_ver_stderr = p.stderr
        vitis_ver_rc = p.returncode

    payload = {
        "generatedAtUtc": _now_utc(),
        "PATH": os.environ.get("PATH", ""),
        "XILINX_BASE": os.environ.get("XILINX_BASE"),
        "which_vivado": which_vivado.stdout.strip(),
        "which_vivado_stderr": which_vivado.stderr,
        "which_vitis_hls": which_vitis_hls.stdout.strip(),
        "which_vitis_hls_stderr": which_vitis_hls.stderr,
        "vivado_bin": str(vivado_bin) if vivado_bin is not None else None,
        "vivado_version_stdout": vivado_ver_stdout,
        "vivado_version_stderr": vivado_ver_stderr,
        "vivado_version_exit_code": vivado_ver_rc,
        "vitis_hls_bin": str(vitis_hls_bin) if vitis_hls_bin is not None else None,
        "vitis_hls_version_stdout": vitis_ver_stdout,
        "vitis_hls_version_stderr": vitis_ver_stderr,
        "vitis_hls_version_exit_code": vitis_ver_rc,
        "vitis_hls_version_applicable": vitis_hls_bin is not None,
        "uname_a": uname.stdout.strip(),
        "uname_a_stderr": uname.stderr,
        "uname_exit_code": uname.returncode,
    }
    _write_json(ENV_JSON, payload)
    return payload


def _write_part_probe_tcl(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"set requested [lsort [get_parts {TARGET_PART}]]",
                "set family [lsort [get_parts xc7a200t*]]",
                'puts "NEMA_REQ_COUNT [llength $requested]"',
                'puts "NEMA_REQ_LIST [join $requested ,]"',
                'puts "NEMA_FAM_COUNT [llength $family]"',
                'puts "NEMA_FAM_LIST [join $family ,]"',
                "exit",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _parse_probe_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def _run_part_probe(vivado_bin: Path) -> dict[str, Any]:
    VIVADO_OUT.mkdir(parents=True, exist_ok=True)
    tcl = VIVADO_OUT / "part_probe_inline.tcl"
    _write_part_probe_tcl(tcl)

    cmd = [str(vivado_bin), "-mode", "batch", "-nolog", "-nojournal", "-source", str(tcl)]
    proc = _run(cmd)

    log_path = VIVADO_OUT / "host_part_probe.log"
    log_path.write_text(
        proc.stdout + ("\n" if proc.stdout and not proc.stdout.endswith("\n") else "") + proc.stderr,
        encoding="utf-8",
    )

    req_count = None
    req_list: list[str] = []
    fam_count = None
    fam_list: list[str] = []

    for line in proc.stdout.splitlines():
        if line.startswith("NEMA_REQ_COUNT "):
            try:
                req_count = int(line.split(" ", 1)[1].strip())
            except ValueError:
                req_count = None
        elif line.startswith("NEMA_REQ_LIST "):
            req_list = _parse_probe_list(line.split(" ", 1)[1].strip())
        elif line.startswith("NEMA_FAM_COUNT "):
            try:
                fam_count = int(line.split(" ", 1)[1].strip())
            except ValueError:
                fam_count = None
        elif line.startswith("NEMA_FAM_LIST "):
            fam_list = _parse_probe_list(line.split(" ", 1)[1].strip())

    can_target = proc.returncode == 0 and TARGET_PART in req_list

    payload = {
        "generatedAtUtc": _now_utc(),
        "targetPart": TARGET_PART,
        "command": cmd,
        "exitCode": proc.returncode,
        "requestedCount": req_count,
        "requestedList": req_list,
        "familyCount": fam_count,
        "familyList": fam_list,
        "canTargetRequestedPart": can_target,
        "hostPartProbeLog": str(log_path),
    }
    _write_json(VIVADO_OUT / "host_part_probe.json", payload)
    return payload


def _extract_b3_canonical_key() -> str:
    if not B3_STATUS.exists():
        raise FileNotFoundError(f"Missing canonical status file: {B3_STATUS}")

    payload = json.loads(B3_STATUS.read_text(encoding="utf-8"))

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

    for candidate in sorted(root.glob("**/sol1")):
        if (candidate / "syn").exists() or (candidate / "impl").exists():
            return candidate.resolve()

    raise FileNotFoundError(f"cannot find HLS solution dir under {root}")


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def _copy_or_empty(src: Path | None, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src is None:
        dst.write_text("", encoding="utf-8")
    else:
        shutil.copyfile(src, dst)


def _run_hls_b3(vitis_hls_bin: Path, b3_key: str) -> dict[str, Any]:
    bench_root = HLS_OUT_ROOT / b3_key
    bench_root.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "scripts/amd/run_artix7_hls.py",
        "--benchmark",
        b3_key,
        "--outdir",
        str(HLS_OUT_ROOT),
        "--part",
        TARGET_PART,
        "--clock-ns",
        f"{CLOCK_NS}",
        "--cosim",
        "on",
    ]

    proc = _run(cmd)
    (bench_root / "run_artix7_hls.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (bench_root / "run_artix7_hls.stderr.log").write_text(proc.stderr, encoding="utf-8")

    run_summary_path = bench_root / "run_artix7_hls.summary.json"
    run_summary: dict[str, Any] = {}
    if run_summary_path.exists():
        run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))

    sol = _find_solution_dir(bench_root)

    csim_src = _first_existing(
        [
            sol / "csim" / "report" / "nema_kernel_csim.log",
            sol / "csim" / "report" / "csim.log",
        ]
    )
    csynth_src = _first_existing(
        [
            sol / "syn" / "report" / "csynth.rpt",
            sol / "syn" / "report" / "nema_kernel_csynth.rpt",
        ]
    )
    cosim_src = _first_existing(
        [
            sol / "sim" / "report" / "verilog" / "nema_kernel.log",
            sol / "sim" / "verilog" / "xsim.log",
            bench_root / "logs" / "vitis_hls.stdout.log",
        ]
    )

    csim_dst = bench_root / "csim.log"
    csynth_dst = bench_root / "csynth.log"
    cosim_dst = bench_root / "cosim.log"

    _copy_or_empty(csim_src, csim_dst)
    _copy_or_empty(csynth_src, csynth_dst)
    _copy_or_empty(cosim_src, cosim_dst)

    selected_part_file = bench_root / "hls_run" / "hls_selected_part.txt"
    selected_part = selected_part_file.read_text(encoding="utf-8").strip() if selected_part_file.exists() else None

    hls_status_path = bench_root / "hls_run" / "hls_status.json"
    hls_status: dict[str, Any] = {}
    if hls_status_path.exists():
        hls_status = json.loads(hls_status_path.read_text(encoding="utf-8"))
    hls_status_part = hls_status.get("part") if isinstance(hls_status.get("part"), str) else None

    observed_part = selected_part or hls_status_part
    part_match_requested = observed_part == TARGET_PART
    runner_ok = bool(proc.returncode == 0 and run_summary.get("ok") is True)

    summary = {
        "generatedAtUtc": _now_utc(),
        "benchmark": b3_key,
        "targetPart": TARGET_PART,
        "command": cmd,
        "runnerExitCode": proc.returncode,
        "runnerOk": runner_ok,
        "runSummaryPath": str(run_summary_path),
        "hlsStatusPath": str(hls_status_path),
        "solutionDir": str(sol),
        "observedPart": observed_part,
        "partMatchRequested": part_match_requested,
        "csimLog": str(csim_dst),
        "csynthLog": str(csynth_dst),
        "cosimLog": str(cosim_dst),
        "csimSource": str(csim_src) if csim_src is not None else None,
        "csynthSource": str(csynth_src) if csynth_src is not None else None,
        "cosimSource": str(cosim_src) if cosim_src is not None else None,
    }
    _write_json(bench_root / "summary.json", summary)
    return summary


def _run_xci_part_sanity(b3_key: str) -> dict[str, Any]:
    bench_root = HLS_OUT_ROOT / b3_key
    sol = _find_solution_dir(bench_root)

    xci_files = sorted((sol / "impl" / "ip" / "hdl" / "ip").glob("**/*.xci"))
    if not xci_files:
        xci_files = sorted(sol.glob("**/*.xci"))

    rows: list[dict[str, Any]] = []
    blocked = False

    for xci in xci_files:
        txt = xci.read_text(encoding="utf-8", errors="replace")
        low = txt.lower()
        has_xcvh1742 = "xcvh1742" in low
        has_lsva4737 = "lsva4737" in low
        has_versal = "versal" in low
        has_forbidden = has_xcvh1742 or has_lsva4737 or has_versal
        blocked = blocked or has_forbidden
        rows.append(
            {
                "xciPath": str(xci),
                "contains_xcvh1742": has_xcvh1742,
                "contains_lsva4737": has_lsva4737,
                "contains_versal": has_versal,
                "hasForbiddenPartString": has_forbidden,
            }
        )

    payload = {
        "generatedAtUtc": _now_utc(),
        "benchmark": b3_key,
        "targetPart": TARGET_PART,
        "xciCount": len(rows),
        "status": "BLOCKED" if blocked else "PASS",
        "blocked": blocked,
        "forbiddenPatterns": ["xcvh1742", "lsva4737", "Versal"],
        "entries": rows,
    }
    _write_json(bench_root / "ip_part_sanity.json", payload)
    return payload


def _resolve_b1_hls_root() -> Path:
    candidates = [
        ROOT / "build" / "amd_hls_strict_v2" / "b1_small",
        ROOT / "build" / "amd_hls" / "b1_small",
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    raise FileNotFoundError("Could not locate reusable HLS root for b1_small")


def _choose_rtl_glob(sol: Path) -> str:
    patterns = [
        sol / "syn" / "verilog" / "*.v",
        sol / "impl" / "verilog" / "*.v",
        sol / "sim" / "verilog" / "*.v",
    ]
    for pattern in patterns:
        if list(pattern.parent.glob(pattern.name)):
            return str(pattern)
    return str(patterns[0])


def _parse_float(token: str | None) -> float | None:
    if token is None:
        return None
    try:
        return float(token)
    except (TypeError, ValueError):
        return None


def _parse_util_report(path: Path) -> dict[str, float | None]:
    out = {"lut": None, "ff": None, "bram": None, "dsp": None}
    if not path.exists():
        return out
    txt = path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "lut": r"\|\s*CLB LUTs\s*\|\s*([0-9.]+)\s*\|",
        "ff": r"\|\s*Registers\s*\|\s*([0-9.]+)\s*\|",
        "bram": r"\|\s*Block RAM Tile\s*\|\s*([0-9.]+)\s*\|",
        "dsp": r"\|\s*DSP Slices\s*\|\s*([0-9.]+)\s*\|",
    }
    for k, pat in patterns.items():
        m = re.search(pat, txt)
        out[k] = _parse_float(m.group(1) if m else None)
    return out


def _parse_timing_report(path: Path) -> dict[str, float | None]:
    out: dict[str, float | None] = {
        "wns": None,
        "tns": None,
        "clock_period_ns": CLOCK_NS,
        "clock_freq_mhz": None,
    }
    if not path.exists():
        return out

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

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

    for line in lines:
        m = re.match(r"^\s*ap_clk\s+\{[^}]+\}\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9]+(?:\.[0-9]+)?)", line)
        if m:
            out["clock_period_ns"] = _parse_float(m.group(1))
            out["clock_freq_mhz"] = _parse_float(m.group(2))
            break

    return out


def _fmax_est(clock_period_ns: float | None, wns: float | None) -> float | None:
    if clock_period_ns is None or wns is None:
        return None
    achieved = clock_period_ns - wns
    if achieved <= 0:
        return None
    return 1000.0 / achieved


def _run_impl_for_bench(bench_key: str, hls_root: Path, vivado_bin: Path, *, skip_reason: str | None = None) -> dict[str, Any]:
    outdir = VIVADO_OUT / bench_key
    logs = outdir / "logs"
    outdir.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    outputs = {
        "postRouteDcp": str(outdir / "post_route.dcp"),
        "postRouteTiming": str(outdir / "post_route_timing.rpt"),
        "postRouteUtilization": str(outdir / "post_route_utilization.rpt"),
        "vivadoLog": str(outdir / "vivado.log"),
    }

    if skip_reason is not None:
        return {
            "benchmark": bench_key,
            "hlsRoot": str(hls_root),
            "solutionDir": None,
            "rtlGlob": None,
            "xciGlob": None,
            "xdcGlob": None,
            "command": None,
            "runnerExitCode": None,
            "implOk": False,
            "reason": skip_reason,
            "part": None,
            "partMatchRequested": False,
            "lut": None,
            "ff": None,
            "bram": None,
            "dsp": None,
            "wns": None,
            "tns": None,
            "clockPeriodNs": CLOCK_NS,
            "clockFreqMhz": None,
            "fmaxEstMhz": None,
            "outputs": outputs,
            "vivadoStatusPath": str(outdir / "vivado_status.json"),
        }

    sol = _find_solution_dir(hls_root)
    rtl_glob = _choose_rtl_glob(sol)
    xci_glob = str(sol / "impl" / "ip" / "hdl" / "ip" / "**" / "*.xci")
    xdc_glob = str(sol / "impl" / "ip" / "constraints" / "*.xdc")

    tcl = ROOT / "scripts" / "amd" / "vivado_artix7_impl_power.tcl"
    cmd = [
        str(vivado_bin),
        "-mode",
        "batch",
        "-source",
        str(tcl),
        "-tclargs",
        "--benchmark",
        bench_key,
        "--top",
        "nema_kernel",
        "--clock-ns",
        f"{CLOCK_NS:.6f}",
        "--part",
        TARGET_PART,
        "--outdir",
        str(outdir),
        "--rtl-glob",
        rtl_glob,
        "--xci-glob",
        xci_glob,
        "--xdc-glob",
        xdc_glob,
    ]

    proc = _run(cmd)
    (logs / "vivado.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (logs / "vivado.stderr.log").write_text(proc.stderr, encoding="utf-8")
    (outdir / "vivado.log").write_text(
        proc.stdout + ("\n" if proc.stdout and not proc.stdout.endswith("\n") else "") + proc.stderr,
        encoding="utf-8",
    )
    (outdir / "run_vivado.command.txt").write_text(" ".join(cmd) + "\n", encoding="utf-8")

    vivado_status_path = outdir / "vivado_status.json"
    vivado_status: dict[str, Any] = {}
    if vivado_status_path.exists():
        vivado_status = json.loads(vivado_status_path.read_text(encoding="utf-8"))

    util = _parse_util_report(Path(outputs["postRouteUtilization"]))
    timing = _parse_timing_report(Path(outputs["postRouteTiming"]))

    part = vivado_status.get("part") if isinstance(vivado_status.get("part"), str) else None
    part_match = part == TARGET_PART

    impl_ok = (
        proc.returncode == 0
        and vivado_status.get("impl_ok") is True
        and Path(outputs["postRouteDcp"]).exists()
        and Path(outputs["postRouteTiming"]).exists()
        and Path(outputs["postRouteUtilization"]).exists()
        and part_match
    )

    return {
        "benchmark": bench_key,
        "hlsRoot": str(hls_root),
        "solutionDir": str(sol),
        "rtlGlob": rtl_glob,
        "xciGlob": xci_glob,
        "xdcGlob": xdc_glob,
        "command": cmd,
        "runnerExitCode": proc.returncode,
        "implOk": bool(impl_ok),
        "reason": "ok" if impl_ok else "vivado_impl_failed_or_incomplete",
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
        "outputs": outputs,
        "vivadoStatusPath": str(vivado_status_path),
    }


def _fmt(x: float | int | None) -> str:
    if x is None:
        return "-"
    if isinstance(x, int):
        return str(x)
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.6f}"


def _write_qor_csv(rows: list[dict[str, Any]]) -> None:
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
        writer = csv.writer(fh)
        writer.writerow(headers)
        for r in rows:
            writer.writerow(
                [
                    r["benchmark"],
                    str(bool(r.get("implOk"))).lower(),
                    r.get("part") or "-",
                    str(bool(r.get("partMatchRequested"))).lower(),
                    _fmt(r.get("lut")),
                    _fmt(r.get("ff")),
                    _fmt(r.get("bram")),
                    _fmt(r.get("dsp")),
                    _fmt(r.get("wns")),
                    _fmt(r.get("tns")),
                    _fmt(r.get("clockPeriodNs")),
                    _fmt(r.get("clockFreqMhz")),
                    _fmt(r.get("fmaxEstMhz")),
                    r.get("reason") or "-",
                    r.get("outputs", {}).get("postRouteDcp", "-"),
                    r.get("outputs", {}).get("postRouteUtilization", "-"),
                    r.get("outputs", {}).get("postRouteTiming", "-"),
                    r.get("outputs", {}).get("vivadoLog", "-"),
                ]
            )


def _parse_power_report(path: Path) -> dict[str, float | None]:
    out = {
        "totalOnChipPowerW": None,
        "dynamicPowerW": None,
        "deviceStaticPowerW": None,
    }
    if not path.exists():
        return out

    txt = path.read_text(encoding="utf-8", errors="replace")

    def _grab(pattern: str) -> float | None:
        m = re.search(pattern, txt, flags=re.IGNORECASE)
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None

    out["totalOnChipPowerW"] = _grab(r"Total On-Chip Power\s*\(W\)\s*\|\s*([0-9.+Ee-]+)")
    out["dynamicPowerW"] = _grab(r"Dynamic\s*\(W\)\s*\|\s*([0-9.+Ee-]+)")
    out["deviceStaticPowerW"] = _grab(r"Device Static\s*\(W\)\s*\|\s*([0-9.+Ee-]+)")
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
    (logs / "vivado_vectorless.exitcode.txt").write_text(str(proc.returncode), encoding="utf-8")
    return proc.returncode, rpt


def _export_timesim_from_dcp(vivado_bin: Path, dcp: Path, bench_out: Path, logs: Path) -> tuple[int, Path, Path]:
    timesim_v = bench_out / "nema_kernel_postroute_timesim.v"
    timesim_sdf = bench_out / "nema_kernel_postroute.sdf"
    tcl = bench_out / "export_postroute_timesim.tcl"
    tcl.write_text(
        "\n".join(
            [
                f"open_checkpoint {{{dcp}}}",
                f"write_verilog -force -mode timesim {{{timesim_v}}}",
                f"write_sdf -force {{{timesim_sdf}}}",
                "exit",
                "",
            ]
        ),
        encoding="utf-8",
    )
    proc = _run([str(vivado_bin), "-mode", "batch", "-source", str(tcl)])
    (logs / "vivado_timesim_export.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (logs / "vivado_timesim_export.stderr.log").write_text(proc.stderr, encoding="utf-8")
    (logs / "vivado_timesim_export.exitcode.txt").write_text(str(proc.returncode), encoding="utf-8")
    return proc.returncode, timesim_v, timesim_sdf


def _attempt_saif(vivado_bin: Path, bench_key: str, bench_out: Path, logs: Path, timesim_v: Path) -> tuple[str, Path | None, dict[str, Any]]:
    tb_v = bench_out / "tb_post_route_min.v"
    tb_v.write_text(
        "\n".join(
            [
                "`timescale 1ns/1ps",
                "module tb_post_route_min;",
                "  reg ap_clk = 1'b0;",
                "  always #2.5 ap_clk = ~ap_clk;",
                "",
                "  nema_kernel dut();",
                "",
                "  initial begin",
                f"    #{int(SAIF_WINDOW_NS)};",
                "    $finish;",
                "  end",
                "endmodule",
                "",
            ]
        ),
        encoding="utf-8",
    )

    prj = bench_out / "postroute_abs.prj"
    prj.write_text(
        "\n".join(
            [
                f"verilog work {timesim_v}",
                f"verilog work {tb_v}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    saif_path = bench_out / "activity.saif"
    xsim_tcl = bench_out / "xsim_dump_saif.tcl"
    xsim_tcl.write_text(
        "\n".join(
            [
                f"open_saif {saif_path}",
                "log_saif [get_objects -r /tb_post_route_min/*]",
                f"run {int(SAIF_WINDOW_NS)} ns",
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
        "saif_window_ns": SAIF_WINDOW_NS,
        "xelab_wall_sec": None,
        "xsim_wall_sec": None,
        "total_wall_sec": None,
    }

    if not xelab_bin.exists() or not xsim_bin.exists() or not glbl.exists():
        return "NOT_AVAILABLE:missing_xelab_or_xsim_or_glbl", None, duration

    snapshot = f"tb_saif_snapshot_{bench_key}"
    xelab_cmd = [
        str(xelab_bin),
        "-prj",
        str(prj),
        "--vlog",
        str(glbl),
        "glbl",
        "tb_post_route_min",
        "-L",
        "unisims_ver",
        "-L",
        "simprims_ver",
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

    (logs / "xelab_saif.stdout.log").write_text(xelab_proc.stdout, encoding="utf-8")
    (logs / "xelab_saif.stderr.log").write_text(xelab_proc.stderr, encoding="utf-8")
    (logs / "xelab_saif.exitcode.txt").write_text(str(xelab_proc.returncode), encoding="utf-8")
    if xelab_proc.returncode != 0:
        duration["total_wall_sec"] = time.monotonic() - t0
        return f"FAIL:xelab_rc_{xelab_proc.returncode}", None, duration

    xsim_cmd = [str(xsim_bin), snapshot, "-tclbatch", str(xsim_tcl)]
    y0 = time.monotonic()
    xsim_proc = _run(xsim_cmd, cwd=bench_out)
    y1 = time.monotonic()
    duration["xsim_wall_sec"] = y1 - y0
    duration["total_wall_sec"] = y1 - t0

    (logs / "xsim_saif.stdout.log").write_text(xsim_proc.stdout, encoding="utf-8")
    (logs / "xsim_saif.stderr.log").write_text(xsim_proc.stderr, encoding="utf-8")
    (logs / "xsim_saif.exitcode.txt").write_text(str(xsim_proc.returncode), encoding="utf-8")
    if xsim_proc.returncode != 0:
        return f"FAIL:xsim_rc_{xsim_proc.returncode}", None, duration

    if not saif_path.exists():
        return "FAIL:saif_not_emitted", None, duration

    return "PASS", saif_path, duration


def _run_saif_power(vivado_bin: Path, dcp: Path, bench_out: Path, logs: Path, saif_path: Path | None) -> tuple[int, Path, Path]:
    tcl = bench_out / "report_power_saif.tcl"
    saif_rpt = bench_out / "power_saif.rpt"
    read_saif_log = bench_out / "read_saif.log"

    if saif_path is None or not saif_path.exists():
        read_saif_log.write_text("READ_SAIF_FINAL:0\nNO_SAIF_INPUT\n", encoding="utf-8")
        (logs / "vivado_saif.stdout.log").write_text("", encoding="utf-8")
        (logs / "vivado_saif.stderr.log").write_text("Skipped: no SAIF input\n", encoding="utf-8")
        (logs / "vivado_saif.exitcode.txt").write_text("127\n", encoding="utf-8")
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
    (logs / "vivado_saif.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (logs / "vivado_saif.stderr.log").write_text(proc.stderr, encoding="utf-8")
    (logs / "vivado_saif.exitcode.txt").write_text(str(proc.returncode), encoding="utf-8")
    return proc.returncode, saif_rpt, read_saif_log


def _run_power_for_bench(vivado_bin: Path, bench_key: str, dcp_path: Path | None) -> dict[str, Any]:
    bench_out = POWER_OUT / bench_key
    logs = bench_out / "logs"
    bench_out.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

    if dcp_path is None or not dcp_path.exists():
        return {
            "benchmark": bench_key,
            "dcp_path": str(dcp_path) if dcp_path is not None else None,
            "vectorless_status": "NOT_AVAILABLE",
            "saif_generation_status": "NOT_AVAILABLE:missing_post_route_dcp",
            "read_saif_status": "NOT_RUN",
            "saif_power_status": "NOT_RUN",
            "vectorless": {"totalOnChipPowerW": None, "dynamicPowerW": None, "deviceStaticPowerW": None},
            "saif": {"totalOnChipPowerW": None, "dynamicPowerW": None, "deviceStaticPowerW": None},
            "saifDuration": {
                "saif_window_ns": SAIF_WINDOW_NS,
                "xelab_wall_sec": None,
                "xsim_wall_sec": None,
                "total_wall_sec": None,
            },
            "artifacts": {
                "power_vectorless_rpt": str(bench_out / "power_vectorless.rpt"),
                "power_saif_rpt": str(bench_out / "power_saif.rpt"),
                "saif": None,
                "read_saif_log": str(bench_out / "read_saif.log"),
            },
            "estimated_label": "ESTIMATED_PRE_BOARD_ONLY",
        }

    vec_rc, vec_rpt = _run_vectorless_power(vivado_bin, dcp_path, bench_out, logs)
    export_rc, timesim_v, _ = _export_timesim_from_dcp(vivado_bin, dcp_path, bench_out, logs)

    if export_rc != 0 or not timesim_v.exists():
        saif_generation_status = f"FAIL:timesim_export_rc_{export_rc}"
        saif_path = None
        saif_duration = {
            "saif_window_ns": SAIF_WINDOW_NS,
            "xelab_wall_sec": None,
            "xsim_wall_sec": None,
            "total_wall_sec": None,
        }
    else:
        saif_generation_status, saif_path, saif_duration = _attempt_saif(vivado_bin, bench_key, bench_out, logs, timesim_v)

    saif_rc, saif_rpt, read_saif_log = _run_saif_power(vivado_bin, dcp_path, bench_out, logs, saif_path)

    vec_metrics = _parse_power_report(vec_rpt)
    saif_metrics = _parse_power_report(saif_rpt)
    read_saif_status = _read_saif_status(read_saif_log)

    vectorless_status = "PASS" if vec_rc == 0 and vec_metrics.get("totalOnChipPowerW") is not None else "FAIL"
    if saif_rc == 127:
        saif_power_status = "NOT_RUN"
    else:
        saif_power_status = (
            "PASS"
            if saif_rc == 0 and read_saif_status == "PASS" and saif_metrics.get("totalOnChipPowerW") is not None
            else "FAIL"
        )

    return {
        "benchmark": bench_key,
        "dcp_path": str(dcp_path),
        "vectorless_status": vectorless_status,
        "saif_generation_status": saif_generation_status,
        "read_saif_status": read_saif_status,
        "saif_power_status": saif_power_status,
        "vectorless": vec_metrics,
        "saif": saif_metrics,
        "saifDuration": saif_duration,
        "artifacts": {
            "power_vectorless_rpt": str(vec_rpt),
            "power_saif_rpt": str(saif_rpt),
            "saif": str(saif_path) if saif_path is not None else None,
            "read_saif_log": str(read_saif_log),
        },
        "estimated_label": "ESTIMATED_PRE_BOARD_ONLY",
    }


def _write_power_csv(rows: list[dict[str, Any]]) -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    headers = [
        "benchmark",
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
        "saif_window_ns",
        "saif_total_wall_sec",
        "dcp_path",
        "saif_path",
        "read_saif_log",
        "power_vectorless_rpt",
        "power_saif_rpt",
        "estimated_label",
    ]

    with POWER_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for r in rows:
            writer.writerow(
                [
                    r["benchmark"],
                    r["vectorless_status"],
                    r["saif_generation_status"],
                    r["read_saif_status"],
                    r["saif_power_status"],
                    _fmt(r["vectorless"].get("totalOnChipPowerW")),
                    _fmt(r["vectorless"].get("dynamicPowerW")),
                    _fmt(r["vectorless"].get("deviceStaticPowerW")),
                    _fmt(r["saif"].get("totalOnChipPowerW")),
                    _fmt(r["saif"].get("dynamicPowerW")),
                    _fmt(r["saif"].get("deviceStaticPowerW")),
                    _fmt(r.get("saifDuration", {}).get("saif_window_ns")),
                    _fmt(r.get("saifDuration", {}).get("total_wall_sec")),
                    r.get("dcp_path") or "-",
                    r.get("artifacts", {}).get("saif") or "-",
                    r.get("artifacts", {}).get("read_saif_log") or "-",
                    r.get("artifacts", {}).get("power_vectorless_rpt") or "-",
                    r.get("artifacts", {}).get("power_saif_rpt") or "-",
                    r.get("estimated_label") or "-",
                ]
            )


def _append_or_replace_section(path: Path, marker: str, section_text: str) -> None:
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    start_tag = f"<!-- {marker}:START -->"
    end_tag = f"<!-- {marker}:END -->"
    block = f"{start_tag}\n{section_text}\n{end_tag}\n"

    if start_tag in original and end_tag in original:
        pattern = re.compile(re.escape(start_tag) + r".*?" + re.escape(end_tag) + r"\n?", re.S)
        updated = re.sub(pattern, block, original)
    else:
        suffix = "\n" if original.endswith("\n") or original == "" else "\n\n"
        updated = original + suffix + block

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")


def _update_docs(
    *,
    b3_key: str,
    probe: dict[str, Any],
    hls_summary: dict[str, Any],
    sanity: dict[str, Any],
    vivado_summary: dict[str, Any],
    power_summary: dict[str, Any],
    g1c_closed: bool,
    g1d_closed: bool,
) -> None:
    gate_lines = [
        "## Round8 v5 (forced Artix-7 + regenerated B3 HLS)",
        "",
        f"- Generated at UTC: {_now_utc()}",
        "- Requested part: `xc7a200tsbg484-1`",
        f"- Host part probe: `build/amd_vivado_artix7_v5/host_part_probe.json` (canTargetRequestedPart=`{str(bool(probe.get('canTargetRequestedPart'))).lower()}`)",
        f"- Canonical B3: `{b3_key}`",
        f"- HLS B3 summary: `build/amd_hls_artix7_v3/{b3_key}/summary.json`",
        f"- HLS B3 XCI sanity: `build/amd_hls_artix7_v3/{b3_key}/ip_part_sanity.json` status=`{sanity.get('status')}`",
        "",
        "| Gate | Status | Evidence |",
        "|---|---|---|",
        f"| G1c | {'CLOSED' if g1c_closed else 'OPEN'} | `build/amd_vivado_artix7_v5/summary.json` + `review_pack/tables/artix7_qor_v5.csv` |",
        f"| G1d | {'CLOSED' if g1d_closed else 'OPEN'} | `build/amd_power_artix7_v5/summary.json` + `review_pack/tables/artix7_power_v5.csv` |",
        "",
        "- Cierre G1c solo válido con post-route real para B1 y B3.",
        "- Cierre G1d solo válido con SAIF-guided PASS para B1 y B3.",
        "- Todos los resultados de potencia aquí son estimaciones pre-board (sin medición en placa).",
    ]
    _append_or_replace_section(DOC_GATE, "ROUND8_V5_GATE", "\n".join(gate_lines))

    power_rows = power_summary.get("results") if isinstance(power_summary.get("results"), list) else []
    saif_lines: list[str] = []
    for row in power_rows:
        if not isinstance(row, dict):
            continue
        duration = row.get("saifDuration") if isinstance(row.get("saifDuration"), dict) else {}
        saif_lines.append(
            f"- {row.get('benchmark')}: saif_window_ns={duration.get('saif_window_ns')} total_wall_sec={duration.get('total_wall_sec')} status={row.get('saif_generation_status')}/{row.get('saif_power_status')}"
        )

    power_lines = [
        "## Round8 v5 methodology note",
        "",
        f"- Generated at UTC: {_now_utc()}",
        "- Output root: `build/amd_power_artix7_v5/`",
        "- Target part: `xc7a200tsbg484-1`",
        "- SAIF window is intentionally short and recorded per benchmark (see summary + CSV).",
        "- Power reports are estimated post-implementation only (vectorless and SAIF-guided when available).",
        "- No value here is measured on board.",
        "",
        "### SAIF durations (round8 v5)",
        *saif_lines,
    ]
    _append_or_replace_section(DOC_POWER, "ROUND8_V5_POWER", "\n".join(power_lines))


def _write_chatgpt_brief(
    *,
    b3_key: str,
    probe: dict[str, Any],
    hls_summary: dict[str, Any],
    sanity: dict[str, Any],
    vivado_rows: list[dict[str, Any]],
    power_rows: list[dict[str, Any]],
    g1c_closed: bool,
    g1d_closed: bool,
) -> None:
    vivado_by_bench = {row.get("benchmark"): row for row in vivado_rows}
    power_by_bench = {row.get("benchmark"): row for row in power_rows}

    b1_impl = vivado_by_bench.get("b1_small", {})
    b3_impl = vivado_by_bench.get(b3_key, {})
    b1_pwr = power_by_bench.get("b1_small", {})
    b3_pwr = power_by_bench.get(b3_key, {})

    lines = [
        "Round8 Artix-7 rerun brief (for ChatGPT)",
        f"UTC: {_now_utc()}",
        f"Target part: {TARGET_PART}",
        f"Probe canTargetRequestedPart: {str(bool(probe.get('canTargetRequestedPart'))).lower()}",
        f"Canonical B3 benchmark key: {b3_key}",
        f"HLS B3 runner ok: {str(bool(hls_summary.get('runnerOk'))).lower()} (exit={hls_summary.get('runnerExitCode')})",
        f"HLS B3 observed part: {hls_summary.get('observedPart')}",
        f"HLS B3 XCI sanity status: {sanity.get('status')}",
        f"Vivado b1_small implOk: {str(bool(b1_impl.get('implOk'))).lower()}",
        f"Vivado {b3_key} implOk: {str(bool(b3_impl.get('implOk'))).lower()}",
        "Impl summary: build/amd_vivado_artix7_v5/summary.json",
        "QoR table: review_pack/tables/artix7_qor_v5.csv",
        f"Power b1_small saif_power_status: {b1_pwr.get('saif_power_status')}",
        f"Power {b3_key} saif_power_status: {b3_pwr.get('saif_power_status')}",
        "Power summary: build/amd_power_artix7_v5/summary.json",
        "Power table: review_pack/tables/artix7_power_v5.csv",
        f"G1c status: {'CLOSED' if g1c_closed else 'OPEN'}",
        f"G1d status: {'CLOSED' if g1d_closed else 'OPEN'}",
        "All power numbers remain ESTIMATED_PRE_BOARD_ONLY.",
        "No result is presented as a board measurement.",
    ]

    if len(lines) != 20:
        raise RuntimeError(f"CHATGPT_BRIEF_round8.md must have 20 lines, got {len(lines)}")

    CHATGPT_BRIEF.parent.mkdir(parents=True, exist_ok=True)
    CHATGPT_BRIEF.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _create_bundle(b3_key: str) -> None:
    include_paths = [
        ENV_JSON,
        HLS_OUT_ROOT / b3_key,
        VIVADO_OUT,
        POWER_OUT,
        QOR_CSV,
        POWER_CSV,
        DOC_GATE,
        DOC_POWER,
        B3_STATUS,
        CHATGPT_BRIEF,
    ]

    with tarfile.open(BUNDLE_TAR, "w:gz") as tar:
        for abs_path in include_paths:
            if not abs_path.exists():
                continue
            arcname = abs_path.relative_to(ROOT)
            tar.add(abs_path, arcname=str(arcname))

    digest = hashlib.sha256(BUNDLE_TAR.read_bytes()).hexdigest()
    BUNDLE_SHA.write_text(f"{digest}  {BUNDLE_TAR.name}\n", encoding="utf-8")


def main() -> int:
    HLS_OUT_ROOT.mkdir(parents=True, exist_ok=True)
    VIVADO_OUT.mkdir(parents=True, exist_ok=True)
    POWER_OUT.mkdir(parents=True, exist_ok=True)

    if PREFERRED_XILINX_BASE.exists():
        os.environ["XILINX_BASE"] = str(PREFERRED_XILINX_BASE)

    vivado_bin = _resolve_vivado_bin()
    vitis_hls_bin = _resolve_bin("vitis_hls")

    _collect_env(vivado_bin, vitis_hls_bin)

    if vivado_bin is None:
        raise RuntimeError("`vivado` not found in PATH; cannot proceed")

    probe = _run_part_probe(vivado_bin)
    if not probe.get("canTargetRequestedPart"):
        raise RuntimeError(
            "Part probe failed: `get_parts xc7a200tsbg484-1` returned empty or probe command failed. "
            "See build/amd_vivado_artix7_v5/host_part_probe.log"
        )

    if vitis_hls_bin is None:
        raise RuntimeError("`vitis_hls` not found in PATH; cannot run B3 HLS rerun")

    b3_key = _extract_b3_canonical_key()

    hls_summary = _run_hls_b3(vitis_hls_bin, b3_key)
    sanity = _run_xci_part_sanity(b3_key)

    b3_block_reason: str | None = None
    if not bool(hls_summary.get("runnerOk")):
        b3_block_reason = "BLOCKED:hls_runner_failed"
    elif not bool(hls_summary.get("partMatchRequested")):
        b3_block_reason = "BLOCKED:hls_selected_part_mismatch"
    elif bool(sanity.get("blocked")):
        b3_block_reason = "BLOCKED:ip_part_mismatch_detected_in_xci"

    b1_hls_root = _resolve_b1_hls_root()
    b3_hls_root = HLS_OUT_ROOT / b3_key

    vivado_rows: list[dict[str, Any]] = []
    vivado_rows.append(_run_impl_for_bench("b1_small", b1_hls_root, vivado_bin))
    vivado_rows.append(_run_impl_for_bench(b3_key, b3_hls_root, vivado_bin, skip_reason=b3_block_reason))

    _write_qor_csv(vivado_rows)

    vivado_summary = {
        "generatedAtUtc": _now_utc(),
        "targetPart": TARGET_PART,
        "canTargetRequestedPart": bool(probe.get("canTargetRequestedPart")),
        "benchmarks": ["b1_small", b3_key],
        "hlsB3Root": str(b3_hls_root),
        "hlsB3Summary": str(HLS_OUT_ROOT / b3_key / "summary.json"),
        "hlsB3IpPartSanity": str(HLS_OUT_ROOT / b3_key / "ip_part_sanity.json"),
        "results": vivado_rows,
        "tableArtifacts": {"csv": str(QOR_CSV)},
    }
    _write_json(VIVADO_OUT / "summary.json", vivado_summary)

    power_rows: list[dict[str, Any]] = []
    for row in vivado_rows:
        dcp = Path(row["outputs"]["postRouteDcp"]) if isinstance(row.get("outputs"), dict) else None
        if not (row.get("implOk") and dcp and dcp.exists()):
            dcp = None
        power_rows.append(_run_power_for_bench(vivado_bin, str(row.get("benchmark")), dcp))

    _write_power_csv(power_rows)

    power_summary = {
        "generatedAtUtc": _now_utc(),
        "targetPart": TARGET_PART,
        "estimatedOnly": True,
        "measuredOnBoard": False,
        "results": power_rows,
        "tableArtifacts": {"csv": str(POWER_CSV)},
        "notes": [
            "All power values are ESTIMATED_PRE_BOARD_ONLY.",
            "No value in this summary is measured on board.",
            "SAIF duration/window is reported per benchmark in saifDuration.",
        ],
    }
    _write_json(POWER_OUT / "summary.json", power_summary)

    required_impl = {"b1_small", b3_key}
    impl_map = {str(r.get("benchmark")): r for r in vivado_rows}
    g1c_closed = all(
        bench in impl_map
        and bool(impl_map[bench].get("implOk"))
        and Path(impl_map[bench].get("outputs", {}).get("postRouteDcp", "")).exists()
        for bench in required_impl
    )

    pwr_map = {str(r.get("benchmark")): r for r in power_rows}
    g1d_closed = all(
        bench in pwr_map
        and pwr_map[bench].get("saif_generation_status") == "PASS"
        and pwr_map[bench].get("read_saif_status") == "PASS"
        and pwr_map[bench].get("saif_power_status") == "PASS"
        for bench in required_impl
    )

    vivado_summary["g1cClosureRecommended"] = g1c_closed
    power_summary["g1dClosureRecommended"] = g1d_closed
    _write_json(VIVADO_OUT / "summary.json", vivado_summary)
    _write_json(POWER_OUT / "summary.json", power_summary)

    _update_docs(
        b3_key=b3_key,
        probe=probe,
        hls_summary=hls_summary,
        sanity=sanity,
        vivado_summary=vivado_summary,
        power_summary=power_summary,
        g1c_closed=g1c_closed,
        g1d_closed=g1d_closed,
    )

    _write_chatgpt_brief(
        b3_key=b3_key,
        probe=probe,
        hls_summary=hls_summary,
        sanity=sanity,
        vivado_rows=vivado_rows,
        power_rows=power_rows,
        g1c_closed=g1c_closed,
        g1d_closed=g1d_closed,
    )

    _create_bundle(b3_key)

    print(
        json.dumps(
            {
                "status": "OK",
                "targetPart": TARGET_PART,
                "b3": b3_key,
                "hlsSummary": str(HLS_OUT_ROOT / b3_key / "summary.json"),
                "hlsIpSanity": str(HLS_OUT_ROOT / b3_key / "ip_part_sanity.json"),
                "vivadoSummary": str(VIVADO_OUT / "summary.json"),
                "powerSummary": str(POWER_OUT / "summary.json"),
                "g1cClosed": g1c_closed,
                "g1dClosed": g1d_closed,
                "bundle": str(BUNDLE_TAR),
                "bundleSha": str(BUNDLE_SHA),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
