"""BrokerRegistry — one BrokerAdapter per account, selected by AccountMode.

Lifecycle:
  - ``load_all()`` — on boot, construct one adapter per ``accounts`` row.
  - ``refresh(account_id)`` — (re)construct after an account is created.
  - ``register(account_id, adapter)`` — insert an already-constructed adapter
    (the lifespan reuses the connected startup paper adapter rather than opening
    a second TradingClient).
  - ``adopt_startup_adapter(startup_adapter)`` — after ``load_all()``, reuse the
    connected startup adapter only for the account whose creds match it, and
    connect each *other* paper account's own per-user adapter (§5a).
  - ``get(account_id)`` — the OrderRouter's per-request lookup.
  - ``close_all()`` — disconnect every adapter on shutdown.

Credential source is :func:`credentials_for_mode` (env) in P5 §2; P5 §4 swaps
that one call for the encrypted credential store, leaving this shape unchanged.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.alpaca.credentials import credentials_for_mode
from app.brokers.base import BrokerAdapter
from app.db.models.account import Account, AccountMode

logger = structlog.get_logger(__name__)


def _key_fingerprint(api_key: str | None) -> str:
    """A non-reversible fingerprint for logging — never the key itself.

    Lets boot logs / tests confirm *which* credential an account resolved to
    (e.g. "did account 2 get ALPACA_PAPER_1, not BFY6?") without ever emitting
    the secret value."""
    if not api_key:
        return "none"
    digest = hashlib.sha256(api_key.encode()).hexdigest()[:8]
    return f"sha256:{digest} (len={len(api_key)})"


def _adapter_api_key(adapter: BrokerAdapter | None) -> str | None:
    """The api key an adapter was built with, or None if it doesn't expose one
    (non-Alpaca / spy adapters)."""
    creds = getattr(adapter, "credentials", None)
    return getattr(creds, "api_key", None)


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

    async def adopt_startup_adapter(
        self,
        startup_adapter: BrokerAdapter,
        *,
        connect: Callable[[BrokerAdapter], Awaitable[None]] | None = None,
    ) -> None:
        """§5a (Range Trader paper activation): reconcile each paper account's
        adapter with the already-connected startup adapter. Call once, after
        ``load_all()``.

        ``load_all()`` builds a per-user adapter for every account from *that
        user's own* encrypted credentials, but never connects them. The startup
        path separately connected exactly one adapter (from the env paper
        creds — historically the BFY6 account). For each **paper** account:

        - if its constructed adapter carries the **same api key** as the startup
          adapter, reuse the connected startup adapter (don't open a second
          TradingClient to the same account);
        - otherwise ``connect()`` its **own** per-user adapter, so a second
          paper account (e.g. ``ALPACA_PAPER_1`` under a different user) trades
          its own Alpaca account rather than the startup one;
        - if ``load_all()`` built no adapter (missing store creds), fall back to
          the startup adapter so the startup account still works — logged at
          WARNING because a *second* account landing here means missing creds.

        Replaces the prior blanket loop that registered the single startup
        adapter for **every** paper account — which silently routed every paper
        account's orders to the startup (env) broker account regardless of which
        user owned it.
        """
        if connect is None:
            connect = self._default_connect

        startup_key = _adapter_api_key(startup_adapter)
        async with self._session_factory() as session:
            paper_accounts = (
                await session.execute(
                    select(Account).where(Account.mode == AccountMode.paper)
                )
            ).scalars().all()

        for account in paper_accounts:
            constructed = self._adapters.get(account.id)
            constructed_key = _adapter_api_key(constructed)

            if constructed is None:
                # No per-user adapter could be built (missing creds). Keep the
                # startup adapter working for the startup account; flag others.
                self._adapters[account.id] = startup_adapter
                logger.warning(
                    "broker_registry_startup_adapter_fallback",
                    account_id=account.id,
                    detail="no per-user adapter constructed; using startup adapter",
                )
            elif (
                startup_key is not None and constructed_key == startup_key
            ):
                # Same credentials as the startup adapter → reuse the connected
                # one instead of opening a second TradingClient.
                self._adapters[account.id] = startup_adapter
                logger.info(
                    "broker_registry_reused_startup_adapter",
                    account_id=account.id,
                    key_fp=_key_fingerprint(startup_key),
                )
            else:
                # A different user's paper account → connect its own adapter so
                # its orders hit its own broker account.
                try:
                    await connect(constructed)
                    logger.info(
                        "broker_registry_connected_per_user_adapter",
                        account_id=account.id,
                        key_fp=_key_fingerprint(constructed_key),
                    )
                except Exception as exc:
                    # A second account's connect failure must not crash boot.
                    # The (unconnected) adapter stays registered and surfaces a
                    # clean error at order time rather than at startup.
                    logger.warning(
                        "broker_registry_per_user_connect_failed",
                        account_id=account.id,
                        key_fp=_key_fingerprint(constructed_key),
                        error=str(exc),
                    )

    @staticmethod
    async def _default_connect(adapter: BrokerAdapter) -> None:
        # connect() is a blocking network call (get_account); off-load it.
        await asyncio.to_thread(adapter.connect)

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
