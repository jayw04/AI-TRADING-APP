"""Position snapshot poller.

Pulls positions from Alpaca, upserts into the `positions` table, deletes
positions Alpaca no longer reports (closed), publishes a snapshot event.

Session 4 added DB persistence (this file). Session 5 will add a second
write path from the trade-update consumer so positions update immediately
on fill rather than waiting for the next 10s poll.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.brokers.base import BrokerAdapter
    from app.brokers.registry import BrokerRegistry

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.brokers.alpaca import AlpacaAdapter
from app.db.models.account import Account, AccountMode
from app.db.models.position import Position
from app.db.models.symbol import Symbol
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)


class PositionSyncService:
    # After this many consecutive polls where Alpaca reports a (account, symbol)
    # we cannot resolve locally (e.g., unknown ticker), the service emits a
    # `system.reconciliation_drift` event and logs WARNING. In-memory counters
    # are intentional — a backend restart resets observations, which is what
    # you want after a deploy.
    _DRIFT_THRESHOLD = 3

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
        # from the registry (built from that user's encrypted creds), so every account's
        # positions are synced — not just the first/startup one. Mirrors AccountSyncService.
        self._broker_registry = broker_registry
        # Keyed by (account_id, ticker) — unresolved tickers can't have a
        # symbol_id (that's why they're unresolved).
        self._drift_counters: dict[tuple[int, str], int] = {}
        self._drift_warned: set[tuple[int, str]] = set()

    async def sync_once(self) -> list[dict[str, Any]]:
        """Pull the *primary* account's positions and reconcile them.

        Back-compat single-account path (the first paper/live account via the startup
        adapter); ``sync_all`` covers every account via the broker registry."""
        async with self._session_factory() as session:
            mode = AccountMode.paper if self._adapter.is_paper else AccountMode.live
            account = (
                await session.execute(
                    select(Account).where(Account.broker == "alpaca", Account.mode == mode)
                )
            ).scalars().first()
        if account is None:
            logger.warning("position_sync_no_account_row")
            await self._bus.publish("positions.snapshot", {"count": 0, "positions": []})
            return []
        return await self._sync_account(account, self._adapter)

    async def sync_all(self) -> dict[str, list[int]]:
        """Sync EVERY broker account's positions from its own per-user adapter (multi-account).

        Each account's adapter comes from the broker registry (constructed per-user from that
        user's encrypted credentials and connected at boot). Falls back to the single-account
        ``sync_once`` when no registry is wired (tests / minimal boots). One account's failure
        is logged and skipped — it never aborts the others. Mirrors AccountSyncService.sync_all."""
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
                await self._sync_account(account, adapter)
                synced.append(account.id)
            except Exception as exc:  # one account must not kill the sweep
                logger.warning(
                    "position_sync_account_failed", account_id=account.id, error=str(exc)
                )
                errors.append(account.id)
        logger.info("position_sync_all_completed", synced=synced, skipped=skipped, errors=errors)
        return {"synced": synced, "skipped": skipped, "errors": errors}

    async def _sync_account(
        self, account: Account, adapter: BrokerAdapter
    ) -> list[dict[str, Any]]:
        """Pull one account's positions, upsert/delete scoped to it, drift-check, publish."""
        raw_positions = await asyncio.to_thread(adapter.get_positions)
        normalized = [_normalize_position(p) for p in raw_positions]

        async with self._session_factory() as session:
            tickers = [p["symbol"] for p in normalized if p["symbol"]]
            symbol_rows = (
                (
                    await session.execute(
                        select(Symbol).where(Symbol.ticker.in_(tickers))
                    )
                ).scalars().all()
                if tickers
                else []
            )
            symbol_id_by_ticker = {s.ticker: s.id for s in symbol_rows}

            now = datetime.now(UTC)
            seen_symbol_ids: set[int] = set()
            unresolved_tickers: set[str] = set()

            for p in normalized:
                ticker = p["symbol"]
                symbol_id = symbol_id_by_ticker.get(ticker)
                if symbol_id is None:
                    # Symbol not in our table — asset sync hasn't picked it up,
                    # or it's a delisted name. Skip for MVP; P4 polish can add
                    # a "create-on-demand" fallback. Tracked for drift detection.
                    logger.warning("position_sync_unknown_symbol", ticker=ticker)
                    if ticker:
                        unresolved_tickers.add(ticker)
                    continue
                seen_symbol_ids.add(symbol_id)

                stmt = sqlite_insert(Position).values(
                    user_id=account.user_id,
                    account_id=account.id,
                    symbol_id=symbol_id,
                    qty=p["qty"],
                    avg_entry_price=p["avg_entry_price"],
                    side=p["side"],
                    market_value=p["market_value"],
                    cost_basis=p["cost_basis"],
                    unrealized_pl=p["unrealized_pl"],
                    unrealized_plpc=p["unrealized_plpc"],
                    updated_at=now,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["account_id", "symbol_id"],
                    set_={
                        "qty": stmt.excluded.qty,
                        "avg_entry_price": stmt.excluded.avg_entry_price,
                        "side": stmt.excluded.side,
                        "market_value": stmt.excluded.market_value,
                        "cost_basis": stmt.excluded.cost_basis,
                        "unrealized_pl": stmt.excluded.unrealized_pl,
                        "unrealized_plpc": stmt.excluded.unrealized_plpc,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await session.execute(stmt)

            # Delete stale positions Alpaca no longer reports. The Position
            # table is the "open positions" cache; closed positions leave
            # history in orders/fills, not here.
            existing_ids = (
                await session.execute(
                    select(Position.symbol_id).where(Position.account_id == account.id)
                )
            ).scalars().all()
            stale = [sid for sid in existing_ids if sid not in seen_symbol_ids]
            if stale:
                await session.execute(
                    delete(Position).where(
                        Position.account_id == account.id,
                        Position.symbol_id.in_(stale),
                    )
                )
                logger.info("position_sync_deleted_stale", count=len(stale))

            await session.commit()

        # Drift detection: a position Alpaca reports that we couldn't resolve
        # to a local Symbol row. Reset counters for tickers we DID see; bump
        # for unresolved ones; warn + publish on the third consecutive miss.
        resolved_keys = {(account.id, t) for t in tickers if t in symbol_id_by_ticker}
        for key in resolved_keys:
            self._drift_counters[key] = 0
            self._drift_warned.discard(key)
        for ticker in unresolved_tickers:
            key = (account.id, ticker)
            self._drift_counters[key] = self._drift_counters.get(key, 0) + 1
            count = self._drift_counters[key]
            if count >= self._DRIFT_THRESHOLD and key not in self._drift_warned:
                self._drift_warned.add(key)
                logger.warning(
                    "reconciliation_drift_detected",
                    account_id=key[0],
                    ticker=key[1],
                    consecutive_polls=count,
                )
                await self._bus.publish(
                    "system.reconciliation_drift",
                    {
                        "account_id": key[0],
                        "ticker": key[1],
                        "consecutive_polls": count,
                    },
                )

        logger.info("position_sync_completed", account_id=account.id, count=len(normalized))
        await self._bus.publish(
            "positions.snapshot",
            {
                "account_id": account.id,
                "count": len(normalized),
                "positions": _decimals_to_str(normalized),
            },
        )
        return normalized


def _to_decimal(v: Any) -> Decimal:
    if v is None or v == "":
        return Decimal(0)
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(0)


def _normalize_position(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": raw.get("symbol"),
        "qty": _to_decimal(raw.get("qty")),
        "avg_entry_price": _to_decimal(raw.get("avg_entry_price")),
        "side": raw.get("side"),
        "market_value": _to_decimal(raw.get("market_value")),
        "cost_basis": _to_decimal(raw.get("cost_basis")),
        "unrealized_pl": _to_decimal(raw.get("unrealized_pl")),
        "unrealized_plpc": _to_decimal(raw.get("unrealized_plpc")),
    }


def _decimals_to_str(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """JSON-friendly snapshot for the event bus subscribers."""
    return [
        {k: (str(v) if isinstance(v, Decimal) else v) for k, v in p.items()}
        for p in positions
    ]
