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


# ---- P10 §4 exposure smoothing -------------------------------------------------

def _calm_then_spike(n_calm: int = 60, n_spike: int = 8) -> list[float]:
    """Calm (±0.1%) for n_calm days, then a fresh vol spike (±5%) at the END — the
    case smoothing is for: a single recent jump shouldn't whipsaw the gross target."""
    return _const_vol_returns(0.001, n_calm) + _const_vol_returns(0.05, n_spike)


def test_smoothing_damps_a_fresh_spike() -> None:
    """After a fresh spike, the raw gross drops hard; the §4-smoothed gross drops
    LESS (it averages in the recent calmer grosses) — so it sits above the raw."""
    rets = _calm_then_spike()
    raw = desired_gross(market_returns=rets, vol_target_annual=_TARGET, vol_ewma_span=_SPAN)
    smoothed = desired_gross(market_returns=rets, vol_target_annual=_TARGET,
                             vol_ewma_span=_SPAN, gross_smooth_span=10)
    assert raw < 1.0                      # the spike did pull gross down
    assert smoothed > raw                 # smoothing tempers the drop
    assert 0.0 <= smoothed <= 1.0


def test_smoothing_default_and_span_one_are_raw() -> None:
    """gross_smooth_span None (default) or ≤1 → no smoothing, byte-identical to §2."""
    rets = _calm_then_spike()
    raw = desired_gross(market_returns=rets, vol_target_annual=_TARGET, vol_ewma_span=_SPAN)
    assert desired_gross(market_returns=rets, vol_target_annual=_TARGET,
                         vol_ewma_span=_SPAN, gross_smooth_span=None) == raw
    assert desired_gross(market_returns=rets, vol_target_annual=_TARGET,
                         vol_ewma_span=_SPAN, gross_smooth_span=1) == raw


def test_smoothing_deterministic_and_in_unit_interval() -> None:
    rets = _calm_then_spike()
    a = desired_gross(market_returns=rets, vol_target_annual=_TARGET,
                      vol_ewma_span=_SPAN, gross_smooth_span=10)
    b = desired_gross(market_returns=list(rets), vol_target_annual=_TARGET,
                      vol_ewma_span=_SPAN, gross_smooth_span=10)
    assert a == b and math.isfinite(a) and 0.0 <= a <= 1.0


# ---- P10 §5 regime modulation (breadth / VIX percentile) -----------------------

# A calm market → vol-target gross caps at 1.0, so the result == the regime factor,
# which lets us assert the regime math directly.
_CALM = _const_vol_returns(0.001)


def test_regime_none_leaves_gross_unchanged() -> None:
    """Default (no regime signals) → byte-identical to the vol-target gross."""
    base = desired_gross(market_returns=_CALM, vol_target_annual=_TARGET, vol_ewma_span=_SPAN)
    withn = desired_gross(market_returns=_CALM, vol_target_annual=_TARGET, vol_ewma_span=_SPAN,
                          breadth=None, vix_percentile=None)
    assert base == withn == 1.0


def test_breadth_ramps_gross_down() -> None:
    """Breadth ≤ floor → factor 0; mid → linear; ≥ full → no cut (defaults 0.3/0.6)."""
    g = lambda b: desired_gross(market_returns=_CALM, vol_target_annual=_TARGET,  # noqa: E731
                                vol_ewma_span=_SPAN, breadth=b)
    assert g(0.20) == 0.0                 # narrow market → fully de-risk
    assert g(0.45) == pytest.approx(0.5)  # halfway up the 0.3→0.6 ramp
    assert g(0.70) == pytest.approx(1.0)  # broad participation → no cut


def test_vix_percentile_ramps_gross_down() -> None:
    """VIX percentile ≤ calm → no cut; mid → linear; ≥ stress → factor 0 (0.5/0.9)."""
    g = lambda v: desired_gross(market_returns=_CALM, vol_target_annual=_TARGET,  # noqa: E731
                                vol_ewma_span=_SPAN, vix_percentile=v)
    assert g(0.40) == pytest.approx(1.0)  # calm
    assert g(0.70) == pytest.approx(0.5)  # halfway up the 0.5→0.9 ramp
    assert g(0.95) == 0.0                 # stress → fully de-risk


def test_worst_regime_signal_governs() -> None:
    """min() — a broad tape (breadth factor 1) can't rescue a VIX stress (factor 0)."""
    g = desired_gross(market_returns=_CALM, vol_target_annual=_TARGET, vol_ewma_span=_SPAN,
                      breadth=0.70, vix_percentile=0.95)
    assert g == 0.0


def test_regime_only_scales_down_never_up() -> None:
    """A healthy regime leaves the (already-capped) gross at 1.0 — never above."""
    g = desired_gross(market_returns=_CALM, vol_target_annual=_TARGET, vol_ewma_span=_SPAN,
                      breadth=0.95, vix_percentile=0.05)
    assert g == 1.0


def test_regime_ignores_nonfinite_signal() -> None:
    """A NaN signal (defensive) is ignored — fail open, no cut."""
    g = desired_gross(market_returns=_CALM, vol_target_annual=_TARGET, vol_ewma_span=_SPAN,
                      breadth=float("nan"))
    assert g == 1.0
