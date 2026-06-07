"""P8 §2 — scanner criteria: safe evaluation + every rejection class + drift guard."""

from __future__ import annotations

import pytest

from app.indicators.computer import CORE_INDICATORS
from app.services.scanner.criteria import (
    ALLOWED_NAMES,
    CriteriaError,
    evaluate,
    validate_criteria,
)


def test_valid_expression_evaluates_true_and_false() -> None:
    parsed = validate_criteria("RSI14 < 35 and ATR14 / close > 0.02")
    assert parsed.names == frozenset({"RSI14", "ATR14", "close"})
    assert parsed.indicators == frozenset({"RSI14", "ATR14"})
    assert evaluate(parsed, {"RSI14": 30.0, "ATR14": 3.0, "close": 100.0}) is True
    assert evaluate(parsed, {"RSI14": 40.0, "ATR14": 3.0, "close": 100.0}) is False


def test_price_aliases_close_and_field_only_criterion() -> None:
    parsed = validate_criteria("price > 100")
    assert parsed.names == frozenset({"price"})
    assert parsed.indicators == frozenset()  # no indicator to compute
    assert evaluate(parsed, {"price": 150.0}) is True


def test_multi_output_subname_maps_to_core() -> None:
    parsed = validate_criteria("macd > signal and bb_lower < close")
    assert parsed.indicators == frozenset({"MACD", "BB"})


@pytest.mark.parametrize(
    "expr",
    [
        "rsi(14) < 30",  # Call
        "unknown_name < 30",  # unknown Name
        "close.real > 1",  # Attribute
        "close[0] > 1",  # Subscript
        "'AAPL' == close",  # string constant
        "__import__('os')",  # Call + dunder
        "[c for c in close]",  # comprehension
        "close ** 2 > 1",  # Pow operator not allowed
        "close > 1 and True",  # bool constant
        "",  # empty
        "   ",  # whitespace only
        "42",  # references no names
    ],
)
def test_rejections(expr: str) -> None:
    with pytest.raises(CriteriaError):
        validate_criteria(expr)


def test_drift_guard_core_indicators_are_all_allowed() -> None:
    # Every single-output CORE_INDICATORS name + every multi-output sub-name must
    # be referenceable; the allowed set is DERIVED from CORE_INDICATORS, so a new
    # engine indicator that breaks the mapping fails here.
    multi = {"MACD", "BB"}
    for name in CORE_INDICATORS:
        if name in multi:
            continue
        assert name in ALLOWED_NAMES, f"{name} not referenceable"
    for sub in ("macd", "signal", "hist", "bb_lower", "bb_mid", "bb_upper"):
        assert sub in ALLOWED_NAMES
