"""MR-002 — directed (outward) binary64 serialization (owner ruling §8).

A bound stops being a bound the moment it is rounded the wrong way, and that is the ONE place in this
program where >= 100 digits of rigorous interval arithmetic collapses to 53 bits. So the serializer
is fixtured against its own edge cases rather than against the values it happens to meet in the
corpus — a value that never appears today appears the day the corpus changes.

The tests assert against the EXACT RATIONAL truth, never against another float. Comparing two floats
to check a float-rounding rule assumes the thing under test.

Three serializers are covered because all three exist in this program's history and the correction
record has to reproduce each:

    L  float(x)                       NEAREST — the defect. Not a bound in either direction.
    N  nextafter(float(x), +-inf)     rigorous, but a full ulp loose, and it maps an exact 0 to
                                      -5e-324 on the lower side.
    D  to_binary64_up / _dn           correctly rounded. The tightest double on the correct side.
"""

from __future__ import annotations

import math
import struct
import sys
from fractions import Fraction

import pytest
from mpmath import iv, mp, mpf

from app.research.mr002.directed import (
    SerializationDefect,
    as_fraction,
    legacy_nearest_dn,
    legacy_nearest_up,
    legacy_nextafter_dn,
    legacy_nextafter_up,
    to_binary64_dn,
    to_binary64_up,
)

mp.dps = 120
iv.dps = 100


def ulp(x: float) -> float:
    return math.nextafter(abs(x), math.inf) - abs(x) if x else 5e-324


def next_up(x: float) -> float:
    return math.nextafter(x, math.inf)


def next_dn(x: float) -> float:
    return math.nextafter(x, -math.inf)


def between(a: float, b: float) -> Fraction:
    """An exact rational strictly BETWEEN two adjacent doubles — representable by neither."""
    return (Fraction(*a.as_integer_ratio()) + Fraction(*b.as_integer_ratio())) / 2


# =====================================================================================
# §8.1 / §8.2 — the defect, in both directions
# =====================================================================================
def test_a_positive_upper_endpoint_that_NEAREST_would_round_DOWN():
    """The dangerous case. The true value sits just above a double, so nearest rounds DOWN and the
    'upper bound' is now BELOW the truth. A gate then compares against a number smaller than the
    real one and can pass what should fail."""
    d = 1.0
    true = Fraction(*d.as_integer_ratio()) + Fraction(1, 10 ** 25)   # a hair above 1.0

    assert legacy_nearest_up(mpf(1) + mpf(1) / mpf(10) ** 25) == d   # L: rounds DOWN to 1.0
    assert Fraction(*d.as_integer_ratio()) < true, "L is BELOW the true value — not an upper bound"

    up = to_binary64_up(true)
    assert Fraction(*up.as_integer_ratio()) >= true                  # D: a genuine upper bound
    assert up == next_up(d)                                          # and the TIGHTEST one


def test_a_negative_lower_endpoint_that_NEAREST_would_round_UP():
    """The mirror image. The true value sits just below -1.0, nearest rounds UP to -1.0, and the
    'lower bound' is now ABOVE the truth."""
    d = -1.0
    true = Fraction(*d.as_integer_ratio()) - Fraction(1, 10 ** 25)   # a hair below -1.0

    assert legacy_nearest_dn(mpf(-1) - mpf(1) / mpf(10) ** 25) == d  # L: rounds UP to -1.0
    assert Fraction(*d.as_integer_ratio()) > true, "L is ABOVE the true value — not a lower bound"

    dn = to_binary64_dn(true)
    assert Fraction(*dn.as_integer_ratio()) <= true
    assert dn == next_dn(d)


# =====================================================================================
# §8.3 — an exactly representable endpoint must serialize to ITSELF
# =====================================================================================
@pytest.mark.parametrize("d", [0.0, 1.0, -1.0, 0.5, -0.25, 1e-10, -1e-10, 1e300, -1e300,
                               5e-324, -5e-324, 2.220446049250313e-16])
def test_an_exactly_representable_endpoint_serializes_to_itself(d):
    """Correct directed rounding of a value that IS a double is that double. N moves a full ulp here
    for no reason and reports a bound looser than the arithmetic proved."""
    assert to_binary64_up(mpf(d)) == d
    assert to_binary64_dn(mpf(d)) == d
    if d != 0.0:
        assert legacy_nextafter_up(mpf(d)) != d, "N is loose on an exact value (that is the point)"


def test_the_exact_zero_endpoint_is_not_turned_into_a_spurious_subnormal():
    """N maps a lower endpoint of exactly 0 to -5e-324. The stationarity energy is mathematically
    >= 0, so N reports it as NEGATIVE — a bound that contradicts the mathematics it came from."""
    assert legacy_nextafter_dn(mpf(0)) == -5e-324
    assert to_binary64_dn(mpf(0)) == 0.0
    assert math.copysign(1.0, to_binary64_dn(mpf(0))) == 1.0        # +0.0, not -0.0


