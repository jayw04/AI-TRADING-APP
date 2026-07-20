# ADR 0042 — Verified Risk-Reducing Orders and the Durable Decision Ledger

| Field | Value |
|---|---|
| Date | 2026-07-14 (decision); formal doc reconstructed + accepted 2026-07-20 |
| Status | **Accepted** (rev 2 accepted at commit `bc994bb`; deployed; canary GREEN 2026-07-17; formal doc reviewed and accepted by owner 2026-07-20) |
| Phase | Cross-phase (risk engine; fast-track fix for the 2026-07-13 incident) |
| Supersedes | — |
| Related | 0002 (single OrderRouter), 0004 circuit-breaker-hard-halt, 0004 daily-loss-from-start-of-day-baseline, 0038 (reducing-exits exempt from gross gate), 0039 (reducing-exits exempt from cooldown), 0043 (loss-control architecture — durable successor, Draft) |

> **Provenance note.** This ADR was written retroactively (2026-07-20) to formalize a decision that
> was made, reviewed (rev 1 `91abae2` → rev 2 accepted `bc994bb`), implemented, and deployed without a
> committed ADR file. The implementing code is on `origin/main` (present at commit `a080889`); it is
> **not** on the `research/mr002-preregistration` working branch where this doc is being authored. All
> file/line references below are as of `a080889`. Where the on-disk state diverges from this doc, the
> code is authoritative and this doc should be corrected — not the reverse.

## Context

On 2026-07-13 the daily-loss and circuit-breaker gates rejected the momentum-portfolio book's own
*risk-reducing* sells. Under lock the book stayed ~98% invested through a −7% day; ~$2,000 (≈36%) of
the loss accrued **after** the control fired. The gates rejected *every* order regardless of risk
effect: the `is_reducing_sell` exemption existed for the gross-exposure gate (ADR 0038) and the
cooldown (ADR 0039), but the loss gates were missed. The control locked in the exposure it exists to
cap. (Incident: `docs/incidents/2026-07-13-risk-gate-traps-risk-CLOSED.md`.)

A durable redesign of the loss controls was owed (that is ADR 0043), but the trap was live on paper and
needed an immediate, correct fix. This ADR is that **fast-track**: make the loss controls *non-trapping*
without weakening them, and make every risk decision durably auditable — deliberately scoped to the
verification-and-record property, leaving the control *architecture* to ADR 0043.

Owner rulings that constrain the fix: do not bypass; do not raise `max_daily_loss` ("an audited
parameter change is still functionally a bypass when its purpose is to defeat the active protection
condition"); classify by **projected risk effect, never by the BUY/SELL verb** (a sell can open a short;
a buy can close one).

## Decision

Under a daily-loss lock or a tripped circuit breaker, the engine permits an order **only if it can
verify the order reduces risk**, classified by projected risk effect; risk-increasing and
risk-neutral orders remain refused; and **every decision — ALLOW or REJECT — is recorded in an
append-only ledger**. Concretely:

1. **Classify by projected risk effect, not by verb** (§ classifier). A pure function maps
   (account snapshot, proposed action) → one of `RISK_REDUCING | RISK_INCREASING | RISK_NEUTRAL |
   INDETERMINATE` with a `Decision` of `ALLOW | REJECT | FAIL_CLOSED` and a reason code. Only a
   `RISK_REDUCING` + `ALLOW` result is a *verified reduction*.
2. **Both loss gates consult the exemption** (engine steps 9 daily-loss and 13 breaker). The breach
   still trips the lock (a historical fact), but the gate rejects only after the shared exemption
   helper returns "not a verified reduction." The two gates call **one** shared classifier/service —
   no per-gate re-implementation (that drift is exactly the ADR 0038 miss).
3. **Causally-complete snapshot, no staleness allowance** (§A). Classification runs against a live
   broker read whose cursor is verified current; a stale/incomplete snapshot yields
   `INDETERMINATE`/`FAIL_CLOSED`, never a guess. A pre-submission consistency check re-classifies once
   if state moved rather than reusing a prior decision.
