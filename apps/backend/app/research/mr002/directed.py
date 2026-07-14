"""MR-002 — DIRECTED (OUTWARD) BINARY64 SERIALIZATION. The one implementation.

A rigorous bound stops being a bound the moment it is rounded the wrong way. An interval carries the
truth at >= 100 digits; the artifact carries a binary64. That last step is where rigor is silently
lost, so it gets its own module, its own fixtures, and no second implementation.

    lower endpoint  ->  round toward NEGATIVE infinity   (largest double <= the true value)
    upper endpoint  ->  round toward POSITIVE infinity   (smallest double >= the true value)

WHAT WENT WRONG, AND WHY "NEARLY RIGHT" WAS NOT RIGHT
-----------------------------------------------------
Three serializers exist in this program's history. Only the third is correct.

  L  `float(x)`                              NEAREST. THE DEFECT. Rounds a rigorous upper bound DOWN
                                             by up to half an ulp, at which point it is not an upper
                                             bound. The gate then compares against a number smaller
                                             than the true one and can PASS something that should
                                             FAIL. This is the dangerous direction.

  N  `math.nextafter(float(x), +-inf)`       Rigorous, but not correctly rounded. It always moves a
                                             full ulp, so it is 1 ulp loose on an exactly-representable
                                             value and up to 2 ulps loose when `float()` already
                                             rounded outward. Worse, it turns an exact ZERO lower
                                             endpoint into -5e-324 — a spurious negative in a quantity
                                             (the stationarity energy) that is mathematically >= 0.
                                             Safe, but it reports a bound looser than the arithmetic
                                             actually proved.

  D  this module                             CORRECTLY DIRECTED. The tightest double on the correct
                                             side. Exactly representable values serialize to
                                             themselves. Zero stays zero.

The decision is made by EXACT RATIONAL COMPARISON — never by comparing two floats, and never by
trusting `float()` to have rounded the way we hoped. `float()` proposes; the rational comparison
disposes.

NON-FINITE IS A STOP, NOT A BOUND. `+inf` is a formally valid upper bound and a useless one: it would
let every gate pass. An authoritative endpoint that is NaN, infinite, or overflows binary64 means the
arithmetic upstream is broken, and this module refuses rather than serializing a vacuous bound.
"""

from __future__ import annotations

import math
from fractions import Fraction

from mpmath import libmp, mpf

__all__ = [
    "SerializationDefect",
    "as_fraction",
    "legacy_nearest_dn",
    "legacy_nearest_up",
    "legacy_nextafter_dn",
    "legacy_nextafter_up",
    "to_binary64_dn",
    "to_binary64_up",
]


class SerializationDefect(RuntimeError):
    """An authoritative endpoint that cannot be serialized to a finite binary64 bound.

    NaN, infinite, or overflowing. Not a rounding question — the arithmetic that produced it is
    broken, and a vacuous bound would hide that.
    """


