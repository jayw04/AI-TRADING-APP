"""Alpaca Trade Updates streaming (skeleton).

This file establishes the shape; the actual long-running task + event-bus
wiring lands in P1 Session 3. Nothing here is started automatically yet.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from app.brokers.alpaca.credentials import AlpacaCredentials

logger = structlog.get_logger(__name__)


TradeUpdateHandler = Callable[[dict[str, Any]], Awaitable[None]]


class TradeUpdatesStream:
    """Wraps alpaca-py's TradingStream and forwards trade updates to a handler.

    Lifecycle (implemented in Session 3):

        stream = TradeUpdatesStream(creds, on_update=lifecycle.handle_trade_update)
        await stream.start()    # creates and runs the underlying stream as a task
        await stream.stop()     # cancels the task

    This skeleton exists so other modules (e.g., the future order lifecycle)
    can reference its type. It does NOT start any work on import.
    """

    def __init__(
        self,
        credentials: AlpacaCredentials,
        on_update: TradeUpdateHandler,
    ) -> None:
        self._creds = credentials
        self._on_update = on_update
        self._stream: Any = None
        self._started = False

    @property
    def is_started(self) -> bool:
        return self._started

    async def start(self) -> None:  # pragma: no cover — implemented in Session 3
        raise NotImplementedError(
            "TradeUpdatesStream.start() is implemented in P1 Session 3."
        )

    async def stop(self) -> None:  # pragma: no cover — implemented in Session 3
        raise NotImplementedError(
            "TradeUpdatesStream.stop() is implemented in P1 Session 3."
        )
