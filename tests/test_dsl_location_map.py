from __future__ import annotations

from nema.dsl.parser import parse_with_locs


def test_parse_with_locs_maps_canonical_field_paths() -> None:
    source = (
        "graph {\n"
        "  external {\n"
        '    sha256 = "sha256:REPLACE";\n'
        "  };\n"
        "}\n"
        "compile {\n"
        "  qformats {\n"
        '    stateTypeId = "state_q8_8";\n'
        "  };\n"
        "}\n"
    )

    obj, locs = parse_with_locs(source, "programs/sample.nema")

    assert obj["graph"]["external"]["sha256"] == "sha256:REPLACE"
    assert obj["compile"]["qformats"]["stateTypeId"] == "state_q8_8"

    assert locs["graph"] == {"line": 1, "col": 1}
    assert locs["graph.external"] == {"line": 2, "col": 3}
    assert locs["graph.external.sha256"] == {"line": 3, "col": 5}

    assert locs["compile"] == {"line": 6, "col": 1}
    assert locs["compile.qformats"] == {"line": 7, "col": 3}
    assert locs["compile.qformats.stateTypeId"] == {"line": 8, "col": 5}
