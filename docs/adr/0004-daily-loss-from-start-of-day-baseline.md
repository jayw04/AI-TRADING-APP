# ADR 0004 v2 — Daily-Loss Circuit Breaker Measured From a Start-of-Day Baseline

| Field | Value |
|---|---|
| Date | 2026-06-17 |
| Status | Accepted (supersedes ADR 0004 v1) |
| Phase | P5 §5 (breaker), refined in P10 |
| Supersedes | ADR 0004 v1 (`0004-circuit-breaker-hard-halt.md`) |
| Related | ADR 0002 (single OrderRouter), ADR 0005 (activation cooldown), ADR 0006 v2 (LLM in order path) |

## Context

ADR 0004 v1 established the account-scoped daily-loss circuit breaker as a hard
halt: when an account's daily P&L crosses `-max_daily_loss`, every order is
rejected and every active strategy in that account's mode transitions to HALTED
until a manual, typed-confirmation reset. That decision — hard halt over soft
warning or adaptive sizing, account-scoped, manual reset, halt-the-strategies —
is unchanged and re-affirmed here.

What v1 got wrong was the *measure* of "daily P&L." v1 defined the trip
precondition as `realized_pnl_today + unrealized_pnl_now ≤ -max_daily_loss`,
where `unrealized_pnl_now` is the **total** open P&L summed across all positions
(`Σ Position.unrealized_pl`). That measure has no start-of-day baseline, which
produces two spurious-halt modes:

1. **Capital deployment counted as loss.** An earlier implementation also signed
   BUY notional into the realized term, so simply *opening* a book larger than
   `max_daily_loss` tripped the breaker. (Fixed in PR #114 — realized P&L now
   recognizes only on closes. That fix stands and is incorporated here.)

2. **Carried-over open losses counted against *today's* limit, every day.** A
   position opened on a prior day that is down `$X` unrealized contributes `-$X`
   to the breaker's "daily" P&L on every subsequent day until it is closed —
   even on a day the account is flat or up. For a concentrated book on a small
   account (the production momentum book is ~10 names on a ~$10k paper account,
   `max_daily_loss` $2,000 = 20%; LIVE default $500 = 5%), this halts trading on
   accumulated drawdown rather than on an actual single-day loss.

