# Live Order Safety (P5 §6)

Two friction layers, both narrow in scope, both enforced in the **OrderRouter**
(the single ADR-0002 dispatch point, so direct router callers — the strategy
engine — are gated too, not just the HTTP API).

| Layer | Scope | What it catches |
|---|---|---|
| Typed-ticker confirmation | Manual LIVE orders | "I clicked the wrong button" |
| Per-strategy cooldown | Strategy orders that fail to submit | Runaway retry loops |

> **No live orders execute yet.** P5 §1's `BrokerModeError` still refuses every
> LIVE account, and the POST /orders endpoint only targets the user's paper
> account. §6 wires the safety so it's in place on day one of §7 (which lifts
> the guard and adds LIVE account selection). The gates are exercised by
> router-level tests today.

## Typed-ticker confirmation

For MANUAL orders on a LIVE account, the OrderRouter requires `confirmation_text`
to equal the symbol after normalization (uppercase, whitespace-stripped — `aapl`
and `  AAPL  ` both match `AAPL`; `AAPL.US` does not match `AAPL`). The check
runs **before** the §1 LIVE guard so the user sees a precise rejection:

- Missing `confirmation_text` → rejected with `CONFIRMATION_REQUIRED`.
- Wrong text → rejected with `CONFIRMATION_MISMATCH`.
- Correct text → confirmation passes; the §1 `BrokerModeError` then refuses it
  (until §7).

Strategy-sourced orders and all paper orders bypass this layer. The frontend
`LiveOrderConfirmModal` is the UX; the server check is the real defense (a
direct API/router call is gated identically).

### What if I typed the wrong ticker?

The order rejects with `CONFIRMATION_MISMATCH` and the attempt is recorded in
the audit log as `LIVE_ORDER_SUBMITTED` with `outcome=rejected`. No order
reached the broker. Re-submit with the correct text.

## Per-strategy cooldown

When a STRATEGY-sourced order fails to submit (risk rejection, unknown symbol,
broker permanent error — anything that lands as `REJECTED`), that strategy
enters a 60-second cooldown (`strategies.cooldown_until`). Subsequent STRATEGY
orders from the same strategy during the window reject with `STRATEGY_COOLDOWN`.

The cooldown:
- Is **per-strategy** (other strategies and all manual orders are unaffected).
- **Resets to 60s on each failure** — a strategy failing every 30s stays in
  cooldown indefinitely (the operator notices via the `strategy_cooldown_set`
  structured log and intervenes; no auto-escalation in §6).
- **Self-clears** after 60s if no further failures.
- Survives backend restarts (persisted).
- Does NOT fire on success, on manual orders, or on post-acceptance events
  (partial fills, broker-side cancels) — submission attempts only.

### Stuck in cooldown?

1. Wait 60s (self-clearing), or
2. Strategy detail page → "Clear now" button (audit-logged as
   `STRATEGY_COOLDOWN_CLEARED`). Clearing is normal user authority — it unlocks
   no new capability, just compresses the wait.

## LIVE_ORDER_SUBMITTED audit

Every LIVE order **attempt** writes an `audit_log` row with action
`LIVE_ORDER_SUBMITTED`, regardless of outcome (including pre-broker rejections
— confirmation failures and the §1 refusal). Cooldown rejections are NOT audited
(a spinning strategy would flood the log; the `strategy_cooldown_set` structured
log is the signal). Paper submissions are never audited here — the orders table
is their trail.

Payload (prices as strings to preserve Decimal precision):

```json
{
  "symbol": "AAPL", "side": "buy", "qty": "1", "type": "market",
  "limit_price": null, "stop_price": null,
  "source": "manual", "strategy_id": null,
  "outcome": "rejected", "reason_code": "CONFIRMATION_MISMATCH",
  "account_id": 2
}
```

## New audit actions (operator reference)

| Action | Meaning | First response |
|---|---|---|
| `LIVE_ORDER_SUBMITTED` | A LIVE order submission attempt | Inspect `outcome` + `reason_code`; a string of `BROKER_MODE_NOT_ENABLED` is the expected §1 refusal pre-§7 |
| `STRATEGY_COOLDOWN_CLEARED` | A user cleared a strategy cooldown | Verify `cleared_by_user_id` is the owner; check the structured logs for the `strategy_cooldown_set` that triggered it |

(When the P5 §8 on-call playbook is authored, these scenarios move there.)

## Inspecting

```bash
# Recent LIVE order attempts
sqlite3 apps/backend/data/workbench.sqlite "
SELECT ts, payload_json FROM audit_log
WHERE action='LIVE_ORDER_SUBMITTED' ORDER BY id DESC LIMIT 20;"

# Strategies currently in cooldown
sqlite3 apps/backend/data/workbench.sqlite "
SELECT id, name, cooldown_until FROM strategies
WHERE cooldown_until IS NOT NULL AND cooldown_until > datetime('now')
ORDER BY cooldown_until;"
```

To find strategies that *entered* cooldown, search the structured logs for
`strategy_cooldown_set` (only manual *clears* are in the audit log).
