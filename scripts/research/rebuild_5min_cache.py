#!/usr/bin/env python3
"""Rebuild the 5-min bar cache in monthly chunks (research data-fidelity fix).

WHY: app.market_data.bar_cache._fetch_and_write issues ONE Alpaca call for the whole missing
span with limit=10000. A cold multi-year intraday fetch therefore truncates at 10k rows (~126
sessions) AND writes `.empty` markers for every un-returned day — poisoning the cache so those
days never re-fetch. Result: the range Top-5 + SPY 5-min caches held ~250 non-contiguous days
(H2-2023 + part of 2025), with 2024/2026 marked bogus-empty. That silently biased the Phase-1/3
backtests. This driver clears the bogus `.empty` markers and re-fetches month-by-month (each
≈1.6k rows, well under the 10k cap) so every session is fetched cleanly.

Disarmed one-off container; pipe on stdin (scripts/ isn't baked into the image):
  docker compose run --rm --no-deps --entrypoint sh backend -c "cd /app && python - < /dev/stdin" \
    < scripts/research/rebuild_5min_cache.py
"""
from __future__ import annotations

import asyncio
import pathlib
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.brokers.registry import BrokerRegistry
from app.config import get_settings
from app.db.models.strategy import Strategy as S
from app.db.session import get_sessionmaker
from app.market_data.bar_cache import BarCache
from app.utils.time import EASTERN

SYMBOLS = ["SPY", "MU", "INTC", "AMD", "TSLA", "META"]
START = datetime(2023, 7, 1, tzinfo=timezone.utc)
END = datetime(2026, 6, 30, tzinfo=timezone.utc)


def months(start: datetime, end: datetime):
    cur = start.replace(day=1)
    while cur <= end:
        nxt = cur.replace(year=cur.year + 1, month=1) if cur.month == 12 else cur.replace(month=cur.month + 1)
        yield cur, min(nxt - timedelta(microseconds=1), end)
        cur = nxt


def etd(ts) -> "pd.Timestamp.date":
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert(EASTERN).date()


async def main() -> None:
    sf = get_sessionmaker()
    st = get_settings()
    reg = BrokerRegistry(sf)
    await reg.load_all()
    async with sf() as s:
        uid = (await s.get(S, 1)).user_id
    bc = BarCache(adapter=reg.get(uid), root=st.bars_cache_root, max_gb=st.bars_cache_max_gb)
    root = pathlib.Path(st.bars_cache_root)

    for sym in SYMBOLS:
        d5 = root / sym / "5Min"
        cleared = 0
        if d5.exists():
            for m in d5.glob("*.empty"):
                m.unlink(missing_ok=True)
                cleared += 1
        print(f"[{sym}] cleared {cleared} bogus .empty markers; fetching monthly...", flush=True)
        for ms, me in months(START, END):
            ok = False
            for attempt in range(4):
                try:
                    await bc.get_bars(sym, "5Min", ms, me)
                    ok = True
                    break
                except Exception as e:  # noqa: BLE001 — transient Alpaca/SSL flap → retry
                    time.sleep(2 * (attempt + 1))
                    if attempt == 3:
                        print(f"   !! {sym} {ms:%Y-%m} failed after retries: {type(e).__name__}", flush=True)
            if not ok:
                continue
        # verify completeness
        df = (await bc.get_bars(sym, "5Min", START, END)).reset_index(drop=True)
        dates = {etd(df.loc[i, "t"]) for i in range(len(df))} if len(df) else set()
        yr = Counter(d.year for d in dates)
        print(f"[{sym}] DONE rows={len(df)} days={len(dates)} per-yr={dict(sorted(yr.items()))}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
