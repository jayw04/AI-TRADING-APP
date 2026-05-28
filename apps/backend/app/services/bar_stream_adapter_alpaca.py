"""Alpaca implementation of :class:`BarStreamAdapter`.

Uses ``alpaca.data.live.StockDataStream``. The exact attribute / method
surface (``subscribe_bars``, ``_run_forever``, ``stop_ws``) has shifted
across alpaca-py releases — if the WS smoke fails with ``AttributeError``,
check the installed version and adjust here rather than pinning back.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog

from app.brokers.alpaca.credentials import load_credentials
from app.config import get_settings
from app.services.bar_stream import StreamedBar
from app.services.bar_stream_adapter import BarCallback

logger = structlog.get_logger(__name__)


class AlpacaBarStreamAdapter:
    """alpaca-py ``StockDataStream`` wrapped to BarStreamAdapter shape."""

    def __init__(self, *, on_bar: BarCallback) -> None:
        self._on_bar = on_bar
        self._stream: Any | None = None
        self._stream_task: asyncio.Task[None] | None = None
        self._subscribed: set[str] = set()

    async def connect(self) -> None:
        from alpaca.data.live import StockDataStream

        creds = load_credentials()
        settings = get_settings()
        feed = getattr(settings, "alpaca_data_feed", None) or "iex"

        self._stream = StockDataStream(
            creds.api_key, creds.api_secret, feed=feed
        )
        self._stream_task = asyncio.create_task(
            self._stream._run_forever(), name="alpaca_bar_stream"
        )
        await asyncio.sleep(0)
        logger.info("alpaca_bar_stream_connected", feed=feed)

    async def disconnect(self) -> None:
        if self._stream is not None:
            try:
                await self._stream.stop_ws()
            except Exception:
                logger.exception("alpaca_bar_stream_stop_ws_failed")
        if self._stream_task is not None:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except (asyncio.CancelledError, Exception):
                pass
            self._stream_task = None
        self._stream = None
        self._subscribed.clear()

    async def subscribe(self, symbols: list[str]) -> None:
        if self._stream is None:
            raise RuntimeError("Not connected")

        async def _handler(bar: Any) -> None:
            try:
                ts = bar.t if isinstance(bar.t, datetime) else datetime.fromisoformat(
                    str(bar.t)
                )
                normalized = StreamedBar(
                    symbol=str(bar.symbol).upper(),
                    ts=ts,
                    open=Decimal(str(bar.o)),
                    high=Decimal(str(bar.h)),
                    low=Decimal(str(bar.l)),
                    close=Decimal(str(bar.c)),
                    volume=Decimal(str(bar.v)),
                )
                await self._on_bar(normalized)
            except Exception:
                logger.exception("alpaca_bar_normalize_failed")

        self._stream.subscribe_bars(_handler, *symbols)
        self._subscribed.update(symbols)

    async def unsubscribe(self, symbols: list[str]) -> None:
        if self._stream is None:
            return
        try:
            self._stream.unsubscribe_bars(*symbols)
        except Exception:
            logger.exception(
                "alpaca_bar_unsubscribe_failed", symbols=symbols
            )
        self._subscribed.difference_update(symbols)

    async def run_until_disconnected(
        self, *, stop_event: asyncio.Event
    ) -> None:
        """Wait until either the stream task ends (disconnect/error) or
        ``stop_event`` fires."""
        if self._stream_task is None:
            return
        stop_waiter = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait(
            [self._stream_task, stop_waiter],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
        if self._stream_task in done:
            exc = self._stream_task.exception()
            if exc:
                raise exc
