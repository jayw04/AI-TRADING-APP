"""Account snapshot poller.

Pulls the live account snapshot from Alpaca and upserts the `accounts_state`
cache row. Publishes `account.snapshot` events for live UI updates.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.brokers.registry import BrokerRegistry

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.brokers.alpaca import AlpacaAdapter
from app.config import get_settings
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.events.bus import EventBus
from app.risk.loss_control.session_baseline import SessionBaselineShadow

logger = structlog.get_logger(__name__)


class AccountSyncService:
    def __init__(
        self,
        adapter: AlpacaAdapter,
        session_factory: async_sessionmaker,
        bus: EventBus,
        broker_registry: BrokerRegistry | None = None,
    ) -> None:
        self._adapter = adapter
        self._session_factory = session_factory
        self._bus = bus
        # P13.5: when present, sync_all() resolves EACH account's own per-user adapter
        # from the registry (built from that user's encrypted creds), so every paper
        # account's balance is synced — not just the first/startup one.
        self._broker_registry = broker_registry

    async def sync_once(self) -> dict[str, Any]:
        """Pull the *primary* paper account's snapshot and upsert its AccountState.

        Back-compat single-account path (the first paper account via the startup adapter);
        ``sync_all`` covers every account via the broker registry."""
        raw = await asyncio.to_thread(self._adapter.get_account)
        payload = _normalize_account(raw)
        async with self._session_factory() as session:
            account = await self._resolve_account(session)
        if account is None:
            logger.warning("account_sync_no_account_row")
            return payload
        await self._upsert_and_publish(account.id, raw, payload, self._adapter)
        return payload

    async def sync_all(self) -> dict[str, list[int]]:
        """Sync EVERY broker account from its own per-user adapter (P13.5 multi-account).

        Each account's adapter comes from the broker registry (constructed per-user from that
        user's encrypted credentials and connected at boot). Falls back to the single-account
        ``sync_once`` when no registry is wired (tests / minimal boots). One account's failure
        is logged and skipped — it never aborts the others."""
        if self._broker_registry is None:
            await self.sync_once()
            return {"synced": [], "skipped": [], "errors": []}
        async with self._session_factory() as session:
            accounts = (
                await session.execute(select(Account).where(Account.broker == "alpaca"))
            ).scalars().all()
        synced: list[int] = []
        skipped: list[int] = []
        errors: list[int] = []
        for account in accounts:
            adapter = self._broker_registry.get(account.id)
            if adapter is None:
                skipped.append(account.id)  # no per-user adapter (missing creds)
                continue
            try:
                raw = await asyncio.to_thread(adapter.get_account)
                await self._upsert_and_publish(
                    account.id, raw, _normalize_account(raw), adapter
                )
                synced.append(account.id)
            except Exception as exc:  # one account must not kill the sweep
                logger.warning("account_sync_account_failed", account_id=account.id, error=str(exc))
                errors.append(account.id)
        logger.info("account_sync_all_completed", synced=synced, skipped=skipped, errors=errors)
        return {"synced": synced, "skipped": skipped, "errors": errors}

    async def _upsert_and_publish(
        self,
        account_id: int,
        raw: dict[str, Any],
        payload: dict[str, Any],
        adapter: Any,
    ) -> None:
        """Upsert one account's AccountState row and publish its snapshot event.

        ``adapter`` is the account's OWN broker adapter — used only by the ADR 0043 §D3 shadow
        baseline capture (to see externally-submitted broker orders); it is not otherwise needed
        here."""
        async with self._session_factory() as session:
            now = datetime.now(UTC)
            stmt = sqlite_insert(AccountState).values(
                account_id=account_id, **payload, updated_at=now, raw_payload=raw,
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
            # ADR 0043 §D3 — SHADOW baseline capture, from the equity JUST reconciled above (never a
            # second broker call for equity). After the AccountState commit + before publish. Fully
            # non-authoritative and exception-isolated: a shadow failure must never interrupt sync,
            # and the result is intentionally discarded — it can become no baseline decision, no
            # transition, no breaker trip.
            await self._maybe_capture_session_baseline(
                session, adapter, account_id, payload["equity"], now
            )
        logger.info("account_sync_completed", account_id=account_id,
                    status=payload["status"], equity=str(payload["equity"]))
        await self._bus.publish(
            "account.snapshot",
            {"account_id": account_id,
             **{k: str(v) if isinstance(v, Decimal) else v for k, v in payload.items()}},
        )

    async def _maybe_capture_session_baseline(
        self,
        session: AsyncSession,
        adapter: Any,
        account_id: int,
        reconciled_equity: Decimal,
        now: datetime,
    ) -> None:
        """ADR 0043 §D3 shadow hook — best-effort, flag-gated, and non-authoritative.

        Off by default (``session_baseline_shadow_enabled``). Any failure is swallowed and logged so
        it can never interrupt account synchronization; ``CancelledError`` (a ``BaseException``) is
        NOT caught, so task cancellation still propagates. The ``ShadowResult`` is discarded — the
        shadow can influence no risk decision."""
        if not get_settings().session_baseline_shadow_enabled:
            return
        try:
            await SessionBaselineShadow(session=session, adapter=adapter).capture(
                account_id=account_id, reconciled_equity=reconciled_equity, now=now
            )
        except Exception:
            logger.exception(
                "risk_session_baseline_shadow_unexpected_failure", account_id=account_id
            )

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
    # Alpaca may omit or zero last_equity on fresh paper accounts; equity − 0 would
    # mis-report the full book as "today's change". Leave day metrics at zero here;
    # GET /account falls back to equity_snapshots when last_equity is unusable.
    if last_equity > 0:
        day_change = equity - last_equity
        day_change_pct = day_change / last_equity  # fraction (matches total_return_pct)
    else:
        day_change = Decimal(0)
        day_change_pct = Decimal(0)
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
