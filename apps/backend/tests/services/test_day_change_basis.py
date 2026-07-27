"""Baseline selection for the cached day-change figure.

The property under test throughout: **a baseline that was not found is never rendered as a number.**
`accounts_state.day_change` feeds the legacy daily-loss basis, so "unknown" leaking out as `0` (or,
worse, as `equity - 0`) is a risk-path input, not a display bug.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.equity_snapshot import EquitySnapshot
from app.db.models.user import User
from app.market.session import MarketSessionType, SessionInfo
from app.services.day_change_basis import (
    BROKER_LAST_EQUITY,
    PRIOR_SESSION_CLOSE_PROXY,
    UNAVAILABLE,
    from_broker_last_equity,
    prior_session_close_proxy,
)

NOW = datetime(2026, 7, 24, 18, 0, tzinfo=UTC)  # 14:00 ET, mid-session
OPEN = datetime(2026, 7, 24, 13, 30, tzinfo=UTC)  # 09:30 ET the same day


class _FixedSession:
    """A market calendar pinned to one day, so eligibility is decided by the snapshot's timestamp
    rather than by whenever the suite happens to run."""

    def __init__(self, *, trading_day: bool = True, regular_open: datetime | None = OPEN) -> None:
        self._trading_day = trading_day
        self._open = regular_open

    def classify(self, instant: datetime) -> SessionInfo:
        return SessionInfo(
            session=MarketSessionType.REGULAR if self._trading_day else MarketSessionType.CLOSED,
            as_of=instant,
            is_trading_day=self._trading_day,
            is_half_day=False,
            regular_open=self._open if self._trading_day else None,
            regular_close=None,
        )


async def _seed(session_factory, snapshots: list[tuple[datetime, str]]) -> None:
    async with session_factory() as session:
        session.add(User(id=1, email="t@example.com", display_name="T"))
        await session.flush()
        session.add(
            Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper")
        )
        for ts, equity in snapshots:
            session.add(
                EquitySnapshot(
                    account_id=1,
                    ts=ts,
                    equity=Decimal(equity),
                    cash=Decimal(0),
                    portfolio_value=Decimal(equity),
                    day_change_pct=Decimal(0),
                )
            )
        await session.commit()


# ---------------------------------------------------------------- broker basis


def test_broker_basis_is_a_fraction_not_a_percentage() -> None:
    """`formatPercent` in the UI multiplies by 100; storing a percentage here double-scaled it."""
    dc = from_broker_last_equity(Decimal("98750.42"), Decimal("100000.00"))
    assert dc is not None
    assert dc.basis == BROKER_LAST_EQUITY
    assert dc.day_change == Decimal("-1249.58")
    assert dc.day_change_pct == Decimal("-1249.58") / Decimal("100000.00")
    assert abs(dc.day_change_pct) < Decimal("0.02")  # fraction, not 1.25


def test_unusable_last_equity_yields_no_basis() -> None:
    """Zero is 'not reported', never 'the account was empty yesterday' — a funded account's prior
    close is never 0, and `equity - 0` would report the whole book as today's move."""
    assert from_broker_last_equity(Decimal("102177.42"), Decimal(0)) is None
    assert from_broker_last_equity(Decimal("102177.42"), None) is None
    assert from_broker_last_equity(Decimal("102177.42"), Decimal("-5")) is None


# ------------------------------------------------------- prior-close proxy


async def test_proxy_preserves_a_real_intraday_loss(session_factory) -> None:
    """The case the reviewer rejected zero over: down $4,000 with no broker last_equity. The loss
    must survive as a loss, because the legacy daily-loss gate reads this number."""
    await _seed(session_factory, [(OPEN - timedelta(days=1), "84000")])
    async with session_factory() as session:
        dc = await prior_session_close_proxy(
            session, 1, Decimal("80000"), NOW, market_session=_FixedSession()
        )
    assert dc is not None
    assert dc.basis == PRIOR_SESSION_CLOSE_PROXY
    assert dc.day_change == Decimal("-4000")
    assert dc.baseline_equity == Decimal("84000")


