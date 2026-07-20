"""ADR 0043 §D3 — the session-baseline SHADOW capture (write + evidence, no enforcement).

WHAT THIS DOES (and, importantly, does NOT do)
----------------------------------------------
Establishes the immutable per-session baseline (``risk_session_baselines``) that will eventually
replace the drifting ``accounts_state.last_equity`` basis for the daily-loss control. In THIS
increment it is **shadow-only**:

* it may WRITE a baseline row and EMIT structured evidence (logs);
* it changes **no risk decision** — no daily-loss threshold, no state-machine transition, no router
  or engine behavior. Nothing here reads back into the order path.

THE RULES (§D3)
---------------
* **Authoritative ET session date.** Derived from the market-session calendar
  (``MarketSession.classify``), never hand-rolled — holidays/half-days come from the same source
  the dispatch gate uses. Off a trading day there is no session to baseline.
* **Capture before activity.** The baseline is the reconciled equity taken *before the first
  sanctioned activity of the session*. If a baseline already exists for (account, session date) it
  is **reused, never replaced** — immutability is the whole point, and a restart only ever loads it.
* **Fail closed.** If no baseline exists but session activity has ALREADY occurred — including
  externally-submitted broker orders, which never appear in the local ``orders`` table — we must NOT
  mint a mid-session baseline. We emit fail-closed shadow evidence instead. Likewise, if we cannot
  *verify* the absence of activity (e.g. the broker read fails), we fail closed rather than guess.

All outcomes are explicit ``ShadowResult`` values; the caller (the account-sync wiring, a later
increment) treats them as telemetry only.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult

from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.risk_session_baseline import (
    BASELINE_SOURCE_RECONCILED_OPEN,
    BASELINE_STATUS_ACTIVE,
    RiskSessionBaseline,
)
from app.db.models.risk_session_baseline_shadow_outcome import (
    RiskSessionBaselineShadowOutcome,
)
from app.market.session import MarketSession, default_market_session

logger = structlog.get_logger(__name__)
_ET = ZoneInfo("America/New_York")

# --- explicit shadow outcomes -----------------------------------------------------------------
SHADOW_CAPTURED = "CAPTURED"  # no baseline + no prior activity → a fresh baseline was written
SHADOW_REUSED = "REUSED"  # an immutable baseline already existed → reused, never replaced
SHADOW_SKIPPED_NON_TRADING = "SKIPPED_NON_TRADING_DAY"  # not a trading day → nothing to baseline
SHADOW_MISSING_AFTER_ACTIVITY = "MISSING_AFTER_ACTIVITY"  # fail-closed: activity before any baseline
SHADOW_INDETERMINATE = "INDETERMINATE"  # fail-closed: could not verify absence of activity


@dataclass(frozen=True)
class ShadowResult:
    """The explicit outcome of a shadow capture attempt (telemetry only — never a risk decision)."""

    outcome: str
    account_id: int
    market_session_date: str | None
    baseline_equity: Decimal | None = None
    baseline_id: int | None = None
    activity_detected: bool = False

    @property
    def fail_closed(self) -> bool:
        return self.outcome in (SHADOW_MISSING_AFTER_ACTIVITY, SHADOW_INDETERMINATE)


def resolve_session_date(
    now: datetime, market_session: MarketSession | None = None
) -> str | None:
    """The authoritative ET trading date ("YYYY-MM-DD") for ``now``, or None off a trading day.

    Derived from the market-session calendar's own schedule (``regular_open``), so holidays and
    half-days are handled by the same authority the dispatch gate uses — never a hand-rolled
    weekday/offset calculation.
    """
    ms = market_session or default_market_session()
    info = ms.classify(now)
    if not info.is_trading_day or info.regular_open is None:
        return None
    return info.regular_open.astimezone(_ET).date().isoformat()


def _broker_order_instant(order: Any) -> datetime | None:
    """The order's activity time as a TIMEZONE-AWARE instant, or None if no field yields one.

    Naive datetimes and naive/invalid ISO strings are treated as UNUSABLE — never assumed to be
    UTC. The alpaca adapter serializes order timestamps via ``model_dump(mode="json")`` on tz-aware
    datetimes, i.e. ISO strings WITH an offset, so a naive value is out-of-contract; assigning it a
    timezone by assumption would be a guess. An unusable value in one field falls through to the
    next; if none is usable the order has no establishable activity time and the caller fails closed
    (§D3 — unverifiable → INDETERMINATE, never a false 'no activity')."""
    for key in ("submitted_at", "created_at", "updated_at"):
        value = order.get(key) if isinstance(order, dict) else getattr(order, key, None)
        if value is None:
            continue
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                return value
            continue  # naive datetime — out of contract, unusable
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt.tzinfo is not None:
                return dt
            continue  # parsed but naive — unusable
    return None


class SessionBaselineShadow:
    """Shadow-only session-baseline capture. Writes ``risk_session_baselines`` + emits evidence;
    never touches a risk decision, the state machine, or the order path."""

    def __init__(
        self,
        session: AsyncSession,
        adapter: Any | None = None,
        market_session: MarketSession | None = None,
    ) -> None:
        self._session = session
        # The broker adapter (concrete, exposing ``list_orders``) is the ONLY window onto
        # externally-submitted orders — they never reach the local ``orders`` table. Optional so the
        # module is testable and so a missing adapter fails closed rather than silently skipping.
        self._adapter = adapter
        self._ms = market_session or default_market_session()

    async def capture(
        self,
        *,
        account_id: int,
        reconciled_equity: Decimal,
        now: datetime | None = None,
    ) -> ShadowResult:
        """Capture or reuse the session baseline for ``account_id``; return the explicit outcome.

        Shadow-only: at most this INSERTs one immutable baseline row and logs. It never replaces an
        existing baseline, never writes when activity has already occurred, and never influences a
        risk decision.
        """
        now = now or datetime.now(UTC)
        info = self._ms.classify(now)
        session_date = resolve_session_date(now, self._ms)
        if session_date is None or info.regular_open is None:
            return await self._emit(SHADOW_SKIPPED_NON_TRADING, account_id, None)

        existing = await self._existing_baseline(account_id, session_date)
        if existing is not None:
            # Immutable: an established baseline is reused across restarts, never re-captured.
            return await self._emit(
                SHADOW_REUSED,
                account_id,
                session_date,
                baseline_equity=existing.baseline_equity,
                baseline_id=existing.id,
            )

        activity = await self._session_activity_occurred(account_id, info.regular_open)
        if activity is None:
            # Could not verify absence of activity → fail closed; do not mint a baseline.
            return await self._emit(SHADOW_INDETERMINATE, account_id, session_date, activity_detected=True)
        if activity:
            # Activity already occurred this session → a clean pre-activity baseline is impossible.
            return await self._emit(
                SHADOW_MISSING_AFTER_ACTIVITY, account_id, session_date, activity_detected=True
            )

        # No baseline, no prior activity → capture. ON CONFLICT DO NOTHING makes a concurrent
        # capture safe: exactly one writer inserts; the other reads back the same immutable row.
        stmt = (
            sqlite_insert(RiskSessionBaseline)
            .values(
                account_id=account_id,
                market_session_date=session_date,
                baseline_equity=reconciled_equity,
                baseline_source=BASELINE_SOURCE_RECONCILED_OPEN,
                captured_at=now,
                status=BASELINE_STATUS_ACTIVE,
                created_by="SYSTEM",
            )
            .on_conflict_do_nothing(
                index_elements=["account_id", "market_session_date"]
            )
        )
        result = cast("CursorResult[Any]", await self._session.execute(stmt))
        await self._session.commit()
        row = await self._session.scalar(
            select(RiskSessionBaseline).where(
                RiskSessionBaseline.account_id == account_id,
                RiskSessionBaseline.market_session_date == session_date,
            )
        )
        # rowcount 1 = we captured; 0 = a concurrent writer captured first → reuse theirs.
        outcome = SHADOW_CAPTURED if result.rowcount == 1 else SHADOW_REUSED
        return await self._emit(
            outcome,
            account_id,
            session_date,
            baseline_equity=row.baseline_equity if row is not None else None,
            baseline_id=row.id if row is not None else None,
        )

    async def _existing_baseline(
        self, account_id: int, session_date: str
    ) -> RiskSessionBaseline | None:
        """The immutable baseline for (account, session date), or None if not yet captured."""
        return await self._session.scalar(
            select(RiskSessionBaseline).where(
                RiskSessionBaseline.account_id == account_id,
                RiskSessionBaseline.market_session_date == session_date,
            )
        )

    async def _session_activity_occurred(
        self, account_id: int, session_open_utc: datetime
    ) -> bool | None:
        """Did any sanctioned activity occur this session? True / False, or None if unverifiable.

        Checks local app-originated orders and fills, AND — crucially — externally-submitted broker
        orders via ``adapter.list_orders`` (they never appear locally). A broker read that fails or
        an absent adapter returns None (unverifiable → the caller fails closed), never a false 'no'.
        """
        local_orders = await self._session.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.account_id == account_id, Order.created_at >= session_open_utc)
        )
        if local_orders:
            return True
        local_fills = await self._session.scalar(
            select(func.count())
            .select_from(Fill)
            .join(Order, Fill.order_id == Order.id)
            .where(Order.account_id == account_id, Fill.filled_at >= session_open_utc)
        )
        if local_fills:
            return True

        if self._adapter is None or not hasattr(self._adapter, "list_orders"):
            # No window onto external broker orders → cannot rule out activity → unverifiable.
            return None
        try:
            broker_orders = await asyncio.to_thread(self._adapter.list_orders)
        except Exception as exc:  # noqa: BLE001 — any broker failure is "unverifiable", fail closed
            logger.warning(
                "risk_session_baseline_broker_activity_check_failed",
                account_id=account_id,
                error=str(exc),
            )
            return None
        for order in broker_orders or []:
            instant = _broker_order_instant(order)
            if instant is None:
                # A broker order whose activity time can't be established means we cannot PROVE
                # that no regular-session activity occurred → unverifiable, fail closed. It must not
                # be dismissed just because other orders are known to be pre-open.
                logger.warning(
                    "risk_session_baseline_broker_order_timestamp_unverifiable",
                    account_id=account_id,
                )
                return None
            if instant >= session_open_utc:
                return True
        return False

    async def _emit(
        self,
        outcome: str,
        account_id: int,
        session_date: str | None,
        *,
        baseline_equity: Decimal | None = None,
        baseline_id: int | None = None,
        activity_detected: bool = False,
    ) -> ShadowResult:
        result = ShadowResult(
            outcome=outcome,
            account_id=account_id,
            market_session_date=session_date,
            baseline_equity=baseline_equity,
            baseline_id=baseline_id,
            activity_detected=activity_detected,
        )
        # Persist the latest outcome (when there is a session to key on) so the enforcement reader
        # can distinguish WHY a baseline is absent — never authoritative, evidence only.
        if session_date is not None:
            await self._persist_outcome(account_id, session_date, outcome)
        # Fail-closed outcomes are the operationally interesting ones — warn; the rest are info.
        log = logger.warning if result.fail_closed else logger.info
        log(
            "risk_session_baseline_shadow",
            outcome=outcome,
            account_id=account_id,
            market_session_date=session_date,
            baseline_equity=str(baseline_equity) if baseline_equity is not None else None,
            activity_detected=activity_detected,
        )
        return result

    async def _persist_outcome(
        self, account_id: int, session_date: str, outcome: str
    ) -> None:
        """Upsert the latest shadow outcome for (account, session date). Evidence only."""
        now = datetime.now(UTC)
        stmt = sqlite_insert(RiskSessionBaselineShadowOutcome).values(
            account_id=account_id,
            market_session_date=session_date,
            outcome=outcome,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["account_id", "market_session_date"],
            set_={"outcome": stmt.excluded.outcome, "updated_at": stmt.excluded.updated_at},
        )
        await self._session.execute(stmt)
        await self._session.commit()
