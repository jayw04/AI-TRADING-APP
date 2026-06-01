# Risk Gates (P5 §5)

P5 §5 introduced four account-level risk gates on top of P1's per-order
checks. See also `docs/runbook/risk-limits.md` (editing limits) and
ADR 0004 (the circuit-breaker hard-halt decision).

| Gate | When checked | What happens on failure |
|---|---|---|
| Circuit breaker | Every order submission | Order rejected (`CIRCUIT_BREAKER`); account's active strategies HALTED |
| Per-day order cap | Every order submission | Order rejected (`MAX_ORDERS_PER_DAY`) |
| Pre-trade buying power (LIVE only) | Every LIVE order submission | Order rejected (`INSUFFICIENT_BUYING_POWER`) |
| PDT warning | UI poll (60s) | Banner displayed; **no** blocking |

> The buying-power gate is **dormant until P5 §7**: the OrderRouter refuses
> LIVE accounts with `BrokerModeError` before the risk engine runs, so no
> live order reaches the gate yet.

## Circuit breaker

**Trip condition:** `realized_pnl_today + unrealized_pnl_now ≤ -max_daily_loss`,
where realized PnL is the signed sum of today's fills (sign from `Order.side`)
and unrealized PnL is the sum of `positions.unrealized_pl` for the account.

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

**Known limitation:** the breaker checks only on order submission. A held
position that drifts deep while no orders are being submitted will not trip
until the next order attempt. P5+ polish: a one-minute APScheduler job calling
`CircuitBreakerService.check()` for every account with open positions.

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
