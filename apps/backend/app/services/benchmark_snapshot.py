"""Benchmark index-fund snapshot + comparison (dashboard).

Captures a daily-close time series for a small set of reference index funds (SPY/VOO/…) so the live
books' return-since-inception can be shown against passive benchmarks over the SAME window. Mirrors
``equity_snapshot.py``: append-only, best-effort, off the order path. The earliest snapshot per
symbol is that benchmark's inception (aligned with the accounts' ``starting_equity`` = earliest
equity snapshot), so both returns cover exactly the live window.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.benchmark_snapshot import BenchmarkSnapshot

logger = structlog.get_logger(__name__)

# Reference index funds shown on the dashboard (ordered; value = display name).
BENCHMARKS: dict[str, str] = {
    "SPY": "S&P 500 (SPDR)",
    "VOO": "S&P 500 (Vanguard)",
    "QQQ": "Nasdaq-100 (Invesco)",
    "IWM": "Russell 2000 (iShares)",
    "DIA": "Dow Jones 30 (SPDR)",
}


async def _latest_close(symbol: str) -> Decimal | None:
    """Most recent daily close for ``symbol`` via Alpaca (sync client wrapped in an executor, same
    pattern as ``market_data.quotes``). ``None`` on any error — best-effort, never fatal."""
    loop = asyncio.get_running_loop()
    try:
        from alpaca.data.enums import DataFeed
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        from app.brokers.alpaca.credentials import load_credentials

        creds = load_credentials()
        client = StockHistoricalDataClient(api_key=creds.api_key, secret_key=creds.api_secret)
        req = StockBarsRequest(
            symbol_or_symbols=symbol, timeframe=TimeFrame.Day, limit=1, feed=DataFeed.IEX
        )
        res = await loop.run_in_executor(None, lambda: client.get_stock_bars(req))
        bars = res.data.get(symbol) if hasattr(res, "data") else None
        if bars:
            return Decimal(str(bars[-1].close))
    except Exception:  # noqa: BLE001 — best-effort market fetch; never raise into the scheduler/API
        return None
    return None


async def snapshot_benchmarks(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """Append one ``BenchmarkSnapshot`` per reference fund from its latest daily close. Idempotent
    per (symbol, day): a symbol already snapshotted today is skipped, so the seed + the daily job
    don't double-count. Returns the number appended."""
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    appended = 0
    async with session_factory() as session:
        for symbol in BENCHMARKS:
            already = (
                await session.execute(
                    select(BenchmarkSnapshot.id).where(
                        BenchmarkSnapshot.symbol == symbol, BenchmarkSnapshot.ts >= day_start
                    )
                )
            ).first()
            if already:
                continue
            close = await _latest_close(symbol)
            if close is None:
                continue
            session.add(BenchmarkSnapshot(symbol=symbol, ts=now, close=close))
            appended += 1
        await session.commit()
    return appended


async def run_daily_benchmark_snapshot(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Scheduler entrypoint: append one benchmark close per fund near market close (alongside the
    equity snapshot). Best-effort; never raises into the scheduler."""
    try:
        n = await snapshot_benchmarks(session_factory)
        logger.info("benchmark_snapshot_persisted", n=n)
    except Exception:
        logger.exception("benchmark_snapshot_failed")


async def benchmark_returns(
    session: AsyncSession, *, since: datetime | None = None
) -> list[dict[str, Any]]:
    """Per benchmark: inception + current + return-since-inception, over the SAME window the
    account's ``total_return`` uses.

    ``since`` scopes the window to a specific account's inception (its ``performance_inception_at``
    or earliest equity snapshot). The inception row is then the first benchmark snapshot on/after
    ``since`` — so an account that started today is compared to the index from today, not from the
    global earliest snapshot. ``since=None`` keeps the prior behaviour (global earliest → latest).
    Symbols with no snapshot in the window are returned with nulls (dashboard shows 'pending first
    snapshot')."""
    out: list[dict[str, Any]] = []
    for symbol, name in BENCHMARKS.items():
        stmt = (
            select(BenchmarkSnapshot.ts, BenchmarkSnapshot.close)
            .where(BenchmarkSnapshot.symbol == symbol)
            .order_by(BenchmarkSnapshot.ts.asc())
        )
        if since is not None:
            stmt = stmt.where(BenchmarkSnapshot.ts >= since)
        rows = (await session.execute(stmt)).all()
        if not rows:
            out.append({"symbol": symbol, "name": name, "inception_date": None,
                        "inception_price": None, "current_price": None, "return_pct": None})
            continue
        first_ts, first_close = rows[0]
        last_ts, last_close = rows[-1]
        # return_pct is a FRACTION (e.g. 0.10 = +10%), matching accounts' total_return_pct so the
        # dashboard formats both with the same formatPercent (which multiplies by 100).
        ret = (float(last_close) / float(first_close) - 1.0) if first_close else 0.0
        out.append({
            "symbol": symbol, "name": name,
            "inception_date": first_ts.date().isoformat(),
            "inception_price": str(first_close),
            "current_price": str(last_close),
            "as_of": last_ts.date().isoformat(),
            "return_pct": round(ret, 6),
        })
    return out
