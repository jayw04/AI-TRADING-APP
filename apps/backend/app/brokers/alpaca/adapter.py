"""AlpacaAdapter — the single outbound interface to Alpaca.

Per ADR 0002, order submission must only be invoked via OrderRouter. The
`submit_order` / `cancel_order` / `replace_order` methods are intentionally
NOT implemented in this session — they land in P1 Session 4 alongside
`OrderRouter`, to avoid creating a callable bypass.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.brokers.alpaca.credentials import AlpacaCredentials, load_credentials
from app.brokers.alpaca.errors import classify

logger = structlog.get_logger(__name__)


class AlpacaAdapter:
    """Thin wrapper over alpaca-py `TradingClient`.

    Lifecycle:
        adapter = AlpacaAdapter()       # loads credentials from env
        adapter.connect()                # creates the TradingClient, verifies auth
        adapter.get_account()            # ... usable read methods ...
        adapter.disconnect()             # drops the client

    Concurrency: instances are not shared across asyncio tasks; the underlying
    alpaca-py `TradingClient` is sync. For async contexts, wrap calls in
    `run_in_executor` at the call site (done in P1 Session 2 polling loops).
    """

    def __init__(self, credentials: AlpacaCredentials | None = None) -> None:
        self._creds = credentials or load_credentials()
        self._trading: Any = None  # alpaca.trading.client.TradingClient
        logger.info(
            "alpaca_adapter_init",
            paper=self._creds.paper,
            base_url=self._creds.base_url,
        )

    # ---- lifecycle ----

    @property
    def is_paper(self) -> bool:
        return self._creds.paper

    @property
    def is_connected(self) -> bool:
        return self._trading is not None

    @property
    def credentials(self) -> AlpacaCredentials:
        """Read-only access to the credentials this adapter was constructed with.

        Used by TradeUpdatesStream to open its own WS connection without
        re-resolving env vars (and to avoid drift if env changes mid-run).
        """
        return self._creds

    def connect(self) -> None:
        """Create the underlying TradingClient and verify by reading the account."""
        if self._trading is not None:
            return
        from alpaca.trading.client import TradingClient

        self._trading = TradingClient(
            api_key=self._creds.api_key,
            secret_key=self._creds.api_secret,
            paper=self._creds.paper,
        )
        try:
            self.get_account()
        except Exception:
            self._trading = None
            raise
        logger.info("alpaca_adapter_connected", paper=self._creds.paper)

    def disconnect(self) -> None:
        self._trading = None
        logger.info("alpaca_adapter_disconnected")

    def _client(self) -> Any:
        if self._trading is None:
            self.connect()
        return self._trading

    # ---- read methods (P1 Session 1 scope) ----

    def get_account(self) -> dict[str, Any]:
        """Return the live account snapshot."""
        try:
            account = self._client().get_account()
            return _to_dict(account)
        except Exception as exc:
            raise classify(exc) from exc

    def get_positions(self) -> list[dict[str, Any]]:
        """Return all open positions for the account."""
        try:
            positions = self._client().get_all_positions()
            return [_to_dict(p) for p in positions]
        except Exception as exc:
            raise classify(exc) from exc

    def list_assets(self, active_only: bool = True) -> list[dict[str, Any]]:
        """List US-equity tradable assets (used by the daily symbol sync in Session 2)."""
        try:
            from alpaca.trading.enums import AssetClass, AssetStatus
            from alpaca.trading.requests import GetAssetsRequest

            req = GetAssetsRequest(
                status=AssetStatus.ACTIVE if active_only else None,
                asset_class=AssetClass.US_EQUITY,
            )
            assets = self._client().get_all_assets(req)
            return [_to_dict(a) for a in assets]
        except Exception as exc:
            raise classify(exc) from exc

    def get_order(self, broker_order_id: str) -> dict[str, Any]:
        try:
            order = self._client().get_order_by_id(broker_order_id)
            return _to_dict(order)
        except Exception as exc:
            raise classify(exc) from exc

    def list_orders(
        self,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        try:
            from alpaca.trading.enums import QueryOrderStatus
            from alpaca.trading.requests import GetOrdersRequest

            req = GetOrdersRequest(
                status=QueryOrderStatus(status) if status else QueryOrderStatus.ALL,
                limit=limit,
            )
            orders = self._client().get_orders(filter=req)
            return [_to_dict(o) for o in orders]
        except Exception as exc:
            raise classify(exc) from exc

    # ---- mutating methods (DELIBERATELY UNIMPLEMENTED — see ADR 0002) ----

    def submit_order(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        """NOT IMPLEMENTED in this session. Lands in P1 Session 4 with OrderRouter.

        Per ADR 0002, this method must only be invoked from `OrderRouter.submit()`.
        It is deliberately left as `NotImplementedError` here to prevent any code
        path from accidentally calling Alpaca's submit endpoint before the risk
        engine is in place.
        """
        raise NotImplementedError(
            "submit_order is implemented in P1 Session 4 alongside OrderRouter. "
            "Per ADR 0002, this method may only be called from OrderRouter.submit()."
        )

    def cancel_order(self, *_args: Any, **_kwargs: Any) -> None:
        raise NotImplementedError("cancel_order lands in P1 Session 4.")

    def replace_order(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("replace_order lands in P1 Session 4.")


def _to_dict(obj: Any) -> dict[str, Any]:
    """Normalize alpaca-py model objects (pydantic v2) to plain dicts."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "_raw"):  # older alpaca-py
        return dict(obj._raw)
    if isinstance(obj, dict):
        return obj
    return dict(getattr(obj, "__dict__", {}) or {})
