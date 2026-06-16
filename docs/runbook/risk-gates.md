# Risk Gates (P5 §5)

P5 §5 introduced four account-level risk gates on top of P1's per-order
checks. See also `docs/runbook/risk-limits.md` (editing limits) and
ADR 0004 (the circuit-breaker hard-halt decision).

| Gate | When checked | What happens on failure |
|---|---|---|
| Market session (§9A) | Every order submission | Order rejected (`MARKET_SESSION_CLOSED`) |
| Circuit breaker | Every order submission | Order rejected (`CIRCUIT_BREAKER`); account's active strategies HALTED |
| Per-day order cap | Every order submission | Order rejected (`MAX_ORDERS_PER_DAY`) |
| Pre-trade buying power (LIVE only) | Every LIVE order submission | Order rejected (`INSUFFICIENT_BUYING_POWER`) |
| PDT warning | UI poll (60s) | Banner displayed; **no** blocking |

> The buying-power gate is **dormant until P5 §7**: the OrderRouter refuses
> LIVE accounts with `BrokerModeError` before the risk engine runs, so no
> live order reaches the gate yet.

## Market-session gate (§9A)

A fail-closed, defense-in-depth check that an order is allowed to trade in the
**current market session**. It is the centralized backstop behind the
`StrategyEngine` dispatch gate (which already skips out-of-session strategy
ticks): even a manual or agent order, or a strategy tick that slipped through,
is re-checked here. Evaluated first alongside the halt short-circuit — both are
global "may we trade at all right now?" gates, independent of the order's
specifics.

| Session (ET) | Behavior |
|---|---|
| Regular 09:30–16:00 | Always allowed |
| Pre-market 04:00–09:30 | Rejected **unless** the order set `extended_hours=true` |
| After-hours 16:00–20:00 | Rejected **unless** the order set `extended_hours=true` |
| Closed (overnight / weekend / holiday) | **Always** rejected |

Session truth comes from `app/market/session.py` (`MarketSession`), which prefers
the `pandas_market_calendars` XNYS schedule and falls back to a curated NYSE
holiday/half-day list when that package isn't installed (the dev box — Norton SSL
blocks the install). A classification error **fails closed** (rejected with
`MARKET_SESSION_CLOSED`), logged as `market_session_classify_failed`.

**Operator response when it fires:**
- During known market hours: check the backend log for
  `market_session_calendar_fallback` (running on the curated list, not mcal) and
  `market_session_classify_failed`. A spurious rejection mid-RTH points at a
  calendar gap or a clock/timezone problem, not at the order.
- Outside RTH: expected. An intraday strategy must set `allow_extended_hours`
  (which flows to the order's `extended_hours`) to act pre/after-market;
  otherwise it is correctly held to regular hours (conservative default, §9A.4).

## Circuit breaker

**Trip condition:** `realized_pnl_today + unrealized_pnl_now ≤ -max_daily_loss`,
where realized PnL is recognized only on **closing trades** — for each of
today's SELL fills, `(sell_price − avg_cost) × qty`, with `avg_cost` built from
the account's full fill history (so a position opened on a prior day carries its
cost basis into today's sells). A BUY realizes nothing; opening a position swaps
cash for an asset that the unrealized term then marks. Unrealized PnL is the sum
of `positions.unrealized_pl` for the account.

> ⚠ Until 2026-06-15 the realized term was the *signed cash flow* of today's
> fills, which counted BUY notional as a realized loss — so opening a book
> larger than `max_daily_loss` tripped the breaker on capital deployment, not on
> loss. Corrected to the close-based calc above (`_compute_realized_pnl_today`).

This is **in addition to** the older *global* daily-loss halt
(`app/risk/halt.py`, keyed on `AccountState.day_change`), which still trips a
system-wide `system_config` flag. The two compose (defense in depth); see
ADR 0004.

When the account breaker trips:
1. `accounts.circuit_breaker_tripped_at` is set to NOW().
2. Every active strategy **running in the account's mode** transitions to
   HALTED. (Strategies have no `account_id` yet — P5 §7 — so they are mapped to
   the account via `user_id` + status↔mode: a PAPER-status strategy belongs to
   the paper account, LIVE to the live account.)
3. An `audit_log` entry is written (`action=CIRCUIT_BREAKER_TRIPPED`) with the
   PnL snapshot and the halted strategy ids.
4. The `system.circuit_breaker` bus event is published (WS `system` topic).
5. The submitting order is rejected with `CIRCUIT_BREAKER`.

While tripped, every order to the account is rejected with the same code.

**Reset:** `POST /api/v1/accounts/{id}/risk/reset-circuit-breaker` with the
account label as `confirmation_text` (the UI's reset modal enforces this; the
server re-checks). The reset re-enables order submission BUT does NOT
auto-restart HALTED strategies — start each one manually
(`audit_log action=CIRCUIT_BREAKER_RESET`).

**Continuous monitor (P10 §6):** besides the order-time check, a 60-second
lifespan job (`app/jobs/breaker_monitor.py` → `breaker_monitor`) calls
`CircuitBreakerService.evaluate()` for every account holding an open position, so
a drawdown that deepens with no order flow (e.g. overnight) trips + HALTs without
waiting for the next order. `evaluate()` is the non-raising sibling of `check()`
(skips already-tripped / no-limit accounts); trips are audited identically with
`payload.source="monitor"`. (Previously a known limitation — order-time check only.)

## Per-day order cap

`risk_limits.max_orders_per_day` (defaults: PAPER 200, LIVE 20). Orders on the
account since 09:30 US/Eastern today count (fixed -5h UTC offset; 1-hour DST
drift accepted for MVP). NULL means unlimited. Edit at Settings → Risk Limits;
changes are audit-logged.

## Pre-trade buying power (LIVE only)

For LIVE submissions, the workbench calls `BrokerAdapter.get_account()` for live
buying power, computes worst-case notional, and rejects if insufficient.

- MARKET: latest cached close × qty × 1.01
- LIMIT / STOP_LIMIT: limit_price × qty
- STOP: stop_price × qty × 1.01
- SELL: always passes

**Fail-open:** if the broker is unreachable the check passes and Alpaca becomes
the authoritative buying-power gate (ADR-style rationale in the session doc
Notes & Gotchas #14). The event is logged (`buying_power_check_failed_open`).

## Pattern Day Trader warning

A "day trade" is opening and closing the same symbol within one US/Eastern
trading day. The analyzer walks fills from the last 5 business days via a
per-symbol position-walk (handles partial fills correctly). We warn at **3** day
trades (FINRA flags at 4) when account equity < $25,000. We DO NOT block — the
user owns the FINRA decision.

## New audit actions (operator reference)

| Action | Meaning | First response |
|---|---|---|
| `CIRCUIT_BREAKER_TRIPPED` | An account hit its daily-loss limit | Read the payload's PnL snapshot + `halted_strategy_ids`; confirm with the trader before reset |
| `CIRCUIT_BREAKER_RESET` | A user reset a tripped breaker | Verify `reset_by_user_id` is the account owner; strategies remain HALTED |
| `RISK_LIMITS_UPDATED` | A user edited risk limits | Review `changes.old`/`changes.new`; watch for loosened caps before a loss event |

(When the P5 §8 on-call playbook is authored, these three scenarios move there.)

## Strategy HALTED status

`StrategyStatus.HALTED` is distinct from ERROR (crashed) and IDLE (user-stopped).
Cause today: a circuit-breaker trip. To restart a HALTED strategy, go to its
detail page and Start it — the status transitions HALTED → IDLE → PAPER/LIVE.
There is no automatic restart anywhere in the system.
