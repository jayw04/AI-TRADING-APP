"""ACADEMIC_12_1_MOMENTUM_FACTOR — frozen construction + exact missing-data rules (PREREG v1.0 §6.2).

Secondary attribution benchmark; not configuration-matched to production, not an activation gate.
These tests pin the ratified construction constants and each of the four frozen missing-data rules,
so no post-hoc choice between skipping and holding is possible.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.strategies import academic_momentum_benchmark as amb
from app.strategies.academic_momentum_benchmark import (
    AcademicMomentumBook,
    MomentumScore,
    RebalanceStatus,
    compute_rebalance,
)


def _sc(sym, mom, hist=True):
    return MomentumScore(symbol=sym, momentum_12_1=mom, has_sufficient_history=hist)


# ---- frozen construction ---------------------------------------------------------

def test_frozen_construction_constants():
    assert amb.BENCHMARK_ID == "ACADEMIC_12_1_MOMENTUM_FACTOR"
    assert amb.LOOKBACK_SESSIONS == 252
    assert amb.SKIP_SESSIONS == 21
    assert amb.SELECTION_QUANTILE == 0.10
    assert amb.WEIGHTING == "equal"
    assert amb.REGIME_OVERLAY is False and amb.PRODUCTION_TRIGGERS is False
    assert amb.REBALANCE == "final_eligible_trading_session_of_each_month"
    assert amb.COST_MODEL == "TURNOVER_COST_BPS"


def test_top_decile_selection_is_equal_weight_and_deterministic():
    scores = [_sc(f"S{i}", 1.0 - 0.01 * i) for i in range(20)]  # 20 names → decile = 2
    sel = amb.select_top_decile(scores)
    assert sel == ["S0", "S1"]                                   # top 2 by momentum
    r = compute_rebalance(date(2026, 6, 30), scores, held=set(), priced=set(f"S{i}" for i in range(20)))
    assert r.status is RebalanceStatus.OK
    assert set(r.target_weights) == {"S0", "S1"}
    assert all(v == pytest.approx(0.5) for v in r.target_weights.values())


def test_decile_is_at_least_one_name():
    scores = [_sc("A", 2.0), _sc("B", 1.0), _sc("C", 0.5)]       # 3 names → ceil(0.3)=1
    assert amb.select_top_decile(scores) == ["A"]


def test_month_end_detection():
    assert amb.is_month_end_rebalance(date(2026, 6, 30), date(2026, 7, 1)) is True
    assert amb.is_month_end_rebalance(date(2026, 6, 29), date(2026, 6, 30)) is False
    assert amb.is_month_end_rebalance(date(2026, 6, 30), None) is True   # last session, no next


# ---- rule 1: insufficient signal history → ineligible ----------------------------

def test_rule1_insufficient_history_is_ineligible():
    scores = [_sc("A", 5.0, hist=False), _sc("B", 1.0, hist=True), _sc("C", 0.5, hist=True)]
    # A has the best momentum but insufficient history → excluded despite ranking first
    assert "A" not in amb.select_top_decile(scores)
    assert amb.eligible_by_history(scores) == [scores[1], scores[2]]


# ---- rule 2: missing price on a selected name → retain if held, no target weight --

def test_rule2_selected_but_unpriced_carries_no_target_weight_and_is_retained_if_held():
    scores = [_sc("A", 3.0), _sc("B", 2.0), _sc("C", 1.0), _sc("D", 0.5), _sc("E", 0.2),
              _sc("F", 0.1), _sc("G", 0.05), _sc("H", 0.01), _sc("I", 0.0), _sc("J", -0.1)]
    # 10 names → decile = 1 → selects A. A is UNPRICED but currently HELD.
    r = compute_rebalance(date(2026, 6, 30), scores, held={"A"}, priced={"B", "C"})
    # A carries no target weight (not in target_weights), and is flagged retained_unpriced
    assert "A" not in r.target_weights
    assert "A" in r.retained_unpriced
    # applying: A's prior weight is retained (not resized, not dropped)
    book = AcademicMomentumBook(weights={"A": 1.0})
    book.apply(r)
    assert "A" in book.held()


# ---- rule 3: held name no longer selected, priced → liquidate --------------------

def test_rule3_dropped_and_priced_is_liquidated_deferred_until_priced():
    scores = [_sc("A", 3.0), _sc("B", 2.0)] + [_sc(f"S{i}", -1.0 - i) for i in range(18)]
    # 20 names → decile 2 → selects A,B. Held X (not selected). X priced → liquidate.
    r = compute_rebalance(date(2026, 6, 30), scores, held={"A", "B", "X"},
                          priced={"A", "B", "X"})
    assert "X" in r.liquidations
    book = AcademicMomentumBook(weights={"A": 0.33, "B": 0.33, "X": 0.34})
    book.apply(r)
    assert "X" not in book.held()

    # if X is UNPRICED it is retained until a priced session (rule 3 deferred)
    r2 = compute_rebalance(date(2026, 6, 30), scores, held={"A", "B", "X"}, priced={"A", "B"})
    assert "X" not in r2.liquidations


# ---- rule 4: whole rebalance unexecutable → INCOMPLETE, retain, exception ---------

def test_rule4_no_selected_name_priced_is_incomplete_and_retains_portfolio():
    scores = [_sc("A", 3.0), _sc("B", 2.0)] + [_sc(f"S{i}", -1.0) for i in range(18)]
    # selects A,B; NEITHER is priced this session → rule 4
    r = compute_rebalance(date(2026, 6, 30), scores, held={"P", "Q"}, priced={"Z"})
    assert r.status is RebalanceStatus.INCOMPLETE
    assert r.target_weights == {}
    assert r.exception is not None

    book = AcademicMomentumBook(weights={"P": 0.5, "Q": 0.5})
    book.apply(r)
    assert book.held() == {"P", "Q"}                    # previous portfolio retained
    assert len(book.exceptions) == 1                    # operational exception recorded


def test_empty_universe_yields_no_selection():
    assert amb.select_top_decile([]) == []
    r = compute_rebalance(date(2026, 6, 30), [], held=set(), priced=set())
    assert r.status is RebalanceStatus.INCOMPLETE and r.target_weights == {}
