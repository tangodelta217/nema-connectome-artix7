from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_b1_cpp_harness_matches_python_digest(tmp_path: Path) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    repo_root = Path(__file__).resolve().parents[1]
    ir_path = repo_root / "example_b1_small_subgraph.json"
    trace_path = tmp_path / "trace.jsonl"
    digest_path = tmp_path / "digest.json"
    outdir = tmp_path / "build"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "sim",
            str(ir_path),
            "--ticks",
            "8",
            "--out",
            str(trace_path),
            "--digest-out",
            str(digest_path),
            "--seed",
            "0",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    py_report = json.loads(digest_path.read_text(encoding="utf-8"))
    expected_digests = py_report["tickDigestsSha256"]

    compile_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "compile",
            str(ir_path),
            "--outdir",
            str(outdir),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    compile_report = json.loads(compile_proc.stdout)
    hls_cpp = Path(compile_report["hls_cpp"])
    cpp_ref_main = Path(compile_report["cpp_ref_main"])
    exe_path = tmp_path / "b1_cpp_ref"

    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-O2",
            str(cpp_ref_main),
            str(hls_cpp),
            "-o",
            str(exe_path),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    run_proc = subprocess.run(
        [str(exe_path), "8"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    cpp_report = json.loads(run_proc.stdout)

    assert cpp_report["tickDigestsSha256"] == expected_digests


def test_b6_delay_cpp_harness_matches_python_digest(tmp_path: Path) -> None:
    if shutil.which("g++") is None:
        pytest.skip("g++ not available")

    repo_root = Path(__file__).resolve().parents[1]
    ir_path = repo_root / "example_b6_delay_small.json"
    trace_path = tmp_path / "trace_b6.jsonl"
    digest_path = tmp_path / "digest_b6.json"
    outdir = tmp_path / "build_b6"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "sim",
            str(ir_path),
            "--ticks",
            "12",
            "--out",
            str(trace_path),
            "--digest-out",
            str(digest_path),
            "--seed",
            "0",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    py_report = json.loads(digest_path.read_text(encoding="utf-8"))
    expected_digests = py_report["tickDigestsSha256"]

    compile_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "nema",
            "compile",
            str(ir_path),
            "--outdir",
            str(outdir),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    compile_report = json.loads(compile_proc.stdout)
    hls_cpp = Path(compile_report["hls_cpp"])
    cpp_ref_main = Path(compile_report["cpp_ref_main"])
    exe_path = tmp_path / "b6_cpp_ref"

    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-O2",
            str(cpp_ref_main),
            str(hls_cpp),
            "-o",
            str(exe_path),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    run_proc = subprocess.run(
        [str(exe_path), "12"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    cpp_report = json.loads(run_proc.stdout)

    assert cpp_report["tickDigestsSha256"] == expected_digests
