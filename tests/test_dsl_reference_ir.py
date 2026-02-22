from __future__ import annotations

import copy
import json
from pathlib import Path

from nema.dsl import lower_to_ir, parse_toml_file
from nema.ir_canonical import canonicalize_ir
from nema.sim import simulate


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _compile_dsl(path: Path) -> dict:
    program = parse_toml_file(path)
    return canonicalize_ir(lower_to_ir(program))


def test_dsl_b1_matches_reference_ir_canonically() -> None:
    compiled = _compile_dsl(Path("programs/b1_small.nema.toml"))
    reference = canonicalize_ir(_load_json(Path("example_b1_small_subgraph.json")))

    assert compiled == reference


def test_dsl_b3_matches_reference_ir_canonically() -> None:
    compiled = _compile_dsl(Path("programs/b3_kernel_302_7500.nema.toml"))
    reference = canonicalize_ir(_load_json(Path("example_b3_kernel_302.json")))

    assert compiled == reference


def test_dsl_ir_defaults_dt_and_tau_m_are_runtime_equivalent() -> None:
    compiled = _compile_dsl(Path("programs/b1_small.nema.toml"))
    assert "dt" not in compiled["graph"]
    assert "tauM" not in compiled["graph"]

    explicit = copy.deepcopy(compiled)
    explicit["graph"]["dt"] = 1.0
    explicit["graph"]["tauM"] = 1.0

    result_default = simulate(compiled, ticks=6, seed=0, base_dir=Path("."))
    result_explicit = simulate(explicit, ticks=6, seed=0, base_dir=Path("."))

    assert result_default["tickDigestsSha256"] == result_explicit["tickDigestsSha256"]
