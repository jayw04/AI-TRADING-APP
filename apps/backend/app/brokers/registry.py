"""BrokerRegistry — one BrokerAdapter per account, selected by AccountMode.

Lifecycle:
  - ``load_all()`` — on boot, construct one adapter per ``accounts`` row.
  - ``refresh(account_id)`` — (re)construct after an account is created.
  - ``register(account_id, adapter)`` — insert an already-constructed adapter
    (the lifespan reuses the connected startup paper adapter rather than opening
    a second TradingClient).
  - ``get(account_id)`` — the OrderRouter's per-request lookup.
  - ``close_all()`` — disconnect every adapter on shutdown.

Credential source is :func:`credentials_for_mode` (env) in P5 §2; P5 §4 swaps
that one call for the encrypted credential store, leaving this shape unchanged.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.alpaca.credentials import credentials_for_mode
from app.brokers.base import BrokerAdapter
from app.db.models.account import Account

logger = structlog.get_logger(__name__)


class BrokerRegistry:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._adapters: dict[int, BrokerAdapter] = {}

    async def load_all(self) -> None:
        """Construct one adapter per account row. Network-free (no connect())."""
        async with self._session_factory() as session:
            rows = (await session.execute(select(Account))).scalars().all()
        for row in rows:
            await self._try_construct(row)

    async def refresh(self, account_id: int) -> None:
        """(Re)construct the adapter for one account — called after creation."""
        async with self._session_factory() as session:
            row = await session.get(Account, account_id)
        if row is None:
            return
        prior = self._adapters.pop(account_id, None)
        if prior is not None:
            self._safe_disconnect(prior)
        await self._try_construct(row)

    def register(self, account_id: int, adapter: BrokerAdapter) -> None:
        """Insert an already-constructed (and possibly connected) adapter.

        The lifespan uses this to reuse the connected startup paper adapter for
        the user's paper account(s) instead of building a second TradingClient.
        """
        self._adapters[account_id] = adapter

    def get(self, account_id: int) -> BrokerAdapter | None:
        return self._adapters.get(account_id)

    def close_all(self) -> None:
        for adapter in self._adapters.values():
            self._safe_disconnect(adapter)
        self._adapters.clear()

    # ---- internal ----

    async def _try_construct(self, account: Account) -> None:
        try:
            self._adapters[account.id] = await self._construct(account)
            logger.info(
                "broker_registry_adapter_loaded",
                account_id=account.id,
                broker=account.broker,
                mode=account.mode.value,
            )
        except Exception as exc:
            # One bad account must not crash boot. The OrderRouter falls back to
            # its default adapter or refuses cleanly when none is registered.
            logger.warning(
                "broker_registry_adapter_failed",
                account_id=account.id,
                error=str(exc),
            )

    async def _construct(self, account: Account) -> BrokerAdapter:
        if account.broker != "alpaca":
            raise ValueError(f"No adapter for broker={account.broker!r}")
        creds = await credentials_for_mode(
            account.mode.value, account.user_id, self._session_factory
        )
        # Do NOT connect() here: connect() makes a network call (get_account).
        # Construction must be network-free so a Norton-blocked dev box or a
        # live account with placeholder creds still boots. The lifespan connects
        # the startup paper adapter; live adapters are never reached at runtime
        # in P5 §2 (the §1 BrokerModeError guard short-circuits first).
        return AlpacaAdapter(credentials=creds)

    def _safe_disconnect(self, adapter: BrokerAdapter) -> None:
        try:
            adapter.disconnect()
        except Exception:
            logger.exception("broker_registry_disconnect_failed")
