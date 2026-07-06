"""Portfolio weight invariants (P10 Phase 3A §4.3).

Mathematical properties every portfolio weight vector must satisfy, *regardless* of
the weighting method that produced it. Enforced by the backtester's weigher (PR B)
and tested independently of method. A violation is a hard error — a silently-wrong
book is worse than a loud failure.

This module is deliberately tiny and dependency-free (math only) so both the
factor-data backtester and the Research Engine can import it without coupling.
"""

from __future__ import annotations

import math


class PortfolioInvariantError(ValueError):
    """A weight vector violated a portfolio invariant."""


def assert_valid_weights(
    weights: dict[str, float],
    *,
    cash: float = 0.0,
    target_gross: float = 1.0,
    long_only: bool = True,
    tolerance: float = 1e-6,
) -> None:
    """Validate one weight vector; raise ``PortfolioInvariantError`` on any violation.

    Invariants checkable on a single vector (hold for ANY weighting method):

    - **finiteness** — no NaN / inf weights (or cash).
    - **sign** — no negative weights when ``long_only`` (within ``tolerance``).
    - **explicit cash** — ``sum(weights) + cash == target_gross`` (within
      ``tolerance``). Cash is explicit, never an implicit residual.

    The remaining documented invariants — *deterministic ordering for identical
    scores*, *stable results for identical inputs*, *deterministic turnover* — are
    properties of the **caller** (same inputs → same dict), not observable from a
    single vector, so they are asserted by tests (the prefix-invariance / repeat-run
    tests), not here.
    """
    weight_sum = 0.0
    for t, w in weights.items():
        if not isinstance(w, (int, float)) or not math.isfinite(w):
            raise PortfolioInvariantError(f"non-finite weight for {t!r}: {w!r}")
        if long_only and w < -tolerance:
            raise PortfolioInvariantError(f"negative weight for {t!r} in long-only book: {w}")
        weight_sum += w
    if not math.isfinite(cash):
        raise PortfolioInvariantError(f"non-finite cash: {cash!r}")
    total = weight_sum + cash
    if abs(total - target_gross) > tolerance:
        raise PortfolioInvariantError(
            f"weights ({weight_sum}) + cash ({cash}) = {total} != target_gross "
            f"{target_gross} (tolerance {tolerance})"
        )