def as_fraction(v) -> Fraction:
    """An mpmath number as its EXACT rational value. No precision assumption, no re-rounding.

    ⚠ THE TRAP THIS FUNCTION EXISTS TO AVOID. The endpoints of an `iv.mpf` are `ivmpf` objects, NOT
    `mpf`. Coercing one with `mpf(v)` converts it at the CURRENT `mp` precision — which defaults to
    15 decimal digits. A 336-bit interval endpoint silently becomes a 53-bit one, i.e. it is rounded
    to double BEFORE anything gets to reason about how to round it to double. Every serializer then
    agrees with every other, the correction reports zero difference everywhere, and the zero means
    nothing. Measured: `mpf(iv.mpf(1)/iv.mpf(3)).b` -> 53 bits, from 336.

    So the raw binary representation is read directly. mpmath numbers are (sign, mantissa, exponent)
    triples, so `to_rational` is exact — unlike `float()`, `str()` or an `mpf()` round-trip, all of
    which round.
    """
    if isinstance(v, Fraction):
        return v
    if isinstance(v, int):
        return Fraction(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise SerializationDefect(f"non-finite float endpoint {v!r}")
        return Fraction(*v.as_integer_ratio())

    if hasattr(v, "_mpi_"):                      # an mpmath INTERVAL (ivmpf)
        lo, hi = v._mpi_
        if lo != hi:
            raise SerializationDefect(
                "as_fraction was handed a NON-DEGENERATE interval, not an endpoint. Serialize `.a` "
                "or `.b` — serializing an interval would have to pick an endpoint silently, and the "
                "whole point of directed rounding is that the choice is never silent.")
        raw = lo
    elif hasattr(v, "_mpf_"):                    # a plain mpmath float
        raw = v._mpf_
    else:
        x = mpf(v)
        raw = x._mpf_

    if raw == libmp.fnan:
        raise SerializationDefect("NaN endpoint — the upstream arithmetic is broken")
    if raw in (libmp.finf, libmp.fninf):
        raise SerializationDefect(
            "infinite endpoint — a formally valid bound that proves nothing; STOP rather than "
            "serialize a vacuous one")
    p, q = libmp.to_rational(raw)
    return Fraction(p, q)


def _directed(v, up: bool) -> float:
    exact = as_fraction(v)

    # `float()` PROPOSES a candidate by rounding to nearest. It is never trusted: the exact rational
    # comparison below decides whether it actually landed on the correct side.
    #
    # ⚠ Do NOT render the offending value with float() in the error message — that is the very call
    # that just overflowed, so the handler would raise the error it is handling. Report the magnitude
    # from the exact rational's bit length instead, which cannot overflow.
    try:
        cand = float(exact)
    except OverflowError as exc:
        raise SerializationDefect(
            f"endpoint overflows binary64 (numerator {exact.numerator.bit_length()} bits, "
            f"denominator {exact.denominator.bit_length()} bits) — no finite bound exists") from exc
    if math.isinf(cand):
        raise SerializationDefect("endpoint overflows binary64 — no finite bound exists")

    got = Fraction(*cand.as_integer_ratio())
    if up:
        if got >= exact:
            return cand                       # already on the correct side (often exactly equal)
        nxt = math.nextafter(cand, math.inf)
        if math.isinf(nxt):
            raise SerializationDefect("upper bound overflows binary64")
        return nxt
    if got <= exact:
        return cand
    nxt = math.nextafter(cand, -math.inf)
    if math.isinf(nxt):
        raise SerializationDefect("lower bound overflows binary64")
    return nxt


def to_binary64_up(x) -> float:
    """The SMALLEST binary64 >= the true value. Accepts an interval (uses its upper endpoint), an
    mpmath number, an exact Fraction, or a float."""
    return _directed(getattr(x, "b", x), up=True)


def to_binary64_dn(x) -> float:
    """The LARGEST binary64 <= the true value. Accepts an interval (uses its lower endpoint)."""
    return _directed(getattr(x, "a", x), up=False)


# ======================================================================================
# The superseded serializers. RETAINED, and used ONLY by the correction harness, which has to
# reproduce what the defective and the merely-loose paths would have written in order to prove that
# no Boolean verdict depended on the difference. Nothing in the evidentiary path may call these.
# ======================================================================================
def legacy_nearest_up(x) -> float:
    """L — THE DEFECT, on an upper endpoint. Round-to-nearest can land BELOW the true value, at which
    point it is not an upper bound and the gate compares against a number smaller than the truth."""
    return float(as_fraction(getattr(x, "b", x)))


def legacy_nearest_dn(x) -> float:
    """L — THE DEFECT, on a lower endpoint. Round-to-nearest can land ABOVE the true value."""
    return float(as_fraction(getattr(x, "a", x)))


def legacy_nextafter_up(x) -> float:
    """N — rigorous but always a full ulp out, and 2 ulps when float() already rounded outward."""
    return math.nextafter(float(as_fraction(getattr(x, "b", x))), math.inf)


def legacy_nextafter_dn(x) -> float:
    """N — as above; also turns an exact zero into -5e-324."""
    return math.nextafter(float(as_fraction(getattr(x, "a", x))), -math.inf)
