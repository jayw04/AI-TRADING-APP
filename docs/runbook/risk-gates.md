# Risk Gates (P5 §5)

P5 §5 introduced four account-level risk gates on top of P1's per-order
checks. See also `docs/runbook/risk-limits.md` (editing limits) and
ADR 0004 v2 (the circuit-breaker hard-halt decision + start-of-day daily-loss measure).

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

**Trip condition (ADR 0004 v2):** `daily_pnl ≤ -max_daily_loss`, where `daily_pnl`
is **today's** P&L measured from a **start-of-day baseline**:
- **Preferred (`daily_pnl_basis = "equity_baseline"`):** `equity − last_equity`
  (== `AccountState.day_change`) — the same measure the global halt uses. Excludes
  capital merely deployed today and losses carried over from prior days.
- **Fail-closed fallback (`"cumulative_fallback"`):** when no usable `AccountState`
  baseline exists (no row, or `last_equity` not yet populated), fall back to
  `realized_pnl_today + unrealized_pnl_now` — the stricter cumulative measure
  (can only trip earlier, never later). Realized PnL is recognized only on
  **closing trades** (`(sell_price − avg_cost) × qty` per SELL fill; a BUY
  realizes nothing); unrealized is the sum of `positions.unrealized_pl`.

The trip payload and `/risk` status carry `daily_pnl` and `daily_pnl_basis` so an
operator can see which measure fired.

