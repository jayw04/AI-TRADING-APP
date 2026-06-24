"""Factor Lab unified runner — end-to-end on a synthetic store (plan v0.2 §3.3).

Exercises the whole pipeline (score → backtest → H1/H2/H3 → walk-forward → cost sweep →
verdict → evidence package) and checks the package is well-formed and the verdict is one
of A/B/C/D. Real-data byte-equivalence vs the committed verdicts is the §5 acceptance
gate (run offline).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from app.factor_data.store import FactorDataStore
from app.research.factor_lab.configs import LOW_001, TREND_001
from app.research.factor_lab.runner import run_program

# A small, fast spec over the synthetic store's recent window (enough history for the
# 252d momentum/vol lookbacks; small bootstrap/windows for speed).
_SMALL = replace(
    LOW_001, n=24, start=date(2019, 9, 2), end=date(2020, 6, 30),
    windows=2, bootstrap=60,
)
# Same window for the participation (TREND) path — enough history for the 200d SMA /
# 200d breadth MA before the first rebalance.
_SMALL_TREND = replace(
    TREND_001, n=24, start=date(2019, 9, 2), end=date(2020, 6, 30),
    windows=2, bootstrap=60,
)

_VALID_OUTCOMES = {"A - Validated", "B - Diversifier / Defensive",
                   "C - Rejected", "D - Inconclusive"}


def test_run_program_end_to_end(volatile_store: FactorDataStore) -> None:
    r = run_program(_SMALL, store=volatile_store)
    # books
    assert set(r["books"]) == {"program", "momentum", "equal_weight", "blend"}
    for b in r["books"].values():
        assert {"cagr", "sharpe", "max_drawdown", "calmar"} <= set(b)
    # hypotheses present
    assert {"delta", "ci_low", "ci_high"} <= set(r["H1_vs_eqw"])
    assert {"delta", "ci_low", "ci_high"} <= set(r["H2_blend_vs_momentum"])
    assert "H3_maxdd_vs_momentum" in r and "H3_maxdd_vs_eqw" in r
    assert r["cost_sweep_sharpe"].keys() == {"5bps", "10bps", "20bps", "50bps"}
    assert len(r["walk_forward"]) == 2
    # verdict
    assert r["outcome"] in _VALID_OUTCOMES
    assert r["metrics"]["beats_regime"] is False  # quantile path, no regime control


def test_run_program_is_deterministic(volatile_store: FactorDataStore) -> None:
    a = run_program(_SMALL, store=volatile_store)
    b = run_program(_SMALL, store=volatile_store)
    assert a["H1_vs_eqw"] == b["H1_vs_eqw"]
    assert a["outcome"] == b["outcome"]
    assert a["books"] == b["books"]


def test_participation_run_program_end_to_end(volatile_store: FactorDataStore) -> None:
    r = run_program(_SMALL_TREND, store=volatile_store)
    # books: the trend pipeline reports trend / momentum / blend / eqw / regime control
    assert set(r["books"]) == {"momentum", "trend", "blend", "equal_weight", "regime_eqw"}
    for b in r["books"].values():
        assert {"cagr", "sharpe", "max_drawdown", "calmar"} <= set(b)
    # hypotheses + the regime competing-explanation control
    assert {"delta", "ci_low", "ci_high"} <= set(r["H1_vs_eqw"])
    assert "H3_maxdd_vs_regime_filter" in r and "H3_sharpe_vs_regime_filter" in r
    assert isinstance(r["beats_regime_filter"], bool)
    # participation mechanism: gross exposure reported, ≤ 1 (cash-aware book)
    assert r["participation_gross_mean"] is None or 0.0 <= r["participation_gross_mean"] <= 1.0
    assert r["cost_sweep_sharpe"].keys() == {"5bps", "10bps", "20bps", "50bps"}
    assert len(r["walk_forward"]) == 2
    assert r["outcome"] in _VALID_OUTCOMES
    assert "beats_regime" in r["metrics"] and "subsumed" in r["metrics"]


def test_participation_is_deterministic(volatile_store: FactorDataStore) -> None:
    a = run_program(_SMALL_TREND, store=volatile_store)
    b = run_program(_SMALL_TREND, store=volatile_store)
    assert a["books"] == b["books"]
    assert a["outcome"] == b["outcome"]
    assert a["H1_vs_eqw"] == b["H1_vs_eqw"]


def test_unsupported_construction_raises(volatile_store: FactorDataStore) -> None:
    # sector_baskets is the construction still pending
    with pytest.raises(NotImplementedError, match="construction"):
        run_program(replace(_SMALL, construction="sector_baskets"), store=volatile_store)
    # participation requires the regime_filter baseline
    with pytest.raises(NotImplementedError, match="regime_filter"):
        run_program(replace(_SMALL_TREND, baseline="equal_weight"), store=volatile_store)
    # quantile rejects a non-equal_weight baseline
    with pytest.raises(NotImplementedError, match="baseline"):
        run_program(replace(_SMALL, baseline="regime_filter"), store=volatile_store)
