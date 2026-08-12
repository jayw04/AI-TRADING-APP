"""The registered economic gap filter (A1-F2 correction).

The frozen construction, registered in preregistration v0.4 under "Price-series policy (V3,
verified)" and reachable through the signed v1.0 authority chain:

    economic_gap_t+1 = (open_t+1 + known_cash_distribution_t+1) / close_t - 1
    entry cancelled at the t+1 open if |economic_gap_t+1| >= 6%

`open` and `close` are the split-adjusted, non-dividend-adjusted pair; the distribution term is the
ACTIONS dividend value, confirmed on the same split basis as the SEP close (A1-F1, two independent
legs on development data).

This replaces the SPQ-1 enricher's `open / distribution_adjusted_close - 1`, which omitted the
distribution from the numerator and divided by an already-distribution-adjusted close - mixing
adjustment bases, the defect freeze blocker V3 exists to prevent. The reference implementation is
`app/research/mr002/execution.py`; this module is bound by its own hash rather than importing it,
because the mounted layer must be independently enumerable.
"""

from __future__ import annotations

import math

GAP_THRESHOLD = 0.06
"""Frozen v0.3 §4 / v0.4: |economic_gap| >= 6% cancels the entry at the t+1 open."""


class GapInputInvalid(Exception):
    """A gap input is structurally unusable. Never a governed disposition - an integrity refusal."""


def economic_gap(
    open_t_plus_1: float,
    close_t: float,
    known_cash_distribution_t_plus_1: float = 0.0,
) -> float:
    """Return the registered economic gap.

    An ex-dividend drop is not a gap: the cash distribution is added to the execution-session open
    before the comparison, so a price fall equal to the distribution produces a gap of zero.

    Fails closed on structurally invalid inputs rather than returning a sentinel, because a
    non-finite gap silently compared against a threshold is how a bad bar becomes a filled order.
    """
    if not (math.isfinite(close_t) and close_t > 0.0):
        raise GapInputInvalid("close_t is non-finite or non-positive")
    if not math.isfinite(open_t_plus_1) or open_t_plus_1 <= 0.0:
        raise GapInputInvalid("open_t+1 is non-finite or non-positive")
    if (
        not math.isfinite(known_cash_distribution_t_plus_1)
        or known_cash_distribution_t_plus_1 < 0.0
    ):
        raise GapInputInvalid("cash distribution is non-finite or negative")
    return (open_t_plus_1 + known_cash_distribution_t_plus_1) / close_t - 1.0


def gap_cancels(gap: float) -> bool:
    """The frozen cancellation test. A non-finite gap cancels: it is never treated as a pass."""
    if not math.isfinite(gap):
        return True
    return abs(gap) >= GAP_THRESHOLD
