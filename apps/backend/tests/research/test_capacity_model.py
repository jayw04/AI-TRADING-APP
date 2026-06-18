"""P10 §3B capacity model — robust participation distribution + AUM ceiling.

The 3A capacity metric was a raw mean of traded$/ADV$ over every (rebalance × name)
trade, which the survivorship-free delisting tail blew up to ~1132%. These tests pin
the §3B replacement: untradeable names are flagged (not averaged in), the participation
stats are robust, and ``capacity_aum`` is the equity-independent AUM ceiling."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.backtest import (
    BacktestRunConfig,
    BacktestSummary,
    MomentumBacktestReport,
    RebalanceHoldings,
    run_momentum_backtest,
)
from app.factor_data.store import FactorDataStore
from app.research.engine.portfolio_eval import (
    _TARGET_PARTICIPATION,
    _capacity,
    _percentile,
    shape_portfolio_result,
)
from app.research.promotion import PORTFOLIO_BACKTEST_PROFILE, evaluate

from ..factor_data.conftest import build_momentum_frames

_START = date(2018, 7, 1)
_END = date(2020, 12, 31)


# ---- the percentile helper -------------------------------------------------------

def test_percentile_edges_and_interpolation() -> None:
    assert _percentile([], 0.5) == 0.0
    assert _percentile([42.0], 0.95) == 42.0
    assert _percentile([0.0, 10.0], 0.5) == pytest.approx(5.0)          # midpoint
    assert _percentile([0.0, 10.0, 20.0, 30.0], 0.0) == pytest.approx(0.0)
    assert _percentile([0.0, 10.0, 20.0, 30.0], 1.0) == pytest.approx(30.0)
    assert _percentile([0.0, 10.0, 20.0, 30.0], 0.5) == pytest.approx(15.0)


# ---- direct _capacity: the delisting-tail regression ------------------------------

def _two_name_store(tmp_path) -> FactorDataStore:
    """A store with one deeply-liquid name (LIQ) and one effectively untradeable name
    (THIN, ~$1/day of volume) — the shape that broke the 3A mean."""
    days = pd.bdate_range("2019-01-01", "2019-04-30")
    rows = []
    for tk, price, vol in (("LIQ", 100.0, 10_000_000), ("THIN", 1.0, 1)):
        for d in days:
            rows.append(dict(
                ticker=tk, date=d.strftime("%Y-%m-%d"),
                open=price, high=price, low=price, close=price,
                volume=vol, closeadj=price, closeunadj=price, lastupdated="2026-01-01",
            ))
    s = FactorDataStore(db_path=str(tmp_path / "cap.duckdb"))
    s.ingest_sep(pd.DataFrame(rows))
    return s


def test_untradeable_name_flagged_not_averaged_in(tmp_path) -> None:
    """★ The fix: a name with ~zero ADV is counted as untradeable and excluded from the
    participation stats — instead of dragging the mean to thousands of percent."""
    store = _two_name_store(tmp_path)
    d = date(2019, 3, 1)  # well past the 20-day ADV lookback
    # One rebalance, both names entered at 50% from flat → traded$ = 0.5 × $100k = $50k each.
    config = BacktestRunConfig(
        start=date(2019, 1, 1), end=date(2019, 4, 30), n=2, lookback_days=1, skip_days=0,
        top_quantile=1.0, turnover_cost_bps=0.0, delisting="last_price_to_cash",
        initial_equity=100_000.0,
    )
    report = MomentumBacktestReport(
        config=config, rebalances=[d],
        equity_curve=[(d, 100_000.0)], baseline_curve=[(d, 100_000.0)],
        holdings=[RebalanceHoldings(d, ["LIQ", "THIN"], 0.0, {"LIQ": 0.5, "THIN": 0.5})],
        metrics=BacktestSummary(0.0, 0.0, 0.0, 0.0),
        baseline_metrics=BacktestSummary(0.0, 0.0, 0.0, 0.0),
    )
    cap = _capacity(store, report, turnover_annual=1.0)
    store.close()

    # THIN ($1/day) is 1 of the 2 trades → flagged, not averaged.
    assert cap["untradeable_trade_fraction"] == pytest.approx(0.5)
    # LIQ: traded $50k / ADV $1e9 = 5e-5 — the only tradeable trade.
    assert cap["avg_adv_participation"] == pytest.approx(50_000 / 1e9, rel=1e-6)
    assert cap["adv_participation_median"] == pytest.approx(50_000 / 1e9, rel=1e-6)
    assert cap["avg_adv_participation"] < 1e-3            # NOT the ~11x the old mean gave
    # capacity_aum from LIQ only: target × ADV$ / |Δw| = 0.10 × 1e9 / 0.5 = 2e8.
    assert cap["capacity_aum"] == pytest.approx(_TARGET_PARTICIPATION * 1e9 / 0.5, rel=1e-6)


# ---- on the liquid fixture: sane numbers + invariants -----------------------------

@pytest.fixture
def bt_store(tmp_path) -> FactorDataStore:
    sep, tk = build_momentum_frames()
    s = FactorDataStore(db_path=str(tmp_path / "bt.duckdb"))
    s.ingest_sep(sep)
    s.ingest_tickers(tk)
    yield s
    s.close()


def test_capacity_sane_and_keys_present(bt_store: FactorDataStore) -> None:
    report = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    s = shape_portfolio_result(report, bt_store).metrics_summary
    for k in ("avg_adv_participation", "adv_participation_median", "adv_participation_p95",
              "capacity_aum", "untradeable_trade_fraction"):
        assert k in s
    # fixture names are deeply liquid (vol 1e6 × ~$100) → participation tiny, nothing untradeable.
    assert 0.0 <= s["avg_adv_participation"] < 0.01
    assert s["untradeable_trade_fraction"] == 0.0
    assert s["capacity_aum"] > 0.0
    # the frozen gate's capacity component (ADV participation <= 2%) now passes.
    res = evaluate(s, PORTFOLIO_BACKTEST_PROFILE)
    cap_comp = next(c for c in res.component_scores if c.component == "capacity")
    assert cap_comp.passed_weight == cap_comp.total_weight  # capacity 1/1 (was failing on the bug)


def test_capacity_aum_invariant_to_book_size(bt_store: FactorDataStore) -> None:
    """★ capacity_aum = target × ADV$ / |Δw| is independent of the book's equity, while
    participation scales linearly with it — the two properties that make the ceiling
    the right 'how much can this run' number."""
    small = shape_portfolio_result(
        run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2, initial_equity=100_000.0),
        bt_store).metrics_summary
    big = shape_portfolio_result(
        run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2, initial_equity=1_000_000.0),
        bt_store).metrics_summary
    assert big["capacity_aum"] == pytest.approx(small["capacity_aum"], rel=1e-6)
    assert big["avg_adv_participation"] == pytest.approx(10 * small["avg_adv_participation"], rel=1e-6)
