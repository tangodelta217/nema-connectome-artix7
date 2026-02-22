"""Environment diagnostics for NEMA hardware toolchain availability."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

_VERSION_TIMEOUT_S = 3.0
_LIBTINFO_PATHS = (
    "/usr/lib/x86_64-linux-gnu/libtinfo.so.5",
    "/lib/x86_64-linux-gnu/libtinfo.so.5",
)


def _which(binary: str) -> str | None:
    return shutil.which(binary)


def _path_exists(path: str) -> bool:
    return Path(path).exists()


def _first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _run_version(binary_path: str | None) -> str | None:
    if not binary_path:
        return None
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


def _read_os_release() -> tuple[str | None, str | None]:
    path = Path("/etc/os-release")
    if not path.exists():
        return None, None
    data: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            token = value.strip().strip('"').strip("'")
            data[key] = token
    except OSError:
        return None, None
    return data.get("ID"), data.get("VERSION_ID")


def _kernel_release() -> str:
    try:
        return os.uname().release
    except OSError:
        return "UNKNOWN"


def _detect_libtinfo_so_5() -> dict[str, Any]:
    checked = list(_LIBTINFO_PATHS)
    present = any(_path_exists(path) for path in checked)
    return {
        "libtinfo_so_5": {
            "present": present,
            "checked_paths": checked,
        }
    }


def run_hw_doctor() -> tuple[int, dict[str, Any]]:
    os_id, version_id = _read_os_release()
    kernel_release = _kernel_release()

    vivado_path = _which("vivado")
    vitis_hls_path = _which("vitis_hls")
    vivado_found = vivado_path is not None
    vitis_hls_found = vitis_hls_path is not None
    hw_available = bool(vivado_found or vitis_hls_found)

    libs = _detect_libtinfo_so_5()
    has_libtinfo = bool(libs["libtinfo_so_5"]["present"])

    xilinxd_set = bool(os.environ.get("XILINXD_LICENSE_FILE"))
    lm_set = bool(os.environ.get("LM_LICENSE_FILE"))

    warnings: list[str] = []
    if os_id == "ubuntu" and version_id == "24.04" and not kernel_release.startswith("6.8."):
        warnings.append(
            "Ubuntu 24.04 detected with kernel != 6.8.*; AMD tested-kernel lists for 24.04 focus on 6.8.x (warning only)."
        )
    if not has_libtinfo:
        warnings.append(
            "libtinfo.so.5 not found; instalar libtinfo5 (Ubuntu 24.04) o revisar docs/HW_SETUP_UBUNTU24.md."
        )
    if not xilinxd_set and not lm_set:
        warnings.append(
            "No Xilinx license env var set; puede ser OK si licencia está en ~/.Xilinx, pero si Vivado falla al arrancar setear XILINXD_LICENSE_FILE."
        )
    if not hw_available:
        warnings.append("Toolchain not found in PATH (vivado/vitis_hls).")

    payload = {
        "os": {
            "id": os_id,
            "version_id": version_id,
        },
        "kernel": {
            "release": kernel_release,
        },
        "libs": libs,
        "license": {
            "xilinxd_license_file_set": xilinxd_set,
            "lm_license_file_set": lm_set,
        },
        "toolchain": {
            "vivado_found": vivado_found,
            "vitis_hls_found": vitis_hls_found,
            "vivado_path": vivado_path,
            "vitis_hls_path": vitis_hls_path,
            "vivado_version": _run_version(vivado_path),
            "vitis_hls_version": _run_version(vitis_hls_path),
        },
        "warnings": warnings,
        # Backward compatibility with existing scripts.
        "hwToolchainAvailable": hw_available,
    }
    return 0, payload


def render_hw_doctor_text(report: dict[str, Any]) -> str:
    os_info = report.get("os", {})
    kernel = report.get("kernel", {})
    libs = report.get("libs", {}).get("libtinfo_so_5", {})
    license_info = report.get("license", {})
    toolchain = report.get("toolchain", {})
    warnings = report.get("warnings", [])

    lines = ["NEMA HW Doctor"]
    lines.append(f"os.id: {os_info.get('id')}")
    lines.append(f"os.version_id: {os_info.get('version_id')}")
    lines.append(f"kernel.release: {kernel.get('release')}")
    lines.append(f"libs.libtinfo_so_5.present: {libs.get('present')}")
    lines.append(f"libs.libtinfo_so_5.checked_paths: {libs.get('checked_paths')}")
    lines.append(f"license.xilinxd_license_file_set: {license_info.get('xilinxd_license_file_set')}")
    lines.append(f"license.lm_license_file_set: {license_info.get('lm_license_file_set')}")
    lines.append(f"toolchain.vivado_found: {toolchain.get('vivado_found')}")
    lines.append(f"toolchain.vivado_path: {toolchain.get('vivado_path')}")
    lines.append(f"toolchain.vivado_version: {toolchain.get('vivado_version')}")
    lines.append(f"toolchain.vitis_hls_found: {toolchain.get('vitis_hls_found')}")
    lines.append(f"toolchain.vitis_hls_path: {toolchain.get('vitis_hls_path')}")
    lines.append(f"toolchain.vitis_hls_version: {toolchain.get('vitis_hls_version')}")
    lines.append(f"hwToolchainAvailable: {'true' if report.get('hwToolchainAvailable') else 'false'}")
    if isinstance(warnings, list) and warnings:
        lines.append("warnings:")
        for item in warnings:
            lines.append(f"  - {item}")
    return "\n".join(lines)
