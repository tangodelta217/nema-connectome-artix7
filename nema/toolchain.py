"""Command implementations for the scaffolded NEMA CLI."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .codegen.hls_gen import generate_hls_project
from .connectome_bundle import build_bundle_directory
from .connectome_ingest import ingest_connectome_bundle_json, verify_connectome_artifact
from .fixed import run_selftest as run_fixed_selftest
from .hw_doctor import run_hw_doctor as run_hw_doctor_command
from .hwtest import run_hwtest_pipeline
from .ir_resolve import materialize_external_bundle
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


def run_hwtest(
    ir_path: Path,
    outdir: Path,
    ticks: int,
    *,
    hw_mode: str = "auto",
    cosim_mode: str = "auto",
    vivado_part: str | None = None,
    write_bitstream: bool = False,
) -> tuple[int, dict]:
    return run_hwtest_pipeline(
        ir_path=ir_path,
        outdir=outdir,
        ticks=ticks,
        hw_mode=hw_mode,
        cosim_mode=cosim_mode,
        vivado_part=vivado_part,
        write_bitstream=write_bitstream,
    )


def run_hw_doctor() -> tuple[int, dict]:
    return run_hw_doctor_command()


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


def run_materialize_external(ir_path: Path, out_path: Path) -> tuple[int, dict]:
    try:
        report = materialize_external_bundle(ir_path=ir_path, out_path=out_path)
    except FileNotFoundError:
        return 1, {"ok": False, "error": f"file not found: {ir_path}"}
    except (IRValidationError, ValueError) as exc:
        return 1, {"ok": False, "error": str(exc)}
    return 0, report


def run_connectome_bundle_build(
    *,
    nodes_csv: Path,
    edges_csv: Path,
    out_dir: Path,
    source: str = "UNKNOWN",
    license_id: str = "UNKNOWN",
    subgraph_id: str = "default",
) -> tuple[int, dict]:
    try:
        report = build_bundle_directory(
            nodes_csv=nodes_csv,
            edges_csv=edges_csv,
            out_dir=out_dir,
            source=source,
            license_id=license_id,
            subgraph_id=subgraph_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        return 1, {"ok": False, "error": str(exc)}
    return 0, report


def run_connectome_bundle_verify(bundle_dir: Path) -> tuple[int, dict]:
    report = verify_connectome_artifact(bundle_dir)
    return (0 if report.get("ok") else 1), report


def run_connectome_ingest(
    *,
    nodes_csv: Path,
    edges_csv: Path,
    out_path: Path,
    subgraph_id: str = "default",
    license_spdx: str = "MIT",
    source_urls: list[str] | None = None,
    source_sha256: str | None = None,
    retrieved_at: str = "1970-01-01T00:00:00Z",
    schema_version: str = "0.1",
) -> tuple[int, dict]:
    try:
        report = ingest_connectome_bundle_json(
            nodes_csv=nodes_csv,
            edges_csv=edges_csv,
            out_path=out_path,
            subgraph_id=subgraph_id,
            license_spdx=license_spdx,
            source_urls=source_urls,
            source_sha256=source_sha256,
            retrieved_at=retrieved_at,
            schema_version=schema_version,
        )
    except (FileNotFoundError, ValueError) as exc:
        return 1, {"ok": False, "error": str(exc)}
    return 0, report


def run_connectome_verify(path: Path) -> tuple[int, dict]:
    report = verify_connectome_artifact(path)
    return (0 if report.get("ok") else 1), report


def _resolve_ir_path(ir_path_raw: str, *, manifest_path: Path) -> Path:
    candidate = Path(ir_path_raw)
    if candidate.is_absolute():
        return candidate
    if candidate.exists():
        return candidate
    return (manifest_path.parent / candidate).resolve()


def run_bench_verify(manifest_path: Path, *, outdir: Path | None = None) -> tuple[int, dict]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 1, {"ok": False, "error": f"manifest not found: {manifest_path}"}
    except json.JSONDecodeError as exc:
        return 1, {"ok": False, "error": f"invalid manifest JSON: {exc}"}

    if not isinstance(manifest, dict):
        return 1, {"ok": False, "error": "manifest must be a JSON object"}

    required = {"irPath", "ticks", "expectedDigests", "expectedGraphCounts", "expectedProvenance"}
    missing = sorted(k for k in required if k not in manifest)
    if missing:
        return 1, {"ok": False, "error": f"manifest missing fields: {missing}"}

    ir_raw = manifest["irPath"]
    ticks = manifest["ticks"]
    expected_digests = manifest["expectedDigests"]
    expected_counts = manifest["expectedGraphCounts"]
    expected_prov = manifest["expectedProvenance"]

    if not isinstance(ir_raw, str) or not ir_raw:
        return 1, {"ok": False, "error": "manifest.irPath must be a non-empty string"}
    if not isinstance(ticks, int) or ticks < 0:
        return 1, {"ok": False, "error": "manifest.ticks must be a non-negative integer"}
    if not isinstance(expected_digests, list) or any(not isinstance(x, str) for x in expected_digests):
        return 1, {"ok": False, "error": "manifest.expectedDigests must be a list of strings"}
    if not isinstance(expected_counts, dict):
        return 1, {"ok": False, "error": "manifest.expectedGraphCounts must be an object"}
    if not isinstance(expected_prov, dict):
        return 1, {"ok": False, "error": "manifest.expectedProvenance must be an object"}

    expected_keys_counts = ("nodeCount", "chemical", "gap", "total")
    missing_counts = [k for k in expected_keys_counts if k not in expected_counts]
    if missing_counts:
        return 1, {"ok": False, "error": f"manifest.expectedGraphCounts missing keys: {missing_counts}"}

    expected_keys_prov = ("externalVerified", "syntheticUsed")
    missing_prov = [k for k in expected_keys_prov if k not in expected_prov]
    if missing_prov:
        return 1, {"ok": False, "error": f"manifest.expectedProvenance missing keys: {missing_prov}"}

    ir_path = _resolve_ir_path(ir_raw, manifest_path=manifest_path)
    if not ir_path.exists():
        return 1, {"ok": False, "error": f"manifest irPath not found: {ir_path}"}

    if outdir is None:
        build_root = Path("build")
        build_root.mkdir(parents=True, exist_ok=True)
        verify_dir = Path(tempfile.mkdtemp(prefix="bench_verify_", dir=str(build_root.resolve())))
    else:
        verify_dir = outdir
        verify_dir.mkdir(parents=True, exist_ok=True)

    code, hwtest_summary = run_hwtest(ir_path=ir_path, outdir=verify_dir, ticks=ticks)
    if code != 0:
        return 1, {
            "ok": False,
            "error": "hwtest failed during bench verify",
            "manifest": str(manifest_path),
            "hwtest": hwtest_summary,
            "verifyOutdir": str(verify_dir),
        }

    bench_report_path_raw = hwtest_summary.get("bench_report")
    if not isinstance(bench_report_path_raw, str) or not bench_report_path_raw:
        return 1, {
            "ok": False,
            "error": "hwtest summary missing bench_report path",
            "manifest": str(manifest_path),
            "verifyOutdir": str(verify_dir),
        }
    bench_report_path = Path(bench_report_path_raw)
    if not bench_report_path.is_absolute():
        bench_report_path = (Path.cwd() / bench_report_path).resolve()

    try:
        bench_report = json.loads(bench_report_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return 1, {
            "ok": False,
            "error": f"failed to read bench_report: {exc}",
            "manifest": str(manifest_path),
            "benchReport": str(bench_report_path),
            "verifyOutdir": str(verify_dir),
        }

    actual_digests = bench_report.get("correctness", {}).get("goldenSim", {}).get("digests")
    actual_graph = bench_report.get("config", {}).get("graph", {})
    actual_prov = bench_report.get("provenance", {})

    mismatches: list[dict] = []
    if actual_digests != expected_digests:
        mismatches.append(
            {
                "field": "digests",
                "expectedCount": len(expected_digests),
                "actualCount": len(actual_digests) if isinstance(actual_digests, list) else None,
                "expectedHead": expected_digests[:3],
                "actualHead": actual_digests[:3] if isinstance(actual_digests, list) else None,
            }
        )

    mapped_actual_counts = {
        "nodeCount": actual_graph.get("nodeCount"),
        "chemical": actual_graph.get("chemicalEdgeCount"),
        "gap": actual_graph.get("gapEdgeCount"),
        "total": actual_graph.get("edgeCountTotal"),
    }
    if mapped_actual_counts != {k: expected_counts.get(k) for k in expected_keys_counts}:
        mismatches.append(
            {
                "field": "graphCounts",
                "expected": {k: expected_counts.get(k) for k in expected_keys_counts},
                "actual": mapped_actual_counts,
            }
        )

    mapped_actual_prov = {
        "externalVerified": actual_prov.get("externalVerified"),
        "syntheticUsed": actual_prov.get("syntheticUsed"),
    }
    if mapped_actual_prov != {k: expected_prov.get(k) for k in expected_keys_prov}:
        mismatches.append(
            {
                "field": "provenance",
                "expected": {k: expected_prov.get(k) for k in expected_keys_prov},
                "actual": mapped_actual_prov,
            }
        )

    digest_match_ok = bench_report.get("correctness", {}).get("digestMatch", {}).get("ok")
    if digest_match_ok is not True:
        mismatches.append(
            {
                "field": "digestMatch.ok",
                "expected": True,
                "actual": digest_match_ok,
            }
        )

    ok = len(mismatches) == 0
    return (
        0 if ok else 1,
        {
            "ok": ok,
            "manifest": str(manifest_path),
            "irPath": str(ir_path),
            "ticks": ticks,
            "benchReport": str(bench_report_path),
            "verifyOutdir": str(verify_dir),
            "mismatches": mismatches,
        },
    )
