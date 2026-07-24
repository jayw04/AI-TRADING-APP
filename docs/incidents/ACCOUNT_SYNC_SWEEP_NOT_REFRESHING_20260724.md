# Defect record — ACCOUNT_SYNC_SWEEP_NOT_REFRESHING

- **Date raised:** 2026-07-24
- **Severity:** **Risk-system availability defect** — `accounts_state` is an active risk input, not telemetry
- **Status:** OPEN · `ROOT_CAUSE_UNKNOWN`
- **Classification:** `ACCOUNT_SYNC_SWEEP_NOT_REFRESHING` · `VALIDATION_ACCOUNT_STATE_STALE_SINCE_2026_07_22`
- **Scope:** confirmed on the ADR-0043 validation host; **production not yet checked** — do not assume validation-only

## Summary

On the ADR-0043 validation host, `accounts_state` has not been refreshed since **2026-07-22 13:23:59 UTC**,
while the backend container has been up and healthy for ~10 h. The account created for the canary on
2026-07-23 has **no `accounts_state` row at all**.

## Evidence (read-only, 2026-07-24)

```
docker ps            workbench-backend  Up 10 hours (healthy)

users                id=1 jay@globalcomplyai.com
                     id=3 adr0043-canary@localhost      (created 2026-07-23 22:26:37)
accounts             id=1 Alpaca Paper (user 1)
                     id=3 ADR-0043 canary (user 3)
accounts_state       ONLY account_id=1 — equity 84466.41, last_equity 84445.51, day_change 20.90,
                     updated_at 2026-07-22 13:23:59        <-- ~2 days stale
equity_snapshots     EMPTY
```

A healthy backend plus a two-day-old snapshot row means the sweep is either not scheduled, not
running, or failing silently on this host. None of those has been established yet.

## Why this is a risk defect rather than observability debt

`accounts_state` feeds the order path:

- `app/risk/engine.py::_daily_loss_day_change` — the legacy daily-loss basis (ADR-0043 flag OFF)
- `app/risk/lock_state.py::current_lock_state` — the shared lock definition used by the order and
  cancel paths

A stalled sweep therefore does not merely make a dashboard stale: it makes the daily-loss gate
evaluate **yesterday's** equity as though it were today's. The account keeps trading against a
number that stopped moving.

## The failure mode this cannot be closed by a one-time resync

```
valid basis written before deploy
      ↓
sweep stalls afterward
      ↓
row keeps an apparently-valid provenance indefinitely
      ↓
risk engine consumes stale P&L as current
```

The `DAILY_PNL_UNAVAILABLE` rail (separate PR) does **not** catch this: the stored basis label still
reads `BROKER_LAST_EQUITY`, which is true about the row's origin and says nothing about its age.
**Provenance and freshness are different dimensions.**

## Required follow-up

1. **Establish the root cause** — is the sweep scheduled on this host, is it running, is it erroring?
   Check production scheduling and recent `accounts_state.updated_at` values across all accounts
   before concluding this is validation-only.
2. **Freshness control** (separate PR): an `ACCOUNT_STATE_STALE` condition with the same shape as the
   unavailable-basis rail — reduction-only, verified reductions still permitted, new risk refused —
   but a **distinct reason and event**, because diagnosis and recovery differ:
   - `DAILY_PNL_UNAVAILABLE` — no trustworthy baseline exists;
   - `ACCOUNT_STATE_STALE` — the measurement pipeline stopped refreshing.
   It should bind to an existing account-sync SLA if one exists rather than inventing a discretionary
   risk parameter.

## Constraints

- Any repair of `accounts_state` must go through the sanctioned account-sync mechanism, **never SQL**.
- Until the freshness control exists, a one-time resync proves only the state at that instant, so it
  is **required but not sufficient** before deploying anything that consumes this row as authoritative.
