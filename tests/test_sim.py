from __future__ import annotations

from pathlib import Path

from nema.sim import simulate


def build_ir() -> dict:
    return {
        "name": "sim_test_ir",
        "constraints": {"allowedSpdx": ["MIT"]},
        "license": {"spdxId": "MIT"},
        "graph": {
            "dt": 1.0,
            "nodes": [
                {"id": "n0", "index": 0, "canonicalOrderId": 0, "vInitRaw": 128, "tauM": 2.0},
                {"id": "n1", "index": 1, "canonicalOrderId": 1, "vInitRaw": -96, "tauM": 3.0},
                {"id": "n2", "index": 2, "canonicalOrderId": 2, "vInitRaw": 64, "tauM": 4.0},
            ],
            "edges": [
                {
                    "id": "e_chem_0",
                    "kind": "CHEMICAL",
                    "source": "n0",
                    "target": "n1",
                    "directed": True,
                    "conductance": 0.7,
                },
                {
                    "id": "e_chem_1",
                    "kind": "CHEMICAL",
                    "source": "n1",
                    "target": "n2",
                    "directed": True,
                    "conductance": 0.5,
                },
                {
                    "id": "e_gap_fwd",
                    "kind": "GAP",
                    "source": "n0",
                    "target": "n2",
                    "directed": True,
                    "conductance": 0.2,
                },
                {
                    "id": "e_gap_rev",
                    "kind": "GAP",
                    "source": "n2",
                    "target": "n0",
                    "directed": True,
                    "conductance": 0.2,
                },
            ],
        },
        "tanhLut": {
            "policy": "nema.tanh_lut.v0.1",
            "artifact": "artifacts/luts/tanh_q8_8.bin",
            "inputType": "Q8.8",
            "outputType": "Q8.8",
        },
    }


def test_sim_determinism_same_inputs_same_digest() -> None:
    ir = build_ir()
    r1 = simulate(ir, ticks=16, seed=42, base_dir=Path("."))
    r2 = simulate(ir, ticks=16, seed=42, base_dir=Path("."))

    assert r1["tickDigestsSha256"] == r2["tickDigestsSha256"]
    assert r1["finalVRawByIndex"] == r2["finalVRawByIndex"]


def test_snapshot_rule_eval_order_independent() -> None:
    ir = build_ir()
    forward = simulate(ir, ticks=16, seed=7, base_dir=Path("."), eval_order="index")
    reverse = simulate(ir, ticks=16, seed=7, base_dir=Path("."), eval_order="reverse")

    assert forward["tickDigestsSha256"] == reverse["tickDigestsSha256"]
    assert forward["finalVRawByIndex"] == reverse["finalVRawByIndex"]
