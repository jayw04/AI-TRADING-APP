# ADR 0043 — Canary Manifest v1.0

**Purpose:** the paper-account verification required before ADR 0043's loss-control state machine is
trusted in `ENFORCE` on any book that has a mandate.
**Status:** Frozen (pre-run). Parameters below are recorded BEFORE the run and are not changed mid-run.
**Mirrors:** `ADR0042_Canary_Manifest_v1.0.md` — same account, same discipline, different property.

> **This is the permanent risk-engine verification account.** It is not converted into a strategy
> account after the canary. A dedicated, controlled account is the only way to re-verify a risk gate
> without contaminating a book that has a mandate. (See the `acct3_canary_artifact_state` note.)

---

## 1. The account

| Field | Value |
|---|---|
| User | 3 |
| Account | 3 — `Alpaca Paper (Conservative)` |
| Baseline positions | the protected legs `F:500, MSFT:20` (the reduction targets) ← precondition |
| Loss-control state | a durable `REDUCTION_ONLY_*` row in `risk_loss_control_state` ← precondition |
| Loss-control mode | `WORKBENCH_LOSS_CONTROL_MODE=ENFORCE` ← precondition (refused otherwise) |

> **Equity is NOT a precondition** (as in 0042): reaching a breach costs real money by design, so the
> account's equity drifts. The harness checks *state* (reduction-only lock / legs present / ENFORCE),
> never a specific equity. Do **not** "reset the balance" — an Alpaca paper reset rotates the API keys.

---

## 2. What it proves (and what it deliberately does not)

**Proves — the loss-control state machine is authoritative in `ENFORCE`:**

| # | Assertion | Property (all mandatory for GREEN) |
|---|---|---|
| A1 | `state_authoritative` | the account is governed by a durable `REDUCTION_ONLY_*` **state row**, not merely the breaker column |
| A2 | `verified_reduction_allowed` | a verified risk-reducing SELL of a protected leg is **ADMITTED** under the lock (ADR 0042 preserved — the gate never traps de-risking) |
| A3 | `new_risk_refused` | a new-risk BUY is **REJECTED** with `LOSS_CONTROL_STOP` and leaves a durable event/ledger trail |
| A4 | `reached_recovery_cooldown` | the recovery drove the account **all the way into `RECOVERY_COOLDOWN`** with a full PASS: aggregate `PASS`, a committed `PREFLIGHT_PASS` event, parent preflight `PASSED`, and **exactly 12 persisted PASS checks**. Merely entering `RECOVERY_PREFLIGHT`, or a preflight `FAIL`/`INCOMPLETE`, is a **RED** canary — not a vacuous pass. |
| A5 | `evaluator_holds` | the cooldown evaluator is **actually invoked** and returns **exactly `HOLD`** (no transition, still in cooldown), with **no `NORMAL` and no `COOLDOWN_COMPLETE` at any point** in the run. A `NO_OP`, a regress to `INTEGRITY_STOP`, or a re-arm to `NORMAL` is RED. |

**Does NOT prove — and refuses to fake:**

- **A completed timed re-arm.** The §D6 dwell tiers (30 min rate/velocity, until-next-session daily
  loss, until-manual-repair integrity) cannot be driven to completion inside one live run. The
  harness asserts the account *enters* cooldown and that the evaluator *holds*; it **never** injects
  fake elapsed time / a fake session boundary to force a `NORMAL` (that is the same class of lie as
  moving `max_daily_loss` to meet the account). The re-arm-to-`NORMAL` path is covered exhaustively by
  the deterministic unit suite (`test_loss_control_cooldown.py`), not by this live canary.

---

## 3. Preconditions — REFUSED, not worked around

`adr0043_canary_run.py` raises `CanaryRefused` (exit 2) rather than proceed if any is absent:

1. `WORKBENCH_LOSS_CONTROL_MODE != ENFORCE` — under OFF/SHADOW the machine is not authoritative, so
   the run would assert nothing.
2. The account is not in a reduction-only loss-control state (**measured** from the state row).
3. A protected leg is missing (a locked account cannot buy it back — the reduction assertion could
   not run).

The limits are **never** relaxed to manufacture a breach (`admissible_shares` is bounded by the
account's own caps; `BreachUnreachable` is raised rather than lowering a limit).

---

## 4. Running it (on the box, never the laptop)

```
ssh workbench
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec -e WORKBENCH_LOSS_CONTROL_MODE=ENFORCE \
       -e ADR0043_COMMIT_SHA=$(git rev-parse HEAD) backend \
  python -m scripts.adr0043_canary_run
```

- **Single-instance** (lock file) — two concurrent harnesses are the 2026-07-14 double-reservation
  condition; the second is refused.
- **Step-level resumable + idempotent, crash-window-closed** — A2/A3 submit with a **deterministic
  `client_order_id`** (`adr0043-<run-id>-a2|a3`) that the router forwards to the broker, so even a
  crash *after* the order is accepted but *before* the checkpoint is written cannot create a second
  order: on retry the harness finds the existing order **by that identity** (local first, then the
  broker) and rebinds instead of submitting. A4 reuses a stable recovery idempotency key (the
  recovery service dedupes). An identity that exists with **contradicting** fields is **refused**, not
  restarted. A **completed** checkpoint is handled **before** the mutable reduction-only/legs
  preconditions (after a full run the account is in `RECOVERY_COOLDOWN`, not reduction-only): it
  verifies the durable A2/A3 orders, the 12/12 preflight PASS, the recorded `HOLD`, and the evidence
  file's SHA-256 against the checkpoint, then returns the prior gate with **zero** side effects — or
  refuses if any of that contradicts durable evidence.
- **Evidence** — `/app/data/adr0043_evidence_enforce.json`, sha256 printed; every order carries a
  pre-order snapshot of the durable state, and every refusal is verified auditable.

The harness's own honesty invariants run in CI (`tests/risk/test_adr0043_canary_harness.py`) — legs
protected, lock measured not assumed, limits never relaxed, an empty/failed assertion set never
reads PASS, single-instance enforced, ENFORCE required.

---

## 5. After a GREEN run

A GREEN `ENFORCE` canary is the safety net before any environment flips `WORKBENCH_LOSS_CONTROL_MODE`
to `ENFORCE` by default. It is also the point at which the **acct-3 reclaim boundary** is reached: once
ADR 0043 is built (PRs 1–8) and this canary has actually run GREEN, acct-3 may be reclaimed (flatten
the legs, reset the breaker via the audited flow, restore to a clean duplicate) — see the
`acct3_canary_artifact_state` note. Until the GREEN run, acct-3 stays frozen.
