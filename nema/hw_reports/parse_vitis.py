"""Parse Vitis HLS report artifacts into a stable QoR summary."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

_REPORT_SUFFIXES = {".rpt", ".xml", ".log"}
_INT_RE = re.compile(r"^[0-9][0-9,]*$")


def _to_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    token = raw.strip().replace(",", "")
    if not token or not token.isdigit():
        return None
    return int(token)


def _first_xml_int(root: ElementTree.Element, paths: list[str]) -> int | None:
    for xpath in paths:
        node = root.find(xpath)
        if node is None or node.text is None:
            continue
        value = _to_int(node.text)
        if value is not None:
            return value
    return None


def _assign_first(target: dict[str, int | None], key: str, value: int | None) -> None:
    if target.get(key) is None and value is not None:
        target[key] = value


def _parse_xml_file(path: Path) -> dict[str, int | None]:
    values: dict[str, int | None] = {
        "lut": None,
        "ff": None,
        "bram": None,
        "dsp": None,
        "ii": None,
        "latencyCycles": None,
    }
    try:
        root = ElementTree.parse(path).getroot()
    except (ElementTree.ParseError, OSError):
        return values

    _assign_first(
        values,
        "lut",
        _first_xml_int(root, [".//AreaEstimates/Resources/LUT", ".//Resources/LUT"]),
    )
    _assign_first(
        values,
        "ff",
        _first_xml_int(root, [".//AreaEstimates/Resources/FF", ".//Resources/FF"]),
    )
    _assign_first(
        values,
        "bram",
        _first_xml_int(root, [".//AreaEstimates/Resources/BRAM_18K", ".//Resources/BRAM_18K", ".//Resources/BRAM"]),
    )
    _assign_first(
        values,
        "dsp",
        _first_xml_int(root, [".//AreaEstimates/Resources/DSP", ".//Resources/DSP"]),
    )
    _assign_first(
        values,
        "ii",
        _first_xml_int(root, [".//SummaryOfOverallLatency/Interval-min", ".//Interval-min"]),
    )
    _assign_first(
        values,
        "latencyCycles",
        _first_xml_int(
            root,
            [
                ".//SummaryOfOverallLatency/Best-caseLatency",
                ".//SummaryOfOverallLatency/Average-caseLatency",
                ".//SummaryOfOverallLatency/Worst-caseLatency",
                ".//Latency",
            ],
        ),
    )
    return values


def _find_rpt_value(text: str, patterns: list[str]) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if not match:
            continue
        for group in match.groups():
            if group is None:
                continue
            value = _to_int(group)
            if value is not None:
                return value
    return None


def _parse_rpt_file(path: Path) -> dict[str, int | None]:
    values: dict[str, int | None] = {
        "lut": None,
        "ff": None,
        "bram": None,
        "dsp": None,
        "ii": None,
        "latencyCycles": None,
    }
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values

    _assign_first(values, "lut", _find_rpt_value(text, [r"\|\s*LUT\s*\|\s*([0-9,]+)\s*\|", r"\bLUT[^0-9]*([0-9,]+)"]))
    _assign_first(values, "ff", _find_rpt_value(text, [r"\|\s*FF\s*\|\s*([0-9,]+)\s*\|", r"\bFF[^0-9]*([0-9,]+)"]))
    _assign_first(
        values,
        "bram",
        _find_rpt_value(text, [r"\|\s*(?:BRAM_18K|BRAM)\s*\|\s*([0-9,]+)\s*\|", r"\bBRAM(?:_18K)?[^0-9]*([0-9,]+)"]),
    )
    _assign_first(values, "dsp", _find_rpt_value(text, [r"\|\s*DSP\s*\|\s*([0-9,]+)\s*\|", r"\bDSP[^0-9]*([0-9,]+)"]))
    _assign_first(
        values,
        "ii",
        _find_rpt_value(text, [r"\bInterval[^0-9]*([0-9,]+)", r"\bII[^0-9]*([0-9,]+)"]),
    )
    _assign_first(
        values,
        "latencyCycles",
        _find_rpt_value(
            text,
            [
                r"Latency\s*\(cycles\).*?\|\s*([0-9,]+)\s*\|",
                r"\bLatency[^0-9]*([0-9,]+)",
            ],
        ),
    )
    return values


def _empty_qor() -> dict[str, Any]:
    return {
        "utilization": {
            "lut": None,
            "ff": None,
            "bram": None,
            "dsp": None,
        },
        "timingOrLatency": {
            "ii": None,
            "latencyCycles": None,
        },
        "sourceReports": [],
    }


def parse_vitis_qor(hw_reports_dir: Path, *, source_prefix: str = "hw_reports") -> dict[str, Any]:
    """Parse report files under hw_reports_dir and return stable QoR fields."""
    payload = _empty_qor()
    if not hw_reports_dir.exists():
        return payload

    report_files = sorted(
        path for path in hw_reports_dir.rglob("*") if path.is_file() and path.suffix.lower() in _REPORT_SUFFIXES
    )
    if not report_files:
        return payload

    source_reports: list[str] = []
    for path in report_files:
        rel = path.relative_to(hw_reports_dir).as_posix()
        if source_prefix:
            source_reports.append(f"{source_prefix.rstrip('/')}/{rel}")
        else:
            source_reports.append(rel)
    payload["sourceReports"] = source_reports

    extracted: dict[str, int | None] = {
        "lut": None,
        "ff": None,
        "bram": None,
        "dsp": None,
        "ii": None,
        "latencyCycles": None,
    }

    xml_files = [path for path in report_files if path.suffix.lower() == ".xml"]
    rpt_files = [path for path in report_files if path.suffix.lower() == ".rpt"]

    def _xml_priority(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        return (0 if name == "csynth.xml" else 1, str(path))

    def _rpt_priority(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        return (0 if name == "csynth.rpt" else 1, str(path))

    for path in sorted(xml_files, key=_xml_priority):
        parsed = _parse_xml_file(path)
        for key in extracted:
            _assign_first(extracted, key, parsed.get(key))

    for path in sorted(rpt_files, key=_rpt_priority):
        parsed = _parse_rpt_file(path)
        for key in extracted:
            _assign_first(extracted, key, parsed.get(key))

    payload["utilization"] = {
        "lut": extracted["lut"],
        "ff": extracted["ff"],
        "bram": extracted["bram"],
        "dsp": extracted["dsp"],
    }
    payload["timingOrLatency"] = {
        "ii": extracted["ii"],
        "latencyCycles": extracted["latencyCycles"],
    }
    return payload