# =====================================================================================
# §8.4 — halfway between two adjacent doubles: representable by NEITHER
# =====================================================================================
def test_a_value_exactly_HALFWAY_between_two_doubles():
    """Nearest rounds half-to-even and lands on the wrong side half the time. Directed rounding has
    no ties: up goes up, down goes down, whatever the mantissa's parity."""
    lo = 1.0
    hi = next_up(lo)
    mid = between(lo, hi)
    assert Fraction(*lo.as_integer_ratio()) < mid < Fraction(*hi.as_integer_ratio())

    assert to_binary64_up(mid) == hi
    assert to_binary64_dn(mid) == lo
    assert legacy_nearest_up(mid) == lo, "nearest ties to even -> lands BELOW an upper bound"


def test_a_value_strictly_between_two_doubles_at_the_gate_scale():
    """The scale that actually matters: the signed-gap band is +/-1e-10."""
    lo = 1e-10
    hi = next_up(lo)
    mid = between(lo, hi)
    assert to_binary64_up(mid) == hi
    assert to_binary64_dn(mid) == lo
    assert Fraction(*to_binary64_up(mid).as_integer_ratio()) >= mid
    assert Fraction(*to_binary64_dn(mid).as_integer_ratio()) <= mid


# =====================================================================================
# §8.5 — subnormals, positive and negative
# =====================================================================================
def test_positive_and_negative_SUBNORMAL_endpoints():
    tiny = 5e-324                                     # the smallest positive subnormal
    assert to_binary64_up(mpf(tiny)) == tiny
    assert to_binary64_dn(mpf(tiny)) == tiny

    half = Fraction(*tiny.as_integer_ratio()) / 2     # below every positive double except 0
    assert to_binary64_up(half) == tiny               # smallest double >= it
    assert to_binary64_dn(half) == 0.0                # largest double <= it

    assert to_binary64_up(-half) == -0.0 or to_binary64_up(-half) == 0.0
    assert to_binary64_dn(-half) == -tiny
    assert Fraction(*to_binary64_dn(-half).as_integer_ratio()) <= -half


def test_a_subnormal_gap_between_two_subnormals():
    a, b = 5e-324, 1e-323
    assert next_up(a) == b
    mid = between(a, b)
    assert to_binary64_up(mid) == b
    assert to_binary64_dn(mid) == a


# =====================================================================================
# §8.6 — signed zero
# =====================================================================================
def test_signed_zero_behaviour():
    """+0.0 and -0.0 are the SAME real number. Both must serialize to a bound of zero, and the sign
    bit must not leak into a comparison — `-0.0 <= 0.0` is true but `copysign` is not."""
    for z in (mpf(0), mpf("-0.0")):
        assert to_binary64_up(z) == 0.0
        assert to_binary64_dn(z) == 0.0
        assert as_fraction(z) == 0

    assert struct.pack("<d", to_binary64_dn(mpf(0))) == struct.pack("<d", 0.0)   # +0.0 exactly


# =====================================================================================
# §8.7 — overflow / non-finite is a STOP, not a bound
# =====================================================================================
def test_a_NON_FINITE_endpoint_is_REFUSED_not_serialized():
    """+inf is a formally valid upper bound and a useless one — it would let every gate pass. NaN is
    not a bound at all. Both mean the upstream arithmetic is broken, so they STOP."""
    with pytest.raises(SerializationDefect, match="infinite"):
        to_binary64_up(mpf("inf"))
    with pytest.raises(SerializationDefect, match="infinite"):
        to_binary64_dn(mpf("-inf"))
    with pytest.raises(SerializationDefect, match="NaN"):
        to_binary64_up(mpf("nan"))
    with pytest.raises(SerializationDefect, match="NaN"):
        to_binary64_dn(mpf("nan"))


def test_an_endpoint_that_OVERFLOWS_binary64_is_refused():
    huge = Fraction(10) ** 400                        # finite, but far beyond binary64
    with pytest.raises(SerializationDefect, match="overflow"):
        to_binary64_up(huge)
    with pytest.raises(SerializationDefect, match="overflow"):
        to_binary64_dn(-huge)


def test_the_largest_finite_double_still_serializes():
    big = sys.float_info.max
    assert to_binary64_up(mpf(big)) == big
    assert to_binary64_dn(mpf(big)) == big

    # One ulp past the largest finite double. (Its ulp is 2**971; `nextafter(max, inf)` is `inf`, so
    # the ulp cannot be measured by subtraction — that is how the test itself first overflowed.)
    just_past = Fraction(*big.as_integer_ratio()) + Fraction(2) ** 971
    with pytest.raises(SerializationDefect, match="overflow"):
        to_binary64_up(just_past)
    with pytest.raises(SerializationDefect, match="overflow"):
        to_binary64_dn(-just_past)


