from __future__ import annotations

from pathlib import Path

from nema.hwtest import CmdResult, _empty_vivado_result, _run_vitis_hls


def test_run_vitis_hls_captures_reports_and_paths(tmp_path: Path, monkeypatch) -> None:
    model_root = tmp_path / "model"
    hls_cpp = model_root / "hls" / "nema_kernel.cpp"
    cpp_ref_main = model_root / "cpp_ref" / "main.cpp"
    hls_cpp.parent.mkdir(parents=True, exist_ok=True)
    cpp_ref_main.parent.mkdir(parents=True, exist_ok=True)
    hls_cpp.write_text("// hls kernel\n", encoding="utf-8")
    cpp_ref_main.write_text("// tb\n", encoding="utf-8")

    def fake_cmd(cmd: list[str], *, cwd: Path) -> CmdResult:
        project_dir = Path(cwd)
        solution = project_dir / "nema_hwtest" / "sol1"
        (solution / "syn" / "report").mkdir(parents=True, exist_ok=True)
        (solution / "sim" / "report").mkdir(parents=True, exist_ok=True)
        (solution / "syn" / "report" / "csynth.rpt").write_text("csynth report\n", encoding="utf-8")
        (solution / "syn" / "report" / "csynth.xml").write_text("<report />\n", encoding="utf-8")
        (solution / "sim" / "report" / "csim.log").write_text("csim log\n", encoding="utf-8")
        (project_dir / "run_hls.log").write_text("run log\n", encoding="utf-8")
        return CmdResult(
            cmd=cmd,
            cwd=str(project_dir),
            returncode=0,
            stdout="ok\n",
            stderr="",
            elapsed_s=0.01,
        )

    monkeypatch.setattr("nema.hwtest._cmd", fake_cmd)
    monkeypatch.setattr(
        "nema.hwtest._detect_vitis_hls",
        lambda: {"available": True, "binary": "/tools/vitis_hls", "version": "Vitis HLS 2025.1"},
    )

    hardware = _run_vitis_hls(
        vitis_binary="/tools/vitis_hls",
        vivado_info={
            "available": False,
            "binary": None,
            "version": None,
        },
        hls_cpp=hls_cpp,
        cpp_ref_main=cpp_ref_main,
        model_root=model_root,
        run_cosim=False,
    )

    assert hardware["toolchain"]["available"] is True
    assert hardware["project"] == str(model_root / "hls_proj")
    assert hardware["csim"]["ok"] is True
    assert hardware["csynth"]["ok"] is True
    assert hardware["cosim"]["attempted"] is False
    assert hardware["cosim"]["ok"] is None

    reports = hardware["reports"]
    assert isinstance(reports, dict)
    assert reports["directory"] == "hw_reports"
    files = reports["files"]
    assert isinstance(files, list)
    assert any(item.endswith(".rpt") for item in files)
    assert any(item.endswith(".xml") for item in files)
    assert any(item.endswith(".log") for item in files)
    assert all(not Path(item).is_absolute() for item in files)
    for rel in files:
        assert (model_root / rel).exists()


def test_run_vitis_hls_marks_cosim_attempted_when_enabled(tmp_path: Path, monkeypatch) -> None:
    model_root = tmp_path / "model"
    hls_cpp = model_root / "hls" / "nema_kernel.cpp"
    cpp_ref_main = model_root / "cpp_ref" / "main.cpp"
    hls_cpp.parent.mkdir(parents=True, exist_ok=True)
    cpp_ref_main.parent.mkdir(parents=True, exist_ok=True)
    hls_cpp.write_text("// hls kernel\n", encoding="utf-8")
    cpp_ref_main.write_text("// tb\n", encoding="utf-8")

    def fake_cmd(cmd: list[str], *, cwd: Path) -> CmdResult:
        project_dir = Path(cwd)
        solution = project_dir / "nema_hwtest" / "sol1"
        (solution / "syn" / "report").mkdir(parents=True, exist_ok=True)
        (solution / "sim" / "report").mkdir(parents=True, exist_ok=True)
        (solution / "syn" / "report" / "csynth.rpt").write_text("csynth report\n", encoding="utf-8")
        (solution / "syn" / "report" / "csynth.xml").write_text("<report />\n", encoding="utf-8")
        (solution / "sim" / "report" / "csim.log").write_text("csim log\n", encoding="utf-8")
        return CmdResult(
            cmd=cmd,
            cwd=str(project_dir),
            returncode=0,
            stdout="ok\n",
            stderr="",
            elapsed_s=0.02,
        )

    monkeypatch.setattr("nema.hwtest._cmd", fake_cmd)
    monkeypatch.setattr(
        "nema.hwtest._detect_vitis_hls",
        lambda: {"available": True, "binary": "/tools/vitis_hls", "version": "Vitis HLS 2025.1"},
    )

    hardware = _run_vitis_hls(
        vitis_binary="/tools/vitis_hls",
        vivado_info={
            "available": False,
            "binary": None,
            "version": None,
        },
        hls_cpp=hls_cpp,
        cpp_ref_main=cpp_ref_main,
        model_root=model_root,
        run_cosim=True,
    )

    assert hardware["cosim"]["attempted"] is True
    assert hardware["cosim"]["ok"] is True
    assert hardware["cosim"]["skipped"] is False


