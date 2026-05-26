# P2 Strategy MVP Smoke Log

> **Template — unfilled.** Run through the six steps during US market hours
> against Alpaca paper. Append your run's data inline; don't edit a
> previous run's record. Each completed run is one section; multiple runs
> stack.

| Field | Value |
|---|---|
| Date | YYYY-MM-DD |
| Time started | HH:MM ET |
| Trader | Jay |
| Branch / tag | feat/p2-tests-smoke-exit at HEAD (or merge commit) |
| Alpaca paper buying power before | $______ |

## Steps

### 1. Register the reference RSI strategy via UI; leave in IDLE

- [ ] Strategies page → "+ New strategy" → defaults
- [ ] Submitted at HH:MM:SS ET
- [ ] Strategy id: ___
- [ ] Status displays IDLE
- [ ] audit_log has STRATEGY_REGISTERED: yes / no
- Notes:

### 2. Run a 30-day backtest from the UI; metrics appear

- [ ] Strategy detail → Backtests tab → Run backtest
- [ ] Range start: ___, end: ___
- [ ] Job submitted; modal polls until done
- [ ] Result modal opens within 60 seconds: yes / no
- [ ] Metrics shown: trade_count=___, total_return=____%, sharpe=____, max_dd=____%
- [ ] Equity curve recharts widget renders: yes / no
- [ ] Trade list populated (count: ___): yes / no
- [ ] backtest_results row persisted: yes / no
- [ ] audit_log has STRATEGY_BACKTESTED: yes / no
- Notes:

### 3. Start strategy on paper during market hours

- [ ] Click Start, confirm
- [ ] Status transitions IDLE → PAPER within 2 seconds
- [ ] WS event `strategy.run_started` received (check browser DevTools → WS)
- [ ] strategy_runs row has started_at set, ended_at NULL
- Notes:

### 4. Wait for (or force) an entry signal; observe order chain

> If RSI doesn't naturally drop below 30 during smoke, edit params to loosen
> the threshold. Stop, edit Params, Start.

- [ ] Entry signal appears in Signals tab within 5 minutes: yes / no
- [ ] signals row has type=entry: yes / no
- [ ] orders row exists with source_type=strategy, source_id=${ID}: yes / no
- [ ] Order filled (during hours): yes / no
- [ ] positions row updated: yes / no
- [ ] strategy.on_fill fired (visible in backend logs as a fill audit): yes / no
- [ ] audit_log shows the full chain: order.created → order.risk_passed →
      order.submitted → order.fill: yes / no
- Notes:

### 5. Force a risk rejection by tightening per-strategy notional cap

```bash
# Insert a tight STRATEGY-scope row; attach via API (strategy must be IDLE
# first, so Stop before PUT).
sqlite3 apps/backend/data/workbench.sqlite "
  INSERT INTO risk_limits (user_id, scope_type, scope_id,
    max_position_notional, allow_short, created_at, updated_at)
  VALUES (1, 'strategy', ${STRATEGY_ID}, 1, 0, datetime('now'), datetime('now'));
"
curl -X POST http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/stop
curl -X PUT http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID} \
  -H "Content-Type: application/json" \
  -d "{\"risk_limits_id\": ${NEW_RISK_ROW_ID}}"
curl -X POST http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/start
```

- [ ] Next entry attempt rejected with POSITION_CAP_NOTIONAL: yes / no
- [ ] Strategy stays in PAPER (does NOT transition to ERROR): yes / no
- [ ] risk_checks row exists with decision=reject: yes / no
- [ ] Signal still logged (the strategy gracefully handled the rejection): yes / no
- Cleanup — restore loose limits before continuing (CRITICAL — see gotcha 3):
  ```bash
  curl -X POST http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/stop
  curl -X PUT http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID} \
    -H "Content-Type: application/json" \
    -d '{"risk_limits_id": null}'
  ```
- Notes:

### 6. Stop strategy; open position left in place; close manually

- [ ] Click Stop
- [ ] Status transitions to IDLE within 2 seconds
- [ ] Any open position from earlier steps is NOT closed automatically: yes / no
- [ ] Positions page still shows it
- [ ] Close via Positions page "Close" button: yes / no
- [ ] strategy_runs row has ended_at set: yes / no
- [ ] audit_log has STRATEGY_STOPPED: yes / no
- Notes:

## Summary

- [ ] All 6 steps passed
- Buying power after: $___
- Open orders / positions after: ___ / ___ (target: both 0)
- Anomalies: (free text)

## Cleanup verification

```bash
docker compose exec backend sqlite3 /app/data/workbench.sqlite \
  "SELECT count(*) FROM orders
   WHERE status NOT IN ('filled','canceled','rejected','expired','replaced');"
# expect: 0
docker compose exec backend sqlite3 /app/data/workbench.sqlite \
  "SELECT count(*) FROM positions;"
# expect: 0
```

If non-zero, force-flush via Alpaca:
```bash
set -a; source .env; set +a
curl -X DELETE https://paper-api.alpaca.markets/v2/orders \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
```