# =====================================================================================
# The invariant, over many values: D is ALWAYS a bound, and always the TIGHTEST one
# =====================================================================================
@pytest.mark.parametrize("scale", [1e-300, 1e-100, 1e-17, 1e-10, 1e-3, 1.0, 1e3, 1e100, 1e300])
def test_D_is_always_a_bound_and_always_tightest(scale):
    """The two properties that define correct directed rounding, checked against the exact rational:
        soundness  up >= true >= dn
        tightness  no double lies strictly between the bound and the true value
    """
    for k in (1, 3, 7, 11, 4999):
        for sign in (1, -1):
            true = sign * Fraction(*scale.as_integer_ratio()) * Fraction(k * 10 ** 18 + 1,
                                                                         10 ** 18)
            up, dn = to_binary64_up(true), to_binary64_dn(true)
            fu, fd = Fraction(*up.as_integer_ratio()), Fraction(*dn.as_integer_ratio())
            assert fd <= true <= fu                                   # soundness
            if fu != true:
                assert Fraction(*next_dn(up).as_integer_ratio()) < true    # tightness
            if fd != true:
                assert Fraction(*next_up(dn).as_integer_ratio()) > true


# =====================================================================================
# THE CALL SITE. Everything above feeds the serializer an `mpf` or a `Fraction` — but production
# hands it an `ivmpf` endpoint, and that is a DIFFERENT TYPE with a different failure mode.
# =====================================================================================
def test_a_REAL_interval_endpoint_keeps_its_full_precision():
    """The bug this fixture exists for, and which the mpf-only tests above sailed straight past.

    `iv.mpf(...).b` is an `ivmpf`, not an `mpf`. Coercing it with `mpf(v)` converts at the CURRENT
    `mp` precision — 15 digits by default. A 336-bit endpoint silently becomes 53-bit: rounded to
    double BEFORE anything reasons about how to round it to double. Every serializer then agrees with
    every other, the correction reports zero difference everywhere, and the zero means NOTHING.

    So: take an endpoint that genuinely needs hundreds of bits, and require that we still see them.
    """
    third = iv.mpf(1) / iv.mpf(3)
    ex = as_fraction(third.b)
    assert ex.numerator.bit_length() > 300, (
        f"the interval endpoint arrived with only {ex.numerator.bit_length()} bits — it was rounded "
        f"to double before serialization, and every rounding comparison downstream is vacuous")

    # 1/3 is below its nearest double, so nearest rounds DOWN and D MUST differ from L.
    cand = float(ex)
    assert Fraction(*cand.as_integer_ratio()) < ex
    assert legacy_nearest_up(third) == cand                    # L: not an upper bound
    assert to_binary64_up(third) == next_up(cand)              # D: the bound, one ulp above
    assert to_binary64_up(third) != legacy_nearest_up(third)


def test_L_and_D_DISAGREE_on_real_interval_endpoints_often():
    """If L and D agreed everywhere, the correction would be a no-op and the population sweep would
    be theatre. On genuine high-precision endpoints they disagree roughly half the time — that is the
    signal the sweep is actually measuring something."""
    disagree = 0
    for k in range(1, 101):
        x = iv.mpf(1) / iv.mpf(2 * k + 1)
        if to_binary64_up(x) != legacy_nearest_up(x):
            disagree += 1
    assert 20 <= disagree <= 80, (
        f"L and D differed on {disagree}/100 real interval endpoints — a rate near 0 or 100 means "
        f"the precision is being destroyed before the comparison, not that rounding agrees")


def test_serializing_a_WHOLE_interval_is_refused():
    """`.a` and `.b` are the only sanctioned inputs. Handing over the interval itself would force a
    silent endpoint choice — and the entire point of directed rounding is that the choice is never
    silent."""
    wide = iv.mpf([1.0, 2.0])
    with pytest.raises(SerializationDefect, match="NON-DEGENERATE"):
        as_fraction(wide)


def test_the_LEGACY_nearest_serializer_is_demonstrably_NOT_a_bound():
    """A negative control for the whole correction. If nearest rounding never violated a bound, this
    exercise would be theatre. It does — find a case and show it."""
    violations = 0
    for k in range(1, 400):
        true = Fraction(*(1e-10).as_integer_ratio()) * Fraction(10 ** 12 + k, 10 ** 12)
        near = legacy_nearest_up(mpf(true.numerator) / mpf(true.denominator))
        if Fraction(*near.as_integer_ratio()) < true:
            violations += 1
    assert violations > 0, (
        "round-to-nearest never produced a non-bound in 400 tries — the premise of this correction "
        "would then be false")


def test_all_three_serializers_agree_on_the_ORDERING_that_matters():
    """D is never looser than N, and N is never unsound. Stated as a property because the correction
    record leans on it: if D <= N for upper bounds, then any verdict N passed, D also passes."""
    for k in range(1, 200):
        true = Fraction(*(1e-10).as_integer_ratio()) * Fraction(10 ** 9 + k, 10 ** 9)
        x = mpf(true.numerator) / mpf(true.denominator)
        d_up, n_up = to_binary64_up(true), legacy_nextafter_up(x)
        assert d_up <= n_up                       # D is tighter than (or equal to) N
        assert Fraction(*n_up.as_integer_ratio()) >= true      # N is still sound
        d_dn, n_dn = to_binary64_dn(true), legacy_nextafter_dn(x)
        assert d_dn >= n_dn
        assert Fraction(*n_dn.as_integer_ratio()) <= true
