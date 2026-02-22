from __future__ import annotations

from nema.dsl.lower import lower_to_ir, lower_to_ir_with_locs
from nema.dsl.parser import parse, parse_with_locs


def test_lower_time_literal_ms_to_nanoseconds_string() -> None:
    ast = parse("cfg { dt = 1ms; };")
    ir = lower_to_ir(ast)

    assert ir["cfg"]["dt"] == {"nanoseconds": "1000000"}


def test_lower_fixed_literal_signed_raw_string() -> None:
    ast = parse("cfg { weight = weight_q4_4(8); };")
    ir = lower_to_ir(ast)

    assert ir["cfg"]["weight"] == {"typeId": "weight_q4_4", "signedRaw": "8"}


def test_lower_fixed_literal_unsigned_raw_string() -> None:
    ast = parse("cfg { conductance = conductance_q4_4(2u); };")
    ir = lower_to_ir(ast)

    assert ir["cfg"]["conductance"] == {"typeId": "conductance_q4_4", "unsignedRaw": "2"}


def test_lower_with_locs_preserves_location_map() -> None:
    ast, locs = parse_with_locs("cfg { dt = 1ms; };", "programs/cfg.nema")
    ir, out_locs = lower_to_ir_with_locs(ast, locs)

    assert ir["cfg"]["dt"] == {"nanoseconds": "1000000"}
    assert out_locs == locs
