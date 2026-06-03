"""Pricing math correctness (P3 Session 1)."""

from __future__ import annotations

from decimal import Decimal

from app.llm.pricing import (
    PRICING_TABLE,
    UNKNOWN_MODEL_PRICING,
    estimate_cost,
    get_pricing,
)


def test_haiku_pricing_known():
    p = get_pricing("claude-haiku-4-5-20251001")
    assert p is PRICING_TABLE["claude-haiku-4-5-20251001"]


def test_unknown_model_returns_high_fallback():
    p = get_pricing("claude-totally-fake")
    assert p is UNKNOWN_MODEL_PRICING
    # Fallback is at least as expensive as the priciest model in the table.
    opus = PRICING_TABLE["claude-opus-4-7"]
    assert p.input_per_million_usd >= opus.input_per_million_usd
    assert p.output_per_million_usd >= opus.output_per_million_usd


def test_estimate_cost_zero_tokens_returns_zero():
    assert estimate_cost("claude-haiku-4-5-20251001", 0, 0) == Decimal("0")


def test_estimate_cost_negative_tokens_treated_as_zero():
    assert estimate_cost("claude-haiku-4-5-20251001", -10, -20) == Decimal("0")


def test_estimate_cost_haiku_known_value():
    # 1M input + 1M output at Haiku rates = $0.80 + $4.00 = $4.80
    cost = estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    assert cost == Decimal("4.8000")


def test_estimate_cost_haiku_typical_turn():
    # 2000 input + 500 output:
    #   Input:  2000 / 1M * $0.80 = $0.0016
    #   Output: 500 / 1M * $4.00 = $0.002
    #   Total:                     $0.0036
    cost = estimate_cost("claude-haiku-4-5-20251001", 2000, 500)
    assert cost == Decimal("0.0036")


def test_estimate_cost_sonnet_typical_turn():
    # 2000 input + 500 output at Sonnet rates:
    #   Input:  2000 / 1M * $3.00  = $0.006
    #   Output: 500 / 1M * $15.00 = $0.0075
    #   Total:                       $0.0135
    cost = estimate_cost("claude-sonnet-4-6", 2000, 500)
    assert cost == Decimal("0.0135")


def test_estimate_cost_rounds_half_up():
    # Haiku output: 33 tokens at $4/M = 33 * 0.000004 = $0.000132 → rounds to $0.0001.
    cost = estimate_cost("claude-haiku-4-5-20251001", 0, 33)
    assert cost == Decimal("0.0001")


def test_estimate_cost_uses_fallback_for_unknown_model():
    # 1000 input at $15/M fallback = $0.0150
    cost = estimate_cost("phantom-model-2030", 1000, 0)
    assert cost == Decimal("0.0150")
