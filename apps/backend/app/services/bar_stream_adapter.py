"""Broker-agnostic interface for bar-stream adapters (P4 §8).

Implementations live alongside this file (e.g. ``bar_stream_adapter_alpaca``).
:class:`BarStreamService` consumes this Protocol so a second broker can be
plugged in at P5+ without touching the service.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from app.services.bar_stream import StreamedBar

BarCallback = Callable[[StreamedBar], Awaitable[None]]


class BarStreamAdapter(Protocol):
    """Implementations push :class:`StreamedBar` instances via the callback
    handed in their constructor. Lifecycle is owned by BarStreamService."""

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def subscribe(self, symbols: list[str]) -> None: ...

    async def unsubscribe(self, symbols: list[str]) -> None: ...

    async def run_until_disconnected(
        self, *, stop_event: asyncio.Event
    ) -> None: ...
