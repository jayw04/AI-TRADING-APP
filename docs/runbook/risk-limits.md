# Risk Limits Runbook

The RiskEngine evaluates every order against the most specific applicable
`risk_limits` row. In P1, only the **GLOBAL** scope is used (per-user).
P2/P3 will add STRATEGY and AGENT_SESSION scopes that override GLOBAL.

## Default seeded values

Seeded on a fresh DB by the lifespan's bootstrap step (see
`app/db/seed.py` or the equivalent Alembic data migration):

| Field | Default | Meaning |
|---|---|---|
| `scope_type` | `global` | Applies to all of a user's orders |
| `scope_id` | NULL | Unused at GLOBAL scope |
| `max_position_qty` | 100 | No single position may exceed 100 shares |
| `max_position_notional` | 25 000 | Notional cap per position, in USD |
| `max_gross_exposure` | 100 000 | Total absolute exposure across all positions |
| `max_daily_loss` | 2 000 | Daily P&L floor — breaching trips the halt flag |
| `max_orders_per_minute` | 10 | Rate limit on submission |
| `allow_short` | false | No opening of short positions |
| `allowed_symbols` | NULL | NULL means all symbols are allowed |
| `denied_symbols` | NULL | NULL means no symbols are explicitly denied |

`allowed_symbols` and `denied_symbols` are JSON arrays of tickers, e.g.
`["AAPL","SPY"]`. An allowlist combined with denylist still uses both — a
ticker on the denylist is rejected even if also on the allowlist.

## Viewing current values

From inside the container:

```bash
docker compose exec backend python -c "
import asyncio, json
from sqlalchemy import select
from app.db.models.risk_limits import RiskLimits
from app.db.session import get_sessionmaker
async def main():
    async with get_sessionmaker()() as s:
        for r in (await s.execute(select(RiskLimits))).scalars().all():
            print(r.scope_type, r.scope_id, r.user_id,
                  r.max_position_qty, r.max_position_notional,
                  r.max_daily_loss, r.allow_short,
                  r.allowed_symbols, r.denied_symbols)
asyncio.run(main())
"
```

Or open the SQLite file directly from your host (the `data/` directory is
a bind mount):

```bash
sqlite3 apps/backend/data/workbench.sqlite \
  "SELECT * FROM risk_limits WHERE scope_type = 'global';"
```

## Changing values (P1: SQL only; P4 adds a Settings UI)

```bash
sqlite3 apps/backend/data/workbench.sqlite \
  "UPDATE risk_limits
   SET max_position_notional = 10000,
       updated_at = datetime('now')
   WHERE scope_type = 'global';"
```

The change takes effect on the **next** order — the engine reads on every
`evaluate()`. No restart needed.

## Reason codes — what each rejection means

Codes are written into `risk_checks.reason_codes` and surfaced to the UI by
`src/lib/risk-reasons.ts::describeReasons`. The full set
(`app/risk/reason_codes.py`):

| Code | Engine source | Plain English |
|---|---|---|
| `OK` | Pass | Approved. |
| `INVALID_INPUT` | Shape checks | Bad qty / missing limit or stop price. |
| `MODE_MISMATCH` | Mode/account consistency | Account is in a different trading mode than the runtime. |
| `SYMBOL_DENIED` | Allowlist / denylist / inactive | Symbol is not allowed for trading. |
| `SHORT_NOT_ALLOWED` | Side + flag | Shorting is disabled for this account. |
| `POSITION_CAP_QTY` | Per-symbol limit | Order would exceed the per-symbol share limit. |
| `POSITION_CAP_NOTIONAL` | Per-symbol limit | Order would exceed the per-symbol dollar limit. |
| `GROSS_EXPOSURE` | Account-wide limit | Order would exceed the total exposure limit. |
| `HALT_REACHED` | Halt flag | Trading is halted (daily loss cap or operator stop). |
| `RATE_LIMIT` | Counter | Too many orders sent in the last minute. |
| `NO_LIMITS_CONFIGURED` | Lookup | No risk_limits row exists for this user — refuses to evaluate. |

## Halt and unhalt

When the daily-loss cap is breached, the engine sets the halt flag in
`system_config`:

```bash
sqlite3 apps/backend/data/workbench.sqlite \
  "SELECT key, value FROM system_config WHERE key='trading.halted';"
# returns ('trading.halted', 'true') when halted
```

Unhalting (P5 adds a UI button; today this is SQL):

```bash
sqlite3 apps/backend/data/workbench.sqlite \
  "UPDATE system_config
   SET value='false', updated_at=datetime('now')
   WHERE key='trading.halted';"
```

The engine re-reads on every evaluate, so the next order goes through with
no restart.

## Tightening for live trading

Before flipping `WORKBENCH_TRADING_MODE=live`, consider:

- Lower `max_position_notional` to a number you'd be comfortable losing
  entirely on a single bad position.
- Lower `max_daily_loss` to a fraction of your real risk budget.
- Add specific tickers to `allowed_symbols` if you intend to trade only a
  small whitelist:

  ```bash
  sqlite3 apps/backend/data/workbench.sqlite \
    "UPDATE risk_limits
     SET allowed_symbols = '[\"AAPL\",\"MSFT\",\"SPY\"]'
     WHERE scope_type='global';"
  ```

Live-mode caveats are in [`live-mode.md`](live-mode.md).

## Strategy-scope risk limits (P2)

P2 introduced the **STRATEGY** scope. A `risk_limits` row with
`scope_type='strategy'` applies to one or more strategies via
`strategies.risk_limits_id`.

Layering: when the Risk Engine evaluates a strategy-attributed order, it
merges the STRATEGY-scope row over the GLOBAL row. NULL fields fall
through to GLOBAL — set only the fields you want to override.

The seed script creates one default STRATEGY-scope row with tighter caps
than GLOBAL:

| Field | GLOBAL | STRATEGY default |
|---|---|---|
| `max_position_notional` | $25,000 | $5,000 |
| `max_gross_exposure` | $100,000 | $15,000 |
| `max_daily_loss` | $2,000 | $500 |
| `max_orders_per_minute` | 10 | 5 |

To create a tighter per-strategy row:

```bash
sqlite3 apps/backend/data/workbench.sqlite "
  INSERT INTO risk_limits (user_id, scope_type, scope_id,
    max_position_qty, max_position_notional, max_gross_exposure,
    max_daily_loss, max_orders_per_minute, allow_short,
    created_at, updated_at)
  VALUES (1, 'strategy', NULL, 50, 2000, 5000, 250, 3, 0,
    datetime('now'), datetime('now'));
"
```

Then attach to a strategy (must be IDLE — PUT rejects with 409 if active):

```bash
curl -X PUT http://127.0.0.1:8000/api/v1/strategies/${ID} \
  -H "Content-Type: application/json" \
  -d '{"risk_limits_id": 3}'
```

P3 will introduce AGENT_SESSION-scope risk limits in the same pattern.
