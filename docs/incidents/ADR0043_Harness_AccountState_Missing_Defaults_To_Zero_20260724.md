# Defect record — ADR0043_HARNESS_ACCOUNT_STATE_MISSING_DEFAULTS_TO_ZERO

- **Date:** 2026-07-24
- **Severity:** **BLOCKING for ADR-0043 Phase 0** (no trading impact — nothing has been submitted)
- **Component:** `apps/backend/scripts/adr0043_canary_lib.py` · `apps/backend/scripts/adr0043_churn_driver.py`
- **Status:** CONFIRMED — dedicated fix PR required before any Phase-0 session
- **Classification:** `PHASE0_BREACH_OBSERVATION_DISARMED` · `PHASE0_OVERSHOOT_GUARD_DISARMED`

## Summary

The canary harness takes its authoritative loss measurement from `accounts_state`, and silently
substitutes **zero** when the row is absent. On the validation host the row for account 3 does not
exist, so every safety-critical loss reading in a Phase-0 run would be a constant `0`.

`adr0043_canary_lib.py:231` `snapshot_state`:

```
"SELECT day_change, equity, last_equity FROM accounts_state WHERE account_id = :a"   # ACCT = 3
...
day_change=D(str(row.get("day_change") or 0)),
equity=D(str(row.get("equity") or 0)),
last_equity=D(str(row.get("last_equity") or 0)),
```

A missing row yields `{}`, and `.get(...) or 0` converts "unmeasured" into "measured zero".

## Evidence (validation host, read-only, 2026-07-24)

```
users:     id=1 jay@globalcomplyai.com   ·  id=3 adr0043-canary@localhost (created 2026-07-23 22:26:37)
accounts:  id=1 Alpaca Paper (user 1)    ·  id=3 ADR-0043 canary (user 3)
accounts_state:  ONLY account_id=1  — equity 84466.41, last_equity 84445.51, day_change 20.90,
                 updated_at 2026-07-22 13:23:59   (stale: backend container up 10 h)
equity_snapshots: EMPTY
```

No account-3 row exists, and neither the driver nor the lib calls an account sync — `snapshot_state`
reads the table directly.

## Impact on the frozen execution plan

| Frozen control | Mechanism | Effect |
|---|---|---|
| §5 loss objective, terminal range −$3,000 … −$3,250 | `breached = snap.day_change <= -target_loss` (`adr0043_churn_driver.py:598`) | never true → the breach the run exists to produce is never observed |
| §10 hard overshoot floor, `day_change < −$3,750` → `CHURN_OVERSHOT` | `adr0043_churn_driver.py:636` | inert |
| `verify_after` state expectations | compares against `snap.day_change` | evaluates against a constant 0 every leg |

The run would not be unbounded — the 12-round-trip / 24-leg / $25,000-per-order caps still bind — but
it would churn to its cap and terminate **without recording the breach**, producing no valid evidence
while spending the session.

## Required correction (owner ruling, 2026-07-24)

The driver must not treat nullable `accounts_state.day_change` as the authoritative ADR-0043 loss
measurement. It must use the same production mechanism ADR-0043 exists to prove:

```
loss = current equity − immutable current-session risk_session_baseline equity
```

Named refusals required (stop before any new submission; after execution has begun, stop further
submissions and preserve evidence):

- account-state row missing
- current equity unavailable
- current-session baseline missing
- baseline belongs to another session
- baseline account / user mismatch
- baseline captured after the first churn submission
- multiple contradictory baselines

**Any semantics equivalent to `row.get("day_change") or 0` must be removed for all safety-critical
fields.** Missing data stays missing and raises a named refusal. A baseline whose value is
numerically zero is *present*, not missing.

## Related

- `docs/runbook/ADR0043_Phase0_SameSession_Runbook_v1.0.md` — Step B is HELD.
- `docs/implementation/ADR0043_Phase0_FrozenExecutionPlan_v1.0.md` — §5 / §10 are the disarmed controls.
- The same "unavailable rendered as zero" defect class was independently rejected in PR #495
  (`accounts_state.day_change` when the broker reports no usable `last_equity`).
