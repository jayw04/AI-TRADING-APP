import asyncio
import pathlib
from datetime import UTC, datetime

from app.config import get_settings
from app.market_data.bar_cache import BarCache

UNI = ['MSFT','NVDA','AMD','TSLA','GOOGL','AMZN','META','NFLX','INTC','MU',
       'F','KO','DIS','BAC','XOM','WMT','SPY','QQQ']
TF = '5Min'
MONTHS = [(2026, m) for m in range(1, 8)]  # Jan..Jul 2026 (~6 months)

s = get_settings()
root = pathlib.Path(s.bars_cache_root)
cleared = 0
for sym in UNI:
    d = root / sym / TF
    if d.exists():
        for e in list(d.glob('*.empty')):
            e.unlink(); cleared += 1
print(f'cleared {cleared} .empty markers', flush=True)

bc = BarCache(adapter=None, root=s.bars_cache_root, max_gb=s.bars_cache_max_gb)

async def go():
    for sym in UNI:
        for (y, m) in MONTHS:
            start = datetime(y, m, 1, tzinfo=UTC)
            ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
            end = datetime(ny, nm, 1, tzinfo=UTC)
            try:
                await bc.get_bars(sym, TF, start, end)
            except Exception as ex:
                print(f'  {sym} {y}-{m:02d} ERR {type(ex).__name__} {str(ex)[:70]}', flush=True)
        tot = await bc.get_bars(sym, TF, datetime(2026,1,1,tzinfo=UTC), datetime.now(UTC))
        days = tot['t'].dt.date.nunique() if len(tot) else 0
        print(f'  {sym}: {len(tot)} bars / {days} days', flush=True)
    print('BACKFILL COMPLETE', flush=True)

asyncio.run(go())
