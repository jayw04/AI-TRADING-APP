# Defect record — ACCOUNT_SYNC_SWEEP_NOT_REFRESHING

- **Date raised:** 2026-07-24
- **Severity:** **Risk-system availability defect** — `accounts_state` is an active risk input, not telemetry
- **Status:** OPEN · validation-host root cause `UNKNOWN`
- **Classification:** `ACCOUNT_SYNC_SWEEP_NOT_REFRESHING` · `VALIDATION_ACCOUNT_STATE_STALE_SINCE_2026_07_22`
- **Scope:** **ADR-0043 validation host only.** Production impact **not observed**; the production
  sweep was **healthy** at inspection time (2026-07-24T13:56:18Z, see below).

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

## Production comparison (read-only inspection, 2026-07-24)

```
capture_utc              2026-07-24T13:56:18Z
instance                 i-0d3294e91e6ad9e1d
backend                  healthy
observed sweep cadence   ~10 seconds
accounts synchronized    1-7
skipped                  none
errors                   none
accounts_state age       ~7-8 seconds across all seven accounts
recent sync errors       none observed in 24 h
```

Every production account holds a state row refreshed seconds before capture, and every
`account_sync_all_completed` event in the window reports `synced [1..7], skipped [], errors []`.
Equity snapshots are one-per-day near the close on both hosts, which matches
`run_daily_equity_snapshot` — that is the designed cadence, not a stall.

Account 2 carried one open order at capture. That is observed operational state, **not** evidence of
a sync defect.

### What this does and does not establish

- It proves the production sweep was healthy **at the inspection instant**. It is **not** a permanent
  freshness guarantee, and nothing here monitors it continuously.
- The **validation-host failure remains unexplained.**
- The two hosts differ in deployment and scheduler topology, so **no root-cause inference should be
  drawn** from production being healthy.
- `ACCOUNT_STATE_STALE` remains a valid future control requirement regardless: **provenance does not
  prove freshness**, and no control currently detects a pipeline that stops refreshing.

### Inspection evidence discipline

On an actively written database, `DB SHA before == after` is neither expected nor a valid no-write
test — the application writer is committing every ~10 s. The correct statement of what was
guaranteed:

```
operator write capability   structurally absent
DB mount                    read-only  (-v /opt/workbench/data:/app/data:ro)
SQLite connection           file:...?mode=ro
statements executed         SELECT only
application writer          remained active throughout
DB hash                     CHANGED, due to normal backend writes
```

This inspection was **operator-read-only while concurrent application writes continued**. It is not
described as "the database was unchanged", because it was not.

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

## It currently gates the ADR-0043 canary chain

Not merely a hygiene issue on that host: `adr0043_canary_lib.py::snapshot_state`, as corrected,
**refuses** with `ACCOUNT_STATE_ROW_MISSING` when the account has no `accounts_state` row — and
account 3 on the validation host has none, precisely because the sweep is not running there. Phase 0
therefore cannot proceed until that host's sweep produces a row through the sanctioned mechanism.

## Required follow-up

1. **Establish the validation-host root cause** — is the sweep scheduled on that host, is it running,
   is it erroring? `PENDING`; read-only and separate from this record. Production has now been
   compared and is healthy, so the investigation is scoped to the validation host alone.
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
