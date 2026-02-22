from __future__ import annotations

import pytest

from nema.dsl.errors import DslError
from nema.dsl.parser import FixedLit, TimeLit, parse


def test_parse_min_program_with_nested_blocks_and_lists() -> None:
    text = """
module {
  name = core;
  params = [1, 2, 3,];
  nested {
    ok = true;
  };
}
"""

    ast = parse(text)

    assert ast == {
        "module": {
            "name": "core",
            "params": [1, 2, 3],
            "nested": {
                "ok": True,
            },
        }
    }


def test_parse_time_and_fixed_literals() -> None:
    text = """
config {
  dt = 15ms;
  weight = weight_q4_4(-4);
}
"""

    ast = parse(text)

    dt = ast["config"]["dt"]
    weight = ast["config"]["weight"]

    assert isinstance(dt, TimeLit)
    assert dt.value == 15
    assert dt.unit == "ms"

    assert isinstance(weight, FixedLit)
    assert weight.type_id == "weight_q4_4"
    assert weight.raw == -4
    assert weight.unsigned is False


def test_parse_missing_semicolon_reports_location() -> None:
    text = "a = 1\nb = 2;"

    with pytest.raises(DslError) as exc_info:
        parse(text)

    err = exc_info.value
    assert "expected token SEMI" in str(err)
    assert err.line == 2
    assert err.col == 1
