# Strategy Authoring Runbook

> P2 ships one strategy type (Python). Pine arrives in P4; Agent in P6. This
> runbook covers Python only.

## File location

Strategies live under `apps/backend/strategies_user/`. The engine's loader
refuses paths outside this directory (ADR 0002 + the strategy-isolation
tripwire in CI both enforce it).

```
apps/backend/strategies_user/
├── examples/
│   └── rsi_meanreversion.py     # reference (do NOT take live unmodified)
└── my_strategy.py
```

## Minimal strategy

```python
from decimal import Decimal
from typing import ClassVar, Any

from app.strategies import Strategy
from app.db.enums import OrderSide, OrderSourceType, OrderType, SignalType, TimeInForce
from app.risk import OrderRequest


class MyStrategy(Strategy):
    name: ClassVar[str] = "my-strategy"
    version: ClassVar[str] = "0.1.0"
    symbols: ClassVar[list[str]] = ["AAPL"]
    schedule: ClassVar[str] = "*/1 * * * *"            # cron, or "event"
    default_params: ClassVar[dict[str, Any]] = {
        "timeframe": "1Min",
        "rsi_buy": 30.0,
        "rsi_sell": 70.0,
    }

    async def on_init(self) -> None:
        # Called once before the first on_bar.
        pass

    async def on_bar(self, bar) -> None:
        indicators = await self.ctx.get_indicators(
            bar.symbol, names=["RSI14"], timeframe=self.params["timeframe"]
        )
        rsi = indicators["RSI14"].dropna()
        if rsi.empty:
            return
        latest_rsi = float(rsi.iloc[-1])

        position = await self.ctx.get_position_for(bar.symbol)
        in_long = position is not None and position.qty > 0

        if not in_long and latest_rsi < self.params["rsi_buy"]:
            req = OrderRequest(
                user_id=0, account_id=0, symbol_id=0,    # ctx fills these
                symbol_ticker=bar.symbol,
                side=OrderSide.BUY, qty=Decimal("10"),
                type=OrderType.MARKET, tif=TimeInForce.DAY,
                source_type=OrderSourceType.STRATEGY,
            )
            await self.ctx.submit_order(req)
            await self.ctx.log_signal(
                bar.symbol, SignalType.ENTRY, payload={"rsi": latest_rsi}
            )

    async def on_fill(self, fill) -> None:
        pass

    async def on_signal(self, signal) -> None:
        pass

    async def on_shutdown(self) -> None:
        pass
```

## The context surface

`self.ctx` is the only object your strategy uses for I/O:

| Method | Description |
|---|---|
| `await ctx.get_recent_bars(symbol, timeframe, n)` | OHLCV DataFrame from the cache |
| `await ctx.get_indicators(symbol, names, timeframe)` | Curated indicators (see below) |
| `await ctx.get_positions()` | Open positions in this strategy's universe |
| `await ctx.get_position_for(symbol)` | One position (or None) |
| `await ctx.submit_order(req)` | Through OrderRouter + Risk Engine |
| `await ctx.log_signal(symbol, type, payload)` | Persist a signal row + emit on bus |

**You cannot reach the broker directly.** The strategy-isolation tripwire
(`scripts/check_strategy_isolation.sh`) fails CI on any `from app.brokers`
or `import app.brokers` under `app/strategies/`. ADR 0002 in code form.

## Supported indicators

`SMA20`, `SMA50`, `SMA200`, `EMA9`, `EMA21`, `RSI14`, `MACD` (dict of
`macd`/`signal`/`hist`), `ATR14`, `VWAP`, `BB` (dict of
`bb_lower`/`bb_mid`/`bb_upper`), `RELVOL20`.

Anything beyond this set: compute it yourself in `on_bar` from raw bars.
Curating the set keeps pandas-ta version churn from breaking strategies.

## Registering and starting

Two paths:

**From the UI (preferred):** Strategies page → "+ New strategy" → fill the
form → Register → Start. Status transitions IDLE → PAPER.

**From the API:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/strategies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-strategy",
    "code_path": "my_strategy.py",
    "type": "python",
    "symbols": ["AAPL"],
    "params": {"rsi_buy": 28}
  }'
# Then:
curl -X POST http://127.0.0.1:8000/api/v1/strategies/${ID}/start
```

## Common pitfalls

1. **Forgetting to subclass `Strategy`.** The loader rejects the file with
   "no Strategy subclass found."
2. **Multiple Strategy subclasses in one file** without declaring
   `__strategy__ = MainClass`. The loader rejects with "multiple Strategy
   subclasses."
3. **Trying to import `app.brokers` directly.** CI fails via the isolation
   tripwire. Use `ctx.submit_order` instead.
4. **Requesting bars for an unauthorized symbol.**
   `ctx.get_recent_bars("ZZZZ", ...)` returns an empty frame and logs a
   warning. Your strategy keeps running but its math sees no data.
5. **Risk Engine rejection is NOT an exception.** `ctx.submit_order` returns
   the rejected order; check `result.status` or `result.rejection_reason`.
   Don't crash on rejection — log a signal and continue.
6. **Editing a running strategy's file.** No hot-reload in P2. Stop the
   strategy, edit, register again (or rely on resume-on-boot which re-loads
   on backend restart). Hot-reload is a P4 polish item.
7. **Cron string typo.** Engine logs
   `strategy_schedule_invalid_falling_back` and dispatches every minute.
   Check logs after register.

## Per-strategy risk limits

When you register, you can set `risk_limits_id` to point at a STRATEGY-scope
`risk_limits` row tighter than GLOBAL. See [risk-limits.md](risk-limits.md)
for the STRATEGY-scope section.

## Errors and recovery

If `on_bar`/`on_signal`/`on_fill` raise an uncaught exception, the engine:
1. Logs the exception.
2. Writes a `strategy.error` audit row.
3. Sets `strategies.status = ERROR` and writes the truncated error text to
   `error_text`.
4. Unregisters the strategy from the scheduler.
5. Publishes `strategy.error` on the bus → UI shows red status badge.

To recover: fix the code, click Start in the UI (or POST `/start`). The
endpoint accepts a strategy in ERROR state and re-dispatches via
`engine.register`, which clears `error_text` on a successful re-init.
