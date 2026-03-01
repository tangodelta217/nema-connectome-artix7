from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_amd_tcl_scripts_have_required_hooks() -> None:
    root = _repo_root()
    hls_tcl = (root / "scripts/amd/vitis_hls_artix7_preboard.tcl").read_text(encoding="utf-8")
    viv_tcl = (root / "scripts/amd/vivado_artix7_impl_power.tcl").read_text(encoding="utf-8")

    assert "--benchmark" in hls_tcl
    assert "--top" in hls_tcl
    assert "--tb" in hls_tcl
    assert "csim_design" in hls_tcl
    assert "csynth_design" in hls_tcl
    assert "set_part" in hls_tcl

    assert "--benchmark" in viv_tcl
    assert "--top" in viv_tcl
    assert "--tb" in viv_tcl
    assert "read_ip" in viv_tcl
    assert "generate_target all" in viv_tcl
    assert "report_timing_summary" in viv_tcl
    assert "report_power" in viv_tcl


def test_run_artix7_hls_dry_run_generates_summary() -> None:
    root = _repo_root()
    outdir = root / "build" / "test_artix7_hls_dry"
    cmd = [
        sys.executable,
        "scripts/amd/run_artix7_hls.py",
        "--benchmark",
        "b1_small",
        "--outdir",
        str(outdir),
        "--dry-run",
    ]
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["dryRun"] is True
    assert payload["benchmark"] == "b1_small"
    assert payload["tbPath"].endswith("hw/tb/b1_small_tb.cpp")
    summary_path = outdir / "b1_small" / "run_artix7_hls.summary.json"
    assert summary_path.exists()


def test_run_artix7_impl_dry_run_generates_summary(tmp_path: Path) -> None:
    root = _repo_root()
    sol = tmp_path / "hls_root" / "hls_run" / "hls_proj" / "nema_hls_prj" / "sol1" / "syn" / "verilog"
    sol.mkdir(parents=True, exist_ok=True)
    (sol / "nema_kernel.v").write_text("module nema_kernel(input ap_clk); endmodule\n", encoding="utf-8")

    cmd = [
        sys.executable,
        "scripts/amd/run_artix7_impl.py",
        "--benchmark",
        "b1_small",
        "--hls-root",
        str(tmp_path / "hls_root"),
        "--outdir",
        str(tmp_path / "impl_out"),
        "--dry-run",
    ]
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["dryRun"] is True
    assert payload["benchmark"] == "b1_small"
    assert payload["rtlGlob"].endswith("syn/verilog/*.v")
