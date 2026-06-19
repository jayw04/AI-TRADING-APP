"""Gross-exposure overlay layer (P10 §2, ADR 0020).

The overlay is a pure, stateless, deterministic function of (market returns, params)
→ a scalar gross in [0, 1]. These tests pin: the cap at 1.0 (never leverages), the
de-risking direction (higher vol → lower gross), fail-open on bad/short data, and
determinism — the invariants ADR 0020 makes load-bearing.
"""

from __future__ import annotations

import math

import pytest

from app.strategies.overlay import desired_gross

_SPAN = 20
_TARGET = 0.15


def _const_vol_returns(daily_sigma: float, n: int = 80) -> list[float]:
    """A deterministic ±daily_sigma square wave → realized daily std ≈ daily_sigma."""
    return [daily_sigma if i % 2 == 0 else -daily_sigma for i in range(n)]


def test_low_vol_caps_at_one() -> None:
    """Calm market (realized vol well below target) → no scaling, capped at 1.0
    (never leverages above full investment)."""
    calm = _const_vol_returns(0.001)  # ~1.6% annual << 15% target
    g = desired_gross(market_returns=calm, vol_target_annual=_TARGET, vol_ewma_span=_SPAN)
    assert g == pytest.approx(1.0)


def test_high_vol_scales_down() -> None:
    """Turbulent market (realized vol above target) → gross < 1.0."""
    wild = _const_vol_returns(0.04)  # ~63% annual >> 15% target
    g = desired_gross(market_returns=wild, vol_target_annual=_TARGET, vol_ewma_span=_SPAN)
    assert 0.0 < g < 1.0


def test_higher_vol_means_lower_gross() -> None:
    """Monotonic: the more volatile the proxy, the smaller the gross target."""
    g_mid = desired_gross(market_returns=_const_vol_returns(0.02),
                          vol_target_annual=_TARGET, vol_ewma_span=_SPAN)
    g_high = desired_gross(market_returns=_const_vol_returns(0.05),
                           vol_target_annual=_TARGET, vol_ewma_span=_SPAN)
    assert g_high < g_mid < 1.0


def test_deterministic() -> None:
    """Identical inputs → identical output (ADR 0020 determinism invariant)."""
    wild = _const_vol_returns(0.04)
    a = desired_gross(market_returns=wild, vol_target_annual=_TARGET, vol_ewma_span=_SPAN)
    b = desired_gross(market_returns=list(wild), vol_target_annual=_TARGET, vol_ewma_span=_SPAN)
    assert a == b


@pytest.mark.parametrize("returns", [[], [0.01], [float("nan"), 0.01]])
def test_fail_open_on_insufficient_history(returns: list[float]) -> None:
    """< 2 finite returns → fail open to gross = 1.0 (no scaling)."""
    g = desired_gross(market_returns=returns, vol_target_annual=_TARGET, vol_ewma_span=_SPAN)
    assert g == 1.0


def test_fail_open_on_zero_vol() -> None:
    """A flat series (σ = 0) → fail open to 1.0 rather than divide by zero."""
    g = desired_gross(market_returns=[0.0] * 40, vol_target_annual=_TARGET, vol_ewma_span=_SPAN)
    assert g == 1.0


def test_nonpositive_target_disables() -> None:
    """A non-positive target means 'no overlay' → 1.0."""
    wild = _const_vol_returns(0.04)
    assert desired_gross(market_returns=wild, vol_target_annual=0.0, vol_ewma_span=_SPAN) == 1.0
    assert desired_gross(market_returns=wild, vol_target_annual=-0.1, vol_ewma_span=_SPAN) == 1.0


def test_output_always_in_unit_interval() -> None:
    """Whatever the inputs, the result is a finite scalar in [0, 1]."""
    for sigma in (0.0005, 0.005, 0.05, 0.2):
        g = desired_gross(market_returns=_const_vol_returns(sigma),
                          vol_target_annual=_TARGET, vol_ewma_span=_SPAN)
        assert math.isfinite(g) and 0.0 <= g <= 1.0
