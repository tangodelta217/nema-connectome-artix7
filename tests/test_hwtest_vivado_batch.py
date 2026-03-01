from __future__ import annotations

from pathlib import Path

from nema.hwtest import CmdResult, _run_vivado_batch


def test_run_vivado_batch_impl_flow_and_fields(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "proj"
    solution_dir = project_dir / "nema_hwtest" / "sol1"
    rtl_dir = solution_dir / "syn" / "verilog"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    (rtl_dir / "nema_kernel.v").write_text("module nema_kernel; endmodule\n", encoding="utf-8")

    captured_tcl = {"text": ""}

    def fake_cmd(cmd: list[str], *, cwd: Path) -> CmdResult:
        tcl_path = Path(cmd[-1])
        captured_tcl["text"] = tcl_path.read_text(encoding="utf-8")
        util = cwd / "vivado_utilization.rpt"
        timing = cwd / "vivado_timing_summary.rpt"
        part_file = cwd / "vivado_selected_part.txt"
        util.write_text("| CLB LUTs* | 123 |\n| CLB Registers | 456 |\n| Block RAM Tile | 7 |\n| DSPs | 8 |\n", encoding="utf-8")
        timing.write_text("WNS(ns): 0.100\nTNS(ns): 0.000\n", encoding="utf-8")
        part_file.write_text("xc7z020clg400-1\n", encoding="utf-8")
        return CmdResult(
            cmd=cmd,
            cwd=str(cwd),
            returncode=0,
            stdout="ok\n",
            stderr="",
            elapsed_s=0.1,
        )

    monkeypatch.setattr("nema.hwtest._cmd", fake_cmd)

    result = _run_vivado_batch(
        vivado_info={"available": True, "binary": "/tools/Xilinx/2025.2/Vivado/bin/vivado"},
        project_dir=project_dir,
        solution_dir=solution_dir,
        part="xc7z020clg400-1",
        clock_ns="5.0",
        top_name="nema_kernel",
    )

    assert "synth_design" in captured_tcl["text"]
    assert "opt_design" in captured_tcl["text"]
    assert "place_design" in captured_tcl["text"]
    assert "route_design" in captured_tcl["text"]
    assert result["attempted"] is True
    assert result["ok"] is True
    assert result["implOk"] is True
    assert result["part"] == "xc7z020clg400-1"
    assert result["clk_ns"] == 5.0
    assert result["bitstreamPlaceholder"] is False
    assert any(str(item).endswith("vivado_utilization.rpt") for item in result["reportFiles"])
    assert any(str(item).endswith("vivado_timing_summary.rpt") for item in result["reportFiles"])


def test_run_vivado_batch_writes_bitstream_when_requested(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "proj"
    solution_dir = project_dir / "nema_hwtest" / "sol1"
    rtl_dir = solution_dir / "syn" / "verilog"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    (rtl_dir / "nema_kernel.v").write_text("module nema_kernel; endmodule\n", encoding="utf-8")

    captured_tcl = {"text": ""}

    def fake_cmd(cmd: list[str], *, cwd: Path) -> CmdResult:
        tcl_path = Path(cmd[-1])
        captured_tcl["text"] = tcl_path.read_text(encoding="utf-8")
        util = cwd / "vivado_utilization.rpt"
        timing = cwd / "vivado_timing_summary.rpt"
        bit = cwd / "nema_kernel.bit"
        part_file = cwd / "vivado_selected_part.txt"
        util.write_text("| CLB LUTs* | 123 |\n", encoding="utf-8")
        timing.write_text("WNS(ns): 0.100\n", encoding="utf-8")
        bit.write_bytes(b"BITSTREAM")
        part_file.write_text("xc7z020clg400-1\n", encoding="utf-8")
        return CmdResult(
            cmd=cmd,
            cwd=str(cwd),
            returncode=0,
            stdout="ok\n",
            stderr="",
            elapsed_s=0.1,
        )

    monkeypatch.setattr("nema.hwtest._cmd", fake_cmd)

    result = _run_vivado_batch(
        vivado_info={"available": True, "binary": "/tools/Xilinx/2025.2/Vivado/bin/vivado"},
        project_dir=project_dir,
        solution_dir=solution_dir,
        part="xc7z020clg400-1",
        clock_ns="5.0",
        write_bitstream=True,
        top_name="nema_kernel",
    )

    assert "write_bitstream -force" in captured_tcl["text"]
    assert result["ok"] is True
    assert isinstance(result["bitstreamPath"], str)
    assert result["bitstreamPath"].endswith("nema_kernel.bit")
    assert result["bitstreamPlaceholder"] is False
    assert any(str(item).endswith(".bit") for item in result["reportFiles"])


def test_run_vivado_batch_versal_device_image_fallback_creates_bit_compat(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = tmp_path / "proj"
    solution_dir = project_dir / "nema_hwtest" / "sol1"
    rtl_dir = solution_dir / "syn" / "verilog"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    (rtl_dir / "nema_kernel.v").write_text("module nema_kernel; endmodule\n", encoding="utf-8")

    captured_tcl = {"text": ""}

    def fake_cmd(cmd: list[str], *, cwd: Path) -> CmdResult:
        tcl_path = Path(cmd[-1])
        captured_tcl["text"] = tcl_path.read_text(encoding="utf-8")
        (cwd / "vivado_utilization.rpt").write_text("| CLB LUTs* | 123 |\n", encoding="utf-8")
        (cwd / "vivado_timing_summary.rpt").write_text("WNS(ns): 0.100\n", encoding="utf-8")
        (cwd / "nema_kernel.pdi").write_bytes(b"PDI_IMAGE")
        (cwd / "vivado_selected_part.txt").write_text("xcvh1742-lsva4737-1LP-e-S\n", encoding="utf-8")
        return CmdResult(
            cmd=cmd,
            cwd=str(cwd),
            returncode=0,
            stdout="ok\n",
            stderr="",
            elapsed_s=0.1,
        )

    monkeypatch.setattr("nema.hwtest._cmd", fake_cmd)

    result = _run_vivado_batch(
        vivado_info={"available": True, "binary": "/tools/Xilinx/2025.2/Vivado/bin/vivado"},
        project_dir=project_dir,
        solution_dir=solution_dir,
        part="xcvh1742-lsva4737-1LP-e-S",
        clock_ns="5.0",
        write_bitstream=True,
        top_name="nema_kernel",
    )

    assert "write_device_image -force" in captured_tcl["text"]
    assert result["ok"] is True
    assert isinstance(result["bitstreamPath"], str)
    assert result["bitstreamPath"].endswith("nema_kernel.bit")
    assert result["bitstreamPlaceholder"] is False
    assert any(str(item).endswith(".pdi") for item in result["reportFiles"])
    assert any(str(item).endswith(".bit") for item in result["reportFiles"])


def test_run_vivado_batch_placeholder_bit_when_generation_fails(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "proj"
    solution_dir = project_dir / "nema_hwtest" / "sol1"
    rtl_dir = solution_dir / "syn" / "verilog"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    (rtl_dir / "nema_kernel.v").write_text("module nema_kernel; endmodule\n", encoding="utf-8")

    def fake_cmd(cmd: list[str], *, cwd: Path) -> CmdResult:
        (cwd / "vivado_utilization.rpt").write_text("| CLB LUTs* | 123 |\n", encoding="utf-8")
        (cwd / "vivado_timing_summary.rpt").write_text("WNS(ns): 0.100\n", encoding="utf-8")
        (cwd / "vivado_selected_part.txt").write_text("xcvh1742-lsva4737-1LP-e-S\n", encoding="utf-8")
        return CmdResult(
            cmd=cmd,
            cwd=str(cwd),
            returncode=1,
            stdout="",
            stderr="bitgen failed\n",
            elapsed_s=0.1,
        )

    monkeypatch.setattr("nema.hwtest._cmd", fake_cmd)

    result = _run_vivado_batch(
        vivado_info={"available": True, "binary": "/tools/Xilinx/2025.2/Vivado/bin/vivado"},
        project_dir=project_dir,
        solution_dir=solution_dir,
        part="xcvh1742-lsva4737-1LP-e-S",
        clock_ns="5.0",
        write_bitstream=True,
        top_name="nema_kernel",
    )

    assert result["ok"] is False
    assert result["bitstreamPlaceholder"] is True
    assert isinstance(result["bitstreamPath"], str)
    bit_path = Path(result["bitstreamPath"])
    assert bit_path.exists()
    assert "NEMA_PLACEHOLDER_BITSTREAM" in bit_path.read_text(encoding="utf-8")


def test_run_vivado_batch_tcl_includes_ip_read_and_generation(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "proj"
    solution_dir = project_dir / "nema_hwtest" / "sol1"
    rtl_dir = solution_dir / "syn" / "verilog"
    ip_dir = solution_dir / "impl" / "ip" / "hdl" / "ip" / "dummy_ip"
    rtl_dir.mkdir(parents=True, exist_ok=True)
    ip_dir.mkdir(parents=True, exist_ok=True)

    (rtl_dir / "nema_kernel.v").write_text(
        "module nema_kernel(input wire clk); dummy_ip u0(); endmodule\n", encoding="utf-8"
    )
    (ip_dir / "dummy_ip.xci").write_text("<ipxact/>\n", encoding="utf-8")

    captured_tcl = {"text": ""}

    def fake_cmd(cmd: list[str], *, cwd: Path) -> CmdResult:
        tcl_path = Path(cmd[-1])
        captured_tcl["text"] = tcl_path.read_text(encoding="utf-8")
        (cwd / "vivado_utilization.rpt").write_text("| CLB LUTs* | 1 |\n", encoding="utf-8")
        (cwd / "vivado_timing_summary.rpt").write_text("WNS(ns): 0.100\n", encoding="utf-8")
        (cwd / "vivado_selected_part.txt").write_text("xc7z020clg400-1\n", encoding="utf-8")
        return CmdResult(
            cmd=cmd,
            cwd=str(cwd),
            returncode=0,
            stdout="ok\n",
            stderr="",
            elapsed_s=0.1,
        )

    monkeypatch.setattr("nema.hwtest._cmd", fake_cmd)

    result = _run_vivado_batch(
        vivado_info={"available": True, "binary": "/tools/Xilinx/2025.2/Vivado/bin/vivado"},
        project_dir=project_dir,
        solution_dir=solution_dir,
        part="xc7z020clg400-1",
        clock_ns="5.0",
        top_name="nema_kernel",
    )

    tcl_text = captured_tcl["text"]
    assert "set ip_xci [glob -nocomplain -types f" in tcl_text
    assert "foreach ip $ip_xci { read_ip $ip }" in tcl_text
    assert "generate_target all [get_files -all -quiet *.xci]" in tcl_text
    assert "catch { synth_ip [get_ips -all] }" in tcl_text
    assert "set_property ip_repo_paths $ip_repo_dirs [current_project]" in tcl_text
    assert "detected *_ip instance but no .xci files were found" in tcl_text
    assert "read_verilog" in tcl_text
    assert "read_ip" in tcl_text
    assert result["ok"] is True


def test_run_vivado_batch_precondition_fails_when_ip_instances_without_xci(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = tmp_path / "proj"
    solution_dir = project_dir / "nema_hwtest" / "sol1"
    syn_dir = solution_dir / "syn" / "verilog"
    syn_dir.mkdir(parents=True, exist_ok=True)
    (syn_dir / "nema_kernel.v").write_text(
        "module nema_kernel(); missing_block_ip u0(); endmodule\n", encoding="utf-8"
    )

    called = {"cmd": False}

    def fake_cmd(cmd: list[str], *, cwd: Path) -> CmdResult:
        called["cmd"] = True
        return CmdResult(
            cmd=cmd,
            cwd=str(cwd),
            returncode=0,
            stdout="ok\n",
            stderr="",
            elapsed_s=0.1,
        )

    monkeypatch.setattr("nema.hwtest._cmd", fake_cmd)

    result = _run_vivado_batch(
        vivado_info={"available": True, "binary": "/tools/Xilinx/2025.2/Vivado/bin/vivado"},
        project_dir=project_dir,
        solution_dir=solution_dir,
        part="xc7z020clg400-1",
        clock_ns="5.0",
        top_name="nema_kernel",
    )

    assert called["cmd"] is False
    assert result["attempted"] is False
    assert result["skipped"] is True
    assert result["ok"] is False
    assert isinstance(result["reason"], str)
    assert "HLS export incomplete" in result["reason"]
