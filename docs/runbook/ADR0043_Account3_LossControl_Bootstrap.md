# ADR-0043 — Account-3 Loss-Control State Bootstrap

> **Status:** tool reviewed and merged; **execution HELD** until the owner authorizes the bootstrap
> under an approved execution package. One-shot, first-provisioning only.

## Why

Phase-0 attempt 1 (2026-07-28) stopped at leg 0 with `LOSS_CONTROL_STOP`: in `ENFORCE` the order
gate reads the durable loss-control state via `LossControlService.load_state_row`, which
deliberately never bootstraps, and account 3 had no `risk_loss_control_state` row — an
`INTEGRITY_STOP`, correctly fail-closed (owner ruling: `VALID / INCONCLUSIVE`, provisioning RED).
Explicit initialization is the service's race-safe `INSERT ... ON CONFLICT DO NOTHING` bootstrap —
performed deliberately **before** enforcement traffic. `scripts/adr0043_bootstrap_loss_control.py`
is that deliberate act for exactly one account.

## What it does (and refuses)

- Target frozen in code: **user 3 / account 3**. The module reads **no environment variable**.
- Verifies the canary broker identity `PA34USW0Q8UO` through the shared **read-only** single-user
  adapter (`build_scoped_adapter` — user-3 credentials only, no `BrokerRegistry.load_all`);
  refuses `PA3QRX9KSPXA` (momentum, account 1) **by name**.
- **Refuses if a row already exists in any state** — first provisioning only.
- The ONE write is `LossControlService.bootstrap_state_row(3)` — never ad-hoc SQL — executed in
  **one atomic transaction with the governance audit record**: insert, in-transaction validation
  (`state=NORMAL`, `state_version=0`, `last_sequence_no=0`, governed `control_version`), an
  authorship check (a conflict no-op row is refused, never claimed), the typed audit row, and a
  no-transition proof all commit together or roll back together. Verified again from a fresh
  post-commit read.
- Governance record: one typed audit row `LOSS_CONTROL_STATE_BOOTSTRAPPED`
  (reason `ADR0043_CANARY_PROVISIONING`). **No `risk_control_events` row is fabricated** — a
  bootstrap is not a NORMAL → NORMAL transition.
- Proves side-effect freedom: control events / orders / HELD reservations / baselines counts
  unchanged; account 1's loss-control row byte-identical; audit delta exactly 1 (commit) or 0.
- Atomic evidence JSON on success **and** refusal; dry run is the default.

## Execution (owner-authorized, on the validation host only)

```bash
# 1. dry run — every read and check, no write
docker exec -w /app workbench-backend \
  python -m scripts.adr0043_bootstrap_loss_control \
  --evidence /app/data/adr0043_lc_bootstrap_dryrun.json

# 2. read the evidence, then commit
docker exec -w /app workbench-backend \
  python -m scripts.adr0043_bootstrap_loss_control --commit \
  --evidence /app/data/adr0043_lc_bootstrap_commit.json
```

Exit codes: `0` success · `2` refusal (evidence still written).

## After the bootstrap

Per the owner's 2026-07-28 ruling: do **not** reuse the July-28 baseline. On a new eligible
session, run `adr0043_session_open` (which now reports and gates on the persisted loss-control
state as step `6b_loss_control`), capture that session's baseline, recompute binding reachability,
return a new frozen execution package, and obtain new explicit Phase-0 authorization.
