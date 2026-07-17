"""Benchmark snapshot — return-since-inception (earliest→latest) + idempotent daily append."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.models.benchmark_snapshot import BenchmarkSnapshot
from app.services import benchmark_snapshot as bench


async def test_benchmark_returns_earliest_to_latest(session_factory):
    async with session_factory() as s:
        t0 = datetime(2026, 7, 7, 16, 10, tzinfo=UTC)
        s.add(BenchmarkSnapshot(symbol="SPY", ts=t0, close=Decimal("100")))
        s.add(BenchmarkSnapshot(symbol="SPY", ts=t0 + timedelta(days=3), close=Decimal("110")))
        await s.commit()
    async with session_factory() as s:
        rows = await bench.benchmark_returns(s)

    spy = next(r for r in rows if r["symbol"] == "SPY")
    assert spy["inception_date"] == "2026-07-07"
    assert float(spy["inception_price"]) == 100.0 and float(spy["current_price"]) == 110.0
    assert spy["return_pct"] == 0.1   # fraction: +10% = 0.10
    # a benchmark with no snapshot yet -> nulls (dashboard shows "pending")
    voo = next(r for r in rows if r["symbol"] == "VOO")
    assert voo["return_pct"] is None and voo["inception_date"] is None


async def test_benchmark_returns_since_scopes_the_window(session_factory):
    """`since` moves inception to the first snapshot on/after it — an account that started later is
    compared to the index from THEN, not from the global earliest snapshot."""
    async with session_factory() as s:
        d7 = datetime(2026, 7, 7, 16, 10, tzinfo=UTC)
        d17 = datetime(2026, 7, 17, 16, 10, tzinfo=UTC)
        d18 = datetime(2026, 7, 18, 16, 10, tzinfo=UTC)
        for ts, px in ((d7, "100"), (d17, "110"), (d18, "121")):
            s.add(BenchmarkSnapshot(symbol="SPY", ts=ts, close=Decimal(px)))
        await s.commit()

    # global window (since=None): 100 -> 121 = +21%
    async with session_factory() as s:
        g = next(r for r in await bench.benchmark_returns(s) if r["symbol"] == "SPY")
    assert g["inception_date"] == "2026-07-07" and g["return_pct"] == 0.21

    # since 07-17: window is 110 -> 121 = +10%, inception moved to 07-17
    async with session_factory() as s:
        w = next(r for r in await bench.benchmark_returns(s, since=d17) if r["symbol"] == "SPY")
    assert w["inception_date"] == "2026-07-17"
    assert float(w["inception_price"]) == 110.0 and w["return_pct"] == 0.1

    # since after the last snapshot: nothing in window -> nulls (dashboard shows "pending")
    async with session_factory() as s:
        e = next(
            r for r in await bench.benchmark_returns(s, since=datetime(2026, 7, 20, tzinfo=UTC))
            if r["symbol"] == "SPY"
        )
    assert e["inception_date"] is None and e["return_pct"] is None


async def test_snapshot_benchmarks_idempotent_per_day(session_factory, monkeypatch):
    async def _fake_close(symbol):
        return Decimal("400")

    monkeypatch.setattr(bench, "_latest_close", _fake_close)
    n1 = await bench.snapshot_benchmarks(session_factory)
    assert n1 == len(bench.BENCHMARKS)          # every fund appended on the first run
    n2 = await bench.snapshot_benchmarks(session_factory)
    assert n2 == 0                              # same calendar day -> all skipped (one point/day)