def test_run_vitis_hls_forces_b3_export_retry_when_impl_ip_missing(tmp_path: Path, monkeypatch) -> None:
    model_root = tmp_path / "B3_kernel_302_7500"
    hls_cpp = model_root / "hls" / "nema_kernel.cpp"
    cpp_ref_main = model_root / "cpp_ref" / "main.cpp"
    hls_cpp.parent.mkdir(parents=True, exist_ok=True)
    cpp_ref_main.parent.mkdir(parents=True, exist_ok=True)
    hls_cpp.write_text("// hls kernel\n", encoding="utf-8")
    cpp_ref_main.write_text("// tb\n", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_cmd(cmd: list[str], *, cwd: Path) -> CmdResult:
        calls.append(cmd)
        project_dir = Path(cwd)
        solution = project_dir / "nema_hwtest" / "sol1"
        (solution / "syn" / "report").mkdir(parents=True, exist_ok=True)
        (solution / "sim" / "report").mkdir(parents=True, exist_ok=True)
        (solution / "syn" / "report" / "csynth.rpt").write_text("csynth report\n", encoding="utf-8")
        (solution / "syn" / "report" / "csynth.xml").write_text("<report />\n", encoding="utf-8")
        (solution / "sim" / "report" / "csim.log").write_text("csim log\n", encoding="utf-8")
        if str(cmd[-1]).endswith("run_hls_export_retry.tcl"):
            (solution / "impl" / "ip" / "hdl" / "ip" / "dummy").mkdir(parents=True, exist_ok=True)
            (solution / "impl" / "ip" / "hdl" / "ip" / "dummy" / "dummy.xci").write_text(
                "<ipxact/>\n", encoding="utf-8"
            )
            (solution / "syn" / "verilog").mkdir(parents=True, exist_ok=True)
            (solution / "syn" / "verilog" / "nema_kernel.v").write_text(
                "module nema_kernel; endmodule\n", encoding="utf-8"
            )
        return CmdResult(
            cmd=cmd,
            cwd=str(project_dir),
            returncode=0,
            stdout="ok\n",
            stderr="",
            elapsed_s=0.02,
        )

    monkeypatch.setattr("nema.hwtest._cmd", fake_cmd)
    monkeypatch.setattr(
        "nema.hwtest._detect_vitis_hls",
        lambda: {"available": True, "binary": "/tools/vitis_hls", "version": "Vitis HLS 2025.1"},
    )
    monkeypatch.setattr(
        "nema.hwtest._run_vivado_batch",
        lambda **kwargs: _empty_vivado_result("vivado unavailable", requested_part=kwargs.get("part")),
    )

    _run_vitis_hls(
        vitis_binary="/tools/vitis_hls",
        vivado_info={
            "available": True,
            "binary": "/tools/vivado",
            "version": "Vivado 2025.2",
        },
        hls_cpp=hls_cpp,
        cpp_ref_main=cpp_ref_main,
        model_root=model_root,
        run_cosim=False,
    )

    assert len(calls) >= 2
    assert str(calls[0][-1]).endswith("run_hls.tcl")
    assert str(calls[1][-1]).endswith("run_hls_export_retry.tcl")
