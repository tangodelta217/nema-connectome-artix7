#!/usr/bin/env python3
"""Round7 rerun: Vivado Artix-7 G1c + G1d with forced Vivado binary and evidence pack."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VIVADO_OUT = ROOT / "build" / "amd_vivado_artix7_v4"
POWER_OUT = ROOT / "build" / "amd_power_artix7_v4"
TABLE_DIR = ROOT / "review_pack" / "tables"
DOC_GATE = ROOT / "docs" / "GATE_STATUS.md"
DOC_POWER = ROOT / "docs" / "POWER_METHODOLOGY.md"
B3_STATUS = ROOT / "build" / "codex_handoff" / "B3_CANONICAL_STATUS.json"
CHATGPT_BRIEF = ROOT / "build" / "codex_handoff" / "CHATGPT_BRIEF_round7.md"
BUNDLE_TAR = ROOT / "codex_handoff_round7_for_chatgpt.tar.gz"
BUNDLE_SHA = ROOT / "codex_handoff_round7_for_chatgpt.sha256"

PREFERRED_VIVADO = Path("/media/tangodelta/Vivado/2025.2/Vivado/bin/vivado")
TARGET_PART = "xc7a200tsbg484-1"
CLOCK_NS = 5.0


@dataclass(frozen=True)
class Bench:
    key: str
    mandatory: bool


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run(cmd: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=env)


def _resolve_vivado_bin() -> Path:
    if PREFERRED_VIVADO.exists() and os.access(PREFERRED_VIVADO, os.X_OK):
        return PREFERRED_VIVADO.resolve()
    fallback = shutil.which("vivado")
    if fallback:
        return Path(fallback).resolve()
    raise FileNotFoundError("Cannot locate Vivado binary: preferred path missing and `command -v vivado` empty")


def _collect_env(vivado_bin: Path) -> dict[str, Any]:
    version_proc = _run([str(vivado_bin), "-version"])
    which_proc = _run(["bash", "-lc", "which vivado || true"])
    uname_proc = _run(["uname", "-a"])

    env_payload = {
        "generatedAtUtc": _now_utc(),
        "vivado_bin": str(vivado_bin),
        "vivado_version_stdout": version_proc.stdout,
        "vivado_version_stderr": version_proc.stderr,
        "vivado_version_exit_code": version_proc.returncode,
        "which_vivado": which_proc.stdout.strip(),
        "which_vivado_stderr": which_proc.stderr,
        "PATH": os.environ.get("PATH", ""),
        "uname_a": uname_proc.stdout.strip(),
    }
    _write_json(VIVADO_OUT / "env.json", env_payload)
    return env_payload


def _write_part_probe_tcl(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"set requested [lsort [get_parts {TARGET_PART}]]",
                "set family [lsort [get_parts xc7a200t*]]",
                "puts \"NEMA_REQ_COUNT [llength $requested]\"",
                "puts \"NEMA_REQ_LIST [join $requested ,]\"",
                "puts \"NEMA_FAM_COUNT [llength $family]\"",
                "puts \"NEMA_FAM_LIST [join $family ,]\"",
                "exit",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _parse_probe_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _run_part_probe(vivado_bin: Path) -> dict[str, Any]:
    tcl_path = VIVADO_OUT / "part_probe_inline.tcl"
    _write_part_probe_tcl(tcl_path)

    cmd = [
        str(vivado_bin),
        "-mode",
        "batch",
        "-nolog",
        "-nojournal",
        "-source",
        str(tcl_path),
    ]
    proc = _run(cmd)
    log_path = VIVADO_OUT / "host_part_probe.log"
    log_path.write_text(proc.stdout + ("\n" if proc.stdout and not proc.stdout.endswith("\n") else "") + proc.stderr, encoding="utf-8")

    req_count = None
    fam_count = None
    req_list: list[str] = []
    fam_list: list[str] = []

    for line in proc.stdout.splitlines():
        if line.startswith("NEMA_REQ_COUNT "):
            try:
                req_count = int(line.split(" ", 1)[1].strip())
            except ValueError:
                req_count = None
        elif line.startswith("NEMA_FAM_COUNT "):
            try:
                fam_count = int(line.split(" ", 1)[1].strip())
            except ValueError:
                fam_count = None
        elif line.startswith("NEMA_REQ_LIST "):
            req_list = _parse_probe_list(line.split(" ", 1)[1].strip())
        elif line.startswith("NEMA_FAM_LIST "):
            fam_list = _parse_probe_list(line.split(" ", 1)[1].strip())

    can_target = proc.returncode == 0 and TARGET_PART in req_list
    payload = {
        "generatedAtUtc": _now_utc(),
        "vivado_bin": str(vivado_bin),
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


def _write_host_not_suitable(probe: dict[str, Any], env_payload: dict[str, Any]) -> None:
    fam_count = probe.get("familyCount")
    req_count = probe.get("requestedCount")

    if probe.get("exitCode") != 0:
        reason = (
            "El part probe falló (exit code != 0). Esto normalmente indica entorno Vivado no funcional "
            "o PATH/toolchain inconsistente."
        )
    elif isinstance(fam_count, int) and fam_count == 0:
        reason = (
            "`get_parts xc7a200t*` devolvió 0. Este host no está usando un Vivado con catálogo Artix-7 "
            "esperado (PATH equivocado o instalación incompleta)."
        )
    elif isinstance(fam_count, int) and fam_count > 0 and (not isinstance(req_count, int) or req_count == 0):
        reason = (
            "El Vivado sí lista parts `xc7a200t*`, pero no incluye exactamente `xc7a200tsbg484-1`. "
            "No se puede garantizar targeting al part solicitado."
        )
    else:
        reason = "No se pudo confirmar disponibilidad exacta del part solicitado."

    md = [
        "# HOST_NOT_SUITABLE",
        "",
        f"Fecha UTC: {_now_utc()}",
        "",
        "## Resultado",
        reason,
        "",
        "## Evidencia",
        f"- vivado_bin usado: `{env_payload.get('vivado_bin')}`",
        f"- which vivado: `{env_payload.get('which_vivado')}`",
        f"- requestedCount (`{TARGET_PART}`): `{probe.get('requestedCount')}`",
        f"- familyCount (`xc7a200t*`): `{probe.get('familyCount')}`",
        f"- familyList: `{','.join(probe.get('familyList') or [])}`",
        f"- host_part_probe.log: `{probe.get('hostPartProbeLog')}`",
        "",
        "Se detiene aquí por regla: sin part exacto no se corre impl/power.",
        "",
    ]
    (VIVADO_OUT / "HOST_NOT_SUITABLE.md").write_text("\n".join(md), encoding="utf-8")


def _find_solution_dir(root: Path) -> Path:
    candidates = [
        root / "hls_run" / "hls_proj" / "nema_hls_prj" / "sol1",
        root / "hls_proj" / "nema_hls_prj" / "sol1",
        root / "nema_hls_prj" / "sol1",
        root / "nema_hwtest" / "sol1",
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    for c in sorted(root.glob("**/sol1")):
        if (c / "syn").exists() or (c / "impl").exists():
            return c.resolve()
    raise FileNotFoundError(f"Cannot find HLS solution dir under {root}")


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


def _resolve_hls_root(bench_key: str) -> Path:
    candidates = [
        ROOT / "build" / "amd_hls_strict_v2" / bench_key,
        ROOT / "build" / "amd_hls" / bench_key,
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    raise FileNotFoundError(f"HLS root not found for benchmark {bench_key}")


def _parse_float(token: str | None) -> float | None:
    if token is None:
        return None
    try:
        return float(token)
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


def _fmt(x: float | None) -> str:
    if x is None:
        return "-"
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.6f}"


def _run_impl_for_bench(bench_key: str, vivado_bin: Path) -> dict[str, Any]:
    hls_root = _resolve_hls_root(bench_key)
    sol = _find_solution_dir(hls_root)
    rtl_glob = _choose_rtl_glob(sol)
    xci_glob = str(sol / "impl" / "ip" / "hdl" / "ip" / "**" / "*.xci")
    xdc_glob = str(sol / "impl" / "ip" / "constraints" / "*.xdc")

    outdir = VIVADO_OUT / bench_key
    logs = outdir / "logs"
    outdir.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)

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

    outputs = {
        "postSynthUtilization": str(outdir / "post_synth_utilization.rpt"),
        "postRouteUtilization": str(outdir / "post_route_utilization.rpt"),
        "postSynthTiming": str(outdir / "post_synth_timing.rpt"),
        "postRouteTiming": str(outdir / "post_route_timing.rpt"),
        "operatingConditions": str(outdir / "operating_conditions.rpt"),
        "vivadoLog": str(outdir / "vivado.log"),
        "postRouteDcp": str(outdir / "post_route.dcp"),
    }
    required_paths = [Path(outputs[k]) for k in outputs]
    required_exists = all(p.exists() for p in required_paths)

    util = _parse_util_report(Path(outputs["postRouteUtilization"]))
    timing = _parse_timing_report(Path(outputs["postRouteTiming"]))
    part = vivado_status.get("part") if isinstance(vivado_status.get("part"), str) else None
    part_match = part == TARGET_PART

    impl_ok = bool(
        proc.returncode == 0
        and vivado_status.get("impl_ok") is True
        and required_exists
        and timing.get("wns") is not None
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
        "implOk": impl_ok,
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


def _write_qor_csv(rows: list[dict[str, Any]]) -> Path:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = TABLE_DIR / "artix7_qor_v4.csv"
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
        "operating_conditions",
        "vivado_log",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
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
                    r.get("outputs", {}).get("operatingConditions", "-"),
                    r.get("outputs", {}).get("vivadoLog", "-"),
                ]
            )
    return csv_path


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

    out["totalOnChipPowerW"] = _grab(r"Total On-Chip Power\s*\(W\)\s*\|\s*([0-9.+-Ee]+)")
    out["dynamicPowerW"] = _grab(r"Dynamic\s*\(W\)\s*\|\s*([0-9.+-Ee]+)")
    out["deviceStaticPowerW"] = _grab(r"Device Static\s*\(W\)\s*\|\s*([0-9.+-Ee]+)")
    return out


def _read_saif_status(read_saif_log: Path) -> str:
    if not read_saif_log.exists():
        return "NOT_RUN"
    txt = read_saif_log.read_text(encoding="utf-8", errors="replace")
    if "READ_SAIF_FINAL:1" in txt:
        return "PASS"
    if "NO_SAIF_INPUT" in txt:
        return "NOT_AVAILABLE"
    return "FAIL"


def _run_vectorless_power(vivado_bin: Path, dcp: Path, bench_out: Path, logs: Path) -> tuple[int, Path]:
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
    proc = _run([str(vivado_bin), "-mode", "batch", "-source", str(vec_tcl)])
    (logs / "vivado_vectorless.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (logs / "vivado_vectorless.stderr.log").write_text(proc.stderr, encoding="utf-8")
    (logs / "vivado_vectorless.exitcode.txt").write_text(str(proc.returncode), encoding="utf-8")
    return proc.returncode, vec_rpt


def _export_timesim_from_dcp(vivado_bin: Path, dcp: Path, bench_out: Path, logs: Path) -> tuple[int, Path, Path]:
    timesim_v = bench_out / "nema_kernel_postroute_timesim.v"
    timesim_sdf = bench_out / "nema_kernel_postroute.sdf"
    export_tcl = bench_out / "export_postroute_timesim.tcl"
    export_tcl.write_text(
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
    proc = _run([str(vivado_bin), "-mode", "batch", "-source", str(export_tcl)])
    (logs / "vivado_timesim_export.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (logs / "vivado_timesim_export.stderr.log").write_text(proc.stderr, encoding="utf-8")
    (logs / "vivado_timesim_export.exitcode.txt").write_text(str(proc.returncode), encoding="utf-8")
    return proc.returncode, timesim_v, timesim_sdf


def _attempt_saif(vivado_bin: Path, bench_key: str, bench_out: Path, logs: Path, timesim_v: Path) -> tuple[str, Path | None]:
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
                "    #200;",
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
                "run 200 ns",
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

    if not xelab_bin.exists() or not xsim_bin.exists() or not glbl.exists():
        return "NOT_AVAILABLE:missing_xelab_or_xsim_or_glbl", None

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
    xelab_proc = _run(xelab_cmd, cwd=bench_out)
    (logs / "xelab_saif.stdout.log").write_text(xelab_proc.stdout, encoding="utf-8")
    (logs / "xelab_saif.stderr.log").write_text(xelab_proc.stderr, encoding="utf-8")
    (logs / "xelab_saif.exitcode.txt").write_text(str(xelab_proc.returncode), encoding="utf-8")
    if xelab_proc.returncode != 0:
        return f"FAIL:xelab_rc_{xelab_proc.returncode}", None

    xsim_cmd = [str(xsim_bin), snapshot, "-tclbatch", str(xsim_tcl)]
    xsim_proc = _run(xsim_cmd, cwd=bench_out)
    (logs / "xsim_saif.stdout.log").write_text(xsim_proc.stdout, encoding="utf-8")
    (logs / "xsim_saif.stderr.log").write_text(xsim_proc.stderr, encoding="utf-8")
    (logs / "xsim_saif.exitcode.txt").write_text(str(xsim_proc.returncode), encoding="utf-8")
    if xsim_proc.returncode != 0:
        return f"FAIL:xsim_rc_{xsim_proc.returncode}", None

    if not saif_path.exists():
        return "FAIL:saif_not_emitted", None

    return "PASS", saif_path


def _run_saif_power(vivado_bin: Path, dcp: Path, bench_out: Path, logs: Path, saif_path: Path | None) -> tuple[int, Path, Path]:
    saif_tcl = bench_out / "report_power_saif.tcl"
    saif_rpt = bench_out / "power_saif.rpt"
    read_saif_log = bench_out / "read_saif.log"

    if saif_path is None or not saif_path.exists():
        read_saif_log.write_text("READ_SAIF_FINAL:0\nNO_SAIF_INPUT\n", encoding="utf-8")
        (logs / "vivado_saif.stdout.log").write_text("", encoding="utf-8")
        (logs / "vivado_saif.stderr.log").write_text("Skipped: no SAIF input\n", encoding="utf-8")
        (logs / "vivado_saif.exitcode.txt").write_text("127\n", encoding="utf-8")
        return 127, saif_rpt, read_saif_log

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

    proc = _run([str(vivado_bin), "-mode", "batch", "-source", str(saif_tcl)])
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
            "dcp_path": str(dcp_path) if dcp_path else None,
            "vectorless_status": "NOT_AVAILABLE",
            "saif_generation_status": "NOT_AVAILABLE:missing_post_route_dcp",
            "read_saif_status": "NOT_RUN",
            "saif_power_status": "NOT_RUN",
            "vectorless": {"totalOnChipPowerW": None, "dynamicPowerW": None, "deviceStaticPowerW": None},
            "saif": {"totalOnChipPowerW": None, "dynamicPowerW": None, "deviceStaticPowerW": None},
            "artifacts": {
                "power_vectorless_rpt": str(bench_out / "power_vectorless.rpt"),
                "power_saif_rpt": str(bench_out / "power_saif.rpt"),
                "saif": None,
                "read_saif_log": str(bench_out / "read_saif.log"),
            },
            "estimated_label": "ESTIMATED_PRE_BOARD_ONLY",
        }

    vec_rc, vec_rpt = _run_vectorless_power(vivado_bin, dcp_path, bench_out, logs)
    export_rc, timesim_v, _timesim_sdf = _export_timesim_from_dcp(vivado_bin, dcp_path, bench_out, logs)

    if export_rc != 0 or not timesim_v.exists():
        saif_generation_status = f"FAIL:timesim_export_rc_{export_rc}"
        saif_path = None
    else:
        saif_generation_status, saif_path = _attempt_saif(vivado_bin, bench_key, bench_out, logs, timesim_v)

    saif_rc, saif_rpt, read_saif_log = _run_saif_power(vivado_bin, dcp_path, bench_out, logs, saif_path)

    vec_metrics = _parse_power_report(vec_rpt)
    saif_metrics = _parse_power_report(saif_rpt)
    read_saif_status = _read_saif_status(read_saif_log)

    vectorless_status = "PASS" if vec_rc == 0 and vec_metrics.get("totalOnChipPowerW") is not None else "FAIL"
    if saif_rc == 127:
        saif_power_status = "NOT_RUN"
    else:
        saif_power_status = "PASS" if (saif_rc == 0 and read_saif_status == "PASS" and saif_metrics.get("totalOnChipPowerW") is not None) else "FAIL"

    return {
        "benchmark": bench_key,
        "dcp_path": str(dcp_path),
        "vectorless_status": vectorless_status,
        "saif_generation_status": saif_generation_status,
        "read_saif_status": read_saif_status,
        "saif_power_status": saif_power_status,
        "vectorless": vec_metrics,
        "saif": saif_metrics,
        "artifacts": {
            "power_vectorless_rpt": str(vec_rpt),
            "power_saif_rpt": str(saif_rpt),
            "saif": str(saif_path) if saif_path else None,
            "read_saif_log": str(read_saif_log),
        },
        "estimated_label": "ESTIMATED_PRE_BOARD_ONLY",
    }


def _write_power_csv(rows: list[dict[str, Any]]) -> Path:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = TABLE_DIR / "artix7_power_v4.csv"
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
        "dcp_path",
        "saif_path",
        "read_saif_log",
        "power_vectorless_rpt",
        "power_saif_rpt",
        "estimated_label",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
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
                    r.get("dcp_path") or "-",
                    r.get("artifacts", {}).get("saif") or "-",
                    r.get("artifacts", {}).get("read_saif_log") or "-",
                    r.get("artifacts", {}).get("power_vectorless_rpt") or "-",
                    r.get("artifacts", {}).get("power_saif_rpt") or "-",
                    r.get("estimated_label") or "-",
                ]
            )
    return csv_path


def _extract_b3_canonical_key() -> str:
    if not B3_STATUS.exists():
        raise FileNotFoundError(f"Missing canonical status file: {B3_STATUS}")

    payload = json.loads(B3_STATUS.read_text(encoding="utf-8"))

    sidecar = payload.get("sidecarPath")
    if isinstance(sidecar, str):
        stem = Path(sidecar).stem
        if stem.startswith("b3_"):
            return stem

    benchmark_manifest = payload.get("benchmarkNameInManifest")
    if isinstance(benchmark_manifest, str):
        low = benchmark_manifest.lower()
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

    raise ValueError("Could not determine canonical B3 benchmark key from B3_CANONICAL_STATUS.json")


def _write_blocked_md_if_needed(power_rows: list[dict[str, Any]]) -> bool:
    blocked_lines: list[str] = []
    for row in power_rows:
        bench = row["benchmark"]
        if row["saif_generation_status"] != "PASS":
            blocked_lines.append(f"- {bench}: saif_generation_status={row['saif_generation_status']}")
        if row["read_saif_status"] != "PASS":
            blocked_lines.append(f"- {bench}: read_saif_status={row['read_saif_status']}")
        if row["saif_power_status"] != "PASS":
            blocked_lines.append(f"- {bench}: saif_power_status={row['saif_power_status']}")

    blocked = len(blocked_lines) > 0
    if blocked:
        content = [
            "# BLOCKED",
            "",
            "No se puede cerrar G1d porque SAIF/post-implementation no quedó PASS para todos los benches requeridos.",
            "",
            "## Causas",
            *blocked_lines,
            "",
            "Todos los resultados son ESTIMATED_PRE_BOARD_ONLY. No hay medición en placa.",
            "",
        ]
        (POWER_OUT / "BLOCKED.md").write_text("\n".join(content), encoding="utf-8")
    return blocked


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
    probe: dict[str, Any],
    vivado_summary_path: Path,
    power_summary_path: Path,
    b3_key: str,
    g1c_closed: bool,
    g1d_closed: bool,
    early_stop: bool,
) -> None:
    gate_lines = [
        "## Round7 v4 (forced Vivado Artix-7)",
        "",
        f"- Generated at UTC: {_now_utc()}",
        f"- Forced vivado_bin evidence: `build/amd_vivado_artix7_v4/env.json`",
        f"- Part probe evidence: `build/amd_vivado_artix7_v4/host_part_probe.json`",
        f"- Requested part: `{TARGET_PART}`",
        f"- canTargetRequestedPart: `{str(bool(probe.get('canTargetRequestedPart'))).lower()}`",
        "",
        "| Gate | Status | Evidence |",
        "|---|---|---|",
        f"| G1c | {'CLOSED' if g1c_closed else 'OPEN'} | `{vivado_summary_path}` + `review_pack/tables/artix7_qor_v4.csv` |",
        f"| G1d | {'CLOSED' if g1d_closed else 'OPEN'} | `{power_summary_path}` + `review_pack/tables/artix7_power_v4.csv` |",
        "",
        f"- B3 canónico usado: `{b3_key}`",
        "- Límites: resultados de potencia son estimaciones pre-board; no medición en placa.",
    ]
    if early_stop:
        gate_lines.append("- Ejecución detenida tras probe (host no apto para targeting exacto del part).")

    _append_or_replace_section(DOC_GATE, "ROUND7_V4_GATE", "\n".join(gate_lines))

    power_lines = [
        "## Round7 v4 methodology note",
        "",
        f"- Generated at UTC: {_now_utc()}",
        f"- Output root: `build/amd_power_artix7_v4/`",
        f"- Target part: `{TARGET_PART}`",
        "- Power reports are post-implementation estimations (vectorless and SAIF-guided when possible).",
        "- All values remain `ESTIMATED_PRE_BOARD_ONLY`; no board measurement claim.",
        "- If SAIF generation/mapping fails for any required benchmark, G1d stays OPEN and `BLOCKED.md` explains exact causes.",
    ]
    _append_or_replace_section(DOC_POWER, "ROUND7_V4_POWER", "\n".join(power_lines))


def _write_chatgpt_brief(
    *,
    vivado_bin: Path,
    probe: dict[str, Any],
    b3_key: str,
    vivado_summary: dict[str, Any],
    power_summary: dict[str, Any],
    g1c_closed: bool,
    g1d_closed: bool,
    early_stop: bool,
) -> None:
    impl_results = vivado_summary.get("results") or []
    power_results = power_summary.get("results") or []

    lines = [
        "Round7 rerun brief (for ChatGPT)",
        f"UTC: {_now_utc()}",
        f"Forced vivado_bin: {vivado_bin}",
        f"Target part: {TARGET_PART}",
        f"Probe canTargetRequestedPart: {str(bool(probe.get('canTargetRequestedPart'))).lower()}",
        f"Probe familyCount xc7a200t*: {probe.get('familyCount')}",
        f"Probe requestedCount exact: {probe.get('requestedCount')}",
        f"Canonical B3 benchmark key: {b3_key}",
        f"Benchmarks planned: b1_small, {b3_key}",
        f"Early stop after probe: {str(early_stop).lower()}",
        f"Impl benches executed: {len(impl_results)}",
        f"Impl summary: build/amd_vivado_artix7_v4/summary.json",
        f"QoR table: review_pack/tables/artix7_qor_v4.csv",
        f"Power benches executed: {len(power_results)}",
        f"Power summary: build/amd_power_artix7_v4/summary.json",
        f"Power table: review_pack/tables/artix7_power_v4.csv",
        f"G1c status: {'CLOSED' if g1c_closed else 'OPEN'}",
        f"G1d status: {'CLOSED' if g1d_closed else 'OPEN'}",
        "No result is presented as on-board measurement.",
        "See HOST_NOT_SUITABLE.md or BLOCKED.md when a gate remains OPEN.",
    ]
    if len(lines) != 20:
        raise RuntimeError(f"CHATGPT_BRIEF_round7.md must have 20 lines, got {len(lines)}")

    CHATGPT_BRIEF.parent.mkdir(parents=True, exist_ok=True)
    CHATGPT_BRIEF.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _create_bundle() -> None:
    include_candidates = [
        VIVADO_OUT,
        POWER_OUT,
        TABLE_DIR / "artix7_qor_v4.csv",
        TABLE_DIR / "artix7_power_v4.csv",
        DOC_GATE,
        DOC_POWER,
        B3_STATUS,
        CHATGPT_BRIEF,
    ]
    include_paths = [p for p in include_candidates if p.exists()]

    with tarfile.open(BUNDLE_TAR, "w:gz") as tar:
        for abs_path in include_paths:
            arcname = abs_path.relative_to(ROOT)
            tar.add(abs_path, arcname=str(arcname))

    digest = hashlib.sha256(BUNDLE_TAR.read_bytes()).hexdigest()
    BUNDLE_SHA.write_text(f"{digest}  {BUNDLE_TAR.name}\n", encoding="utf-8")


def main() -> int:
    VIVADO_OUT.mkdir(parents=True, exist_ok=True)
    POWER_OUT.mkdir(parents=True, exist_ok=True)

    vivado_bin = _resolve_vivado_bin()
    env_payload = _collect_env(vivado_bin)
    probe = _run_part_probe(vivado_bin)

    b3_key = _extract_b3_canonical_key()
    benches = [Bench("b1_small", True), Bench(b3_key, True)]

    if not probe.get("canTargetRequestedPart"):
        _write_host_not_suitable(probe, env_payload)

        vivado_summary = {
            "generatedAtUtc": _now_utc(),
            "vivado_bin": str(vivado_bin),
            "targetPart": TARGET_PART,
            "canTargetRequestedPart": False,
            "results": [],
            "g1cClosureRecommended": False,
            "reason": "probe_failed_or_part_unavailable",
        }
        _write_json(VIVADO_OUT / "summary.json", vivado_summary)

        power_summary = {
            "generatedAtUtc": _now_utc(),
            "targetPart": TARGET_PART,
            "estimatedOnly": True,
            "measuredOnBoard": False,
            "results": [],
            "g1dClosureRecommended": False,
            "reason": "skipped_because_part_probe_failed",
        }
        _write_json(POWER_OUT / "summary.json", power_summary)

        _update_docs(
            probe=probe,
            vivado_summary_path=VIVADO_OUT / "summary.json",
            power_summary_path=POWER_OUT / "summary.json",
            b3_key=b3_key,
            g1c_closed=False,
            g1d_closed=False,
            early_stop=True,
        )
        _write_chatgpt_brief(
            vivado_bin=vivado_bin,
            probe=probe,
            b3_key=b3_key,
            vivado_summary=vivado_summary,
            power_summary=power_summary,
            g1c_closed=False,
            g1d_closed=False,
            early_stop=True,
        )
        _create_bundle()
        print(json.dumps({"status": "STOPPED_HOST_NOT_SUITABLE", "probe": probe}, indent=2, ensure_ascii=False))
        return 0

    impl_rows: list[dict[str, Any]] = []
    for bench in benches:
        impl_rows.append(_run_impl_for_bench(bench.key, vivado_bin))

    qor_csv = _write_qor_csv(impl_rows)

    g1c_closed = all(
        row.get("implOk")
        and row.get("partMatchRequested")
        and Path(row.get("outputs", {}).get("postRouteUtilization", "")).exists()
        and Path(row.get("outputs", {}).get("postRouteTiming", "")).exists()
        for row in impl_rows
    )

    vivado_summary = {
        "generatedAtUtc": _now_utc(),
        "vivado_bin": str(vivado_bin),
        "targetPart": TARGET_PART,
        "canTargetRequestedPart": True,
        "benchmarks": [b.key for b in benches],
        "results": impl_rows,
        "g1cClosureRecommended": g1c_closed,
        "tableArtifacts": {"csv": str(qor_csv)},
    }
    _write_json(VIVADO_OUT / "summary.json", vivado_summary)

    power_rows: list[dict[str, Any]] = []
    for row in impl_rows:
        dcp = Path(row["outputs"]["postRouteDcp"]) if row.get("outputs") else None
        if not (row.get("implOk") and dcp and dcp.exists()):
            dcp = None
        power_rows.append(_run_power_for_bench(vivado_bin, row["benchmark"], dcp))

    power_csv = _write_power_csv(power_rows)
    blocked = _write_blocked_md_if_needed(power_rows)

    g1d_closed = all(
        r.get("vectorless_status") == "PASS"
        and r.get("saif_generation_status") == "PASS"
        and r.get("read_saif_status") == "PASS"
        and r.get("saif_power_status") == "PASS"
        for r in power_rows
    )

    power_summary = {
        "generatedAtUtc": _now_utc(),
        "targetPart": TARGET_PART,
        "estimatedOnly": True,
        "measuredOnBoard": False,
        "results": power_rows,
        "g1dClosureRecommended": bool(g1d_closed),
        "blocked": bool(blocked),
        "tableArtifacts": {"csv": str(power_csv)},
        "notes": [
            "All power values are ESTIMATED_PRE_BOARD_ONLY.",
            "No value in this summary is measured on board.",
        ],
    }
    _write_json(POWER_OUT / "summary.json", power_summary)

    _update_docs(
        probe=probe,
        vivado_summary_path=VIVADO_OUT / "summary.json",
        power_summary_path=POWER_OUT / "summary.json",
        b3_key=b3_key,
        g1c_closed=g1c_closed,
        g1d_closed=g1d_closed,
        early_stop=False,
    )

    _write_chatgpt_brief(
        vivado_bin=vivado_bin,
        probe=probe,
        b3_key=b3_key,
        vivado_summary=vivado_summary,
        power_summary=power_summary,
        g1c_closed=g1c_closed,
        g1d_closed=g1d_closed,
        early_stop=False,
    )

    _create_bundle()

    print(
        json.dumps(
            {
                "status": "OK",
                "g1cClosureRecommended": g1c_closed,
                "g1dClosureRecommended": g1d_closed,
                "vivadoSummary": str(VIVADO_OUT / "summary.json"),
                "powerSummary": str(POWER_OUT / "summary.json"),
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
