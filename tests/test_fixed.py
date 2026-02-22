from __future__ import annotations

from nema.fixed import (
    Fixed,
    FixedType,
    abs_fixed,
    add,
    clip,
    cmp_fixed,
    mac,
    mul,
    mux,
    shift_left,
    shift_right_arith,
    shift_right_logical,
    sub,
)


def test_saturating_add_sub_at_signed_limits() -> None:
    t = FixedType.signed_type(int_bits=3, frac_bits=4, total_bits=8)
    max_v = Fixed.from_raw(t, t.raw_max)
    min_v = Fixed.from_raw(t, t.raw_min)
    one_lsb = Fixed.from_raw(t, 1)

    assert add(max_v, one_lsb).raw == t.raw_max
    assert sub(min_v, one_lsb).raw == t.raw_min
    assert sub(max_v, Fixed.from_raw(t, -1)).raw == t.raw_max
    assert add(min_v, Fixed.from_raw(t, -1)).raw == t.raw_min


def test_saturating_add_sub_at_unsigned_limits() -> None:
    t = FixedType.unsigned_type(int_bits=4, frac_bits=4, total_bits=8)
    max_v = Fixed.from_raw(t, t.raw_max)
    zero = Fixed.from_raw(t, 0)
    one_lsb = Fixed.from_raw(t, 1)

    assert add(max_v, one_lsb).raw == t.raw_max
    assert sub(zero, one_lsb).raw == 0


def test_mul_sign_coverage() -> None:
    t = FixedType.signed_type(int_bits=5, frac_bits=2, total_bits=8)
    pos = Fixed.from_raw(t, 3)   # 0.75
    one = Fixed.from_raw(t, 4)   # 1.00
    neg = Fixed.from_raw(t, -3)  # -0.75
    neg_one = Fixed.from_raw(t, -4)

    assert mul(pos, one).raw == 3
    assert mul(neg, one).raw == -3
    assert mul(neg, neg_one).raw == 3


def test_mul_rne_ties_to_even() -> None:
    t = FixedType.signed_type(int_bits=5, frac_bits=2, total_bits=8)
    half = Fixed.from_raw(t, 2)          # 0.50
    three_quarters = Fixed.from_raw(t, 3)  # 0.75
    one_and_quarter = Fixed.from_raw(t, 5)  # 1.25

    # 0.5 * 0.75 = 0.375  -> tie between 0.25 (raw 1) and 0.5 (raw 2), choose even raw 2.
    assert mul(half, three_quarters).raw == 2
    # 0.5 * 1.25 = 0.625 -> tie between 0.5 (raw 2) and 0.75 (raw 3), choose even raw 2.
    assert mul(half, one_and_quarter).raw == 2
    # Negative tie should be symmetric.
    assert mul(Fixed.from_raw(t, -2), three_quarters).raw == -2


def test_mul_overflow_saturates() -> None:
    t = FixedType.signed_type(int_bits=2, frac_bits=1, total_bits=4)

    assert mul(Fixed.from_raw(t, 7), Fixed.from_raw(t, 7)).raw == t.raw_max
    assert mul(Fixed.from_raw(t, -8), Fixed.from_raw(t, 7)).raw == t.raw_min


def test_mac_rne_single_rounding() -> None:
    t = FixedType.signed_type(int_bits=5, frac_bits=2, total_bits=8)
    acc = Fixed.from_raw(t, 1)   # 0.25
    a = Fixed.from_raw(t, 3)     # 0.75
    b = Fixed.from_raw(t, 2)     # 0.50

    # Exact: 0.25 + (0.75 * 0.5) = 0.625 -> tie, RNE picks raw 2 (0.5).
    assert mac(acc, a, b).raw == 2


def test_mac_overflow_saturates() -> None:
    t = FixedType.signed_type(int_bits=2, frac_bits=1, total_bits=4)

    assert mac(Fixed.from_raw(t, 7), Fixed.from_raw(t, 7), Fixed.from_raw(t, 7)).raw == t.raw_max
    assert mac(Fixed.from_raw(t, -8), Fixed.from_raw(t, -8), Fixed.from_raw(t, 7)).raw == t.raw_min


def test_shift_behavior() -> None:
    s8i = FixedType.signed_type(int_bits=7, frac_bits=0, total_bits=8)
    neg2 = Fixed.from_raw(s8i, -2)

    assert shift_right_arith(neg2, 1).raw == -1
    assert shift_right_logical(neg2, 1).raw == 127
    assert shift_left(Fixed.from_raw(s8i, 100), 1).raw == s8i.raw_max


def test_abs_clip_cmp_mux_utilities() -> None:
    s8q4 = FixedType.signed_type(int_bits=3, frac_bits=4, total_bits=8)
    s8q2 = FixedType.signed_type(int_bits=5, frac_bits=2, total_bits=8)

    assert abs_fixed(Fixed.from_raw(s8q4, s8q4.raw_min)).raw == s8q4.raw_max

    x = Fixed.from_raw(s8q4, -32)
    lo = Fixed.from_raw(s8q4, -16)
    hi = Fixed.from_raw(s8q4, 16)
    assert clip(x, lo, hi).raw == lo.raw

    half_q4 = Fixed.from_raw(s8q4, 8)  # 0.5
    half_q2 = Fixed.from_raw(s8q2, 2)  # 0.5
    assert cmp_fixed(half_q4, half_q2) == 0
    assert cmp_fixed(Fixed.from_raw(s8q4, 9), half_q2) == 1

    a = Fixed.from_raw(s8q4, 11)
    b = Fixed.from_raw(s8q4, -11)
    assert mux(True, a, b).raw == a.raw
    assert mux(False, a, b).raw == b.raw
