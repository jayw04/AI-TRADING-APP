"""Portfolio Construction Engine — multi-sleeve blend, de-risk overlay, look-through evidence."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.research.factor_lab.portfolio import construct_portfolio, regime_gross_multiplier


def _two_sleeve_returns(n: int = 250, seed: int = 3) -> pd.DataFrame:
    # Two equal-vol, ~uncorrelated sleeves → ERC ≈ 50/50.
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"equity": 0.01 * rng.standard_normal(n), "cross_asset": 0.01 * rng.standard_normal(n)},
        index=idx,
    )


def test_regime_multiplier():
    assert regime_gross_multiplier("GREEN") == 1.0
    assert regime_gross_multiplier("RED") == 0.6
    assert regime_gross_multiplier("BLACK") == 0.3
    assert regime_gross_multiplier("unknown") == 1.0  # never de-risks on an unknown reading


def test_blend_combines_internal_weights_exactly():
    rets = _two_sleeve_returns()
    book = construct_portfolio(
        rets,
        {"equity": {"AAPL": 1.0}, "cross_asset": {"TLT": 0.6, "GLD": 0.4}},
        equity_sleeve="equity",
    )
    sw = book.sleeve_weights
    assert abs(sum(sw.values()) - 1.0) < 1e-9 and all(v > 0 for v in sw.values())
    # book weight = sleeve weight × internal weight (GREEN regime → ×1.0).
    assert abs(book.weights["AAPL"] - sw["equity"] * 1.0) < 1e-12
    assert abs(book.weights["TLT"] - sw["cross_asset"] * 0.6) < 1e-12
    assert abs(book.weights["GLD"] - sw["cross_asset"] * 0.4) < 1e-12
    assert abs(book.gross - 1.0) < 1e-9


def test_cross_sleeve_symbol_is_netted():
    rets = _two_sleeve_returns()
    book = construct_portfolio(
        rets, {"equity": {"SPY": 1.0}, "cross_asset": {"SPY": 0.5, "TLT": 0.5}},
        equity_sleeve="equity",
    )
    sw = book.sleeve_weights
    assert abs(book.weights["SPY"] - (sw["equity"] * 1.0 + sw["cross_asset"] * 0.5)) < 1e-12


def test_correlation_regime_derisks_gross():
    rets = _two_sleeve_returns()
    iw = {"equity": {"AAPL": 1.0}, "cross_asset": {"TLT": 1.0}}
    green = construct_portfolio(rets, iw, equity_sleeve="equity", regime="GREEN")
    red = construct_portfolio(rets, iw, equity_sleeve="equity", regime="RED")
    assert abs(red.gross - 0.6 * green.gross) < 1e-9      # RED ×0.6, de-risk only
    assert red.weights["AAPL"] < green.weights["AAPL"]


def test_lookthrough_evidence_present():
    rets = _two_sleeve_returns()
    book = construct_portfolio(
        rets, {"equity": {"AAPL": 1.0}, "cross_asset": {"TLT": 1.0}}, equity_sleeve="equity",
    )
    assert book.sleeve_correlation is not None           # spec §6.1 — the #1 risk
    assert book.equity_risk_fraction is not None         # spec §6.2 — look-through disclosure
    # equal-risk by construction → each sleeve ≈ half the risk.
    assert 0.4 < book.equity_risk_fraction < 0.6
    assert abs(sum(book.sleeve_risk_contributions.values()) - 1.0) < 1e-9
