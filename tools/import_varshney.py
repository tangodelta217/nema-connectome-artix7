#!/usr/bin/env python3
"""Deterministic importer for Varshney/OpenWorm C. elegans connectivity.

Creates canonical NEMA assets (sidecar + IR + bench manifest + golden trace)
from a vendored raw dataset file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUESTED_BENCH = "b3_varshney_exec_expanded_gap_279_7284"
DEFAULT_RAW_URL = "https://raw.githubusercontent.com/openworm/c302/master/c302/data/herm_full_edgelist.csv"
DEFAULT_XLSX_URL = "https://raw.githubusercontent.com/openworm/c302/master/c302/data/NeuronConnectFormatted.xlsx"


@dataclass(frozen=True)
class Row:
    idx: int
    src: str
    dst: str
    kind: str
    weight: float


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_rows(path: Path, *, node_re: re.Pattern[str]) -> tuple[list[Row], dict[str, int]]:
    rows: list[Row] = []
    stats = {
        "rawRows": 0,
        "keptRows": 0,
        "droppedBadType": 0,
        "droppedNodeFilter": 0,
        "droppedParse": 0,
    }
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        cols = {c.strip() for c in (reader.fieldnames or [])}
        required = {"Source", "Target", "Weight", "Type"}
        if not required.issubset(cols):
            raise SystemExit(f"raw CSV missing required columns {sorted(required)} (got {sorted(cols)})")
        for idx, raw in enumerate(reader):
            stats["rawRows"] += 1
            try:
                src = str(raw.get("Source", "")).strip()
                dst = str(raw.get("Target", "")).strip()
                typ = str(raw.get("Type", "")).strip().lower()
                weight = abs(float(str(raw.get("Weight", "")).strip()))
            except Exception:
                stats["droppedParse"] += 1
                continue

            if typ not in {"chemical", "electrical"}:
                stats["droppedBadType"] += 1
                continue

            if not (node_re.fullmatch(src) and node_re.fullmatch(dst)):
                stats["droppedNodeFilter"] += 1
                continue

            rows.append(Row(idx=idx, src=src, dst=dst, kind=typ, weight=weight))
            stats["keptRows"] += 1

    return rows, stats


def _build_graph(rows: list[Row], *, conductance_scale: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    nodes_sorted = sorted({row.src for row in rows} | {row.dst for row in rows})
    nodes = [
        {
            "id": node_id,
            "index": i,
            "canonicalOrderId": i,
            "vInitRaw": 0,
            "tauM": 2.0,
        }
        for i, node_id in enumerate(nodes_sorted)
    ]

    chemical_rows = [row for row in rows if row.kind == "chemical"]
    chemical_rows.sort(key=lambda r: (r.src, r.dst, r.weight, r.idx))

    edges: list[dict[str, Any]] = []
    for i, row in enumerate(chemical_rows):
        edges.append(
            {
                "id": f"e_chem_{i:06d}",
                "kind": "CHEMICAL",
                "source": row.src,
                "target": row.dst,
                "directed": True,
                "conductance": round(row.weight * conductance_scale, 8),
                "weight": row.weight,
                "modelId": "CHEMICAL_CURRENT_V0",
            }
        )

    gap_pairs: dict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        if row.kind != "electrical":
            continue
        a, b = sorted((row.src, row.dst))
        gap_pairs[(a, b)] += row.weight

    for j, (a, b) in enumerate(sorted(gap_pairs.keys())):
        conductance = round(gap_pairs[(a, b)] * conductance_scale, 8)
        edges.append(
            {
                "id": f"e_gap_{j:06d}_fwd",
                "kind": "GAP",
                "source": a,
                "target": b,
                "directed": True,
                "conductance": conductance,
                "modelId": "GAP_CONDUCTANCE_V0",
            }
        )
        edges.append(
            {
                "id": f"e_gap_{j:06d}_rev",
                "kind": "GAP",
                "source": b,
                "target": a,
                "directed": True,
                "conductance": conductance,
                "modelId": "GAP_CONDUCTANCE_V0",
            }
        )

    stats = {
        "nodeCount": len(nodes),
        "chemicalEdgeCount": len(chemical_rows),
        "gapEdgeCount": len(gap_pairs),
        "gapDirectedCount": 2 * len(gap_pairs),
        "edgeCountTotal": len(edges),
    }
    return nodes, edges, stats


def _run_sim(repo_root: Path, *, ir_path: Path, ticks: int, trace_path: Path, digest_path: Path, seed: int) -> list[str]:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "nema",
        "sim",
        str(ir_path),
        "--ticks",
        str(ticks),
        "--out",
        str(trace_path),
        "--digest-out",
        str(digest_path),
        "--seed",
        str(seed),
    ]
    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(
            "nema sim failed for generated varshney IR:\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    digests: list[str] = []
    with trace_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            digest = obj.get("digestSha256")
            if isinstance(digest, str) and digest:
                digests.append(digest)
    return digests


def main() -> int:
    parser = argparse.ArgumentParser(description="Import canonical Varshney dataset into NEMA assets")
    parser.add_argument("--raw-csv", type=Path, default=Path("datasets/raw/varshney/herm_full_edgelist.csv"))
    parser.add_argument("--raw-csv-url", default=DEFAULT_RAW_URL)
    parser.add_argument("--raw-xlsx", type=Path, default=Path("datasets/raw/varshney/NeuronConnectFormatted.xlsx"))
    parser.add_argument("--raw-xlsx-url", default=DEFAULT_XLSX_URL)
    parser.add_argument("--sidecar", type=Path, default=Path("datasets/sidecars/varshney_exec_v1.json"))
    parser.add_argument("--bench-root", type=Path, default=Path("benches"))
    parser.add_argument("--ir-root", type=Path, default=Path("artifacts/ir"))
    parser.add_argument("--trace-root", type=Path, default=Path("artifacts/traces"))
    parser.add_argument("--ticks", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--node-regex", default=r"^[A-Z][A-Z0-9]*$")
    parser.add_argument("--conductance-scale", type=float, default=0.01)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    raw_csv = (repo_root / args.raw_csv).resolve()
    raw_xlsx = (repo_root / args.raw_xlsx).resolve()
    if not raw_csv.exists():
        raise SystemExit(f"raw dataset CSV not found: {raw_csv}")

    node_re = re.compile(args.node_regex)
    rows, filter_stats = _read_rows(raw_csv, node_re=node_re)
    nodes, edges, counts = _build_graph(rows, conductance_scale=args.conductance_scale)

    bench_name = f"b3_varshney_exec_expanded_gap_{counts['nodeCount']}_{counts['edgeCountTotal']}"
    model_id = f"B3_varshney_exec_expanded_gap_{counts['nodeCount']}_{counts['edgeCountTotal']}"

    sidecar_path = (repo_root / args.sidecar).resolve()
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_bench_path = (repo_root / "datasets" / "sidecars" / f"{bench_name}.json").resolve()
    sidecar_bench_path.parent.mkdir(parents=True, exist_ok=True)

    ir_root = (repo_root / args.ir_root).resolve()
    ir_root.mkdir(parents=True, exist_ok=True)
    ir_path = ir_root / f"{bench_name}.json"

    lut_path = (repo_root / "artifacts" / "luts" / "tanh_q8_8.bin").resolve()
    if not lut_path.exists():
        raise SystemExit(f"missing LUT artifact required by IR: {lut_path}")

    raw_csv_sha = _sha256_file(raw_csv)
    raw_xlsx_sha = _sha256_file(raw_xlsx) if raw_xlsx.exists() else None

    sidecar: dict[str, Any] = {
        "formatId": "nema.varshney.sidecar.v1",
        "requestedBenchmark": REQUESTED_BENCH,
        "resolvedBenchmark": bench_name,
        "source": {
            "dataset": "openworm/c302 herm_full_edgelist.csv",
            "rawCsvPath": str(raw_csv.relative_to(repo_root)),
            "rawCsvSha256": raw_csv_sha,
            "rawCsvUrl": args.raw_csv_url,
            "rawXlsxPath": str(raw_xlsx.relative_to(repo_root)) if raw_xlsx.exists() else None,
            "rawXlsxSha256": raw_xlsx_sha,
            "rawXlsxUrl": args.raw_xlsx_url,
        },
        "rules": {
            "nodeFilterRegex": args.node_regex,
            "edgeTypeMap": {
                "chemical": "CHEMICAL (directed)",
                "electrical": "GAP (aggregate undirected pairs, expand to two directed edges)",
            },
            "conductanceRule": f"conductance = abs(weight) * {args.conductance_scale}",
            "stableOrdering": {
                "nodes": "lexicographic node id",
                "chemicalEdges": "(source,target,weight,rowIndex)",
                "gapPairs": "sorted undirected pair",
            },
        },
        "filterStats": filter_stats,
        "graphCounts": counts,
        "graph": {
            "nodes": nodes,
            "edges": edges,
        },
    }

    for path in (sidecar_path, sidecar_bench_path):
        path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lut_rel_from_ir = os.path.relpath(lut_path, start=ir_path.parent)
    ir_payload: dict[str, Any] = {
        "name": f"example_{bench_name}",
        "modelId": model_id,
        "constraints": {"allowedSpdx": ["Apache-2.0", "MIT"]},
        "license": {"spdxId": "MIT"},
        "graph": {
            "stats": {
                "nodeCount": counts["nodeCount"],
                "chemicalEdgeCount": counts["chemicalEdgeCount"],
                "gapEdgeCount": counts["gapEdgeCount"],
            },
            "nodes": nodes,
            "edges": edges,
        },
        "tanhLut": {
            "policy": "nema.tanh_lut.v0.1",
            "artifact": lut_rel_from_ir,
            "inputType": "Q8.8",
            "outputType": "Q8.8",
            "checksumSha256": _sha256_file(lut_path),
        },
        "dataset": {
            "source": "openworm/c302",
            "rawCsv": str(raw_csv.relative_to(repo_root)),
            "rawCsvSha256": raw_csv_sha,
            "sidecar": str(sidecar_bench_path.relative_to(repo_root)),
        },
    }
    ir_path.write_text(json.dumps(ir_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    trace_root = (repo_root / args.trace_root).resolve()
    trace_root.mkdir(parents=True, exist_ok=True)
    trace_path = trace_root / f"{bench_name}.trace.jsonl"
    digest_path = trace_root / f"{bench_name}.digest.json"
    digests = _run_sim(
        repo_root,
        ir_path=ir_path,
        ticks=args.ticks,
        trace_path=trace_path,
        digest_path=digest_path,
        seed=args.seed,
    )

    bench_dir = (repo_root / args.bench_root / f"B3_varshney_exec_expanded_gap_{counts['nodeCount']}_{counts['edgeCountTotal']}").resolve()
    bench_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = bench_dir / "manifest.json"
    manifest = {
        "expectedDigests": digests,
        "expectedGraphCounts": {
            "chemical": counts["chemicalEdgeCount"],
            "gap": counts["gapEdgeCount"],
            "nodeCount": counts["nodeCount"],
            "total": counts["edgeCountTotal"],
        },
        "expectedProvenance": {
            "externalVerified": False,
            "syntheticUsed": False,
        },
        "irPath": str(ir_path.relative_to(repo_root)),
        "name": f"B3_varshney_exec_expanded_gap_{counts['nodeCount']}_{counts['edgeCountTotal']}",
        "ticks": args.ticks,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "ok": True,
        "requestedBenchmark": REQUESTED_BENCH,
        "resolvedBenchmark": bench_name,
        "canonicalAssetsReady": True,
        "usedAliasFallback": bench_name != REQUESTED_BENCH,
        "datasetSource": {
            "rawCsvPath": str(raw_csv.relative_to(repo_root)),
            "rawCsvSha256": raw_csv_sha,
            "rawCsvUrl": args.raw_csv_url,
            "rawXlsxPath": str(raw_xlsx.relative_to(repo_root)) if raw_xlsx.exists() else None,
            "rawXlsxSha256": raw_xlsx_sha,
        },
        "sidecarPath": str(sidecar_bench_path.relative_to(repo_root)),
        "sidecarSha256": _sha256_file(sidecar_bench_path),
        "manifestPath": str(manifest_path.relative_to(repo_root)),
        "irPath": str(ir_path.relative_to(repo_root)),
        "benchmarkNameInManifest": manifest["name"],
        "tracePath": str(trace_path.relative_to(repo_root)),
        "strictG1bEligible": True,
        "blockingReason": None,
        "graphCounts": counts,
        "filterStats": filter_stats,
        "ticks": args.ticks,
        "seed": args.seed,
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
