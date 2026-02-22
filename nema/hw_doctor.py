"""Environment diagnostics for NEMA hardware toolchain availability."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

_VERSION_TIMEOUT_S = 3.0
_NOT_FOUND = "NOT_FOUND"


def _which(binary: str) -> str | None:
    return shutil.which(binary)


def _first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _run_version(binary_path: str) -> str:
    try:
        proc = subprocess.run(
            [binary_path, "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return f"TIMEOUT ({_VERSION_TIMEOUT_S:.0f}s)"
    except OSError as exc:
        return f"ERROR ({exc})"

    line = _first_non_empty_line(proc.stdout) or _first_non_empty_line(proc.stderr)
    if line:
        return line
    return f"EXIT_{proc.returncode}"


def _xilinx_path_entries() -> list[str]:
    raw = os.environ.get("PATH")
    if not raw:
        return []
    return [entry for entry in raw.split(os.pathsep) if "xilinx" in entry.lower()]


def run_hw_doctor() -> tuple[int, dict[str, Any]]:
    vitis_path = _which("vitis_hls")
    vivado_path = _which("vivado")

    tools = {
        "vitis_hls": {
            "which": vitis_path or _NOT_FOUND,
            "version": _run_version(vitis_path) if vitis_path else _NOT_FOUND,
        },
        "vivado": {
            "which": vivado_path or _NOT_FOUND,
            "version": _run_version(vivado_path) if vivado_path else _NOT_FOUND,
        },
    }

    env: dict[str, Any] = {}
    for name in ("XILINX_VIVADO", "XILINX_HLS", "LM_LICENSE_FILE"):
        value = os.environ.get(name)
        if value:
            env[name] = value
    path_entries = _xilinx_path_entries()
    if path_entries:
        env["PATH"] = path_entries

    payload = {
        "hwToolchainAvailable": bool(vitis_path or vivado_path),
        "tools": tools,
        "env": env,
    }
    return 0, payload


def render_hw_doctor_text(report: dict[str, Any]) -> str:
    lines = ["NEMA HW Doctor"]
    tools = report.get("tools", {})
    vitis = tools.get("vitis_hls", {})
    vivado = tools.get("vivado", {})

    lines.append(f"vitis_hls.which: {vitis.get('which', _NOT_FOUND)}")
    lines.append(f"vitis_hls.version: {vitis.get('version', _NOT_FOUND)}")
    lines.append(f"vivado.which: {vivado.get('which', _NOT_FOUND)}")
    lines.append(f"vivado.version: {vivado.get('version', _NOT_FOUND)}")

    env = report.get("env", {})
    for name in ("XILINX_VIVADO", "XILINX_HLS", "LM_LICENSE_FILE"):
        if name in env:
            lines.append(f"env.{name}: {env[name]}")
    if "PATH" in env:
        path_entries = env.get("PATH")
        if isinstance(path_entries, list):
            joined = os.pathsep.join(str(item) for item in path_entries)
        else:
            joined = str(path_entries)
        lines.append(f"env.PATH: {joined}")

    lines.append(f"hwToolchainAvailable: {'true' if report.get('hwToolchainAvailable') else 'false'}")
    return "\n".join(lines)
