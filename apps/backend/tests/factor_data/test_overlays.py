"""R3 risk overlays: drawdown-control exposure scaling (backtest harness)."""

from __future__ import annotations

from datetime import date, timedelta

from app.factor_data.backtest import (
    DEFAULT_DD_BANDS,
    _drawdown_overlay,
    _scale_for_drawdown,
)


def _curve(equities: list[float]) -> list[tuple[date, float]]:
    d0 = date(2024, 1, 1)
    return [(d0 + timedelta(days=i), e) for i, e in enumerate(equities)]


def test_scale_for_drawdown_bands() -> None:
    assert _scale_for_drawdown(0.0, DEFAULT_DD_BANDS) == 1.0
    assert _scale_for_drawdown(-0.05, DEFAULT_DD_BANDS) == 1.0   # above shallowest band
    assert _scale_for_drawdown(-0.12, DEFAULT_DD_BANDS) == 0.66  # breached −10%
    assert _scale_for_drawdown(-0.17, DEFAULT_DD_BANDS) == 0.50  # breached −15%
    assert _scale_for_drawdown(-0.25, DEFAULT_DD_BANDS) == 0.33  # breached −20%


def test_drawdown_overlay_dampens_the_trough() -> None:
    # A steady ~30% decline then a bounce (curve starts post-initial, as a real
    # book curve does). The overlay de-risks as the drawdown deepens, so its
    # trough is SHALLOWER than the raw book's.
    raw = _curve([90, 80, 70, 77])  # initial_equity is 100
    overlaid = _drawdown_overlay(raw, initial_equity=100.0)
    raw_trough = min(e for _, e in raw)
    ov_trough = min(e for _, e in overlaid)
    assert ov_trough > raw_trough  # exposure cut on the way down → shallower drawdown
    assert overlaid[0][1] == 90.0  # first day: no prior drawdown → full exposure


def test_drawdown_overlay_is_passthrough_when_flat_or_rising() -> None:
    # No drawdown ever → scale stays 1.0 → overlay equals the raw curve.
    rising = _curve([101, 103, 106])  # initial_equity is 100
    overlaid = _drawdown_overlay(rising, initial_equity=100.0)
    assert [round(e, 6) for _, e in overlaid] == [101.0, 103.0, 106.0]


def test_drawdown_overlay_empty_curve() -> None:
    assert _drawdown_overlay([], initial_equity=100.0) == []
