from __future__ import annotations

import struct
from pathlib import Path

from nema.sim import simulate


def _lut_path() -> Path:
    return Path(__file__).resolve().parents[1] / "artifacts" / "luts" / "tanh_q8_8.bin"


def _read_lut_q8_8() -> list[int]:
    payload = _lut_path().read_bytes()
    return [struct.unpack("<h", payload[i : i + 2])[0] for i in range(0, len(payload), 2)]


def _tanh_raw_q8_8(raw_v: int, lut: list[int]) -> int:
    raw_min = -(1 << 15)
    return lut[(raw_v - raw_min) & 0xFFFF]


def _base_ir() -> dict:
    return {
        "name": "micrograph",
        "constraints": {"allowedSpdx": ["MIT"]},
        "license": {"spdxId": "MIT"},
        "tanhLut": {
            "policy": "nema.tanh_lut.v0.1",
            "artifact": str(_lut_path()),
            "inputType": "Q8.8",
            "outputType": "Q8.8",
        },
    }


def test_snapshot_chain_uses_snapshot_not_sequential() -> None:
    lut = _read_lut_q8_8()
    ir = _base_ir()
    ir["graph"] = {
        "dt": 1.0,
        "nodes": [
            {"id": "n0", "index": 0, "canonicalOrderId": 0, "tauM": 1.0, "vInitRaw": 256},
            {"id": "n1", "index": 1, "canonicalOrderId": 1, "tauM": 1.0, "vInitRaw": 0},
            {"id": "n2", "index": 2, "canonicalOrderId": 2, "tauM": 1.0, "vInitRaw": 0},
        ],
        "edges": [
            {"id": "e01", "kind": "CHEMICAL", "source": "n0", "target": "n1", "directed": True, "conductance": 1.0},
            {"id": "e12", "kind": "CHEMICAL", "source": "n1", "target": "n2", "directed": True, "conductance": 1.0},
        ],
    }

    report = simulate(ir, ticks=1, base_dir=Path("."))
    a0 = _tanh_raw_q8_8(256, lut)
    a1 = _tanh_raw_q8_8(0, lut)
    expected_snapshot = [256, a0, a1]
    assert report["finalVRawByIndex"] == expected_snapshot

    # Naive sequential reference (incorrect): n2 sees updated n1 within same tick.
    seq_n0 = 256
    seq_n1 = 0 + _tanh_raw_q8_8(seq_n0, lut)
    seq_n2 = 0 + _tanh_raw_q8_8(seq_n1, lut)
    sequential_wrong = [seq_n0, seq_n1, seq_n2]
    assert report["finalVRawByIndex"] != sequential_wrong


def test_gap_single_edge_symmetric_and_not_double_counted() -> None:
    ir = _base_ir()
    ir["graph"] = {
        "dt": 1.0,
        "nodes": [
            {"id": "n0", "index": 0, "canonicalOrderId": 0, "tauM": 1.0, "vInitRaw": 256},
            {"id": "n1", "index": 1, "canonicalOrderId": 1, "tauM": 1.0, "vInitRaw": 0},
        ],
        "edges": [
            {"id": "g01", "kind": "GAP", "source": "n0", "target": "n1", "directed": True, "conductance": 0.5},
        ],
    }

    one_edge = simulate(ir, ticks=1, base_dir=Path("."))
    assert one_edge["finalVRawByIndex"] == [128, 128]

    # Mirrored directed representation must not change the undirected contribution.
    ir_mirror = _base_ir()
    ir_mirror["graph"] = {
        "dt": 1.0,
        "nodes": [
            {"id": "n0", "index": 0, "canonicalOrderId": 0, "tauM": 1.0, "vInitRaw": 256},
            {"id": "n1", "index": 1, "canonicalOrderId": 1, "tauM": 1.0, "vInitRaw": 0},
        ],
        "edges": [
            {"id": "g01", "kind": "GAP", "source": "n0", "target": "n1", "directed": True, "conductance": 0.5},
            {"id": "g10", "kind": "GAP", "source": "n1", "target": "n0", "directed": True, "conductance": 0.5},
        ],
    }
    mirrored = simulate(ir_mirror, ticks=1, base_dir=Path("."))

    assert mirrored["finalVRawByIndex"] == one_edge["finalVRawByIndex"]
    assert mirrored["tickDigestsSha256"] == one_edge["tickDigestsSha256"]
    assert mirrored["finalVRawByIndex"] != [0, 256]
