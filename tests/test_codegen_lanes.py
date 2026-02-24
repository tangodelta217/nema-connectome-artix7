from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _compile_ir(repo_root: Path, ir_path: Path, outdir: Path) -> dict:
    proc = subprocess.run(
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
    return json.loads(proc.stdout)


def _sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_ir_with_lanes(base_ir: Path, dst: Path, *, synapse_lanes: int, neuron_lanes: int) -> None:
    payload = json.loads(base_ir.read_text(encoding="utf-8"))
    payload["modelId"] = f"b1_lanes_{synapse_lanes}_{neuron_lanes}"
    compile_obj = payload.get("compile")
    if not isinstance(compile_obj, dict):
        compile_obj = {}
        payload["compile"] = compile_obj
    schedule_obj = compile_obj.get("schedule")
    if not isinstance(schedule_obj, dict):
        schedule_obj = {}
        compile_obj["schedule"] = schedule_obj
    schedule_obj["synapseLanes"] = synapse_lanes
    schedule_obj["neuronLanes"] = neuron_lanes
    dst.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_codegen_lanes_change_emitted_artifacts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    base_ir = repo_root / "example_b1_small_subgraph.json"

    ir_11 = tmp_path / "b1_11.json"
    ir_84 = tmp_path / "b1_84.json"
    _write_ir_with_lanes(base_ir, ir_11, synapse_lanes=1, neuron_lanes=1)
    _write_ir_with_lanes(base_ir, ir_84, synapse_lanes=8, neuron_lanes=4)

    report_11 = _compile_ir(repo_root, ir_11, tmp_path / "out11")
    report_84 = _compile_ir(repo_root, ir_84, tmp_path / "out84")

    h_11 = Path(report_11["hls_header"])
    h_84 = Path(report_84["hls_header"])
    cpp_11 = Path(report_11["hls_cpp"])
    cpp_84 = Path(report_84["hls_cpp"])

    header_11 = h_11.read_text(encoding="utf-8")
    header_84 = h_84.read_text(encoding="utf-8")
    cpp_txt_11 = cpp_11.read_text(encoding="utf-8")
    cpp_txt_84 = cpp_84.read_text(encoding="utf-8")

    assert "static constexpr int SYNAPSE_LANES = 1;" in header_11
    assert "static constexpr int NEURON_LANES = 1;" in header_11
    assert "static constexpr int SYNAPSE_LANES = 8;" in header_84
    assert "static constexpr int NEURON_LANES = 4;" in header_84

    assert "#pragma HLS UNROLL factor=1" in cpp_txt_11
    assert "#pragma HLS UNROLL factor=8" in cpp_txt_84
    assert "#pragma HLS UNROLL factor=4" in cpp_txt_84

    header_hash_11 = _sha256_text(h_11)
    header_hash_84 = _sha256_text(h_84)
    cpp_hash_11 = _sha256_text(cpp_11)
    cpp_hash_84 = _sha256_text(cpp_84)

    # At least one generated artifact must differ when lanes change.
    assert header_hash_11 != header_hash_84 or cpp_hash_11 != cpp_hash_84
