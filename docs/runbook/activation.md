# Strategy Activation (P5 §7)

The session that opens the live order path. See ADR 0005 (24-hour activation
cooldown) for the central decision.

## Strategy statuses

| Status | Submits orders? | Enter | Exit |
|---|---|---|---|
| IDLE | No | default; cancel; deactivate | wizard → PENDING_LIVE; start → PAPER |
| PAPER | Yes (paper) | start on paper | stop → IDLE |
| PENDING_LIVE | No | wizard from IDLE/PAPER | 24h elapses → LIVE; cancel → IDLE |
| LIVE | Yes (live) | scheduler after 24h | deactivate → IDLE; breaker → HALTED |
| HALTED | No | circuit-breaker trip | reset breaker; restart |
| ERROR | No | engine crash | fix + restart |

`PENDING_LIVE` is **not** in `ACTIVE_STRATEGY_STATUSES` — it cannot submit orders.

## Prerequisites (six)

The wizard refuses initiation unless all are satisfied:

1. **LIVE account exists** — the user has an Alpaca live account (Settings →
   Accounts; TOTP-gated). (strategies have no `account_id`; the strategy's
   account is resolved by `user_id` + mode.)
2. **Live broker credentials** — `alpaca_live_key` + `alpaca_live_secret` in the
   credential store.
3. **TOTP enrolled** — `users.totp_verified_at` is set.
4. **Recent backtest** — a `backtest_results` row for the strategy in the last 7
   days. (There is no `backtests` table; a result row means a backtest ran.) The
   workbench checks engagement, not quality — that's the user's call.
5. **LIVE risk limits** — a GLOBAL `risk_limits` row with `broker_mode=live`
   (the §5 migration seeds one).
6. **No active circuit breaker** on the live account (`circuit_breaker_tripped_at`
   is NULL).

## Activation flow

1. **Initiate** (`POST /strategies/{id}/activate`, body `{confirmation_name,
   totp_code}`): the server re-verifies the typed name (case-sensitive), the
   TOTP code (defense against session hijack — the cookie is 14 days, the code
   30 s), and re-checks all six prerequisites at the last moment. On success →
   `PENDING_LIVE`, `live_activation_initiated_at = now`, audit
   `STRATEGY_ACTIVATION_INITIATED`.
2. **Cooldown (24h)**: orders from the strategy are rejected with
   `STRATEGY_PENDING_LIVE`. The `ActivationCountdown` banner shows on the
   detail page. **Cancel anytime** (`POST /activate/cancel`) — no TOTP, no typed
   name; cancellation is the safe direction (ADR 0005). Audit
   `STRATEGY_ACTIVATION_CANCELED`.
3. **Completion**: the `activation_completion` scheduler job (every 60 s) flips
   `PENDING_LIVE → LIVE` once 24 h has elapsed since
   `live_activation_initiated_at`. Idempotent across restarts. Audit
   `STRATEGY_LIVE_ACTIVATED`.

## The lifted live-order guard

P5 §1's blanket `BrokerModeError` raise is replaced (in `OrderRouter.submit`) by
a conditional, returning a typed REJECTED order:

- **MANUAL + LIVE** → permitted (the §6 typed-ticker confirmation gate enforces
  `confirmation_text == symbol` first).
- **STRATEGY + LIVE** → permitted only if `strategy.status == LIVE`
  (`PENDING_LIVE` → `STRATEGY_PENDING_LIVE`; other → `STRATEGY_NOT_LIVE`; missing
  id → `STRATEGY_ID_REQUIRED`; unknown → `STRATEGY_NOT_FOUND`).
- **AGENT (agent_proposal/agent_strategy) + LIVE** → `AGENT_LIVE_DISABLED` (P6).

`POST /api/v1/orders` now accepts an optional `account_id` (defaults to the
user's paper account), `source`, and `strategy_id`. Every LIVE attempt is
audited `LIVE_ORDER_SUBMITTED` (§6).

## Deactivation

`POST /strategies/{id}/deactivate` body `{liquidate}`. Immediate, no cooldown
(you can always stop trading). If `liquidate=true`, the service submits closing
**MANUAL** market orders (auto `confirmation_text = symbol`) for open positions in
the strategy's symbols, via the OrderRouter — so they pass the normal risk gates
and are audited. MANUAL source is used (not STRATEGY) so liquidation works for
both LIVE and HALTED strategies and isn't blocked by the strategy-status guard or
the §6 cooldown. Audit `STRATEGY_DEACTIVATED`.

## LIVE account creation

`POST /api/v1/accounts` with `mode=live` requires `totp_code` (re-verified).
Audit `LIVE_ACCOUNT_CREATED`. The BrokerRegistry refreshes so the new account's
adapter is loaded.

## New audit actions (operator reference)

`STRATEGY_ACTIVATION_INITIATED`, `STRATEGY_ACTIVATION_CANCELED`,
`STRATEGY_LIVE_ACTIVATED`, `STRATEGY_DEACTIVATED`, `LIVE_ACCOUNT_CREATED`.
(When the P5 §8 on-call playbook is authored, these scenarios move there.)

## Inspecting

```bash
# Strategies in the activation cooldown
sqlite3 apps/backend/data/workbench.sqlite "
SELECT id, name, live_activation_initiated_at,
       datetime(live_activation_initiated_at, '+24 hours') AS goes_live_at
FROM strategies WHERE status='pending_live' ORDER BY live_activation_initiated_at;"

# Recent activation audit trail
sqlite3 apps/backend/data/workbench.sqlite "
SELECT ts, action, target_id FROM audit_log
WHERE action LIKE 'STRATEGY_%' OR action='LIVE_ACCOUNT_CREATED'
ORDER BY id DESC LIMIT 20;"
```

## Failure modes

- **Stuck in PENDING_LIVE:** confirm the scheduler is running (look for
  `activation_completion_pass` logs ~every 60 s), `live_activation_initiated_at`
  is set, and 24 h has actually elapsed. The job uses `< cutoff`, so it's
  idempotent and catches up after a restart.
- **"Prerequisites not satisfied":** the error names the failing prereqs (most
  often `recent_backtest`, `live_broker_credentials`, or `circuit_breaker_clear`).
- **Liquidation partial failure:** the strategy still transitions to IDLE; the
  response lists the orders that DID submit. Re-deactivate is a no-op; submit the
  remaining closing orders manually.

> **Not production-ready until §8.** §7 opens the live path in code; §8
> (production hardening) adds the monitoring/health/backup infra. Don't activate
> a real strategy on a §7 build.