Notably, the platform's pre-existing *global* daily-loss halt (`app/risk/halt.py`,
RiskEngine) is already keyed on `AccountState.day_change` (= `equity -
last_equity`, the broker's start-of-day equity baseline). So the two daily-loss
gates disagreed on what "daily loss" means. This ADR reconciles them.

## Decision

The daily-loss circuit breaker trips on **today's P&L measured from a
start-of-day baseline**, not on cumulative open P&L:

1. **Preferred basis — broker start-of-day equity.** `daily_pnl = equity -
   last_equity` (== `AccountState.day_change`), the same measure the global
   daily-loss halt already uses. This excludes capital merely deployed today and
   losses carried over from prior days.

2. **Fail-closed fallback — cumulative.** When no usable `AccountState` baseline
   exists (no row yet, or `last_equity` not populated because a broker sync
   hasn't run), fall back to `realized_pnl_today + unrealized_pnl_now` — the
   *stricter* measure, which can only trip the breaker **earlier**, never later.
   An absent baseline therefore never weakens the gate.

Trip actions, account-scoping, strategy HALT, and manual typed-confirmation reset
are **unchanged from v1**.

## Rationale

- **"Daily loss" should mean loss *in a day*.** The limit is named and documented
  as a per-day bound. Measuring from the start-of-day equity baseline makes the
  behavior match the name and match a trader's intuition (it equals Alpaca's own
  `day_change`). The v1 measure conflated a daily quantity (today's realized)
  with a cumulative quantity (all-time open P&L).

- **Consistency between the two daily-loss gates.** The global halt and the
  account breaker now compute daily loss the same way. Two gates with two
  different definitions of the same limit is a latent source of confusion and of
  exactly the kind of "why did it halt?" incident this ADR responds to.

- **The conservatism trade-off is made deliberately, and bounded.** This change
  makes the breaker trip *less* eagerly: a book sitting on a large carried-over
  unrealized loss but flat on the day no longer halts. In a risk engine the
  default bias is to fail toward halting, so the loosening is justified
  explicitly: halting on capital that is merely deployed or on a prior day's
  drawdown is not loss-control, it is a false positive that trains the user to
  reflexively reset the breaker — which erodes the "force the user to look"
  value the breaker exists for. Protection against *accumulated* drawdown is a
  distinct concern (a max-open-drawdown limit) and, if wanted, belongs in its own
  check, not smuggled into the daily-loss measure. The fallback keeps the strict
  cumulative behavior whenever the precise baseline is unavailable.

- **Stays DB-bound.** `AccountState` is a local table kept fresh by
  `AccountSyncService`; reading it is not a broker round-trip on the order path.
  The breaker remains a couple of indexed queries, consistent with v1.

## Implementation notes

- `CircuitBreakerService._compute_daily_pnl(account_id, *, realized, unrealized)
  -> tuple[Decimal, str]` returns `(daily_pnl, basis)` where `basis` is
  `"equity_baseline"` or `"cumulative_fallback"`. Used by `check()`,
  `evaluate()`, and `status()`.
- Baseline guard: the equity basis is used only when an `AccountState` row exists
  and `last_equity > 0` (an unpopulated row defaults `last_equity` to 0 → treated
  as no baseline → fallback).
- `CircuitBreakerStatus` and the `/accounts/{id}/risk` API response gain
  `daily_pnl` and `daily_pnl_basis` fields (additive). `realized_pnl_today` and
  `unrealized_pnl_now` are retained for transparency; `headroom` is now computed
  from `daily_pnl`.
- The `CIRCUIT_BREAKER_TRIPPED` audit payload now records `daily_pnl` and
  `daily_pnl_basis` alongside the realized/unrealized breakdown.
- No schema migration: `AccountState` already carries `equity` / `last_equity` /
  `day_change`.
- Realized P&L (PR #114) is unchanged: recognized only on closing trades via
  running average cost; buys realize 0.

## Consequences

**Positive:**
- The breaker trips on genuine single-day losses, not on capital deployment or
  carried-over open positions. The production momentum book can rebalance without
  spuriously halting on week-old open positions.
- The account breaker and global halt now agree on "daily loss."
- The `daily_pnl_basis` field makes it auditable which measure tripped (or held).

**Negative:**
- The breaker is less conservative: a book sitting on a large unrealized loss
  carried from prior days no longer halts on open of a flat day. Accumulated
  drawdown is no longer caught by *this* gate (it never was a clean fit — see
  Rationale). If a max-open-drawdown bound is wanted, it needs its own check.
- Correctness now depends on `AccountState` freshness on the preferred path. A
  stale `equity` (sync lagging) makes `daily_pnl` slightly stale — the same
  property the global halt already accepts. The fail-closed fallback covers the
  *missing* case, not the *stale* case.

**Neutral:**
- Existing breaker tests that seeded no `AccountState` exercise the fallback path
  and pass unchanged; new tests cover the equity-baseline path.

## Alternatives considered (not chosen)

- **Snapshot start-of-day unrealized P&L into a new table.** Would keep the
  realized/unrealized decomposition and compute `realized_today + (unrealized_now
  − unrealized_at_open)`. Rejected: needs a migration plus a daily-capture job,
  and reproduces a number the broker already computes correctly as
  `last_equity`. More moving parts for the same result.
- **Keep v1 (cumulative) semantics.** Rejected: it is the source of the spurious
  halts and disagrees with the global halt.
- **Add a separate max-open-drawdown breaker now.** Deferred, not rejected — a
  legitimate future check, but a distinct decision with its own limit and ADR;
  bundling it here would conflate two gates again.

## Re-evaluation triggers

- If a daily-loss halt is ever traced to a **stale** `AccountState.equity` (sync
  lag) letting a real intraday loss exceed the limit before the breaker sees it,
  revisit the freshness contract (e.g. force a sync in `check()` for live
  accounts, or shorten the breaker-monitor interval).
- If accumulated open drawdown (distinct from daily loss) causes an account loss
  that the user expected the breaker to prevent, that is the signal to add a
  dedicated max-open-drawdown check (the deferred alternative above).
- If the global halt and account breaker are ever consolidated into one mechanism
  (the cleanup noted in v1), fold this measure into that ADR.
