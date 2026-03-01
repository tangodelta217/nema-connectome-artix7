#!/usr/bin/env python3
"""Run deterministic Artix-7 Vitis HLS pre-board flow."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BenchConfig:
    benchmark: str
    manifest: Path | None
    tb_cpp: Path
    fallback_ir: Path | None = None


BENCHES: dict[str, BenchConfig] = {
    "b1_small": BenchConfig(
        benchmark="b1_small",
        manifest=Path("benches/B1_small/manifest.json"),
        tb_cpp=Path("hw/tb/b1_small_tb.cpp"),
    ),
    "b2_mid_64_1024": BenchConfig(
        benchmark="b2_mid_64_1024",
        manifest=Path("benches/B2_mid/manifest.json"),
        tb_cpp=Path("hw/tb/b2_mid_64_1024_tb.cpp"),
    ),
    "b3_varshney_exec_expanded_gap_279_7284": BenchConfig(
        benchmark="b3_varshney_exec_expanded_gap_279_7284",
        manifest=None,
        tb_cpp=Path("hw/tb/b3_varshney_exec_expanded_gap_279_7284_tb.cpp"),
        fallback_ir=None,
    ),
    "b3_varshney_exec_expanded_gap_300_5824": BenchConfig(
        benchmark="b3_varshney_exec_expanded_gap_300_5824",
        manifest=Path("benches/B3_varshney_exec_expanded_gap_300_5824/manifest.json"),
        tb_cpp=Path("hw/tb/b3_varshney_exec_expanded_gap_300_5824_tb.cpp"),
        fallback_ir=None,
    ),
    "b6_delay_small": BenchConfig(
        benchmark="b6_delay_small",
        manifest=Path("benches/B6_delay_small/manifest.json"),
        tb_cpp=Path("hw/tb/b6_delay_small_tb.cpp"),
    ),
}


def _run(
    cmd: list[str],
    *,
    cwd: Path,
    activate: bool,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    if activate and Path("tools/hw/activate_xilinx.sh").exists():
        cmd_text = " ".join(shlex.quote(part) for part in cmd)
        wrapped = f"source tools/hw/activate_xilinx.sh >/dev/null 2>&1; {cmd_text}"
        return subprocess.run(
            ["bash", "-lc", wrapped],
            cwd=cwd,
            text=True,
            capture_output=True,
            env=env,
        )
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=env)


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _load_alias_entry(repo_root: Path, benchmark: str) -> tuple[Path, dict[str, Any]] | None:
    alias_path = repo_root / "benchmarks" / "aliases.json"
    if not alias_path.exists():
        return None
    try:
        payload = json.loads(alias_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    entry = payload.get(benchmark)
    if not isinstance(entry, dict):
        return None
    manifest_rel = entry.get("manifestPath")
    if not isinstance(manifest_rel, str) or not manifest_rel:
        return None
    manifest_path = (repo_root / manifest_rel).resolve()
    if not manifest_path.exists():
        return None
    return manifest_path, entry


def _resolve_ir(
    config: BenchConfig,
    *,
    repo_root: Path,
    manifest_override: Path | None,
    ir_override: Path | None,
) -> tuple[Path, Path | None, bool]:
    if ir_override is not None:
        return (repo_root / ir_override).resolve(), None, False
    if manifest_override is not None:
        manifest_path = (repo_root / manifest_override).resolve()
        payload = _load_manifest(manifest_path)
        ir_rel = payload.get("irPath")
        if not isinstance(ir_rel, str) or not ir_rel:
            raise ValueError(f"manifest {manifest_path} missing irPath")
        return (repo_root / ir_rel).resolve(), manifest_path, False
    if config.manifest is not None:
        manifest_path = (repo_root / config.manifest).resolve()
        if manifest_path.exists():
            payload = _load_manifest(manifest_path)
            ir_rel = payload.get("irPath")
            if not isinstance(ir_rel, str) or not ir_rel:
                raise ValueError(f"manifest {manifest_path} missing irPath")
            return (repo_root / ir_rel).resolve(), manifest_path, False
    alias_entry = _load_alias_entry(repo_root, config.benchmark)
    if alias_entry is not None:
        alias_manifest_path, _ = alias_entry
        payload = _load_manifest(alias_manifest_path)
        ir_rel = payload.get("irPath")
        if not isinstance(ir_rel, str) or not ir_rel:
            raise ValueError(f"alias manifest {alias_manifest_path} missing irPath")
        return (repo_root / ir_rel).resolve(), alias_manifest_path, True
    if config.fallback_ir is not None:
        return (repo_root / config.fallback_ir).resolve(), None, True
    raise ValueError(f"no IR source available for benchmark {config.benchmark}")


def _extract_manifest_expected(manifest_path: Path | None) -> tuple[list[str], str]:
    if manifest_path is None or not manifest_path.exists():
        return [], ""
    payload = _load_manifest(manifest_path)
    expected = payload.get("expectedDigests")
    if not isinstance(expected, list):
        expected_list: list[str] = []
    else:
        expected_list = [str(x).strip().lower() for x in expected if isinstance(x, str) and x.strip()]
    bench_name = payload.get("name")
    if not isinstance(bench_name, str) or not bench_name.strip():
        bench_name = manifest_path.parent.name
    return expected_list, bench_name


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Vitis HLS pre-board flow for Artix-7 benchmarks")
    parser.add_argument("--benchmark", required=True, choices=sorted(BENCHES.keys()))
    parser.add_argument("--ir", type=Path, help="override IR path")
    parser.add_argument("--manifest", type=Path, help="override manifest path")
    parser.add_argument("--outdir", type=Path, default=Path("build/artix7_hls"))
    parser.add_argument("--top", default="nema_kernel")
    parser.add_argument("--clock-ns", type=float, default=5.0)
    parser.add_argument("--part", default="xc7a200t-1sbg484c")
    parser.add_argument("--cosim", choices=("on", "off"), default="off")
    parser.add_argument("--activate-xilinx", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    os.chdir(repo_root)

    cfg = BENCHES[args.benchmark]
    outdir = (repo_root / args.outdir / args.benchmark).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    logs_dir = outdir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    ir_path, manifest_path, alias_used = _resolve_ir(
        cfg,
        repo_root=repo_root,
        manifest_override=args.manifest,
        ir_override=args.ir,
    )
    if not ir_path.exists():
        raise FileNotFoundError(f"IR not found: {ir_path}")

    tb_path = (repo_root / cfg.tb_cpp).resolve()
    if not tb_path.exists():
        raise FileNotFoundError(f"TB not found: {tb_path}")

    compile_out = outdir / "compile_out"
    compile_out.mkdir(parents=True, exist_ok=True)
    compile_cmd = [
        sys.executable,
        "-m",
        "nema",
        "compile",
        str(ir_path),
        "--outdir",
        str(compile_out),
    ]

    compile_rc = None
    compile_stdout = ""
    compile_stderr = ""
    hls_cpp = compile_out / "UNKNOWN" / "hls" / "nema_kernel.cpp"
    hls_h = compile_out / "UNKNOWN" / "hls" / "nema_kernel.h"
    model_root: Path | None = None

    if not args.dry_run:
        compile_proc = subprocess.run(compile_cmd, text=True, capture_output=True, cwd=repo_root)
        compile_rc = compile_proc.returncode
        compile_stdout = compile_proc.stdout
        compile_stderr = compile_proc.stderr
        (logs_dir / "compile.stdout.log").write_text(compile_stdout, encoding="utf-8")
        (logs_dir / "compile.stderr.log").write_text(compile_stderr, encoding="utf-8")
        if compile_proc.returncode != 0:
            summary = {
                "ok": False,
                "stage": "compile",
                "benchmark": args.benchmark,
                "ir": str(ir_path),
                "compileCommand": compile_cmd,
                "compileExitCode": compile_proc.returncode,
            }
            (outdir / "run_artix7_hls.summary.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return compile_proc.returncode
        compile_payload = json.loads(compile_stdout)
        model_root = Path(compile_payload["model_root"]).resolve()
        hls_cpp = Path(compile_payload["hls_cpp"]).resolve()
        hls_h = Path(compile_payload["hls_header"]).resolve()

    tcl_script = (repo_root / "scripts/amd/vitis_hls_artix7_preboard.tcl").resolve()
    hls_run_out = outdir / "hls_run"
    hls_run_out.mkdir(parents=True, exist_ok=True)
    expected_digests, manifest_bench_name = _extract_manifest_expected(manifest_path)
    expected_file: Path | None = None
    if expected_digests:
        expected_file = outdir / "expected_digests.txt"
        expected_file.write_text("\n".join(expected_digests) + "\n", encoding="utf-8")

    hls_cmd = [
        "vitis_hls",
        "-f",
        str(tcl_script),
        "--benchmark",
        args.benchmark,
        "--top",
        args.top,
        "--tb",
        str(tb_path),
        "--kernel-cpp",
        str(hls_cpp),
        "--kernel-h",
        str(hls_h),
        "--clock-ns",
        f"{args.clock_ns:.6f}",
        "--part",
        args.part,
        "--outdir",
        str(hls_run_out),
        "--cosim",
        args.cosim,
    ]
    hls_env = {
        "NEMA_BENCHMARK": args.benchmark,
        "NEMA_BENCH_ID": manifest_bench_name or args.benchmark,
        "NEMA_TOP": args.top,
        "NEMA_TB": str(tb_path),
        "NEMA_KERNEL_CPP": str(hls_cpp),
        "NEMA_KERNEL_H": str(hls_h),
        "NEMA_CLOCK_NS": f"{args.clock_ns:.6f}",
        "NEMA_PART": args.part,
        "NEMA_OUTDIR": str(hls_run_out),
        "NEMA_COSIM": args.cosim,
    }
    if manifest_path is not None:
        hls_env["NEMA_MANIFEST_PATH"] = str(manifest_path)
    if expected_file is not None:
        hls_env["NEMA_EXPECTED_DIGESTS_FILE"] = str(expected_file)

    hls_rc = None
    hls_stdout = ""
    hls_stderr = ""
    if not args.dry_run:
        hls_proc = _run(
            hls_cmd,
            cwd=repo_root,
            activate=args.activate_xilinx,
            extra_env=hls_env,
        )
        hls_rc = hls_proc.returncode
        hls_stdout = hls_proc.stdout
        hls_stderr = hls_proc.stderr
        (logs_dir / "vitis_hls.stdout.log").write_text(hls_stdout, encoding="utf-8")
        (logs_dir / "vitis_hls.stderr.log").write_text(hls_stderr, encoding="utf-8")

    summary = {
        "ok": bool(args.dry_run or (hls_rc == 0)),
        "dryRun": args.dry_run,
        "benchmark": args.benchmark,
        "aliasUsed": alias_used,
        "manifestPath": str(manifest_path) if manifest_path is not None else None,
        "manifestBenchName": manifest_bench_name or None,
        "irPath": str(ir_path),
        "tbPath": str(tb_path),
        "modelRoot": str(model_root) if model_root is not None else None,
        "hlsCpp": str(hls_cpp),
        "hlsHeader": str(hls_h),
        "part": args.part,
        "clockNs": args.clock_ns,
        "compileCommand": compile_cmd,
        "compileExitCode": compile_rc,
        "hlsCommand": hls_cmd,
        "hlsExitCode": hls_rc,
        "hlsOutdir": str(hls_run_out),
        "expectedDigestFile": str(expected_file) if expected_file is not None else None,
    }
    (outdir / "run_artix7_hls.summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (outdir / "run_artix7_hls.command.txt").write_text(
        "compile:\n" + " ".join(compile_cmd) + "\n\nhls:\n" + " ".join(hls_cmd) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else (hls_rc or 1)


if __name__ == "__main__":
    raise SystemExit(main())
