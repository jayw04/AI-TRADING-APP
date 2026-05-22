# P1 Paper-Trading Smoke Log

The exit-gate manual smoke matrix from
[TradingWorkbench_P1_Session7_v0.1.md §7.7](../implementation/TradingWorkbench_P1_Session7_v0.1.md).
Six steps against Alpaca paper. Run during regular market hours
(Mon–Fri, 09:30–16:00 ET) for deterministic fills.

**This log is append-only.** If a step fails on the first try, write what
failed, fix the bug, then add a second attempt at the bottom — don't
overwrite history.

---

## Run header

| Field | Value |
|---|---|
| Date | _YYYY-MM-DD_ |
| Time started | _HH:MM ET_ |
| Trader | Jay |
| Branch / tag | `feat/p1-tests-smoke-exit` at HEAD |
| Backend commit | _short sha_ |
| Alpaca paper buying power before | $ _____ |

---

## Step 1 — Market BUY 1 share AAPL → fills near market

- [ ] Submitted at _HH:MM:SS ET_
- [ ] Status went `submitted → filled` within _____ seconds
- [ ] Order ID: _____
- [ ] Fill price: $ _____
- [ ] Position appeared on Positions page: yes / no
- [ ] Audit log chain present:
      `ORDER_RISK_PASSED → ORDER_SUBMITTED → ORDER_FILL_INGESTED`: yes / no
- Notes:

## Step 2 — Limit BUY 1 AAPL well below market → cancel

- [ ] Submitted at _HH:MM:SS ET_ with limit price $ _____ (well below market)
- [ ] Order appears in Orders **Working** tab: yes / no
- [ ] Clicked **Cancel** on the row
- [ ] Order moved to **History** with status `canceled`: yes / no
- [ ] Audit log has `ORDER_CANCEL_REQUESTED` (and later `ORDER_CANCELED`
      from the trade-update consumer): yes / no
- Notes:

## Step 3 — Submit BUY 10 000 AAPL (oversize) → expect risk rejection

- [ ] Submitted via the ticket
- [ ] Amber banner appeared in UI: yes / no
- [ ] Banner text mentions "per-symbol share limit" or "per-symbol dollar
      limit": yes / no
- [ ] No order reached Alpaca (checked Alpaca dashboard): yes / no
- [ ] `risk_checks` row exists with `decision=reject` and the right reason
      code (`POSITION_CAP_QTY` and/or `POSITION_CAP_NOTIONAL`): yes / no
- Notes:

## Step 4 — Force a daily-loss halt

Halt the system manually (mirrors what the engine would do if the daily-loss
cap were breached):

```bash
sqlite3 apps/backend/data/workbench.sqlite \
  "INSERT OR REPLACE INTO system_config(user_id, key, value, updated_at)
   VALUES(NULL, 'trading.halted', 'true', datetime('now'));"
```

- [ ] Tried to submit a 1-share market BUY: rejected with `HALT_REACHED`: yes / no
- [ ] UI banner shows the rejection in plain English: yes / no

Unhalt before continuing:

```bash
sqlite3 apps/backend/data/workbench.sqlite \
  "UPDATE system_config SET value='false', updated_at=datetime('now')
   WHERE key='trading.halted';"
```

- [ ] After unhalt, a new 1-share BUY goes through: yes / no
- Notes:

> ⚠ If you forget to unhalt, all subsequent paper trading is blocked until
> you fix it. This step has bitten the project before.

## Step 5 — Modify a working order's limit price

- [ ] Submit a LIMIT BUY 1 AAPL at $ _____ (well below market)
- [ ] Order appears in **Working**
- [ ] Click **Modify** on the row, change limit to $ _____
- [ ] Verify in Alpaca dashboard that the limit changed: yes / no
- [ ] Audit log has `ORDER_REPLACE_REQUESTED`: yes / no
- [ ] Cancel the order afterward to clean up
- Notes:

## Step 6 — Close a position via the Positions page

- [ ] Submit a MARKET BUY 1 AAPL (waits for fill)
- [ ] Position appears on the Positions page
- [ ] Click **Close** on the row → confirm in the browser dialog
- [ ] A new SELL order is created via `POST /api/v1/positions/AAPL/close`
- [ ] Position goes to zero after the close fills: yes / no
- [ ] Audit log has both fills + risk checks for both orders: yes / no
- Notes:

---

## Cleanup verification

After the six steps:

```bash
sqlite3 apps/backend/data/workbench.sqlite \
  "SELECT count(*) AS open_orders FROM orders
   WHERE status NOT IN ('filled','canceled','rejected','expired','replaced');"
# expect: 0

sqlite3 apps/backend/data/workbench.sqlite \
  "SELECT count(*) FROM positions;"
# expect: 0
```

If non-zero, clean up via the Alpaca paper API (replace creds from `.env`):

```bash
set -a; source .env; set +a
curl -X DELETE https://paper-api.alpaca.markets/v2/orders \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
```

---

## Summary

- [ ] All 6 steps passed
- Buying power after: $ _____ (~ same as before, minus any partial fills
      that didn't close cleanly)
- Open orders / positions after: ___ / ___ (both should be zero)
- Anomalies / notes:
