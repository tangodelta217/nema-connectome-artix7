"""Command implementations for the scaffolded NEMA CLI."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .codegen.hls_gen import generate_hls_project
from .fixed import run_selftest as run_fixed_selftest
from .ir_validate import IRValidationError, load_ir, validate_ir
from .lowering.csr import lower_ir_to_csr
from .sim import simulate


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_ir(ir_path: Path) -> tuple[int, dict]:
    try:
        report = validate_ir(ir_path)
    except FileNotFoundError:
        return 1, {"ok": False, "error": f"file not found: {ir_path}"}
    except IRValidationError as exc:
        return 1, {"ok": False, "error": str(exc)}
    return 0, report


def run_sim(
    ir_path: Path,
    ticks: int,
    out_path: Path,
    *,
    digest_path: Path | None = None,
    seed: int = 0,
) -> tuple[int, dict]:
    code, report = check_ir(ir_path)
    if code != 0:
        return code, report
    if ticks < 0:
        return 1, {"ok": False, "error": "--ticks must be >= 0"}

    if digest_path is None:
        digest_path = out_path.with_name("digest.json")

    try:
        ir_payload, _ = load_ir(ir_path)
        sim_report = simulate(
            ir_payload,
            ticks=ticks,
            seed=seed,
            trace_path=out_path,
            base_dir=ir_path.parent,
        )
    except (FileNotFoundError, ValueError, IRValidationError) as exc:
        return 1, {"ok": False, "error": str(exc)}

    write_json(digest_path, sim_report)

    return 0, {
        "ok": True,
        "trace_path": str(out_path),
        "digest_path": str(digest_path),
        "ticks": ticks,
        "ir_sha256": report["ir_sha256"],
        "policy": sim_report["policy"],
        "last_digest_sha256": (
            sim_report["tickDigestsSha256"][-1] if sim_report["tickDigestsSha256"] else None
        ),
    }


def run_compile(ir_path: Path, outdir: Path) -> tuple[int, dict]:
    code, report = check_ir(ir_path)
    if code != 0:
        return code, report

    outdir.mkdir(parents=True, exist_ok=True)
    try:
        gen_report = generate_hls_project(ir_path=ir_path, outdir=outdir)
    except (FileNotFoundError, ValueError, IRValidationError) as exc:
        return 1, {"ok": False, "error": str(exc)}

    manifest = {
        "ok": True,
        "generator": "nema compile",
        "mode": "hls_codegen",
        "ir_sha256": gen_report["ir_sha256"],
        "model_id": gen_report["model_id"],
        "artifacts": gen_report,
    }
    manifest_path = Path(gen_report["model_root"]) / "compile_manifest.json"
    write_json(manifest_path, manifest)

    return 0, {
        "ok": True,
        "outdir": str(outdir),
        "model_id": gen_report["model_id"],
        "model_root": gen_report["model_root"],
        "hls_header": gen_report["hls_header"],
        "hls_cpp": gen_report["hls_cpp"],
        "cpp_ref_main": gen_report["cpp_ref_main"],
        "manifest": str(manifest_path),
        "ir_sha256": gen_report["ir_sha256"],
        "mode": "hls_codegen",
    }


def _detect_vitis_hls() -> dict:
    binary = shutil.which("vitis_hls")
    if not binary:
        return {
            "vitis_hls_found": False,
            "binary": None,
            "status": "unavailable",
            "detail": "vitis_hls not found on PATH",
        }

    proc = subprocess.run([binary, "-version"], check=False, capture_output=True, text=True)
    first_line = (proc.stdout or proc.stderr).splitlines()
    version_line = first_line[0] if first_line else "unknown"
    return {
        "vitis_hls_found": True,
        "binary": binary,
        "status": "available_not_invoked",
        "detail": "cosim flow scaffolded but not implemented yet",
        "version_line": version_line,
        "exit_code": proc.returncode,
    }


def run_hwtest(ir_path: Path, outdir: Path, ticks: int) -> tuple[int, dict]:
    outdir.mkdir(parents=True, exist_ok=True)

    sim_code, sim_report = run_sim(
        ir_path,
        ticks=ticks,
        out_path=outdir / "trace.jsonl",
        digest_path=outdir / "digest.json",
        seed=0,
    )
    if sim_code != 0:
        return sim_code, sim_report

    compile_code, compile_report = run_compile(ir_path, outdir=outdir)
    if compile_code != 0:
        return compile_code, compile_report

    cosim_report = _detect_vitis_hls()
    bench_report = {
        "ok": True,
        "mode": "placeholder",
        "ir_path": str(ir_path),
        "ir_sha256": sim_report["ir_sha256"],
        "ticks": ticks,
        "sim": sim_report,
        "compile": compile_report,
        "cosim": cosim_report,
        "result": "stub_complete",
    }

    bench_report_path = outdir / "bench_report.json"
    write_json(bench_report_path, bench_report)
    return 0, {
        "ok": True,
        "bench_report": str(bench_report_path),
        "mode": "placeholder",
    }


def selftest_fixed() -> tuple[int, dict]:
    report = run_fixed_selftest()
    return (0 if report["ok"] else 1), report


def dump_csr(ir_path: Path, out_path: Path) -> tuple[int, dict]:
    code, report = check_ir(ir_path)
    if code != 0:
        return code, report

    try:
        ir_payload, _ = load_ir(ir_path)
        lowered = lower_ir_to_csr(ir_payload)
    except (FileNotFoundError, ValueError, IRValidationError) as exc:
        return 1, {"ok": False, "error": str(exc)}

    write_json(out_path, lowered)
    return 0, {
        "ok": True,
        "ir_sha256": report["ir_sha256"],
        "out_path": str(out_path),
        "node_count": lowered["node_count"],
        "chemical_edge_count": lowered["chemical_edge_count"],
        "gap_edge_count": lowered["gap_edge_count"],
        "lowering_policy": lowered["loweringPolicy"],
    }
