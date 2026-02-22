from __future__ import annotations

import json

import pytest

from nema.cli import main
from nema.hw_doctor import run_hw_doctor


def test_hw_doctor_json_absent_toolchain_has_stable_keys(monkeypatch, capsys) -> None:
    monkeypatch.setattr("nema.hw_doctor._which", lambda _name: None)
    monkeypatch.setattr("nema.hw_doctor._path_exists", lambda _path: False)
    monkeypatch.setattr("nema.hw_doctor._read_os_release", lambda: ("ubuntu", "24.04"))
    monkeypatch.setattr("nema.hw_doctor._kernel_release", lambda: "6.8.0-31-generic")
    monkeypatch.delenv("XILINXD_LICENSE_FILE", raising=False)
    monkeypatch.delenv("LM_LICENSE_FILE", raising=False)

    code = main(["hw", "doctor", "--format", "json"])
    assert code == 0

    payload = json.loads(capsys.readouterr().out)
    assert set(payload.keys()) == {
        "hwToolchainAvailable",
        "kernel",
        "libs",
        "license",
        "os",
        "toolchain",
        "warnings",
    }
    assert payload["os"] == {"id": "ubuntu", "version_id": "24.04"}
    assert payload["kernel"] == {"release": "6.8.0-31-generic"}
    assert payload["toolchain"]["vivado_found"] is False
    assert payload["toolchain"]["vitis_hls_found"] is False
    assert payload["toolchain"]["vivado_path"] is None
    assert payload["toolchain"]["vitis_hls_path"] is None
    assert payload["hwToolchainAvailable"] is False
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    assert any("Toolchain not found in PATH" in item for item in warnings)


@pytest.mark.parametrize(
    ("present_path", "expected"),
    [
        (None, False),
        ("/usr/lib/x86_64-linux-gnu/libtinfo.so.5", True),
    ],
)
def test_hw_doctor_libtinfo_detection(monkeypatch, present_path: str | None, expected: bool) -> None:
    monkeypatch.setattr("nema.hw_doctor._which", lambda _name: None)
    monkeypatch.setattr("nema.hw_doctor._read_os_release", lambda: ("ubuntu", "24.04"))
    monkeypatch.setattr("nema.hw_doctor._kernel_release", lambda: "6.8.0-31-generic")
    monkeypatch.delenv("XILINXD_LICENSE_FILE", raising=False)
    monkeypatch.delenv("LM_LICENSE_FILE", raising=False)

    def fake_exists(path: str) -> bool:
        return present_path is not None and path == present_path

    monkeypatch.setattr("nema.hw_doctor._path_exists", fake_exists)

    code, payload = run_hw_doctor()
    assert code == 0
    lib_info = payload["libs"]["libtinfo_so_5"]
    assert lib_info["present"] is expected
    assert lib_info["checked_paths"] == [
        "/usr/lib/x86_64-linux-gnu/libtinfo.so.5",
        "/lib/x86_64-linux-gnu/libtinfo.so.5",
    ]