4. **Cancellation is not automatically reducing** (§B). Cancelling a protective reduction is
   `RISK_INCREASING`; cancelling a risk-increasing resting order is reducing. The verb "cancel" carries
   no exemption.
5. **Source-neutral** (§C). STRATEGY, MANUAL, and AGENT orders are classified by identical code;
   `source_type` is recorded for audit, never for privilege.
6. **Reservations + a database-atomic reducible-capacity claim** (§D). Concurrent reducing orders
   cannot both be admitted against the same shares: capacity is claimed by a single conditional SQL
   UPDATE (compare-and-swap), not by trusting the broker as a backstop.
7. **Append-only decision ledger** (§7). Table `risk_decisions` records each decision with the full
   causal context needed to replay it; a retry references the prior row via `supersedes_id` and never
   overwrites. The ledger is **separate from the hash-chained `audit_log`** — no new `AuditAction`
   values were introduced.

**Invariant established:** a loss control must never block an order the engine *verifies* to be
risk-reducing, and must never admit one it cannot verify. Risk-increasing orders remain refused.

## Rationale

- **Why classify by projected effect, not verb?** The owner ruling is grounded in the failure: the
  strategy's *sells* were the de-risking action the gate blocked. A verb-based rule is both unsafe
  (a sell can open a short) and was the proximate trap. The classifier reasons over position + side +
  projected gross/leverage, and demands a price only on the permitted-reduction path — a refinement the
  2026-07-13 canary itself forced after an earlier version mislabeled plainly-classifiable orders
  `NO_PRICE`.
- **Why one shared classifier for both gates?** ADR 0038 gave the exemption to the gross gate only; the
  loss gates were missed *because the logic was not shared*. A single `classify()` behind a single
  service, called by both gates, makes the miss structurally impossible to repeat.
- **Why no staleness allowance (§A)?** "The order path may not act on a position it is not sure of."
  A "N-seconds-old is fine" cache is exactly how a de-risk can be computed against a phantom position.
  Fail-closed to `INDETERMINATE` is safe; a wrong ALLOW is not.
- **Why a database-atomic claim (§D)?** On 2026-07-14 two independent Python processes each read
  `reserved=0` and each received ALLOW for the same 183 shares (KOKU); only the broker stopped the
  second. "The broker is not a safety mechanism." Correctness must hold across processes, so the claim
  is a conditional UPDATE that succeeds iff `reserved_qty + qty <= reducible_capacity_qty`; the
  per-account `asyncio.Lock` is retained only as a contention optimization, not for correctness.
- **Why an append-only ledger separate from `audit_log` (§7)?** The incident's durable lesson was that
  the `orders` table records only orders *accepted for submission* and is purged — it is silent on
  everything refused. Refusals are the safety-critical events. The ledger records *what was proposed
  and why it was refused* with replayable context (`risk_policy_version`, state hashes, cursors). It is
  kept separate from `audit_log` because it is high-volume, decision-level, and replay-oriented rather
  than the consequential-action chain.
- **Trade-offs accepted:** every locked-mode order now does a live broker read + a classify + a ledger
  write (latency and I/O on the refusal path); the ledger grows unboundedly (retention is owed); and a
  fail-closed classifier will refuse a *genuine* reduction when it cannot verify state — friction that
  is the safe direction but is real.

## Implementation notes

