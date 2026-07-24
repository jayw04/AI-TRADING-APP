"""Provenance for the day-change figure cached on ``accounts_state``.

``day_change`` answers "how much is this account up or down *today*", which requires a baseline —
the account's equity at the start of the current session. Alpaca normally supplies one as
``last_equity`` (prior close). When it does not — it omits the field, or reports ``0`` on a freshly
created paper account — there is no baseline, and the honest answer is **"unknown"**, not zero.

The failure this module exists to prevent: ``equity - 0`` reports the entire book as today's change,
and a plain ``0`` claims a measured flat day. Both are assertions about a quantity nobody measured,
and ``accounts_state.day_change`` is an input to the legacy daily-loss basis
(``app/risk/engine.py::_daily_loss_day_change`` with the ADR-0043 flag OFF), so a wrong value there
is a risk-path input, not a display nit.

Three bases, most trustworthy first:

``BROKER_LAST_EQUITY``
    Alpaca's own prior-close equity. The normal case.

``PRIOR_SESSION_CLOSE_PROXY``
    The latest ``equity_snapshots`` point strictly before the current session's open, and no more
    than ``MAX_PROXY_AGE`` old. That series is written once per account near the close
    (``services/equity_snapshot.py``), so this is a **prior-close proxy and nothing more**. It is
    explicitly NOT a current-session opening baseline, and must never be described as one or
    treated as equivalent to ``risk_session_baselines`` — the immutable ADR-0043 session baseline
    is a different, stronger artifact captured at the open of the session it belongs to.

``UNAVAILABLE``
    No usable baseline. ``day_change`` is reported as ``None`` by the API. The numeric column keeps
    ``0`` so that existing consumers behave exactly as they do today; **the label, not the number,
    is the truth**. Teaching the risk path to act on ``UNAVAILABLE`` (reduction-only protection) is
    deliberately a separate change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.equity_snapshot import EquitySnapshot
from app.market.session import MarketSession, default_market_session

BROKER_LAST_EQUITY = "BROKER_LAST_EQUITY"
PRIOR_SESSION_CLOSE_PROXY = "PRIOR_SESSION_CLOSE_PROXY"
UNAVAILABLE = "UNAVAILABLE"

#: How stale a prior-close snapshot may be and still stand in for the day baseline. Four calendar
#: days covers a Friday close read on the following Tuesday (long weekend); beyond that the
#: "prior close" is some other session's close and the proxy is refused.
MAX_PROXY_AGE = timedelta(days=4)


@dataclass(frozen=True)
class DayChange:
    """A day-change figure together with the provenance of the baseline behind it."""

    day_change: Decimal
    day_change_pct: Decimal
    basis: str
    baseline_equity: Decimal | None

    @property
    def measurable(self) -> bool:
        """True when a baseline was actually found. ``False`` ⇒ the numbers are placeholders."""
        return self.basis != UNAVAILABLE


UNMEASURED = DayChange(
    day_change=Decimal(0), day_change_pct=Decimal(0), basis=UNAVAILABLE, baseline_equity=None
)


def _metrics(equity: Decimal, baseline: Decimal, basis: str) -> DayChange:
    change = equity - baseline
    return DayChange(
        day_change=change,
        day_change_pct=change / baseline,  # fraction, matching total_return_pct
        basis=basis,
        baseline_equity=baseline,
    )


def from_broker_last_equity(equity: Decimal, last_equity: Decimal | None) -> DayChange | None:
    """The broker-supplied basis, or ``None`` when ``last_equity`` cannot serve as a baseline.

    ``None`` (field absent) and any value ``<= 0`` are both unusable: a funded account's prior close
    is never zero, so a zero here means "not reported", not "the account was empty yesterday".
    """
    if last_equity is None or last_equity <= 0:
        return None
    return _metrics(equity, last_equity, BROKER_LAST_EQUITY)


async def prior_session_close_proxy(
    session: AsyncSession,
    account_id: int,
    equity: Decimal,
    now: datetime,
    market_session: MarketSession | None = None,
) -> DayChange | None:
    """The fallback basis: the latest equity snapshot strictly before this session's open.

    Returns ``None`` — never a zero — when no snapshot qualifies. Eligibility is deliberately
    narrow:

    * **strictly before the current session's open**, so a snapshot taken after today's activity
      began can never be mistaken for an opening baseline. The cutoff comes from the market
      calendar (``regular_open``), the same authority the dispatch gate uses; off a trading day
      there is no open yet, so the cutoff is ``now``;
    * **no older than ``MAX_PROXY_AGE``**;
    * **strictly positive** — a zero or negative recorded equity is not a usable baseline.
    """
    # Everything below compares against values stored in UTC. SQLite's DATETIME renders the naive
    # components of whatever it is handed, so a non-UTC ``now`` would silently compare local wall
    # time against UTC rows.
    now = now.astimezone(UTC) if now.tzinfo is not None else now.replace(tzinfo=UTC)

    ms = market_session or default_market_session()
    info = ms.classify(now)
    cutoff = info.regular_open if (info.is_trading_day and info.regular_open is not None) else now

    row = (
        await session.execute(
            select(EquitySnapshot.ts, EquitySnapshot.equity)
            .where(EquitySnapshot.account_id == account_id, EquitySnapshot.ts < cutoff)
            .order_by(EquitySnapshot.ts.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None

    ts, baseline = row
    if ts.tzinfo is None:  # SQLite hands back naive datetimes; the column is stored in UTC
        ts = ts.replace(tzinfo=UTC)
    if now - ts > MAX_PROXY_AGE or baseline is None or baseline <= 0:
        return None
    return _metrics(equity, Decimal(str(baseline)), PRIOR_SESSION_CLOSE_PROXY)
