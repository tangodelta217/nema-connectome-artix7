"""Parse Vivado batch reports into stable utilization/timing summaries."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_REPORT_SUFFIXES = {".rpt", ".log", ".xml"}


def _empty_payload() -> dict[str, Any]:
    return {
        "utilization": {
            "lut": None,
            "ff": None,
            "bram": None,
            "dsp": None,
        },
        "timing": {
            "wns": None,
            "tns": None,
            "whs": None,
            "ths": None,
            "failingEndpoints": None,
        },
        "sourceReports": [],
    }


def _to_number(raw: str | None) -> int | float | None:
    if raw is None:
        return None
    token = raw.strip().replace(",", "")
    if not token:
        return None
    try:
        value = float(token)
    except ValueError:
        return None
    if value.is_integer():
        return int(value)
    return value


def _assign_first(
    target: dict[str, int | float | None],
    key: str,
    value: int | float | None,
) -> None:
    if target.get(key) is None and value is not None:
        target[key] = value


def _find_first(text: str, patterns: list[str]) -> int | float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            continue
        for idx in range(1, (match.lastindex or 0) + 1):
            value = _to_number(match.group(idx))
            if value is not None:
                return value
    return None


def _extract_design_timing_summary_values(text: str) -> dict[str, int | float | None]:
    """Extract WNS/TNS/Failing Endpoints from Vivado's tabular timing summary."""
    result: dict[str, int | float | None] = {
        "wns": None,
        "tns": None,
        "failingEndpoints": None,
    }
    marker = re.search(r"Design Timing Summary", text, flags=re.IGNORECASE)
    if not marker:
        return result

    lines = text[marker.end() :].splitlines()
    header_idx: int | None = None
    for idx, line in enumerate(lines):
        if "WNS(ns)" in line and "TNS(ns)" in line:
            header_idx = idx
            break
    if header_idx is None:
        return result

    for line in lines[header_idx + 1 : header_idx + 32]:
        stripped = line.strip()
        if not stripped:
            continue
        if set(stripped) <= {"-", " ", "|"}:
            continue
        numbers = re.findall(r"-?[0-9]+(?:\.[0-9]+)?", stripped)
        if len(numbers) < 3:
            continue
        result["wns"] = _to_number(numbers[0])
        result["tns"] = _to_number(numbers[1])
        result["failingEndpoints"] = _to_number(numbers[2])
        break
    return result


def _is_vivado_report(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    if "vivado" in parts:
        return True
    return (
        "utilization" in name
        or "timing_summary" in name
        or "timing" in name and "summary" in name
        or name.startswith("vivado_")
    )


def parse_vivado_qor(hw_reports_dir: Path, *, source_prefix: str = "hw_reports") -> dict[str, Any]:
    """Parse Vivado report files under ``hw_reports_dir``."""
    payload = _empty_payload()
    if not hw_reports_dir.exists():
        return payload

    def _candidate_priority(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        suffix = path.suffix.lower()
        if "timing_summary" in name and suffix == ".rpt":
            return (0, str(path))
        if "utilization" in name and suffix == ".rpt":
            return (1, str(path))
        if suffix == ".rpt":
            return (2, str(path))
        if suffix == ".log":
            return (3, str(path))
        return (4, str(path))

    candidates = sorted(
        (
            path
            for path in hw_reports_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in _REPORT_SUFFIXES and _is_vivado_report(path.relative_to(hw_reports_dir))
        ),
        key=_candidate_priority,
    )
    if not candidates:
        return payload

    source_reports: list[str] = []
    for path in candidates:
        rel = path.relative_to(hw_reports_dir).as_posix()
        if source_prefix:
            source_reports.append(f"{source_prefix.rstrip('/')}/{rel}")
        else:
            source_reports.append(rel)
    payload["sourceReports"] = source_reports

    util = payload["utilization"]
    timing = payload["timing"]

    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        _assign_first(
            util,
            "lut",
            _find_first(
                text,
                [
                    r"\|\s*(?:CLB LUTs\*?|Slice LUTs\*?)\s*\|\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*\|",
                    r"\b(?:CLB LUTs|Slice LUTs)\b[^0-9\-]*([0-9][0-9,]*(?:\.[0-9]+)?)",
                ],
            ),
        )
        _assign_first(
            util,
            "ff",
            _find_first(
                text,
                [
                    r"\|\s*(?:CLB Registers|Slice Registers)\s*\|\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*\|",
                    r"\b(?:CLB Registers|Slice Registers)\b[^0-9\-]*([0-9][0-9,]*(?:\.[0-9]+)?)",
                ],
            ),
        )
        _assign_first(
            util,
            "bram",
            _find_first(
                text,
                [
                    r"\|\s*(?:Block RAM Tile|RAMB36(?:/FIFO)?\*?|RAMB18)\s*\|\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*\|",
                    r"\b(?:Block RAM Tile|RAMB36|RAMB18)\b[^0-9\-]*([0-9][0-9,]*(?:\.[0-9]+)?)",
                ],
            ),
        )
        _assign_first(
            util,
            "dsp",
            _find_first(
                text,
                [
                    r"\|\s*DSPs\s*\|\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*\|",
                    r"\bDSPs?\b[^0-9\-]*([0-9][0-9,]*(?:\.[0-9]+)?)",
                ],
            ),
        )

        _assign_first(
            timing,
            "wns",
            _find_first(
                text,
                [
                    r"\bWNS(?:\(ns\))?\s*[:=]\s*(-?[0-9]+(?:\.[0-9]+)?)",
                ],
            ),
        )
        _assign_first(
            timing,
            "tns",
            _find_first(
                text,
                [
                    r"\bTNS(?:\(ns\))?\s*[:=]\s*(-?[0-9]+(?:\.[0-9]+)?)",
                ],
            ),
        )
        _assign_first(
            timing,
            "whs",
            _find_first(
                text,
                [
                    r"\bWHS(?:\(ns\))?\s*[:=]\s*(-?[0-9]+(?:\.[0-9]+)?)",
                ],
            ),
        )
        _assign_first(
            timing,
            "ths",
            _find_first(
                text,
                [
                    r"\bTHS(?:\(ns\))?\s*[:=]\s*(-?[0-9]+(?:\.[0-9]+)?)",
                ],
            ),
        )
        _assign_first(
            timing,
            "failingEndpoints",
            _find_first(
                text,
                [
                    r"\bFailing Endpoints\b\s*[:=]\s*([0-9][0-9,]*)",
                    r"\bSetup\s*:\s*([0-9][0-9,]*)\s*Failing Endpoints\b",
                ],
            ),
        )

        summary_values = _extract_design_timing_summary_values(text)
        _assign_first(timing, "wns", summary_values.get("wns"))
        _assign_first(timing, "tns", summary_values.get("tns"))
        _assign_first(timing, "failingEndpoints", summary_values.get("failingEndpoints"))

    return payload