> ⚠ History: until 2026-06-15 the realized term signed BUY notional as a loss, so
> opening a book tripped on capital deployment (fixed, PR #114). Until 2026-06-17
> the trip used `realized + TOTAL unrealized` with no start-of-day baseline, so a
> position carrying a prior-day open loss counted against *today's* limit every
> day — fixed by the start-of-day baseline above (ADR 0004 v2).

This is **in addition to** the older *global* daily-loss halt
(`app/risk/halt.py`, also keyed on `AccountState.day_change`), which still trips a
system-wide `system_config` flag. The two now use the same daily-loss measure and
compose (defense in depth); see ADR 0004 v2.

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

## Short restriction — is BROKER-verified (`SHORT_NOT_ALLOWED`)

When `risk_limits.allow_short` is false, a SELL is refused if it would leave a **short at the
broker**. The gate compares the order against the **broker's signed position**, fetched live for
that decision (ADR 0042 `fetch_snapshot`) — **not** against the local `positions` row.

**Why it must be the broker's number.** On 2026-07-16 account 2 was found holding an AMD **−4
short** with `allow_short = 0`. The gate had not been bypassed — it had been *told the wrong
position*. An Alpaca paper-account reset (07-07 15:36) wiped the broker's positions while the local
order ledger kept every pre-reset fill, leaving the local view **+7 long of reality**; `SELL 7` read
as a legal flatten and opened a real −7 short. The ledger can also be wrong the *other* way — when
it lags behind the broker it refuses genuine reductions. See
`docs/incidents/2026-07-16-account2-ghost-positions-short-gate-escape.md`.

### Operator response to the two warnings

**`short_gate_ledger_broker_divergence`** — *the loud one.* The ledger and the broker disagree about
what the account owns (`local_qty`, `broker_qty`, `delta` are logged).

> The current short-gate decision was made against the broker position and is therefore protected.
> The account remains **operationally degraded**: ledger-derived positions and any control depending
> on them are **untrusted** until the account-reset boundary is identified and reconciled.

Do **not** read this as "nothing is broken" — the *decision* is protected, the *account* is not.

Usual cause: a broker-account reset or recreation orphaning pre-reset fills. **A `GET
/v2/orders/{broker_order_id}` returning 404 is decisive only in COMBINATION with:**

1. the order **predating** the broker account's `created_at`;
2. **post-reset** ledger fills reproducing the current broker positions;
3. **post-reset** orders remaining retrievable.

A standalone 404 is **not** universally proof of a reset (an order can 404 for other reasons).
Confirm by partitioning the ledger at the account's Alpaca `created_at`: if post-reset orders
reconcile to the broker but all-time orders do not, the difference is the ghosts.

⚠ Reconciliation will not surface this: the only implemented domain is `position`, which compares
*local positions* vs broker (they agree), never *ledger-implied* vs broker.

**`short_gate_unverified_broker_unreadable`** — the broker could not be read, so the gate fell back
to the ledger for this decision and **allowed** what the ledger permits. This is deliberate:
`OrderRouter.submit` runs this gate *before* `RiskDecisionService.decide`, so rejecting here would
block a locked account's de-risking SELL upstream of the ADR-0042 path built to allow it — the
2026-07-13 incident.

> The fallback preserves the registered ability to reduce risk, but the sell decision is
> **unverified**. Restore broker readability and reconcile the account **before allowing continued
> autonomous sell activity.**

**This warning is not a successful verification.** The residual exposure — a short slipping through —
needs an outage *and* a ghost *and* a zero-crossing sell at once, but the decision itself carries no
broker evidence. Investigate broker health (account 3's `/v2/positions` timed out >15s on
2026-07-15).

**`short_gate_unverified_no_broker_registry`** — no registry wired. Production always wires one
(`lifespan.py`), so in production this is **not** a warning to investigate at leisure:

> **Treat as a service-construction or deployment failure. Disable affected autonomous order
> submission and escalate immediately.**

Every SELL on an `allow_short = 0` account is being decided with **no broker evidence at all**.
Follow-up: this should become a **readiness/startup failure** rather than a runtime warning.

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

## Gross-exposure cap — and the reducing-exit exemption (ADR 0038)

`risk_limits.max_gross_exposure` caps the account's total notional. Projected gross =
settled positions (Σ|market_value|) + in-flight BUY notional (routed, not yet filled) +
this order's notional when it is a BUY. An order that pushes projected over the cap is
rejected `GROSS_EXPOSURE`. In-flight BUYs are counted so a burst of baskets can't each pass
against the same settled snapshot and stack leverage (incident 2026-06-22, CAP-014).

**A position-reducing SELL is EXEMPT (ADR 0038).** A SELL fully covered by the current long
(`current_qty >= order qty` — the same "not a short" test the short restriction uses) can only
*lower* gross, so it skips this gate. An exposure cap must never block an exposure-*reducing*
order: refusing a de-risking exit traps risk on a book already over the cap (incident
2026-07-07 — a strategy over its $10k cap could not stop out; its stop-loss SELLs were rejected
`GROSS_EXPOSURE` every 5-min cycle). Short-*opening* sells (qty beyond the held long) are NOT
exempt and stay gated (and are rejected first by the short restriction when `allow_short` is
false). BUYs are unaffected — the cap stays fully binding on every risk-increasing order.

**Operator note.** A book that cannot exit while `GROSS_EXPOSURE` shows on its SELLs is the
pre-ADR-0038 trap; on a patched build a reducing exit always passes. The separate causes of
*getting* over the cap — a market-BUY over-fill via NULL `estimated_notional`, or sizing above
the cap — are addressed by sizing the strategy to fit its `max_gross_exposure`
(`per_position_budget × N ≤ cap`).

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
| `LOSS_CONTROL_ENFORCED` | The ADR 0043 loss-control **state machine** contributed to an order rejection in `ENFORCE` mode | See the scenario below — read the provenance, do **not** bootstrap or force `NORMAL` |

(When the P5 §8 on-call playbook is authored, these scenarios move there.)

## `LOSS_CONTROL_ENFORCED` — the loss-control state machine (ADR 0043 PR4)

**This is interpretation + diagnosis only. It does not authorize enabling `ENFORCE`, running a
canary, or resetting anything.** The mode is `OFF` by default; a `LOSS_CONTROL_ENFORCED` row exists
only where `WORKBENCH_LOSS_CONTROL_MODE=ENFORCE` has been deliberately turned on.

**What it means.** In `ENFORCE`, the persisted loss-control state machine participates in the
order decision. When it authoritatively **contributes to a rejection**, the engine writes this
audit row (atomically with the `RiskCheck` rejection) and the order carries `LOSS_CONTROL_STOP` in
its reasons (alongside any independent gate reason, e.g. `CIRCUIT_BREAKER`, which is never
discarded). A matching legacy rejection keeps its own reason **and** records the loss-control
provenance; an `ADR_LOOSER` divergence (loss control would have permitted) never appears here — it
does not weaken an independent rejection and writes no row.

**Read the payload:**

1. `loss_control_mode` — confirm it is `ENFORCE` (an `OFF`/`SHADOW` row should never exist).
2. `target_id` — the account.
3. `loss_control_state` + `loss_control_state_version` — the persisted state the decision used.
4. `loss_control_outcome` — `INTEGRITY_STOP` / `REFUSE` / …
5. `verified_reduction` — whether the order was a verified de-risking reduction.
6. `legacy_outcome` + `divergence` — `MATCH` (both denied) vs `ADR_STRICTER` (only loss control
   denied) vs `ERROR` (the gate or a governing transition failed).
7. `trigger` + `trigger_committed` — present when the trip was a **transition-commit failure**:
   `trigger_committed=False` with `error=TRIGGER_COMMIT_FAILED` means the governing state transition
   did not persist, so the order was failed **closed** rather than evaluated against possibly-stale
   state.
8. `state_known` (in the paired `risk_loss_control_shadow_comparison` log) — `False` means **no
   persisted state row**; the account fails closed to `INTEGRITY_STOP`.

**A `LOSS_CONTROL_STOP` from a missing-state, `ERROR`, or transition-commit-failure condition is an
integrity refusal — NOT a trading-limit adjustment request.** Do not treat it as "the cap is too
tight".

**Operator action:**
- **Do not** bootstrap the account or manually force its state to `NORMAL` — that would paper over
  the integrity condition the fail-closed exists to surface.
- Keep `ENFORCE` disabled, or return the account to its previously authorized mode
  (`OFF`/`SHADOW`), while investigating.
- Recovery from a loss-control lock has **no sanctioned operator procedure yet** — the checked
  recovery preflight (PR6) and re-arm/hysteresis (PR7) are not implemented. Until then, a genuine
  lock is cleared only by the existing audited circuit-breaker reset flow for the *breaker*
  component, never by editing loss-control state directly.
- The three loss-control flags are independent (`SESSION_BASELINE_SHADOW_ENABLED`,
  `SESSION_BASELINE_ENFORCEMENT_ENABLED`, `LOSS_CONTROL_MODE`); toggling `LOSS_CONTROL_MODE` back to
  `OFF`/`SHADOW` neither disables baseline capture nor changes the daily-loss basis.

## Strategy HALTED status

`StrategyStatus.HALTED` is distinct from ERROR (crashed) and IDLE (user-stopped).
Cause today: a circuit-breaker trip. To restart a HALTED strategy, go to its
detail page and Start it — the status transitions HALTED → IDLE → PAPER/LIVE.
There is no automatic restart anywhere in the system.
