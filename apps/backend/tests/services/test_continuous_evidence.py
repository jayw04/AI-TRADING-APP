"""Continuous Evidence Engine — Phase 1 pure-core tests (offline, no DB)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.account import Account, AccountMode
from app.db.models.equity_snapshot import EquitySnapshot
from app.db.models.user import User
from app.services import continuous_evidence as ce


def _curve(values: list[float]) -> list[tuple[datetime, float]]:
    d0 = datetime(2026, 1, 1, tzinfo=UTC)
    return [(d0 + timedelta(days=i), v) for i, v in enumerate(values)]


# ---- progressive confidence / maturity ----

def test_evidence_maturity_thresholds():
    assert ce.evidence_maturity(0) == ce._MATURITY_INSUFFICIENT
    assert ce.evidence_maturity(20) == ce._MATURITY_INSUFFICIENT
    assert ce.evidence_maturity(21) == ce._MATURITY_PRELIM
    assert ce.evidence_maturity(62) == ce._MATURITY_PRELIM
    assert ce.evidence_maturity(63) == ce._MATURITY_EMERGING
    assert ce.evidence_maturity(125) == ce._MATURITY_EMERGING
    assert ce.evidence_maturity(126) == ce._MATURITY_MODERATE
    assert ce.evidence_maturity(252) == ce._MATURITY_MATURE


def test_evidence_debt_high_when_long_live_but_low_evidence():
    assert ce.evidence_debt(70, ce._MATURITY_PRELIM) == "High"     # 3mo+ still preliminary
    assert ce.evidence_debt(30, ce._MATURITY_INSUFFICIENT) == "Moderate"
    assert ce.evidence_debt(10, ce._MATURITY_INSUFFICIENT) == "Low"
    assert ce.evidence_debt(200, ce._MATURITY_MODERATE) == "Low"


def test_review_cadence_tightens_when_young():
    assert ce.review_cadence_days(ce._MATURITY_INSUFFICIENT) == 30
    assert ce.review_cadence_days(ce._MATURITY_MODERATE) == 90


# ---- four-state classification (skeptical) ----

def test_classify_metric_insufficient_dominates_until_mature():
    # even a wildly out-of-band value is INSUFFICIENT while evidence is immature
    st, _ = ce.classify_metric(-5.0, 0.1, 1.5, ce._MATURITY_INSUFFICIENT)
    assert st == ce.INSUFFICIENT


def test_classify_metric_consistent_and_watch_when_mature():
    assert ce.classify_metric(0.8, 0.1, 1.5, ce._MATURITY_MATURE)[0] == ce.CONSISTENT
    assert ce.classify_metric(2.0, 0.1, 1.5, ce._MATURITY_MATURE)[0] == ce.WATCH   # above band
    assert ce.classify_metric(-0.5, 0.1, 1.5, ce._MATURITY_MATURE)[0] == ce.WATCH  # below band


def test_classify_metric_none_observation_is_insufficient():
    assert ce.classify_metric(None, 0.1, 1.5, ce._MATURITY_MATURE)[0] == ce.INSUFFICIENT


def test_phase1_never_emits_investigate():
    # Phase 1 escalates at most to WATCH; INVESTIGATE is Phase 2
    states = {ce.classify_metric(v, 0.1, 1.5, ce._MATURITY_MATURE)[0] for v in (-9, 0.5, 9)}
    assert ce.INVESTIGATE not in states


# ---- envelope matching ----

def test_match_envelope_aliases():
    assert ce.match_envelope("momentum-growth").family == "momentum"
    assert ce.match_envelope("Conservative Momentum").family == "momentum"
    assert ce.match_envelope("low_vol book").family == "low_vol"
    assert ce.match_envelope("Sector Rotation").family == "sector"
    assert ce.match_envelope("Range Trader").family == "range"
    assert ce.match_envelope("Risk-Balanced Multi-Asset").family == "combined"
    assert ce.match_envelope("something unknown") is None


# ---- difference helper ----

def test_difference_signed_distance_outside_band():
    assert ce._difference(0.5, 0.1, 1.5) == 0.0        # inside
    assert ce._difference(-0.4, 0.1, 1.5) == -0.5      # below low by 0.5
    assert ce._difference(2.0, 0.1, 1.5) == 0.5        # above high by 0.5


# ---- book evidence (pure core) ----

def test_book_evidence_short_history_is_insufficient():
    ev = ce.book_evidence_from_curve(
        "momentum", 1, _curve([100.0, 101.0, 102.0]), ce.match_envelope("momentum"))
    assert ev.days_live == 3
    assert ev.maturity == ce._MATURITY_INSUFFICIENT
    assert ev.state == ce.INSUFFICIENT
    # every metric row is Insufficient regardless of the (noisy) observed value
    assert all(m.state == ce.INSUFFICIENT for m in ev.metrics)


def test_book_evidence_matured_drawdown_within_band_is_consistent():
    # 30 points (Preliminary), dips ~5% then recovers -> maxDD ~ -0.05 within [-0.45, 0]
    vals = [100.0] * 10 + [95.0] + [100.0] * 19
    ev = ce.book_evidence_from_curve(
        "momentum", 1, _curve(vals), ce.match_envelope("momentum"))
    assert ev.maturity == ce._MATURITY_PRELIM
    mdd = next(m for m in ev.metrics if m.metric == "max_drawdown")
    assert mdd.observed is not None and -0.06 < mdd.observed < -0.04
    assert mdd.state == ce.CONSISTENT
    assert ev.state in (ce.CONSISTENT, ce.WATCH)   # not INSUFFICIENT once matured


def test_book_evidence_no_envelope_still_reported():
    ev = ce.book_evidence_from_curve("mystery", 9, _curve([100.0, 101.0]), None)
    assert ev.envelope_source is None
    assert ev.state == ce.INSUFFICIENT
    assert ev.metrics == []


# ---- engine integration (in-memory DB) ----

@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker]:
    from app.config import get_settings
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_engine, get_sessionmaker

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield get_sessionmaker()
    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


async def test_compute_reports_insufficient_for_new_book(factory) -> None:
    base = datetime(2026, 6, 25, 16, 10, tzinfo=UTC)
    async with factory() as s:
        s.add(User(id=1, email="mom@t"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="momentum-growth"))
        # 5 trading days (with two snapshots on one day -> collapsed to one point)
        eqs = [100.0, 101.0, 99.0, 102.0, 103.0]
        for i, e in enumerate(eqs):
            ts = base + timedelta(days=i)
            s.add(EquitySnapshot(account_id=1, ts=ts, equity=Decimal(str(e * 1000)),
                                 cash=Decimal(0), portfolio_value=Decimal(0), day_change_pct=Decimal(0)))
        # a second snapshot the same day as day 0 -> must collapse (still 5 distinct days)
        s.add(EquitySnapshot(account_id=1, ts=base + timedelta(hours=2), equity=Decimal("100500"),
                             cash=Decimal(0), portfolio_value=Decimal(0), day_change_pct=Decimal(0)))
        await s.commit()

    async with factory() as s:
        res = await ce.compute(s, [(1, "momentum-growth")])

    assert len(res) == 1
    b = res[0]
    assert b.days_live == 5                       # collapsed to one point per day
    assert b.maturity == ce._MATURITY_INSUFFICIENT
    assert b.state == ce.INSUFFICIENT             # skeptical: too little history
    assert b.envelope_source is not None          # matched the momentum envelope
    assert {m.metric for m in b.metrics} == {"sharpe", "max_drawdown"}
