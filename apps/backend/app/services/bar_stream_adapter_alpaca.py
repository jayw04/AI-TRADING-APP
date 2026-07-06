"""Alpaca implementation of :class:`BarStreamAdapter`.

Uses ``alpaca.data.live.StockDataStream``. The exact attribute / method
surface (``subscribe_bars``, ``_run_forever``, ``stop_ws``) has shifted
across alpaca-py releases — if the WS smoke fails with ``AttributeError``,
check the installed version and adjust here rather than pinning back.
"""

from __future__ import annotations

import asyncio
import contextlib
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
        self._stream: Any = None  # alpaca StockDataStream (untyped SDK object)
        self._stream_task: asyncio.Task[None] | None = None
        self._subscribed: set[str] = set()

    async def connect(self) -> None:
        from alpaca.data.enums import DataFeed
        from alpaca.data.live import StockDataStream

        creds = load_credentials()
        settings = get_settings()
        feed_name = (getattr(settings, "alpaca_data_feed", None) or "iex").lower()
        try:
            feed = DataFeed(feed_name)
        except ValueError:
            feed = DataFeed.IEX

        self._stream = StockDataStream(
            creds.api_key, creds.api_secret, feed=feed
        )
        # We drive ONE connection lifecycle ourselves (connect -> consume) rather than
        # alpaca-py's StockDataStream._run_forever(). _run_forever busy-waits for a first
        # subscription on `await asyncio.sleep(0)` (100% CPU whenever the stream is up with
        # NO symbols subscribed — our common case) and its reconnect loop sleeps only 0.01s.
        # By calling _start_ws()/_consume() directly the task simply ENDS (raises) on a
        # disconnect, and the outer BarStreamService._run reconnects with capped backoff —
        # no busy-wait, no spin. (Depends on alpaca-py internals; pinned version.)
        self._stream._loop = asyncio.get_running_loop()
        self._stream._should_run = True
        self._stream_task = asyncio.create_task(
            self._connect_and_consume(), name="alpaca_bar_stream"
        )
        await asyncio.sleep(0)
        logger.info("alpaca_bar_stream_connected", feed=feed)

    async def _connect_and_consume(self) -> None:
        """One connection lifetime: connect + auth + (re)subscribe, then consume until the
        socket drops (raises) or stop is signalled (returns). NO internal reconnect/wait
        loop — the outer service supervises reconnect."""
        assert self._stream is not None
        await self._stream._start_ws()
        self._stream._running = True  # so live subscribe_bars()/unsubscribe_bars() take effect
        await self._stream._consume()

    async def disconnect(self) -> None:
        if self._stream is not None:
            try:
                await self._stream.stop_ws()
            except Exception:
                logger.exception("alpaca_bar_stream_stop_ws_failed")
        if self._stream_task is not None:
            self._stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._stream_task
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
