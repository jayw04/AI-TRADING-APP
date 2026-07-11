"""MKT-PROJ-001 §1 — build the historical training dataset (FR-001).

Run INSIDE the backend container on the box (needs Alpaca creds + the DB):

    sudo docker exec workbench-backend python3 /app/data/mkt_proj_001/build_dataset.py \
        --start 2016-01-04 [--end YYYY-MM-DD]

Month-chunked minute fetches (the bar_cache 10k-truncation guard), rows built
via app.services.market_projection.dataset, persisted idempotently (delete +
insert per (date, projection_type, proxy, feature_version)). Prints a summary:
row counts, exclusions by reason, label distribution per horizon.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import date

from app.services.market_projection import dataset as ds
from app.services.market_projection.schemas import FEATURE_VERSION


def month_iter(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + (m == 12), (m % 12) + 1)


def build(start: date, end: date) -> list[dict]:
    client = ds._client()
    sessions = ds.nyse_sessions(start, end)
    print(f"sessions: {len(sessions)}  {sessions.index[0]} .. {sessions.index[-1]}")
    daily = ds.fetch_daily(client, ds.ALL_SYMBOLS, start, end)
    print("daily rows:", {s: len(df) for s, df in daily.items()})

    rows: list[dict] = []
    cum_vol: dict = {}
    for y, m in month_iter(start, end):
        month_days = [d for d in sessions.index if d.year == y and d.month == m]
        if not month_days:
            continue
        from datetime import date as _date, timedelta as _td
        m_start = _date(y, m, 1)
        m_end = _date(y + (m == 12), (m % 12) + 1, 1) - _td(days=1)
        minute = ds.fetch_minute_range(client, ds.ALL_SYMBOLS, m_start, m_end)
        month_sessions = sessions.loc[month_days]
        if "SPY" in minute:
            cum_vol.update(ds.spy_cum_volume_table(minute["SPY"], month_sessions))
        built = ds.build_rows_for_sessions(
            sessions, daily, minute, spy_cum_vol_at=cum_vol, only_days=month_days
        )
        rows.extend(built)
        print(f"{y}-{m:02d}: sessions={len(month_days)} rows+={len(built)} total={len(rows)}")
    return rows


async def persist(rows: list[dict]) -> None:
    # Lazy imports: --dry-run must work in a container that predates the §1
    # model/migration (the hot-copy research pattern).
    from sqlalchemy import delete

    from app.db.models.market_projection import MarketProjectionTrainingRow
    from app.db.session import get_sessionmaker

    sf = get_sessionmaker()
    dates = sorted({r["date"] for r in rows})
    async with sf() as s:
        await s.execute(
            delete(MarketProjectionTrainingRow).where(
                MarketProjectionTrainingRow.date >= dates[0],
                MarketProjectionTrainingRow.date <= dates[-1],
                MarketProjectionTrainingRow.feature_version == FEATURE_VERSION,
            )
        )
        s.add_all(MarketProjectionTrainingRow(**r) for r in rows)
        await s.commit()


def summarize(rows: list[dict]) -> dict:
    out: dict = {}
    for ptype in ("PRE_OPEN_TODAY", "PRE_CLOSE_TOMORROW"):
        sub = [r for r in rows if r["projection_type"] == ptype]
        valid = [r for r in sub if r["valid_for_training"]]
        out[ptype] = {
            "rows": len(sub),
            "valid": len(valid),
            "exclusions": dict(Counter(r["exclusion_reason"] for r in sub
                                       if r["exclusion_reason"])),
            "labels": dict(Counter(r["label"] for r in valid)),
            "material_share": round(
                sum(1 for r in valid if r["label"] in ("UP", "DOWN")) / len(valid), 3
            ) if valid else None,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat, default=date(2016, 1, 4))
    ap.add_argument("--end", type=date.fromisoformat, default=date.today())
    ap.add_argument("--dry-run", action="store_true", help="build + summarize, no DB write")
    args = ap.parse_args()

    rows = build(args.start, args.end)
    print(json.dumps(summarize(rows), indent=2))
    if not args.dry_run:
        asyncio.run(persist(rows))
        print(f"persisted {len(rows)} rows (feature_version={FEATURE_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
