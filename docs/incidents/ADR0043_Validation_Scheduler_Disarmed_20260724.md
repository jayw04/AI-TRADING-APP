# Defect record — ADR0043_VALIDATION_SCHEDULER_DISARMED

- **Date:** 2026-07-24
- **Severity:** Blocking for Phase 0 (readiness contract), **not** a request to make this host autonomous
- **Component:** validation host `i-01527ac7b7c7efa35` runtime configuration + the Phase-0 runbook
- **Status:** OPEN — resolution is scoped synchronization, **not** global scheduler enablement

## Summary

```
WORKBENCH_SCHEDULER_ENABLED=false
```

The scheduler on the validation host is **intentionally disarmed**, consistent with a validation box
that must not act autonomously (`WORKBENCH_LIVE_TRADING_ALLOWED=false` alongside it).

Causal chain: `app/config.py` defaults `scheduler_enabled=True`; `app/lifespan.py` passes it as
`enabled=` when starting the scheduler; `app/api/healthz.py` treats a disarmed scheduler as
intentional and **does not degrade health** — which is why the container reports *healthy* while
performing no synchronization at all.

Evidence: **zero** `account_sync` log lines and **zero** scheduler log lines across the container's
entire life (created 2026-07-23T19:56:20Z, `RestartCount=0`).

Nothing failed. The sweep was never armed.

## Classification

- `VALIDATION_SCHEDULER_INTENTIONALLY_DISARMED`
- `ACCOUNT_STATE_NOT_AUTONOMOUSLY_MAINTAINED`
- `RUNBOOK_ASSUMED_A_SWEEP_THAT_CANNOT_OCCUR`

This is a **runbook / configuration-assumption defect**, not evidence that this instance should
become autonomous.

## Why enabling the scheduler is NOT the fix

The startup wiring constructs account, position and asset synchronization under one scheduler and
starts them from a single global flag. Flipping it would:

- begin writing state for **every** locally configured account, including account 1;
- introduce unrelated scheduled activity into the canary runtime;
- make the restart materially broader than the stated reconciliation task;
- weaken the claim that only sanctioned, reviewed canary actions occurred on this host.

## Resolution

A **sanctioned, account-scoped** one-shot synchronization for user/account 3/3 only —
account state plus approved position reconciliation, and nothing else. It must not iterate accounts,
must not touch account 1, must not schedule recurring work, must not submit/cancel/replace/close
orders, must not capture the session baseline, and must not alter risk limits or loss-control state.

If the existing service has no account-scoped entry point, `sync_all` is **not** an acceptable
substitute: the narrow operation gets added to the governed operator tooling and tested before
execution.

Verification is three explicit scoped observations — execute the scoped sync, verify the row and
broker identity, then two read-only broker/DB reconciliations at the expected cadence proving
consistency and no unintended mutation. The point is to prove **account 3 is correctly synchronized**,
not to prove a scheduler that intentionally stays disabled.
