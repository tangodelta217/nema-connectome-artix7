from __future__ import annotations

import copy

from nema.lowering.csr import lower_ir_to_csr


def _ir_fixture() -> dict:
    return {
        "name": "csr_fixture",
        "constraints": {"allowedSpdx": ["MIT"]},
        "license": {"spdxId": "MIT"},
        "graph": {
            "nodes": [
                {"id": "nB", "index": 7, "canonicalOrderId": 2},
                {"id": "nA", "index": 3, "canonicalOrderId": 1},
                {"id": "nC", "index": 5, "canonicalOrderId": 0},
            ],
            "edges": [
                {
                    "id": "e2",
                    "kind": "CHEMICAL",
                    "source": "nC",
                    "target": "nB",
                    "directed": True,
                    "conductance": 0.5,
                },
                {
                    "id": "e1",
                    "kind": "CHEMICAL",
                    "source": "nA",
                    "target": "nB",
                    "directed": True,
                    "conductance": -0.25,
                },
                {
                    "id": "e0",
                    "kind": "CHEMICAL",
                    "source": "nC",
                    "target": "nA",
                    "directed": True,
                    "weight": 0.75,
                    "modelId": "chemical_current_v0",
                },
                {
                    "id": "g1",
                    "kind": "GAP",
                    "source": "nA",
                    "target": "nC",
                    "directed": True,
                    "conductance": 0.25,
                },
                {
                    "id": "g1_mirror",
                    "kind": "GAP",
                    "source": "nC",
                    "target": "nA",
                    "directed": True,
                    "conductance": 0.25,
                },
                {
                    "id": "g2",
                    "kind": "GAP",
                    "source": "nB",
                    "target": "nC",
                    "directed": True,
                    "conductance": 0.5,
                },
            ],
        },
    }


def test_csr_lowering_expected_layout_and_packing() -> None:
    lowered = lower_ir_to_csr(_ir_fixture())

    assert lowered["node_count"] == 3
    assert lowered["canonical"]["node_id_by_canonical_idx"] == ["nC", "nA", "nB"]

    chemical = lowered["chemical_csr"]
    assert chemical["row_ptr_u16"] == [0, 0, 1, 3]
    assert chemical["col_or_pre_u16"] == [0, 0, 1]
    assert chemical["weight_s8"] == [96, 64, -32]
    assert chemical["weight_u8"] == [96, 64, 224]
    assert chemical["model_id_u8"] == [0, 0, 0]

    gaps = lowered["gap_records"]
    assert gaps["a_idx_u16"] == [0, 0]
    assert gaps["b_idx_u16"] == [1, 2]
    assert gaps["conductance_u8"] == [64, 128]
    assert gaps["model_id_u8"] == [0, 0]


def test_csr_deterministic_across_runs_and_input_order() -> None:
    base = _ir_fixture()
    r1 = lower_ir_to_csr(copy.deepcopy(base))
    r2 = lower_ir_to_csr(copy.deepcopy(base))
    assert r1 == r2

    permuted = copy.deepcopy(base)
    permuted["graph"]["nodes"] = list(reversed(permuted["graph"]["nodes"]))
    permuted["graph"]["edges"] = list(reversed(permuted["graph"]["edges"]))
    r3 = lower_ir_to_csr(permuted)
    assert r1 == r3
