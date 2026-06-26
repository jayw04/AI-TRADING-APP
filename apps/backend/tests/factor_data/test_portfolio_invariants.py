"""Phase 3A §4.3 — portfolio weight invariants (hold for ANY weighting method)."""

from __future__ import annotations

import math

import pytest

from app.factor_data.portfolio import PortfolioInvariantError, assert_valid_weights


def test_fully_invested_equal_weight_ok() -> None:
    assert_valid_weights({"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25})


def test_inverse_vol_like_weights_sum_to_one_ok() -> None:
    raw = {"A": 1 / 0.1, "B": 1 / 0.2, "C": 1 / 0.4}
    s = sum(raw.values())
    assert_valid_weights({k: v / s for k, v in raw.items()})


def test_explicit_cash_buffer_ok() -> None:
    assert_valid_weights({"A": 0.49, "B": 0.49}, cash=0.02)


def test_weights_not_summing_to_target_raises() -> None:
    with pytest.raises(PortfolioInvariantError, match="target_gross"):
        assert_valid_weights({"A": 0.5, "B": 0.3})            # sums to 0.8, no cash


def test_implicit_residual_rejected() -> None:
    # 0.8 invested with NO declared cash must fail — cash must be explicit.
    with pytest.raises(PortfolioInvariantError):
        assert_valid_weights({"A": 0.8}, cash=0.0)


def test_negative_weight_rejected_long_only() -> None:
    with pytest.raises(PortfolioInvariantError, match="negative"):
        assert_valid_weights({"A": 1.2, "B": -0.2})


def test_negative_weight_allowed_when_not_long_only() -> None:
    assert_valid_weights({"A": 1.2, "B": -0.2}, long_only=False)


def test_nan_weight_rejected() -> None:
    with pytest.raises(PortfolioInvariantError, match="non-finite"):
        assert_valid_weights({"A": float("nan"), "B": 1.0})


def test_inf_weight_rejected() -> None:
    with pytest.raises(PortfolioInvariantError, match="non-finite"):
        assert_valid_weights({"A": math.inf})


def test_custom_target_gross_ok() -> None:
    assert_valid_weights({"A": 0.3, "B": 0.3}, target_gross=0.6)


def test_within_tolerance_ok() -> None:
    assert_valid_weights({"A": 0.5, "B": 0.5 + 5e-7})          # < 1e-6 tol
