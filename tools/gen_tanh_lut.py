#!/usr/bin/env python3
"""Generate canonical tanh LUT artifacts (policy nema.tanh_lut.v0.1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path


@dataclass(frozen=True)
class FixedTypeId:
    signed: bool
    int_bits: int
    frac_bits: int
    total_bits: int

    @property
    def raw_min(self) -> int:
        if self.signed:
            return -(1 << (self.total_bits - 1))
        return 0

    @property
    def raw_max(self) -> int:
        if self.signed:
            return (1 << (self.total_bits - 1)) - 1
        return (1 << self.total_bits) - 1

    @property
    def scale(self) -> int:
        return 1 << self.frac_bits

    @property
    def slug(self) -> str:
        prefix = "q" if self.signed else "uq"
        return f"{prefix}{self.int_bits}_{self.frac_bits}"


_SIGNED_Q_RE = re.compile(r"^[qQ](\d+)\.(\d+)$")
_UNSIGNED_Q_RE = re.compile(r"^[uU][qQ](\d+)\.(\d+)$")


def parse_fixed_type_id(type_id: str) -> FixedTypeId:
    """Parse fixed type IDs like Q8.8 / q8.8 / UQ8.8."""
    signed_match = _SIGNED_Q_RE.match(type_id)
    if signed_match:
        int_bits = int(signed_match.group(1))
        frac_bits = int(signed_match.group(2))
        return FixedTypeId(
            signed=True,
            int_bits=int_bits,
            frac_bits=frac_bits,
            total_bits=int_bits + frac_bits,
        )

    unsigned_match = _UNSIGNED_Q_RE.match(type_id)
    if unsigned_match:
        int_bits = int(unsigned_match.group(1))
        frac_bits = int(unsigned_match.group(2))
        return FixedTypeId(
            signed=False,
            int_bits=int_bits,
            frac_bits=frac_bits,
            total_bits=int_bits + frac_bits,
        )

    raise ValueError(f"unsupported fixed type ID: {type_id}")


def quantize_rne_saturate(value: Decimal, out_type: FixedTypeId) -> int:
    scaled = value * Decimal(out_type.scale)
    rounded = int(scaled.to_integral_value(rounding=ROUND_HALF_EVEN))
    if rounded > out_type.raw_max:
        return out_type.raw_max
    if rounded < out_type.raw_min:
        return out_type.raw_min
    return rounded


def tanh_decimal(x: Decimal) -> Decimal:
    """Numerically stable tanh using Decimal operations."""
    if x == 0:
        return Decimal(0)
    if x > 0:
        exp_neg_2x = (-2 * x).exp()
        return (Decimal(1) - exp_neg_2x) / (Decimal(1) + exp_neg_2x)
    exp_2x = (2 * x).exp()
    return (exp_2x - Decimal(1)) / (exp_2x + Decimal(1))


def generate_tanh_table(input_type: FixedTypeId, output_type: FixedTypeId) -> list[int]:
    if output_type.total_bits != 16 or not output_type.signed:
        raise ValueError("this generator currently writes signed int16 outputs only")

    results: list[int] = []
    with localcontext() as ctx:
        # High precision avoids platform float differences in edge quantization.
        ctx.prec = 80
        dec_in_scale = Decimal(input_type.scale)
        for raw_in in range(input_type.raw_min, input_type.raw_max + 1):
            x = Decimal(raw_in) / dec_in_scale
            y = tanh_decimal(x)
            raw_out = quantize_rne_saturate(y, output_type)
            results.append(raw_out)
    return results


def pack_int16_le(values: list[int]) -> bytes:
    payload = bytearray()
    for value in values:
        payload.extend(struct.pack("<h", value))
    return bytes(payload)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate_lut_artifacts(
    input_type_id: str,
    output_type_id: str,
    outdir: Path = Path("artifacts/luts"),
) -> dict:
    input_type = parse_fixed_type_id(input_type_id)
    output_type = parse_fixed_type_id(output_type_id)
    table = generate_tanh_table(input_type, output_type)

    outdir.mkdir(parents=True, exist_ok=True)
    out_prefix = f"tanh_{output_type.slug}"
    bin_path = outdir / f"{out_prefix}.bin"
    json_path = outdir / f"{out_prefix}.json"

    payload = pack_int16_le(table)
    digest = sha256_hex(payload)

    bin_path.write_bytes(payload)
    json_path.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")

    return {
        "policy": "nema.tanh_lut.v0.1",
        "input_type": input_type_id,
        "output_type": output_type_id,
        "entries": len(table),
        "bin_path": str(bin_path),
        "json_path": str(json_path),
        "sha256": digest,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate canonical tanh LUT artifacts")
    parser.add_argument("--input-type", default="Q8.8", help="fixed input type ID (e.g. Q8.8)")
    parser.add_argument("--output-type", default="Q8.8", help="fixed output type ID (e.g. Q8.8)")
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("artifacts/luts"),
        help="artifact output directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = generate_lut_artifacts(
        input_type_id=args.input_type,
        output_type_id=args.output_type,
        outdir=args.outdir,
    )
    print(report["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