- **Classifier — `apps/backend/app/risk/risk_effect.py`** (pure, no I/O). Enums `RiskEffect`,
  `Decision`, `RiskEffectReason`, `ActionType`; `RISK_POLICY_VERSION = "0042.1"` (recorded on every
  ledger row for replay). `classify(snap, action) -> RiskEffectDecision`;
  `available_reducible_quantity(snap, symbol) = current_long − open_reducing_sell_qty −
  reserved_reducing_qty`, floored at 0; `RiskEffectDecision.is_verified_reduction = (RISK_REDUCING and
  ALLOW)`. **Two distinct capacity reason codes, kept distinct on purpose:**
  `EXCEEDS_REDUCIBLE_QUANTITY` (static snapshot check → `INDETERMINATE`/fail-closed) vs
  `EXCEEDS_REDUCIBLE_CAPACITY` (lost a concurrent atomic claim → `RISK_INCREASING`/`REJECT`,
  determinate).
- **Engine wiring — `apps/backend/app/risk/engine.py`.** Step 9 (daily loss, ~340–376) and step 13
  (breaker, ~426–452) both call `_permits_verified_reduction(...)` (~571–658); a per-evaluation
  `reduction_cache` ensures an order is classified/reserved **exactly once** even though step 9 trips
  the lock that step 13 then observes. Lock definitions in `apps/backend/app/risk/lock_state.py`
  (`LOCK_UNLOCKED|LOCK_DAILY_LOSS|LOCK_BREAKER`; breaker checked before daily-loss; `lock_trigger`
  [historical] distinguished from `permitted_effect` [forward-looking]).
- **Snapshot — `apps/backend/app/risk/account_snapshot.py`** `fetch_snapshot(...)`: always a live
  broker read; `broker_cursor` vs `observed_cursor` causality → INDETERMINATE/FAIL_CLOSED if behind.
- **Write API — `apps/backend/app/risk/decision_service.py` `RiskDecisionService`:** `decide(...)`
  (one ledger row per call, incl. rejections; fetch snapshot → classify → on verified reduction refresh
  + atomically claim capacity → insert ledger + reservation → commit), `confirm_unchanged_or_reclassify`,
  `release_reservation`, `settle_reservation_for_order` (FILLED→CONSUMED else RELEASED),
  `reap_orphaned_reservations(older_than_seconds=300)`, module `run_reservation_reaper_pass(...)`, and
  `permits_while_locked(result)` (locked-mode matrix). The atomic claim `_claim_capacity(...)`:
  ```sql
  UPDATE risk_capacity_state
     SET reserved_qty = reserved_qty + :qty, state_version = state_version + 1
   WHERE account_id = :account_id AND symbol = :symbol
     AND snapshot_version = :expected_version
     AND reserved_qty + :qty <= reducible_capacity_qty
  ```
  success iff exactly one row updated; else `_deny_for_capacity` → REJECT `EXCEEDS_REDUCIBLE_CAPACITY`.
- **Schema (3 tables) + migration chain** `d3f6a1c8b2e4` (strategy_slot_claims) → **`e5b2c9d7f1a3`**
  `risk_decisions` → **`f7a3d1e9c5b2`** `risk_reservations` → **`a4c7e1f9d2b8`** `risk_capacity_state`
  (also `ADD COLUMN capacity_state_version` on `risk_decisions`). Single head.
  - `risk_decisions` (`app/db/models/risk_decision.py`) — append-only; key columns: `account_id`,
    `strategy_id`, `source_type`, `action_type`, `symbol/side/qty`, `lock_state`, `lock_reason`,
    `daily_pnl`, `risk_policy_version`, `before_state_hash`, `projected_after_state_hash`,
    `broker_cursor`, `position_qty_before/after`, `gross_exposure_before/after`,
    `leverage_before/after`, `available_reducible_qty`, `risk_effect`, `decision`, `reason_codes`
    (JSON), `decided_at`, `correlation_id`, `supersedes_id` (self-FK), `retry_generation`,
    `capacity_state_version`. Indexes on `(account_id, decided_at)` and `(correlation_id)`.
  - `risk_reservations` (`app/db/models/risk_reservation.py`) — `HELD|CONSUMED|RELEASED`; open index
    `(account_id, symbol, state)`.
  - `risk_capacity_state` (`app/db/models/risk_capacity_state.py`) — `reserved_qty` authoritative
    accumulator (never recomputed), `state_version` monotonic, `snapshot_version`; unique
    `(account_id, symbol)` (identity only; the aggregate invariant is enforced by the conditional
    UPDATE, not the index).
