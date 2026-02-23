from __future__ import annotations

from pathlib import Path

from nema.hw_reports.parse_vivado import parse_vivado_qor


def test_parse_vivado_qor_extracts_utilization_and_timing() -> None:
    hw_reports_dir = Path("tests/fixtures/hw_reports/vivado/minimal")
    payload = parse_vivado_qor(hw_reports_dir)

    assert payload["utilization"]["lut"] == 1234
    assert payload["utilization"]["ff"] == 2468
    assert payload["utilization"]["bram"] == 10.5
    assert payload["utilization"]["dsp"] == 42

    assert payload["timing"]["wns"] == -0.123
    assert payload["timing"]["tns"] == -4.56
    assert payload["timing"]["whs"] == 0
    assert payload["timing"]["ths"] == 0
    assert payload["timing"]["failingEndpoints"] == 12

    assert payload["sourceReports"] == [
        "hw_reports/vivado_timing_summary.rpt",
        "hw_reports/vivado_utilization.rpt",
    ]


def test_parse_vivado_qor_empty_when_missing() -> None:
    payload = parse_vivado_qor(Path("tests/fixtures/hw_reports/does_not_exist"))
    assert payload["utilization"] == {"lut": None, "ff": None, "bram": None, "dsp": None}
    assert payload["timing"] == {
        "wns": None,
        "tns": None,
        "whs": None,
        "ths": None,
        "failingEndpoints": None,
    }
    assert payload["sourceReports"] == []