async def test_snapshot_taken_after_the_open_is_not_a_baseline(session_factory) -> None:
    """A mid-session point already contains today's move; using it would report ~0 change."""
    await _seed(session_factory, [(OPEN + timedelta(minutes=30), "84000")])
    async with session_factory() as session:
        dc = await prior_session_close_proxy(
            session, 1, Decimal("80000"), NOW, market_session=_FixedSession()
        )
    assert dc is None


async def test_snapshot_older_than_the_bound_is_refused(session_factory) -> None:
    await _seed(session_factory, [(OPEN - timedelta(days=5), "84000")])
    async with session_factory() as session:
        dc = await prior_session_close_proxy(
            session, 1, Decimal("80000"), NOW, market_session=_FixedSession()
        )
    assert dc is None


async def test_long_weekend_stays_within_the_bound(session_factory) -> None:
    """Why four days: a Friday close (20:00 UTC) must still serve the session after a Monday
    holiday — roughly 3 d 22 h later, comfortably inside the bound, while a genuinely skipped week
    is not."""
    await _seed(session_factory, [(NOW - timedelta(days=3, hours=22), "84000")])
    async with session_factory() as session:
        dc = await prior_session_close_proxy(
            session, 1, Decimal("80000"), NOW, market_session=_FixedSession()
        )
    assert dc is not None and dc.day_change == Decimal("-4000")


async def test_the_bound_is_exact(session_factory) -> None:
    await _seed(session_factory, [(NOW - timedelta(days=4, minutes=1), "84000")])
    async with session_factory() as session:
        dc = await prior_session_close_proxy(
            session, 1, Decimal("80000"), NOW, market_session=_FixedSession()
        )
    assert dc is None


async def test_latest_eligible_snapshot_wins(session_factory) -> None:
    await _seed(
        session_factory,
        [(OPEN - timedelta(days=3), "70000"), (OPEN - timedelta(days=1), "84000")],
    )
    async with session_factory() as session:
        dc = await prior_session_close_proxy(
            session, 1, Decimal("80000"), NOW, market_session=_FixedSession()
        )
    assert dc is not None and dc.baseline_equity == Decimal("84000")


async def test_zero_equity_snapshot_is_not_a_baseline(session_factory) -> None:
    await _seed(session_factory, [(OPEN - timedelta(days=1), "0")])
    async with session_factory() as session:
        dc = await prior_session_close_proxy(
            session, 1, Decimal("80000"), NOW, market_session=_FixedSession()
        )
    assert dc is None


async def test_no_snapshots_yields_no_basis(session_factory) -> None:
    await _seed(session_factory, [])
    async with session_factory() as session:
        dc = await prior_session_close_proxy(
            session, 1, Decimal("80000"), NOW, market_session=_FixedSession()
        )
    assert dc is None


async def test_off_a_trading_day_the_cutoff_is_now(session_factory) -> None:
    """No open has happened, so the most recent point still stands as the prior close."""
    await _seed(session_factory, [(NOW - timedelta(hours=2), "84000")])
    async with session_factory() as session:
        dc = await prior_session_close_proxy(
            session,
            1,
            Decimal("80000"),
            NOW,
            market_session=_FixedSession(trading_day=False, regular_open=None),
        )
    assert dc is not None and dc.day_change == Decimal("-4000")


async def test_another_accounts_snapshot_is_never_borrowed(session_factory) -> None:
    await _seed(session_factory, [(OPEN - timedelta(days=1), "84000")])
    async with session_factory() as session:
        dc = await prior_session_close_proxy(
            session, 2, Decimal("80000"), NOW, market_session=_FixedSession()
        )
    assert dc is None


# ------------------------------------------------------------------- wiring


def test_model_default_matches_constant() -> None:
    """The column spells the literal out to avoid a models→services import; pin the two together."""
    col = AccountState.__table__.c.day_change_basis
    assert col.default.arg == UNAVAILABLE
    assert col.server_default.arg == UNAVAILABLE
