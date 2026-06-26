"""Factor Lab ProgramSpec — defaults + validation (plan v0.2 §3.1)."""

from __future__ import annotations

from datetime import date

import pytest

from app.research.factor_lab.spec import ProgramSpec, VerdictSpec


def _spec(**over) -> ProgramSpec:
    base = dict(
        id="X-001", name="Example", philosophy="test",
        factor="momentum", factor_params={"lookback_days": 252, "skip_days": 0},
        n=200, start=date(2000, 1, 1), end=date(2026, 6, 12),
        verdict=VerdictSpec(rules=(), default_outcome="D", default_action="-"),
    )
    base.update(over)
    return ProgramSpec(**base)


def test_defaults_are_the_standard_quantile_book() -> None:
    s = _spec()
    assert s.construction == "quantile"
    assert s.top_quantile == 0.20
    assert s.weighting == "equal_weight"
    assert s.baseline == "equal_weight"
    assert s.seed == 17 and s.bootstrap == 2000 and s.windows == 5


def test_rejects_unknown_construction() -> None:
    with pytest.raises(ValueError, match="construction"):
        _spec(construction="magic")


def test_rejects_unknown_baseline() -> None:
    with pytest.raises(ValueError, match="baseline"):
        _spec(baseline="spy_only")


def test_rejects_bad_top_quantile() -> None:
    with pytest.raises(ValueError, match="top_quantile"):
        _spec(top_quantile=0.0)
    with pytest.raises(ValueError, match="top_quantile"):
        _spec(top_quantile=1.5)


def test_participation_and_sector_baskets_are_valid() -> None:
    assert _spec(construction="participation").construction == "participation"
    assert _spec(construction="sector_baskets").construction == "sector_baskets"
    assert _spec(baseline="regime_filter").baseline == "regime_filter"
