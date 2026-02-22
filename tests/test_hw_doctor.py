from __future__ import annotations

import json

from nema.cli import main
from nema.hw_doctor import run_hw_doctor


def test_hw_doctor_reports_unavailable_when_toolchain_missing(monkeypatch) -> None:
    monkeypatch.setattr("nema.hw_doctor._which", lambda _name: None)
    monkeypatch.delenv("XILINX_VIVADO", raising=False)
    monkeypatch.delenv("XILINX_HLS", raising=False)
    monkeypatch.delenv("LM_LICENSE_FILE", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    code, payload = run_hw_doctor()

    assert code == 0
    assert payload["hwToolchainAvailable"] is False
    assert payload["tools"]["vitis_hls"]["which"] == "NOT_FOUND"
    assert payload["tools"]["vitis_hls"]["version"] == "NOT_FOUND"
    assert payload["tools"]["vivado"]["which"] == "NOT_FOUND"
    assert payload["tools"]["vivado"]["version"] == "NOT_FOUND"


def test_hw_doctor_json_snapshot_is_stable(monkeypatch, capsys) -> None:
    class _Proc:
        def __init__(self, *, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_which(name: str) -> str | None:
        if name == "vitis_hls":
            return "/opt/Xilinx/Vitis_HLS/2025.1/bin/vitis_hls"
        if name == "vivado":
            return "/opt/Xilinx/Vivado/2025.1/bin/vivado"
        return None

    def fake_run(cmd, check, capture_output, text, timeout):  # noqa: ANN001
        assert check is False
        assert capture_output is True
        assert text is True
        assert timeout == 3.0
        if cmd[0].endswith("vitis_hls"):
            return _Proc(returncode=0, stdout="Vitis HLS 2025.1\nBuild 000\n")
        if cmd[0].endswith("vivado"):
            return _Proc(returncode=0, stdout="Vivado v2025.1 (64-bit)\nBuild 000\n")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("nema.hw_doctor._which", fake_which)
    monkeypatch.setattr("nema.hw_doctor.subprocess.run", fake_run)
    monkeypatch.setenv("XILINX_VIVADO", "/opt/Xilinx/Vivado/2025.1")
    monkeypatch.setenv("XILINX_HLS", "/opt/Xilinx/Vitis_HLS/2025.1")
    monkeypatch.setenv("LM_LICENSE_FILE", "27000@licenseserver")
    monkeypatch.setenv("PATH", "/usr/bin:/opt/Xilinx/Vivado/2025.1/bin:/opt/xilinx/Vitis_HLS/2025.1/bin")

    code = main(["hw", "doctor", "--format", "json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    rendered = json.dumps(payload, indent=2, sort_keys=True)

    assert rendered == (
        '{\n'
        '  "env": {\n'
        '    "LM_LICENSE_FILE": "27000@licenseserver",\n'
        '    "PATH": [\n'
        '      "/opt/Xilinx/Vivado/2025.1/bin",\n'
        '      "/opt/xilinx/Vitis_HLS/2025.1/bin"\n'
        "    ],\n"
        '    "XILINX_HLS": "/opt/Xilinx/Vitis_HLS/2025.1",\n'
        '    "XILINX_VIVADO": "/opt/Xilinx/Vivado/2025.1"\n'
        "  },\n"
        '  "hwToolchainAvailable": true,\n'
        '  "tools": {\n'
        '    "vitis_hls": {\n'
        '      "version": "Vitis HLS 2025.1",\n'
        '      "which": "/opt/Xilinx/Vitis_HLS/2025.1/bin/vitis_hls"\n'
        "    },\n"
        '    "vivado": {\n'
        '      "version": "Vivado v2025.1 (64-bit)",\n'
        '      "which": "/opt/Xilinx/Vivado/2025.1/bin/vivado"\n'
        "    }\n"
        "  }\n"
        "}"
    )
