"""ADR 0043 §D3 — the daily-loss basis selector.

Deterministic (session_date passed explicitly). Pins the source precedence, per-account isolation,
immutability, the specific fallback reasons (never a generic 'fallback'), and validation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.models.account import Account, AccountMode
from app.db.models.risk_session_baseline import (
    BASELINE_STATUS_ACTIVE,
    BASELINE_STATUS_SUPERSEDED,
    RiskSessionBaseline,
)
from app.db.models.risk_session_baseline_shadow_outcome import (
    RiskSessionBaselineShadowOutcome,
)
from app.db.models.user import User
from app.risk.loss_control.daily_loss_basis import (
    BASIS_LEGACY_CUMULATIVE_FALLBACK,
    BASIS_LEGACY_LAST_EQUITY,
    BASIS_SESSION_BASELINE,
    FALLBACK_BASELINE_INVALID,
    FALLBACK_BASELINE_SESSION_MISMATCH,
    FALLBACK_CAPTURE_INDETERMINATE,
    FALLBACK_MISSING_AFTER_ACTIVITY,
    FALLBACK_NO_BASELINE_CAPTURED,
    select_daily_loss_basis,
)
from app.risk.loss_control.session_baseline import (
    SHADOW_INDETERMINATE,
    SHADOW_MISSING_AFTER_ACTIVITY,
)

D = Decimal
TODAY = "2026-07-20"
PRIOR = "2026-07-17"
NOW = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)


@pytest.fixture
async def acct(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(User(id=2, email="jo@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P1"))
        s.add(Account(id=2, user_id=2, broker="alpaca", mode=AccountMode.paper, label="P2"))
        await s.commit()
    return 1


async def _add_baseline(session_factory, account_id, date, equity, *, status=BASELINE_STATUS_ACTIVE):
    async with session_factory() as s:
        s.add(RiskSessionBaseline(
            account_id=account_id, market_session_date=date, baseline_equity=D(equity),
            baseline_source="RECONCILED_OPEN", captured_at=NOW, status=status,
        ))
        await s.commit()


async def _add_outcome(session_factory, account_id, date, outcome):
    async with session_factory() as s:
        s.add(RiskSessionBaselineShadowOutcome(
            account_id=account_id, market_session_date=date, outcome=outcome, updated_at=NOW,
        ))
        await s.commit()


async def _select(session_factory, account_id=1, *, current_equity="98000", last_equity="95000",
                  realized="0", unrealized="0", session_date=TODAY, allow_cumulative=False):
    async with session_factory() as s:
        return await select_daily_loss_basis(
            s, account_id,
            current_equity=D(current_equity) if current_equity is not None else None,
            last_equity=D(last_equity) if last_equity is not None else None,
            realized=D(realized), unrealized=D(unrealized),
            session_date=session_date, applicable_limit=D("5000"),
            allow_cumulative_fallback=allow_cumulative,
        )


# ------------------------------------------------------------ source precedence


async def test_session_baseline_wins_over_last_equity(session_factory, acct):
    await _add_baseline(session_factory, 1, TODAY, "100000")
    b = await _select(session_factory, current_equity="98000", last_equity="95000")
    assert b.basis_source == BASIS_SESSION_BASELINE
    assert b.day_change == D("-2000")  # 98000 − 100000 (baseline), NOT −3000 (last_equity 95000)
    assert b.baseline_id is not None and b.baseline_equity == D("100000")
    assert b.fallback_reason is None


async def test_missing_baseline_uses_legacy_last_equity(session_factory, acct):
    b = await _select(session_factory, current_equity="98000", last_equity="95000")
    assert b.basis_source == BASIS_LEGACY_LAST_EQUITY
    assert b.day_change == D("3000")
    assert b.fallback_reason == FALLBACK_NO_BASELINE_CAPTURED


async def test_cumulative_fallback_only_when_sanctioned(session_factory, acct):
    # No baseline, no last_equity. allow_cumulative True (breaker path) → cumulative.
    b = await _select(session_factory, last_equity=None, realized="-400", unrealized="-100",
                      allow_cumulative=True)
    assert b.basis_source == BASIS_LEGACY_CUMULATIVE_FALLBACK and b.day_change == D("-500")
    # Step-9 path (allow_cumulative False) → no usable basis, day_change None (gate skips).
    b2 = await _select(session_factory, last_equity=None, allow_cumulative=False)
    assert b2.day_change is None and b2.basis_source is None
    assert b2.fallback_reason == FALLBACK_NO_BASELINE_CAPTURED


# ------------------------------------------------------------ rejection of unusable baselines


async def test_prior_session_baseline_is_rejected(session_factory, acct):
    await _add_baseline(session_factory, 1, PRIOR, "100000")  # a baseline, but for another session
    b = await _select(session_factory, current_equity="98000", last_equity="95000")
    assert b.basis_source == BASIS_LEGACY_LAST_EQUITY  # prior-session baseline NEVER used
    assert b.day_change == D("3000")
    assert b.fallback_reason == FALLBACK_BASELINE_SESSION_MISMATCH


async def test_inactive_baseline_is_rejected(session_factory, acct):
    await _add_baseline(session_factory, 1, TODAY, "100000", status=BASELINE_STATUS_SUPERSEDED)
    b = await _select(session_factory)
    assert b.basis_source == BASIS_LEGACY_LAST_EQUITY
    assert b.fallback_reason == FALLBACK_BASELINE_INVALID


@pytest.mark.parametrize("equity", ["0", "-100.00"])
async def test_zero_or_negative_baseline_equity_fails_validation(session_factory, acct, equity):
    await _add_baseline(session_factory, 1, TODAY, equity)
    b = await _select(session_factory)
    # Never produce a distorted day-change from a non-positive baseline — reject and fall back.
    assert b.basis_source == BASIS_LEGACY_LAST_EQUITY
    assert b.fallback_reason == FALLBACK_BASELINE_INVALID


# ------------------------------------------------------------ specific fallback reasons


async def test_missing_after_activity_reason(session_factory, acct):
    await _add_outcome(session_factory, 1, TODAY, SHADOW_MISSING_AFTER_ACTIVITY)
    b = await _select(session_factory)
    assert b.fallback_reason == FALLBACK_MISSING_AFTER_ACTIVITY


async def test_indeterminate_reason(session_factory, acct):
    await _add_outcome(session_factory, 1, TODAY, SHADOW_INDETERMINATE)
    b = await _select(session_factory)
    assert b.fallback_reason == FALLBACK_CAPTURE_INDETERMINATE


async def test_fallback_reason_always_present_when_baseline_not_used(session_factory, acct):
    b = await _select(session_factory)  # no baseline
    assert b.basis_source != BASIS_SESSION_BASELINE and b.fallback_reason is not None
    await _add_baseline(session_factory, 1, TODAY, "100000")
    b2 = await _select(session_factory)  # baseline present
    assert b2.basis_source == BASIS_SESSION_BASELINE and b2.fallback_reason is None


# ------------------------------------------------------------ isolation, immutability, no-guess


async def test_no_cross_account_baseline(session_factory, acct):
    await _add_baseline(session_factory, 1, TODAY, "100000")  # ONLY account 1 has a baseline
    b = await _select(session_factory, account_id=2, current_equity="98000", last_equity="95000")
    assert b.basis_source == BASIS_LEGACY_LAST_EQUITY  # account 2 cannot see account 1's baseline
    assert b.fallback_reason == FALLBACK_NO_BASELINE_CAPTURED


async def test_restart_reselects_the_same_immutable_baseline(session_factory, acct):
    await _add_baseline(session_factory, 1, TODAY, "100000")
    first = await _select(session_factory)
    second = await _select(session_factory)  # a "restart" re-reads the same immutable row
    assert first.baseline_id == second.baseline_id
    assert first.day_change == second.day_change == D("-2000")


async def test_missing_session_date_does_not_guess(session_factory, acct):
    # A baseline exists for the real date, but session_date=None must NOT be replaced by a guess.
    await _add_baseline(session_factory, 1, TODAY, "100000")
    b = await _select(session_factory, session_date=None, current_equity="98000", last_equity="95000")
    assert b.basis_source == BASIS_LEGACY_LAST_EQUITY  # no session date → baseline not used
    assert b.market_session_date is None
    assert b.fallback_reason == FALLBACK_NO_BASELINE_CAPTURED


async def test_flag_on_fallback_equals_legacy_value(session_factory, acct):
    # With no baseline, the enforced day-change EQUALS the legacy last_equity day-change — so the
    # only thing enforcement changes vs legacy is the basis SOURCE (+ derived value when a baseline
    # exists), never the arithmetic when falling back.
    b = await _select(session_factory, current_equity="98000", last_equity="95000")
    assert b.day_change == D("98000") - D("95000")


async def test_provenance_is_flat_strings(session_factory, acct):
    await _add_baseline(session_factory, 1, TODAY, "100000")
    b = await _select(session_factory)
    p = b.provenance()
    assert p["basis_source"] == BASIS_SESSION_BASELINE
    # Values are flat strings (Numeric columns keep their scale, e.g. "100000.0000").
    assert D(p["baseline_equity"]) == D("100000") and D(p["day_change"]) == D("-2000")
    assert all(v is None or isinstance(v, str) for v in p.values())


async def test_no_stray_rows_written(session_factory, acct):
    # The selector reads only — it must not write baselines or outcomes.
    await _select(session_factory)
    async with session_factory() as s:
        bases = await s.scalar(select(func.count()).select_from(RiskSessionBaseline))
        outs = await s.scalar(select(func.count()).select_from(RiskSessionBaselineShadowOutcome))
    assert bases == 0 and outs == 0
