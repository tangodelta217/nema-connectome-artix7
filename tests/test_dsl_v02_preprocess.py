from __future__ import annotations

from pathlib import Path

import pytest

from nema.dsl.errors import DslError
from nema.dsl.lower import lower_to_ir_with_locs
from nema.dsl.parser import parse_with_locs
from nema.dsl.preprocess import PREPROCESSED_PATH, preprocess_file


def test_include_and_const_substitution_ok(tmp_path: Path) -> None:
    defs = tmp_path / "defs.nema"
    defs.write_text(
        "\n".join(
            [
                "modelId = b1_small;",
                "const STEP = 2;",
                "const RAW = -4;",
                'const LABEL = "alpha";',
                "",
            ]
        ),
        encoding="utf-8",
    )

    main = tmp_path / "main.nema"
    main.write_text(
        "\n".join(
            [
                'include "defs.nema";',
                "config {",
                "  dt = ${STEP}ms;",
                "  weight = weight_q4_4(${RAW});",
                '  text = "k-${LABEL}";',
                "};",
                "",
            ]
        ),
        encoding="utf-8",
    )

    preprocessed = preprocess_file(main)
    ast, locs = parse_with_locs(preprocessed.text, PREPROCESSED_PATH)
    lowered, lowered_locs = lower_to_ir_with_locs(ast, preprocessed.source_map.remap_locs(locs))

    assert lowered["modelId"] == "b1_small"
    assert lowered["config"]["dt"] == {"nanoseconds": "2000000"}
    assert lowered["config"]["weight"] == {"typeId": "weight_q4_4", "signedRaw": "-4"}
    assert lowered["config"]["text"] == "k-alpha"
    assert lowered_locs["modelId"]["path"] == str(defs.resolve())


def test_include_loop_error() -> None:
    fixture = Path("tests/fixtures/diag/2501_include_loop.nema")
    with pytest.raises(DslError) as exc_info:
        preprocess_file(fixture)

    diag = exc_info.value.diagnostic
    assert diag.code == "NEMA-DSL2501"
    assert "include loop" in diag.message


def test_include_must_be_at_top_of_file(tmp_path: Path) -> None:
    inc = tmp_path / "defs.nema"
    inc.write_text("modelId = test;\n", encoding="utf-8")

    main = tmp_path / "main.nema"
    main.write_text('modelId = x;\ninclude "defs.nema";\n', encoding="utf-8")

    with pytest.raises(DslError) as exc_info:
        preprocess_file(main)

    assert exc_info.value.diagnostic.code == "NEMA-DSL2502"


def test_source_map_remaps_parser_error_to_included_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.nema"
    bad.write_text("foo = ;\n", encoding="utf-8")

    main = tmp_path / "main.nema"
    main.write_text('include "bad.nema";\nbar = 1;\n', encoding="utf-8")

    preprocessed = preprocess_file(main)
    with pytest.raises(DslError) as exc_info:
        parse_with_locs(preprocessed.text, PREPROCESSED_PATH)

    mapped = preprocessed.remap_error(exc_info.value).diagnostic
    assert mapped.code == "NEMA-DSL1101"
    assert mapped.path == str(bad.resolve())
    assert mapped.line == 1
    assert mapped.col == 7
