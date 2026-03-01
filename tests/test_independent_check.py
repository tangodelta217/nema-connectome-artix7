from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _digest_for_vraw(values: list[int]) -> str:
    packed = b"".join(int(v).to_bytes(2, byteorder="little", signed=True) for v in values)
    return hashlib.sha256(packed).hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _create_minimal_artifact(tmp_path: Path, *, corrupt_first_golden_digest: bool = False) -> Path:
    run_dir = tmp_path / "run"
    golden_dir = run_dir / "golden"
    reports_dir = run_dir / "hw_reports"
    golden_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    ticks = [
        {"tick": 0, "vRawByIndex": [1, -2, 3]},
        {"tick": 1, "vRawByIndex": [4, -5, 6]},
    ]

    digests: list[str] = []
    trace_lines: list[str] = []
    for item in ticks:
        digest = _digest_for_vraw(item["vRawByIndex"])
        digests.append(digest)
        trace_lines.append(
            json.dumps(
                {
                    "tick": item["tick"],
                    "vRawByIndex": item["vRawByIndex"],
                    "digestSha256": digest,
                }
            )
        )

    (golden_dir / "trace.jsonl").write_text("\n".join(trace_lines) + "\n", encoding="utf-8")
    _write_json(golden_dir / "digest.json", {"tickDigestsSha256": digests, "ticks": 2})

    (reports_dir / "csynth.rpt").write_text(
        """
== Performance Estimates
Latency (cycles)
| min | max |
| 100 | 100 |
Interval-min 2
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (reports_dir / "vivado_timing_summary.rpt").write_text(
        "WNS(ns): 0.500\nTNS(ns): 0.000\n",
        encoding="utf-8",
    )
    (reports_dir / "vivado_utilization.rpt").write_text(
        "| CLB LUTs | 123 |\n| CLB Registers | 456 |\n",
        encoding="utf-8",
    )

    golden_digests = list(digests)
    if corrupt_first_golden_digest:
        golden_digests[0] = "0" * 64

    bench_report = {
        "ok": True,
        "modelId": "test_model",
        "bench": {"targetId": "CE/2-1"},
        "createdAt": "2026-02-27T00:00:00Z",
        "config": {
            "schedule": {
                "policy": "nema.tick.v0.1",
                "snapshotRule": True,
                "evalOrder": "index",
                "synapseLanes": 1,
                "neuronLanes": 1,
            }
        },
        "correctness": {
            "goldenSim": {
                "ok": True,
                "digests": golden_digests,
                "digestPath": "golden/digest.json",
                "tracePath": "golden/trace.jsonl",
                "error": None,
            },
            "cppReference": {
                "ok": True,
                "digests": digests,
                "binaryPath": None,
                "error": None,
            },
            "digestMatch": {"ok": not corrupt_first_golden_digest, "mismatchTick": 0 if corrupt_first_golden_digest else None},
        },
        "hardware": {
            "toolchain": {"available": False},
            "reports": {
                "files": [
                    "hw_reports/csynth.rpt",
                    "hw_reports/vivado_timing_summary.rpt",
                    "hw_reports/vivado_utilization.rpt",
                ]
            },
            "qor": {
                "ii": 2,
                "latencyCycles": 100,
                "timingOrLatency": {"ii": 2, "latencyCycles": 100},
                "utilization": {"lut": 123, "ff": 456, "bram": None, "dsp": None},
            },
            "vivado": {
                "wns": 0.5,
                "timing": {"wns": 0.5},
                "utilization": {"lut": 123, "ff": 456, "bram": None, "dsp": None},
                "util": {"lut": 123, "ff": 456, "bram": None, "dsp": None},
                "timingReport": "hw_reports/vivado_timing_summary.rpt",
                "utilizationReport": "hw_reports/vivado_utilization.rpt",
            },
            "csim": {"ok": True},
            "csynth": {"ok": True},
            "cosim": {"attempted": False, "ok": None, "skipped": True},
        },
    }
    _write_json(run_dir / "bench_report.json", bench_report)
    return run_dir / "bench_report.json"


def _run_checker(report_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "tools/independent_check.py",
            "--bench-report",
            str(report_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_independent_check_passes_on_consistent_artifact(tmp_path: Path) -> None:
    report_path = _create_minimal_artifact(tmp_path, corrupt_first_golden_digest=False)
    proc = _run_checker(report_path)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "errors=0" in proc.stdout


def test_independent_check_detects_digest_inconsistency(tmp_path: Path) -> None:
    report_path = _create_minimal_artifact(tmp_path, corrupt_first_golden_digest=True)
    proc = _run_checker(report_path)

    assert proc.returncode == 1
    assert "DIGEST_RECOMPUTE_MISMATCH" in proc.stdout
