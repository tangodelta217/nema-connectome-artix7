from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.gen_tanh_lut import generate_lut_artifacts, parse_fixed_type_id


EXPECTED_Q8_8_SHA256 = "7d21f56cc692fadb62283328037b0319745d1a08b4369d4fbffe8dc6cb260d88"


def _lut_index(raw_in: int, input_type_id: str = "Q8.8") -> int:
    input_type = parse_fixed_type_id(input_type_id)
    return raw_in - input_type.raw_min


def test_tanh_lut_checksum_matches_expected(tmp_path: Path) -> None:
    report = generate_lut_artifacts("Q8.8", "Q8.8", outdir=tmp_path)

    assert report["sha256"] == EXPECTED_Q8_8_SHA256
    bin_path = tmp_path / "tanh_q8_8.bin"
    assert bin_path.exists()
    assert hashlib.sha256(bin_path.read_bytes()).hexdigest() == EXPECTED_Q8_8_SHA256


def test_tanh_lut_spot_checks_q8_8(tmp_path: Path) -> None:
    generate_lut_artifacts("Q8.8", "Q8.8", outdir=tmp_path)
    json_path = tmp_path / "tanh_q8_8.json"
    values = json.loads(json_path.read_text(encoding="utf-8"))

    # Saturation corners and selected interior points.
    assert values[_lut_index(-32768)] == -256
    assert values[_lut_index(32767)] == 256
    assert values[_lut_index(0)] == 0
    assert values[_lut_index(256)] == 195
    assert values[_lut_index(-256)] == -195
    assert values[_lut_index(1024)] == 256
    assert values[_lut_index(-1024)] == -256
