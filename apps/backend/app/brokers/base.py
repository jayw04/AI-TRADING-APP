"""Broker-agnostic adapter Protocol.

ADR 0002 says strategies cannot import broker code. P5 §2 extends that posture:
ONLY ``app.brokers.*`` may import a broker's trading/order SDK (alpaca-py
today). Everything above the OrderRouter touches brokers exclusively through
this Protocol, resolved per-account by :class:`app.brokers.registry.BrokerRegistry`.
``check_broker_isolation.sh`` enforces the import boundary from CI.

This Protocol is deliberately shaped to match the existing
:class:`app.brokers.alpaca.AlpacaAdapter` (P1) — sync methods, ``dict`` returns,
``_router_token``-gated mutators — so the adapter satisfies it with zero code
change (structural typing). A future PR may migrate to an async/DTO surface;
that is out of scope for P5 §2 (see the v1.0 session doc, §2.0).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BrokerAdapter(Protocol):
    """The surface the OrderRouter needs from any broker. Mirrors the real
    AlpacaAdapter; no DTOs, sync calls, mutators gated by ``_router_token``
    (ADR 0002 — only the OrderRouter knows the token)."""

    # ---- introspection ----
    @property
    def is_paper(self) -> bool: ...

    @property
    def is_connected(self) -> bool: ...

    # ---- lifecycle ----
    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    # ---- reads ----
    def get_account(self) -> dict[str, Any]: ...

    def get_positions(self) -> list[dict[str, Any]]: ...

    # ---- mutators (ADR 0002: _router_token-gated) ----
    def submit_order(
        self,
        *,
        symbol: str,
        qty: Any,
        side: str,
        type_: str,
        tif: str,
        limit_price: Any = None,
        stop_price: Any = None,
        extended_hours: bool = False,
        client_order_id: str | None = None,
        _router_token: str | None = None,
    ) -> dict[str, Any]: ...

    def cancel_order(
        self,
        broker_order_id: str,
        *,
        _router_token: str | None = None,
    ) -> None: ...

    def replace_order(
        self,
        broker_order_id: str,
        *,
        new_qty: Any = None,
        new_limit_price: Any = None,
        _router_token: str | None = None,
    ) -> dict[str, Any]: ...
