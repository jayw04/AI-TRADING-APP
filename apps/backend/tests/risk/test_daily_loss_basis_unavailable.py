"""A daily-loss limit that CANNOT BE EVALUATED is not a satisfied daily-loss limit.

``accounts_state.day_change`` carries ``0`` as a placeholder when no baseline was found; the
truth is in ``day_change_basis``. Reading the number alone turned "unknown" into a measured flat
day, so ``daily_pnl <= -max_daily_loss`` could never become true and ``current_lock_state()``
returned UNLOCKED — silently removing the ADR 0042 restricted-mode protection on exactly the
accounts whose baseline had gone missing (a rebuilt DB, or a sync that has not run yet).

The unavailable case therefore gets its OWN lock state. It is restricted like any other lock —
reduction-only through the ADR 0042 classifier — but it is never represented as an artificial
threshold breach, and the placeholder ``0`` is never returned as ``daily_pnl``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.db.enums import RiskScopeType
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.risk_limits import RiskLimits
from app.db.models.user import User
from app.risk.lock_state import (
    LOCK_BASELINE_UNAVAILABLE,
    LOCK_BREAKER,
    LOCK_DAILY_LOSS,
    LOCK_UNLOCKED,
    REASON_BASIS_UNAVAILABLE,
    REASON_NO_ACCOUNT_STATE,
    current_lock_state,
)
from app.services.day_change_basis import (
    BROKER_LAST_EQUITY,
    PRIOR_SESSION_CLOSE_PROXY,
    UNAVAILABLE,
)

D = Decimal
MAX_DAILY_LOSS = D("5000")


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    """User 1 / account 1 with a $5,000 daily-loss limit and NO AccountState row."""
    async with session_factory() as s:
        s.add(User(id=1, email="t@local"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
                      label="Paper", created_at=_now()))
        s.add(RiskLimits(id=1, user_id=1, broker_mode=AccountMode.paper,
                         scope_type=RiskScopeType.GLOBAL, max_daily_loss=MAX_DAILY_LOSS,
                         created_at=_now(), updated_at=_now()))
        await s.commit()
    return session_factory


async def _add_state(session_factory, *, day_change: Decimal, basis: str) -> None:
    async with session_factory() as s:
        s.add(AccountState(
            account_id=1, cash=D("0"), equity=D("100000") + day_change,
            last_equity=D("100000"), buying_power=D("0"),
            portfolio_value=D("100000"), daytrade_count=0,
            day_change=day_change, day_change_pct=D("0"), day_change_basis=basis,
            status="ACTIVE", updated_at=_now(), raw_payload={},
        ))
        await s.commit()


async def _trip_breaker(session_factory) -> None:
    async with session_factory() as s:
        account = await s.get(Account, 1)
        account.circuit_breaker_tripped_at = _now()
        await s.commit()


async def _lock_state(session_factory):
    async with session_factory() as s:
        return await current_lock_state(s, account_id=1, user_id=1)


# --------------------------------------------------------------- unavailable basis

async def test_missing_account_state_is_restricted_not_unlocked(seeded):
    """No sync has ever run for this account. The limit exists and cannot be evaluated."""
    lock, reason, pnl = await _lock_state(seeded)

    assert lock == LOCK_BASELINE_UNAVAILABLE
    assert reason == REASON_NO_ACCOUNT_STATE
    assert pnl is None


async def test_unavailable_basis_is_restricted_not_unlocked(seeded):
    """THE REGRESSION: day_change=0 with basis UNAVAILABLE is a placeholder, not a flat day."""
    await _add_state(seeded, day_change=D("0"), basis=UNAVAILABLE)

    lock, reason, pnl = await _lock_state(seeded)

    assert lock == LOCK_BASELINE_UNAVAILABLE
    assert reason == REASON_BASIS_UNAVAILABLE
    assert lock != LOCK_UNLOCKED  # the defect this test exists to prevent
    assert pnl is None, "the placeholder 0 must never be reported as a measured P&L"


async def test_unavailable_basis_is_never_an_artificial_breach(seeded):
    """Fail closed, but do NOT pretend an unknown P&L is a measured loss."""
    await _add_state(seeded, day_change=D("0"), basis=UNAVAILABLE)

    lock, reason, pnl = await _lock_state(seeded)

    assert lock != LOCK_DAILY_LOSS
    assert reason != "daily_loss_exceeded"
    assert pnl is None


async def test_no_daily_loss_limit_configured_is_not_gratuitously_restricted(session_factory):
    """With no max_daily_loss there is no protection to lose, so nothing to fail closed about."""
    async with session_factory() as s:
        s.add(User(id=1, email="t@local"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
                      label="Paper", created_at=_now()))
        s.add(RiskLimits(id=1, user_id=1, broker_mode=AccountMode.paper,
                         scope_type=RiskScopeType.GLOBAL, max_daily_loss=None,
                         created_at=_now(), updated_at=_now()))
        await s.commit()
    await _add_state(session_factory, day_change=D("0"), basis=UNAVAILABLE)

    lock, reason, _pnl = await _lock_state(session_factory)

    assert lock == LOCK_UNLOCKED
    assert reason is None


# ------------------------------------------------------- healthy state is unchanged

@pytest.mark.parametrize("basis", [BROKER_LAST_EQUITY, PRIOR_SESSION_CLOSE_PROXY])
async def test_measured_breach_still_locks_daily_loss(seeded, basis):
    """Both real bases are measurements; a breach must still read as DAILY_LOSS, not the new state."""
    await _add_state(seeded, day_change=D("-6790.61"), basis=basis)

    lock, reason, pnl = await _lock_state(seeded)

    assert lock == LOCK_DAILY_LOSS
    assert reason == "daily_loss_exceeded"
    assert pnl == D("-6790.61")


async def test_measured_loss_within_limit_stays_unlocked(seeded):
    await _add_state(seeded, day_change=D("-100.00"), basis=BROKER_LAST_EQUITY)

    lock, reason, pnl = await _lock_state(seeded)

    assert lock == LOCK_UNLOCKED
    assert reason is None
    assert pnl == D("-100.00")


async def test_measured_profit_stays_unlocked(seeded):
    await _add_state(seeded, day_change=D("2500.00"), basis=BROKER_LAST_EQUITY)

    lock, _reason, pnl = await _lock_state(seeded)

    assert lock == LOCK_UNLOCKED
    assert pnl == D("2500.00")


async def test_exactly_at_the_limit_locks(seeded):
    """The gate is `<=`, so the boundary is a breach. Pinned so the fix cannot move it."""
    await _add_state(seeded, day_change=-MAX_DAILY_LOSS, basis=BROKER_LAST_EQUITY)

    lock, _reason, _pnl = await _lock_state(seeded)

    assert lock == LOCK_DAILY_LOSS


# ------------------------------------------------------------------ breaker wins

async def test_tripped_breaker_takes_precedence_over_unavailable_basis(seeded):
    """The breaker is the durable lock; it is still reported first, and still leaks no placeholder."""
    await _add_state(seeded, day_change=D("0"), basis=UNAVAILABLE)
    await _trip_breaker(seeded)

    lock, reason, pnl = await _lock_state(seeded)

    assert lock == LOCK_BREAKER
    assert reason == "circuit_breaker_tripped"
    assert pnl is None


async def test_tripped_breaker_reports_a_measured_pnl_when_one_exists(seeded):
    await _add_state(seeded, day_change=D("-250.00"), basis=BROKER_LAST_EQUITY)
    await _trip_breaker(seeded)

    lock, _reason, pnl = await _lock_state(seeded)

    assert lock == LOCK_BREAKER
    assert pnl == D("-250.00")


# --------------------------------------------------------------------- contracts

async def test_missing_account_is_unlocked(session_factory):
    """An account that does not exist is not a risk surface; unchanged behaviour."""
    lock, reason, pnl = await _lock_state(session_factory)

    assert (lock, reason, pnl) == (LOCK_UNLOCKED, None, None)


def test_lock_state_fits_the_ledger_column():
    """`risk_decisions.lock_state` is String(24); a silently truncated lock state is unsearchable."""
    assert len(LOCK_BASELINE_UNAVAILABLE) <= 24


def test_unavailable_reasons_are_distinguishable():
    """"No sync has run" and "sync ran, found nothing" have different operational fixes."""
    assert REASON_NO_ACCOUNT_STATE != REASON_BASIS_UNAVAILABLE