- **No new `AuditAction` values.** The durable record is the `risk_decisions` ledger. Step 9 still emits
  the pre-existing `CIRCUIT_BREAKER_TRIPPED` audit via `CircuitBreakerService.trip()`.
- **Canary (live-paper proof).** In-repo `apps/backend/scripts/adr0042_*.py`: `adr0042_canary_lib.py`
  (harness, PROTECTED-symbol enforcement, cap-derived sizing — never moves limits),
  `adr0042_churn_to_breach.py` (pre-lock: reach the frozen cap via real realized loss),
  `adr0042_canary_run.py` (post-lock assertion sequence, run once),
  `adr0042_concurrency_worker.py` (second OS process for the cross-process claim assertion),
  `adr0042_make_manifest.py` / `adr0042_preflight.py` (provenance manifest + in-container hash
  verification). Manifest `adr0042_manifest.json`; doc `docs/implementation/ADR0042_Canary_Manifest_v1.0.md`.
  ⚠ The orchestration wrappers `adr0042_orchestrate.sh`, `adr0042_selfheal.sh`, and the runtime
  checkpoint `adr0042_canary_state.json` live **on the deployment box only** and are absent from git —
  they cannot be cited by repo path.

## Consequences

- **Positive.** The exact 07-13 trap is fixed on live paper (canary GREEN, non-vacuous: under a tripped
  breaker `SELL 50 F` = ALLOW/`VERIFIED_REDUCTION` while `BUY 1 F` still REJECTs and `max_daily_loss`
  is unmoved). Refusals are now durably recorded and replayable. Cross-process double-admission is
  impossible by construction. The exemption cannot silently skip a gate (shared classifier).
- **Negative.** Locked-mode orders now require a live broker read + classify + ledger write (latency/IO
  on the refusal path). The ledger grows unboundedly — **retention/rotation is owed.** A fail-closed
  classifier refuses genuine reductions when it cannot verify state (safe, but real friction). Three
  new tables + a migration chain to maintain.
- **Neutral.** The breaker's hard-halt semantics (ADR 0004) are unchanged; this ADR changes *what a
  locked account may still do*, not *that* a lock exists. The control *architecture* (separation,
  persisted baseline, recovery) is deliberately untouched — that is ADR 0043.

## Alternatives considered (not chosen)

1. **Raise `max_daily_loss` / widen the breaker to let the sells through.** Rejected on owner ruling —
   functionally a bypass; also admits risk-increasing orders indiscriminately.
2. **Verb-based exemption ("allow all SELLs under lock").** Rejected: a sell can open a short and a buy
   can close one; unsafe and imprecise.
3. **Cache the account snapshot with an age tolerance.** Rejected (§A): a stale snapshot is how a
   de-risk gets computed against a phantom position. Fail-closed instead.
4. **In-memory per-account lock as the correctness mechanism.** Rejected (§D): does not hold across OS
   processes — the 2026-07-14 KOKU double-ALLOW proved it. Kept only as a contention optimization.
5. **Record decisions in `audit_log`.** Rejected: decision-level volume, replay orientation, and the
   need to record every refusal make it a poor fit for the consequential-action hash chain; a dedicated
   append-only ledger is the right home.

## Re-evaluation triggers

- A locked account is again unable to de-risk through the product path (the invariant regressed).
- A verified-reduction classification is later shown to have admitted a risk-*increasing* order (the
  classifier is wrong).
- A concurrent double-admission occurs despite §D (the atomic claim failed).
- The `risk_decisions` ledger growth becomes an operational problem before a retention policy ships.
- ADR 0043 lands and subsumes parts of this fast-track — at which point the overlapping sections here
  should be marked superseded rather than left as the governing text.
