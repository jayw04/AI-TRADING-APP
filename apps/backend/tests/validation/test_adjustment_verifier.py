"""Corporate-action adjustment verifier (R5b) + the widened R5a seam.

Pins the arithmetic (dividend, split, reverse split, same-day composition), the composition rules
(identical duplicates conflict, incompatible splits conflict, contraticker events unsupported), the
source-authority requirement, and — the load-bearing one — that an EMPTY action table cannot yield a
proven verdict when the adjusted series visibly moves against the raw series.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from app.factor_data.store import FactorDataStore
from app.validation.adjustment_verifier import (
    ActionClass,
    ActionSourceDeclaration,
    AdjustmentVerdict,
    AdjustmentVerificationError,
    Tolerance,
    classify_action,
    relevance_digest,
    verify_adjustments,
)

WINDOW_START = date(2026, 6, 1)
SESSION = date(2026, 6, 30)
TICKERS = ["AAA", "BBB", "CCC"]

SOURCE = ActionSourceDeclaration(identity="sharadar/ACTIONS@test", authoritative=True,
                                 coverage_start=date(2020, 1, 1), coverage_end=date(2026, 12, 31))


def _sessions(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


SESSIONS = _sessions(WINDOW_START, SESSION)


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


@pytest.fixture
def store(tmp_path):
    """Three names, flat $100 raw closes and an adjusted series equal to the raw one — no adjustment
    events anywhere, so each test can introduce exactly the one it is about."""
    st = FactorDataStore(db_path=str(tmp_path / "adj.duckdb"))
    st.ingest_sep(_frame([
        {"ticker": t, "date": d, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
         "volume": 1_000_000, "closeadj": 100.0, "closeunadj": 100.0, "lastupdated": d}
        for d in SESSIONS for t in TICKERS]))
    st.record_ingest_run("actions", datetime(2026, 6, 30, 22, 0), datetime(2026, 6, 30, 22, 1),
                         0, "ok")
    yield st
    st.close()


def _set_prices(store, ticker: str, when: date, *, close: float, closeadj: float) -> None:
    store.con.execute("UPDATE sep SET close = ?, closeadj = ? WHERE ticker = ? AND date = ?",
                      [close, closeadj, ticker, when])


def _apply_event(store, ticker: str, ex_date: date, *, close: float, closeadj: float = 100.0) -> None:
    """Apply an ex-date price step to the ex-date AND every session after it: a split or distribution
    shifts the raw path against the adjusted path permanently, not for one day."""
    store.con.execute("UPDATE sep SET close = ?, closeadj = ? WHERE ticker = ? AND date >= ?",
                      [close, closeadj, ticker, ex_date])


def _add_action(store, ticker: str, when: date, action: str, value: float | None,
                contraticker: str | None = None) -> None:
    store.con.execute("INSERT INTO actions VALUES (?, ?, ?, ?, ?, ?)",
                      [when, action, ticker, ticker, value, contraticker])


def _verify(store, **kw):
    kw.setdefault("window_start", WINDOW_START)
    kw.setdefault("session_date", SESSION)
    kw.setdefault("relevant_tickers", TICKERS)
    kw.setdefault("source", SOURCE)
    kw.setdefault("store_identity_sha256", "store-identity-under-test")
    return verify_adjustments(store, **kw)


EX_DATE = SESSIONS[10]
PREV = SESSIONS[9]


# ---- the arithmetic ---------------------------------------------------------------------------------

def test_a_correctly_reflected_cash_dividend_is_proven(store):
    """$1 dividend on a $100 name: raw close drops to 99, the adjusted series carries the total
    return, so closeadj_t/closeadj_{t-1} == (99 + 1)/100 == 1.0."""
    _apply_event(store, "AAA", EX_DATE, close=99.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN and ev.proven
    assert ev.adjustment_series_consistent_with_declared_actions is True
    check = ev.checks[0]
    assert check.action_class is ActionClass.CASH_DIVIDEND
    assert check.declared_cash_per_share == 1.0
    assert check.expected_ratio == pytest.approx(1.0) and check.observed_ratio == pytest.approx(1.0)
    assert check.absolute_residual is not None and check.relative_tolerance > 0


def test_a_two_for_one_split_is_proven(store):
    """2:1 split: raw close halves to 50, the adjusted series is unchanged (2 × 50/100 == 1)."""
    _apply_event(store, "AAA", EX_DATE, close=50.0)
    _add_action(store, "AAA", EX_DATE, "split", 2.0)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    assert ev.checks[0].action_class is ActionClass.SPLIT
    assert ev.checks[0].declared_split_multiplier == 2.0


def test_a_reverse_split_is_proven(store):
    """1:4 reverse split: raw close quadruples, multiplier 0.25."""
    _apply_event(store, "AAA", EX_DATE, close=400.0)
    _add_action(store, "AAA", EX_DATE, "split", 0.25)
    assert _verify(store).verdict is AdjustmentVerdict.PROVEN


def test_a_same_day_split_and_dividend_compose(store):
    """2:1 split plus a $0.50 (post-split) dividend: expected 2 × (49.5 + 0.5)/100 == 1.0."""
    _apply_event(store, "AAA", EX_DATE, close=49.5)
    _add_action(store, "AAA", EX_DATE, "split", 2.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 0.5)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    assert ev.checks[0].action_class is ActionClass.SPLIT_AND_CASH


def test_two_cash_distributions_on_one_date_sum(store):
    _apply_event(store, "AAA", EX_DATE, close=98.5)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    _add_action(store, "AAA", EX_DATE, "distribution", 0.5)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.PROVEN
    assert ev.checks[0].declared_cash_per_share == pytest.approx(1.5)


def test_a_series_that_contradicts_the_declared_action_is_a_conflict(store):
    """The dividend is declared but the adjusted series behaves as if nothing happened."""
    _apply_event(store, "AAA", EX_DATE, close=99.0, closeadj=99.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.INTEGRITY_STOP_CONFLICT
    assert ev.proven is False
    assert ev.adjustment_series_consistent_with_declared_actions is False


# ---- composition rules ------------------------------------------------------------------------------

def test_identical_duplicate_rows_are_a_conflict(store):
    _apply_event(store, "AAA", EX_DATE, close=99.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)                  # byte-identical duplicate
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.INTEGRITY_STOP_CONFLICT
    assert "duplicate" in ev.checks[0].detail


def test_incompatible_split_ratios_on_one_date_are_a_conflict(store):
    _apply_event(store, "AAA", EX_DATE, close=50.0)
    _add_action(store, "AAA", EX_DATE, "split", 2.0)
    _add_action(store, "AAA", EX_DATE, "split", 3.0)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.INTEGRITY_STOP_CONFLICT
    assert "incompatible split" in ev.checks[0].detail


def test_a_contraticker_event_is_unsupported(store):
    _add_action(store, "AAA", EX_DATE, "spinoff", 1.0, contraticker="SPINCO")
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION
    assert ev.proven is False


@pytest.mark.parametrize(("label", "contra", "expected"), [
    ("dividend", None, ActionClass.CASH_DIVIDEND),
    ("split", None, ActionClass.SPLIT),
    ("spinoff", "NEWCO", ActionClass.SPINOFF_DISTRIBUTION),
    ("merger", "ACQ", ActionClass.MERGER_CONVERSION),
    ("tickerchange", None, ActionClass.SYMBOL_TRANSITION),
    ("some novel corporate event", None, ActionClass.UNSUPPORTED),
])
def test_action_classification(label, contra, expected):
    assert classify_action(label, contra) is expected


def test_an_action_without_a_declared_value_is_insufficient_data(store):
    _add_action(store, "AAA", EX_DATE, "dividend", None)
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA


def test_a_missing_prior_mark_is_insufficient_data_not_harmless(store):
    """Missing either side of the relationship is NOT evidence that the action was harmless."""
    first = SESSIONS[0]
    _add_action(store, "AAA", first, "dividend", 1.0)                    # no prior session in-window
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA
    assert ev.checks[0].verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA


# ---- the empty-source hole (why row counts cannot be trusted) ----------------------------------------

def test_an_adjustment_with_no_declared_action_is_not_proven(store):
    """The governed store today holds ZERO action rows while `closeadj` departs from `close` on ~48% of
    its rows. Counting declared actions would call this window clean; the series says otherwise."""
    _apply_event(store, "AAA", EX_DATE, close=99.0)                      # a visible ex-date, undeclared
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA
    assert ev.proven is False
    assert ev.unexplained_adjustment_count == 1
    assert ev.unexplained_examples[0].ticker == "AAA"
    assert ev.total_actions_in_window == 0


def test_a_clean_window_with_an_authoritative_source_is_no_relevant_actions(store):
    ev = _verify(store)
    assert ev.verdict is AdjustmentVerdict.NO_RELEVANT_ACTIONS and ev.proven is True
    assert ev.adjustment_series_consistent_with_declared_actions is True


# ---- source authority -------------------------------------------------------------------------------

def test_a_source_not_declared_authoritative_can_never_prove(store):
    ev = _verify(store, source=ActionSourceDeclaration(identity="unregistered", authoritative=False))
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA
    assert ev.declared_action_source_authoritative is False


def test_a_source_that_does_not_cover_the_window_cannot_prove(store):
    ev = _verify(store, source=ActionSourceDeclaration(
        identity="sharadar/ACTIONS@partial", authoritative=True,
        coverage_start=date(2026, 6, 15), coverage_end=date(2026, 6, 30)))
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA
    assert "coverage" in ev.detail


def test_consistency_and_source_authority_are_reported_separately(store):
    """The arithmetic proves consistency with the DECLARED rows; it cannot prove the declaration itself
    is correct. The two facts stay separate in the evidence."""
    _apply_event(store, "AAA", EX_DATE, close=99.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    ev = _verify(store, source=ActionSourceDeclaration(identity="x", authoritative=False))
    assert ev.adjustment_series_consistent_with_declared_actions is False   # not evaluated
    assert ev.declared_action_source_authoritative is False
    assert ev.proven is False


# ---- relevance scope + evidence --------------------------------------------------------------------

def test_actions_outside_the_relevance_set_do_not_gate(store):
    _apply_event(store, "CCC", EX_DATE, close=99.0)
    _add_action(store, "CCC", EX_DATE, "dividend", 1.0)
    ev = _verify(store, relevant_tickers=["AAA", "BBB"])
    assert ev.verdict is AdjustmentVerdict.NO_RELEVANT_ACTIONS
    assert ev.total_actions_in_window == 1
    assert ev.relevant_actions_in_window == 0 and ev.irrelevant_actions_in_window == 1
    assert ev.relevant_ticker_count == 2


def test_the_relevance_digest_binds_the_store_identity():
    a = relevance_digest(["AAA", "BBB"], WINDOW_START, SESSION, "identity-1")
    b = relevance_digest(["AAA", "BBB"], WINDOW_START, SESSION, "identity-2")
    c = relevance_digest(["BBB", "AAA"], WINDOW_START, SESSION, "identity-1")
    assert a != b                       # same names, different store state → different digest
    assert a == c                       # order-independent
    assert len(a) == 64


def test_evidence_is_open_provenance_only(store):
    _apply_event(store, "AAA", EX_DATE, close=99.0)
    _add_action(store, "AAA", EX_DATE, "dividend", 1.0)
    d = _verify(store).to_open_provenance()
    assert d["verdict"] == "PROVEN"
    assert d["tolerance"]["price_quantum"] == 1e-4
    assert d["checks"][0]["relative_tolerance"] > 0
    forbidden = {"strategy_return", "sharpe", "equity", "pnl", "scores", "ranking", "weights"}
    assert not (forbidden & set(d))


def test_no_relevant_securities_is_insufficient_data(store):
    ev = _verify(store, relevant_tickers=[])
    assert ev.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA


def test_a_non_queryable_store_fails_closed():
    with pytest.raises(AdjustmentVerificationError, match="not a queryable store"):
        verify_adjustments(object(), window_start=WINDOW_START, session_date=SESSION,
                           relevant_tickers=TICKERS, source=SOURCE)


# ---- tolerance discipline ---------------------------------------------------------------------------

def test_the_tolerance_scales_with_the_price_quantum(store):
    """A 1e-4 quantum is a far larger relative error on a $1 name than on a $100 name, so the band is
    derived from the smallest price involved rather than picked as a round number."""
    tol = Tolerance()
    assert tol.for_prices(100.0) == pytest.approx(5e-6)      # 5 x 1e-4 x (1/100)
    assert tol.for_prices(1.0) == pytest.approx(5e-4)
    assert tol.for_prices(100.0, 100.0, 100.0, 100.0) == pytest.approx(2e-5)   # four rounded prices
    assert tol.for_prices(1_000_000.0) == tol.relative_floor  # the floor takes over
    assert tol.for_prices() == tol.relative_floor


def test_a_penny_stock_rounding_difference_is_within_tolerance(store):
    """$0.50 name, a $0.01 dividend, and the adjusted series rounded at the stored 4-decimal quantum:
    consistent, and it must not be reported as a contradiction."""
    store.con.execute("UPDATE sep SET close = 0.5, closeadj = 0.5 WHERE ticker = 'BBB'")
    _apply_event(store, "BBB", EX_DATE, close=0.49, closeadj=0.5001)     # 1e-4 rounding on the adj leg
    _add_action(store, "BBB", EX_DATE, "dividend", 0.01)
    ev = _verify(store, relevant_tickers=["BBB"])
    assert ev.verdict is AdjustmentVerdict.PROVEN
    assert ev.checks[0].relative_residual is not None
    assert ev.checks[0].relative_residual <= ev.checks[0].relative_tolerance
