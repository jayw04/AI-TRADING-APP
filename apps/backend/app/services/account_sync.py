"""Account snapshot poller.

Pulls the live account snapshot from Alpaca and upserts the `accounts_state`
cache row. Publishes `account.snapshot` events for live UI updates.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.brokers.alpaca import AlpacaAdapter
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)


class AccountSyncService:
    def __init__(
        self,
        adapter: AlpacaAdapter,
        session_factory: async_sessionmaker,
        bus: EventBus,
    ) -> None:
        self._adapter = adapter
        self._session_factory = session_factory
        self._bus = bus

    async def sync_once(self) -> dict[str, Any]:
        """Pull the latest account snapshot, upsert AccountState, publish event."""
        raw = await asyncio.to_thread(self._adapter.get_account)
        payload = _normalize_account(raw)

        async with self._session_factory() as session:
            # For MVP single-user, the *first* paper Alpaca account is the target.
            # Multi-account support comes later when accounts.broker_account_id lands.
            account = await self._resolve_account(session)
            if account is None:
                logger.warning("account_sync_no_account_row")
                return payload

            now = datetime.now(UTC)
            stmt = sqlite_insert(AccountState).values(
                account_id=account.id,
                **payload,
                updated_at=now,
                raw_payload=raw,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["account_id"],
                set_={
                    "cash": stmt.excluded.cash,
                    "equity": stmt.excluded.equity,
                    "last_equity": stmt.excluded.last_equity,
                    "buying_power": stmt.excluded.buying_power,
                    "portfolio_value": stmt.excluded.portfolio_value,
                    "daytrade_count": stmt.excluded.daytrade_count,
                    "day_change": stmt.excluded.day_change,
                    "day_change_pct": stmt.excluded.day_change_pct,
                    "status": stmt.excluded.status,
                    "pattern_day_trader": stmt.excluded.pattern_day_trader,
                    "trading_blocked": stmt.excluded.trading_blocked,
                    "account_blocked": stmt.excluded.account_blocked,
                    "raw_payload": stmt.excluded.raw_payload,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(stmt)
            await session.commit()

        logger.info(
            "account_sync_completed",
            status=payload["status"],
            equity=str(payload["equity"]),
        )
        await self._bus.publish(
            "account.snapshot",
            {
                "account_id": account.id,
                **{k: str(v) if isinstance(v, Decimal) else v for k, v in payload.items()},
            },
        )
        return payload

    async def _resolve_account(self, session: AsyncSession) -> Account | None:
        mode = AccountMode.paper if self._adapter.is_paper else AccountMode.live
        result = await session.execute(
            select(Account).where(Account.broker == "alpaca", Account.mode == mode)
        )
        return result.scalars().first()


def _to_decimal(v: Any, default: str = "0") -> Decimal:
    if v is None or v == "":
        return Decimal(default)
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(default)


def _normalize_account(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Alpaca's account fields to `AccountState` column names."""
    equity = _to_decimal(raw.get("equity"))
    last_equity = _to_decimal(raw.get("last_equity"))
    day_change = equity - last_equity
    day_change_pct = (
        (day_change / last_equity * Decimal(100)) if last_equity > 0 else Decimal(0)
    )
    return {
        "cash": _to_decimal(raw.get("cash")),
        "equity": equity,
        "last_equity": last_equity,
        "buying_power": _to_decimal(raw.get("buying_power")),
        "portfolio_value": _to_decimal(raw.get("portfolio_value") or raw.get("equity")),
        "daytrade_count": int(raw.get("daytrade_count") or 0),
        "day_change": day_change,
        "day_change_pct": day_change_pct,
        "status": str(raw.get("status") or "UNKNOWN"),
        "pattern_day_trader": bool(raw.get("pattern_day_trader") or False),
        "trading_blocked": bool(raw.get("trading_blocked") or False),
        "account_blocked": bool(raw.get("account_blocked") or False),
    }
