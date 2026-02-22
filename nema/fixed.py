"""Fixed-point utilities for the NEMA ISA scaffold.

This module implements deterministic fixed-point math with:
- overflow mode: SATURATE
- rounding mode: RNE (round to nearest, ties to even)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction


class OverflowMode(str, Enum):
    SATURATE = "SATURATE"


class RoundingMode(str, Enum):
    RNE = "RNE"


def _round_div_pow2_rne(value: int, shift: int) -> int:
    """Round value / 2**shift with RNE semantics."""
    if shift < 0:
        raise ValueError("shift must be >= 0")
    if shift == 0:
        return value

    sign = -1 if value < 0 else 1
    magnitude = abs(value)
    quotient = magnitude >> shift
    remainder = magnitude & ((1 << shift) - 1)
    half = 1 << (shift - 1)

    if remainder > half:
        quotient += 1
    elif remainder == half and (quotient & 1):
        quotient += 1

    return sign * quotient


def _round_fraction_rne(value: Fraction) -> int:
    """Round a rational number to integer with RNE semantics."""
    sign = -1 if value < 0 else 1
    numerator = abs(value.numerator)
    denominator = value.denominator

    quotient, remainder = divmod(numerator, denominator)
    twice_remainder = 2 * remainder

    if twice_remainder > denominator:
        quotient += 1
    elif twice_remainder == denominator and (quotient & 1):
        quotient += 1

    return sign * quotient


def _rescale_raw(value: int, from_frac: int, to_frac: int, rounding: RoundingMode) -> int:
    """Convert a raw fixed value between frac resolutions."""
    if from_frac == to_frac:
        return value

    if from_frac < to_frac:
        return value << (to_frac - from_frac)

    shift = from_frac - to_frac
    if rounding != RoundingMode.RNE:
        raise ValueError(f"unsupported rounding mode: {rounding}")
    return _round_div_pow2_rne(value, shift)


@dataclass(frozen=True)
class FixedType:
    signed: bool
    int_bits: int
    frac_bits: int
    total_bits: int
    overflow: OverflowMode = OverflowMode.SATURATE
    rounding: RoundingMode = RoundingMode.RNE

    def __post_init__(self) -> None:
        if self.int_bits < 0 or self.frac_bits < 0 or self.total_bits <= 0:
            raise ValueError("int_bits/frac_bits/total_bits must be non-negative with total_bits > 0")
        if self.signed and self.total_bits < 2:
            raise ValueError("signed fixed type requires at least 2 bits")
        if self.frac_bits >= self.total_bits:
            raise ValueError("frac_bits must be less than total_bits")
        if self.int_bits + self.frac_bits > self.total_bits:
            raise ValueError("int_bits + frac_bits cannot exceed total_bits")
        if self.overflow != OverflowMode.SATURATE:
            raise ValueError(f"unsupported overflow mode: {self.overflow}")
        if self.rounding != RoundingMode.RNE:
            raise ValueError(f"unsupported rounding mode: {self.rounding}")

    @property
    def scale(self) -> int:
        return 1 << self.frac_bits

    @property
    def mask(self) -> int:
        return (1 << self.total_bits) - 1

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

    def saturate_raw(self, raw: int) -> int:
        if raw > self.raw_max:
            return self.raw_max
        if raw < self.raw_min:
            return self.raw_min
        return raw

    def to_bits(self, raw: int) -> int:
        clamped = self.saturate_raw(raw)
        if self.signed and clamped < 0:
            return (1 << self.total_bits) + clamped
        return clamped & self.mask

    def from_bits(self, bits: int) -> int:
        bits &= self.mask
        if not self.signed:
            return bits
        sign_bit = 1 << (self.total_bits - 1)
        if bits & sign_bit:
            return bits - (1 << self.total_bits)
        return bits

    def quantize_from_raw(self, raw: int, source_frac_bits: int) -> int:
        scaled = _rescale_raw(raw, source_frac_bits, self.frac_bits, self.rounding)
        return self.saturate_raw(scaled)

    def quantize_real(self, value: int | float | Fraction) -> int:
        scaled = Fraction(value) * self.scale
        rounded = _round_fraction_rne(scaled)
        return self.saturate_raw(rounded)

    @classmethod
    def signed_type(
        cls,
        int_bits: int,
        frac_bits: int,
        total_bits: int,
        overflow: OverflowMode = OverflowMode.SATURATE,
        rounding: RoundingMode = RoundingMode.RNE,
    ) -> "FixedType":
        return cls(
            signed=True,
            int_bits=int_bits,
            frac_bits=frac_bits,
            total_bits=total_bits,
            overflow=overflow,
            rounding=rounding,
        )

    @classmethod
    def unsigned_type(
        cls,
        int_bits: int,
        frac_bits: int,
        total_bits: int,
        overflow: OverflowMode = OverflowMode.SATURATE,
        rounding: RoundingMode = RoundingMode.RNE,
    ) -> "FixedType":
        return cls(
            signed=False,
            int_bits=int_bits,
            frac_bits=frac_bits,
            total_bits=total_bits,
            overflow=overflow,
            rounding=rounding,
        )


@dataclass(frozen=True)
class Fixed:
    ftype: FixedType
    raw: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", self.ftype.saturate_raw(int(self.raw)))

    @classmethod
    def from_raw(cls, ftype: FixedType, raw: int) -> "Fixed":
        return cls(ftype=ftype, raw=raw)

    @classmethod
    def from_real(cls, ftype: FixedType, value: int | float | Fraction) -> "Fixed":
        return cls(ftype=ftype, raw=ftype.quantize_real(value))

    def to_float(self) -> float:
        return self.raw / self.ftype.scale

    def bits(self) -> int:
        return self.ftype.to_bits(self.raw)


def cast(value: Fixed, out_type: FixedType) -> Fixed:
    out_raw = out_type.quantize_from_raw(value.raw, source_frac_bits=value.ftype.frac_bits)
    return Fixed.from_raw(out_type, out_raw)


def add(a: Fixed, b: Fixed, out_type: FixedType | None = None) -> Fixed:
    out = out_type or a.ftype
    common_frac = max(a.ftype.frac_bits, b.ftype.frac_bits, out.frac_bits)
    a_common = _rescale_raw(a.raw, a.ftype.frac_bits, common_frac, a.ftype.rounding)
    b_common = _rescale_raw(b.raw, b.ftype.frac_bits, common_frac, b.ftype.rounding)
    summed = a_common + b_common
    out_raw = out.quantize_from_raw(summed, source_frac_bits=common_frac)
    return Fixed.from_raw(out, out_raw)


def sub(a: Fixed, b: Fixed, out_type: FixedType | None = None) -> Fixed:
    out = out_type or a.ftype
    common_frac = max(a.ftype.frac_bits, b.ftype.frac_bits, out.frac_bits)
    a_common = _rescale_raw(a.raw, a.ftype.frac_bits, common_frac, a.ftype.rounding)
    b_common = _rescale_raw(b.raw, b.ftype.frac_bits, common_frac, b.ftype.rounding)
    diffed = a_common - b_common
    out_raw = out.quantize_from_raw(diffed, source_frac_bits=common_frac)
    return Fixed.from_raw(out, out_raw)


def mul(a: Fixed, b: Fixed, out_type: FixedType | None = None) -> Fixed:
    out = out_type or a.ftype
    prod_raw = a.raw * b.raw
    prod_frac = a.ftype.frac_bits + b.ftype.frac_bits
    out_raw = out.quantize_from_raw(prod_raw, source_frac_bits=prod_frac)
    return Fixed.from_raw(out, out_raw)


def mac(acc: Fixed, a: Fixed, b: Fixed, out_type: FixedType | None = None) -> Fixed:
    out = out_type or acc.ftype
    prod_frac = a.ftype.frac_bits + b.ftype.frac_bits
    common_frac = max(acc.ftype.frac_bits, prod_frac, out.frac_bits)

    acc_common = _rescale_raw(acc.raw, acc.ftype.frac_bits, common_frac, acc.ftype.rounding)
    prod_common = _rescale_raw(a.raw * b.raw, prod_frac, common_frac, out.rounding)
    summed = acc_common + prod_common

    out_raw = out.quantize_from_raw(summed, source_frac_bits=common_frac)
    return Fixed.from_raw(out, out_raw)


def shift_left(value: Fixed, amount: int, out_type: FixedType | None = None) -> Fixed:
    if amount < 0:
        raise ValueError("shift amount must be >= 0")
    out = out_type or value.ftype
    shifted = value.raw << amount
    out_raw = out.quantize_from_raw(shifted, source_frac_bits=value.ftype.frac_bits)
    return Fixed.from_raw(out, out_raw)


def shift_right_arith(value: Fixed, amount: int, out_type: FixedType | None = None) -> Fixed:
    if amount < 0:
        raise ValueError("shift amount must be >= 0")
    out = out_type or value.ftype
    shifted = value.raw >> amount
    out_raw = out.quantize_from_raw(shifted, source_frac_bits=value.ftype.frac_bits)
    return Fixed.from_raw(out, out_raw)


def shift_right_logical(value: Fixed, amount: int, out_type: FixedType | None = None) -> Fixed:
    if amount < 0:
        raise ValueError("shift amount must be >= 0")

    bits = value.bits()
    shifted_bits = (bits >> amount) & value.ftype.mask
    shifted_raw = value.ftype.from_bits(shifted_bits)
    shifted = Fixed.from_raw(value.ftype, shifted_raw)

    if out_type is None or out_type == value.ftype:
        return shifted
    return cast(shifted, out_type)


def abs_fixed(value: Fixed, out_type: FixedType | None = None) -> Fixed:
    out = out_type or value.ftype
    if not value.ftype.signed:
        return cast(value, out)

    if value.raw == value.ftype.raw_min:
        magnitude_raw = value.ftype.raw_max
    else:
        magnitude_raw = abs(value.raw)

    magnitude = Fixed.from_raw(value.ftype, magnitude_raw)
    return cast(magnitude, out)


def cmp_fixed(a: Fixed, b: Fixed) -> int:
    common_frac = max(a.ftype.frac_bits, b.ftype.frac_bits)
    a_common = _rescale_raw(a.raw, a.ftype.frac_bits, common_frac, a.ftype.rounding)
    b_common = _rescale_raw(b.raw, b.ftype.frac_bits, common_frac, b.ftype.rounding)
    return (a_common > b_common) - (a_common < b_common)


def clip(value: Fixed, lower: Fixed, upper: Fixed) -> Fixed:
    if cmp_fixed(lower, upper) > 0:
        raise ValueError("lower bound must be <= upper bound")
    if cmp_fixed(value, lower) < 0:
        return cast(lower, value.ftype)
    if cmp_fixed(value, upper) > 0:
        return cast(upper, value.ftype)
    return value


def mux(select: bool, when_true: Fixed, when_false: Fixed) -> Fixed:
    return when_true if select else when_false


# Short aliases often used by ISA code generation.
shl = shift_left
shr_arith = shift_right_arith
shr_logical = shift_right_logical
abs_sat = abs_fixed
cmp = cmp_fixed


def run_selftest() -> dict:
    """Run deterministic fixed-point self-checks used by `nema selftest fixed`."""
    failures: list[dict] = []
    checks = 0

    def expect(name: str, got: int, want: int) -> None:
        nonlocal checks
        checks += 1
        if got != want:
            failures.append({"name": name, "got": got, "want": want})

    s8q4 = FixedType.signed_type(int_bits=3, frac_bits=4, total_bits=8)
    expect(
        "sat_add_max",
        add(Fixed.from_raw(s8q4, s8q4.raw_max), Fixed.from_raw(s8q4, 1)).raw,
        s8q4.raw_max,
    )
    expect(
        "sat_sub_min",
        sub(Fixed.from_raw(s8q4, s8q4.raw_min), Fixed.from_raw(s8q4, 1)).raw,
        s8q4.raw_min,
    )

    s8q2 = FixedType.signed_type(int_bits=5, frac_bits=2, total_bits=8)
    expect(
        "mul_rne_tie_up_to_even",
        mul(Fixed.from_raw(s8q2, 2), Fixed.from_raw(s8q2, 3)).raw,
        2,
    )
    expect(
        "mul_rne_tie_stay_even",
        mul(Fixed.from_raw(s8q2, 2), Fixed.from_raw(s8q2, 5)).raw,
        2,
    )
    expect(
        "mac_single_rounding",
        mac(Fixed.from_raw(s8q2, 1), Fixed.from_raw(s8q2, 3), Fixed.from_raw(s8q2, 2)).raw,
        2,
    )

    s8i = FixedType.signed_type(int_bits=7, frac_bits=0, total_bits=8)
    neg2 = Fixed.from_raw(s8i, -2)
    expect("shift_arith", shr_arith(neg2, 1).raw, -1)
    expect("shift_logical", shr_logical(neg2, 1).raw, 127)

    return {
        "ok": not failures,
        "suite": "fixed",
        "checks": checks,
        "failures": failures,
    }
