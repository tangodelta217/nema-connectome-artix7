from __future__ import annotations

from pathlib import Path

from nema.hw_reports.parse_vitis import parse_vitis_qor


def test_parse_vitis_qor_extracts_utilization_and_latency() -> None:
    hw_reports_dir = Path("tests/fixtures/hw_reports/minimal")
    payload = parse_vitis_qor(hw_reports_dir)

    assert payload["utilization"]["lut"] == 890
    assert payload["utilization"]["ff"] == 567
    assert payload["utilization"]["bram"] == 3
    assert payload["utilization"]["dsp"] == 4
    assert payload["ii"] == 2
    assert payload["latencyCycles"] == 120
    assert payload["timingOrLatency"]["ii"] == 2
    assert payload["timingOrLatency"]["latencyCycles"] == 120
    assert payload["sourceReports"] == [
        "hw_reports/syn/report/csynth.rpt",
        "hw_reports/syn/report/csynth.xml",
    ]
