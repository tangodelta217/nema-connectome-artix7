from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_toolchain_scripts_exist_and_executable() -> None:
    scripts = [
        Path("tools/hw/activate_xilinx.sh"),
        Path("tools/run_hw_gates.sh"),
        Path("tools/run_hw_gates_two_parts.sh"),
        Path("tools/hw/smoke_toolchain.sh"),
        Path("tools/fpga/deploy_bitstream.sh"),
    ]
    for script in scripts:
        assert script.exists(), f"missing script: {script}"
        assert os.access(script, os.X_OK), f"script is not executable: {script}"


def test_activate_xilinx_warns_when_wrapper_missing(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fake_settings = tmp_path / "fake_settings64.sh"
    fake_settings.write_text("#!/usr/bin/env bash\nexport PATH=/usr/bin:/bin\n", encoding="utf-8")
    fake_settings.chmod(0o755)

    fake_home = tmp_path / "home"
    (fake_home / ".local" / "bin").mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["XILINX_SETTINGS64"] = str(fake_settings)

    proc = subprocess.run(
        ["bash", "-lc", "source tools/hw/activate_xilinx.sh"],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    warning_line = (
        "activate_xilinx.sh: WARNING: vitis_hls not found in PATH after activation. "
        "hint: bash tools/hw/install_wrappers.sh"
    )
    matching = [line for line in proc.stderr.splitlines() if "vitis_hls not found in PATH after activation" in line]
    assert matching == [warning_line]
