# ADR 0043 — Live ENFORCE Canary Runbook (v1.0)

> **Governing status (keep stated until GREEN evidence exists):**
> - **ADR-0043 code implementation: COMPLETE** (PRs 1–8 merged; main `c8b3ac2`).
> - **ADR-0043 live operational validation: PENDING.**
> - **Account 3: NOT RECLAIMABLE.**
>
> The reclaim boundary is reached **only** after a fresh-box live ENFORCE canary produces **GREEN**
> evidence with its recorded SHA-256, independently countersigned. Do not collapse the two milestones.

**Frozen contract:** `docs/implementation/ADR0043_Canary_Manifest_v1.0.md`.
**Required source revision:** `c8b3ac24b839d7b19c40979a9e4be859151dbab7`.
**Account / user:** 3. **Protected legs:** `F:500`, `MSFT:20`. **Mode:** `WORKBENCH_LOSS_CONTROL_MODE=ENFORCE`.

The live canary (`scripts/adr0043_canary_run.py`) is **assertion-only**: it requires ENFORCE, a durable
`REDUCTION_ONLY_*` state row, and the protected legs; otherwise it **refuses**. It never establishes the
lock, never fakes elapsed time or a session boundary, and never relaxes limits.

**The overriding rule:** never change limits, authority configuration, trip-cause classification,
session baseline, positions, or durable state to make any check pass. If the environment does not
legitimately produce a lock or a GREEN, that is a real result to preserve and explain — not a defect to
engineer around.

## "Fresh box" — definition

A **fresh box** is a **newly provisioned EC2 runtime deployed for this validation attempt, before
baseline capture or loss generation begins**. It is **not** a box provisioned *after* the lock was
created somewhere else.

## Runtime-continuity invariant (load-bearing)

> **The same fresh EC2 instance, backend image, configuration, database, broker credentials, and
> session baseline must be used continuously from baseline capture through Phase 0, the formal canary,
> evidence extraction, and countersignature. No reprovision, database copy, container-image replacement,
> or configuration change is permitted inside that boundary.**

This is a consequence of the deployment architecture: the application database is host-local SQLite
(`./data/workbench.sqlite` on the Compose host), **not** a shared remote DB. So Phase 0 must establish
the durable lock **on the very box that will run the canary** — provisioning happens **first** (Phase
A0–A4), then Phase 0 on that same runtime, then the canary on that same runtime. Establishing the lock on
a predecessor instance and provisioning "fresh" afterward would either leave the canary with no lock or
force an ungoverned database copy that destroys the fresh-and-independent provenance claim.

The one permitted exception: a **normal container restart** *only* when required to enable baseline
capture, and *only* **before** the baseline is captured — with the final container identity and
configuration recorded afterward.

---

## Milestone sequence

| Phase | Purpose |
|---|---|
| **A0–A4** | **Fresh-box provision and immutable runtime provenance** (this comes FIRST) |
| 0A–0G | Establish the eligible **daily-loss** lock **on that same runtime** |
| **B–K** | Formal canary, evidence, verification, and countersignature (same runtime) |
| — | Countersigned GREEN → **then** account-3 governance / reclaim decision |

A **Phase 0 failure is a setup-readiness failure, not an ADR-0043 canary failure** (the formal canary has
not begun). Preserve and explain it; never work around it by changing limits, authority, cause, baseline,
positions, or state.

---

# Phase A — Fresh box and immutable runtime provenance (FIRST)

## A0. Establish the operator run identity

```
export ADR0043_RUN_ID="adr0043-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "evidence/$ADR0043_RUN_ID"
export EVIDENCE_DIR="$PWD/evidence/$ADR0043_RUN_ID"
printf '%s\n' \
  "run_id=$ADR0043_RUN_ID" \
  "required_commit=c8b3ac24b839d7b19c40979a9e4be859151dbab7" \
  "account_id=3" "user_id=3" "required_mode=ENFORCE" \
  "started_utc=$(date -u +%FT%TZ)" > "$EVIDENCE_DIR/run_identity.txt"
```

> **Operator run id vs harness run id — do NOT assert they match.** `ADR0043_RUN_ID` labels the external
> evidence package. The harness checkpoint generates and persists its **own** internal `run_id`, and the
> deterministic A2/A3 `client_order_id` values derive from that harness run id. The countersignature
> preserves **both** (`operator_evidence_run_id`, `harness_checkpoint_run_id`, `a2_client_order_id`,
> `a3_client_order_id`). Do not reuse a run identity for a different EC2 instance or a reset account.

## A1. Provision the fresh EC2 box

Provision a **new** EC2 instance through the approved infrastructure/deployment process for the paper
stack. The requirement is not a particular size — it is that the runtime be **new and attributable**: no
reused checkpoint/lock, no stale evidence, no unreviewed local code, no manually edited DB, no hidden
harness process. **Never run the canary from the laptop.**

Record instance identity immediately (`hostname`, `boot_id`, `kernel`, and — where instance metadata is
enabled — `instance_id`, `ami_id`, `instance_type`) into `$EVIDENCE_DIR/instance_identity.txt`. A metadata
failure is **documented, not bypassed**.

## A2. Deploy exactly `c8b3ac2`

```
git fetch --prune origin && git checkout main
git reset --hard c8b3ac24b839d7b19c40979a9e4be859151dbab7 && git clean -fd
git rev-parse HEAD          # must equal c8b3ac2…; tree must be clean
```

Capture `HEAD` + `git status --porcelain=v1` + `git show -s --format=fuller HEAD` to
`$EVIDENCE_DIR/git_state.txt`. **STOP** if HEAD differs, the tree is dirty, there are unreviewed
deployment overrides, or the running container later reports code inconsistent with this revision.

## A3. Record instance / image / config / migration provenance

`COMPOSE="sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml"`.

- **Compose/image:** `$COMPOSE version`, `config --services`, `config --images`, `sha256sum
  docker-compose.yml docker-compose.prod.yml`, and the **actual** running container image ids (`docker
  inspect … {{.Config.Image}} {{.Image}}`), especially the backend (`image_name`, `image_id`, `created`,
  `started`, `restart_count`). If the image is in ECR with a repository **digest**, preserve that digest —
  never rely on a mutable tag like `latest`.
- **Config:** hash the source-controlled files plus a **redacted** env representation (mask
  `SECRET|TOKEN|PASSWORD|KEY|CREDENTIAL`); manually inspect the redacted file before copying; **no
  plaintext credentials in the evidence package**.
- **Alembic:** `$COMPOSE exec -T backend alembic heads` (**exactly one `(head)`**) and `alembic current`
  (**must equal the repository head**). **STOP** on >1 head, a DB behind, an unknown revision, or any
  proposal to `alembic stamp head` merely to pass (valid only when the schema is independently known to
  match, never to manufacture readiness).

## A4. Confirm one backend and clean canary-artifact paths

- Exactly **one** intended backend container; **no** `scripts.adr0043_canary_run` process running.
- Inspect (EXISTS/ABSENT + `ls -l` + `sha256sum`) `/app/data/adr0043_canary_state.json`,
  `/app/data/adr0043_canary.lock`, `/app/data/adr0043_evidence_enforce.json` — a fresh run expects these
  **absent**. **Do not auto-delete a lock or checkpoint.** If one exists, inspect PID/liveness, container
  restart time/logs, and whether it is genuinely resumable, and **document the decision**. A contradictory
  checkpoint should produce a **refusal** — a valid safety outcome, not something to work around.

> **Expected at this point:** the fresh backend syncs account 3's broker state (the `F`/`MSFT` positions,
> account status) into its fresh local DB, and the loss-control state is `NORMAL` (a fresh DB has no
> prior lock). That is correct — the durable `REDUCTION_ONLY_*` lock is established in **Phase 0 below, on
> this same box**, not carried over from anywhere.

---

## Continuity record — Phase 0 start

Capture (and store in `$EVIDENCE_DIR/continuity_phase0.txt`): `instance_id`, `boot_id`, backend
container/image digest, git commit, configuration checksum, **database file identity + SHA-256**, Alembic
current revision, broker account identity, session baseline id/version (once 0A completes).

The **immutable** items — commit, image digest, configuration checksum — must be **identical** to the
formal-canary-start record. The **database SHA-256 will legitimately change** as Phase 0 writes orders and
state events, so it is **recorded at boundaries, not required equal**.

---

# Phase 0 — Establish a canary-eligible daily-loss lock (on the same fresh box)

## 0C-prime. Freeze the recovery-authority path first

For the first ADR-0043 live validation:

- **Trip origin:** `DAILY_LOSS` · **Expected locked state:** `REDUCTION_ONLY_DAILY_LOSS`
- **Recovery requester:** user 3, the account owner · **Additional operator authority:** *not required*.

The canary requests recovery as the owner (user 3). Per the authority matrix, the owner can self-authorize
a `PREFLIGHT_PASS` **only** for a daily-loss origin; a `REDUCTION_ONLY_BREAKER` origin lands
`AUTHORIZATION_REQUIRED` and the owner's `approve()` is refused → **A4 is RED**.

- **Do NOT** add user 3 to `WORKBENCH_RISK_OPERATOR_USER_IDS` merely to help A4 pass — that changes the
  authority configuration under test.
- **If account 3 enters `REDUCTION_ONLY_BREAKER`** instead of `REDUCTION_ONLY_DAILY_LOSS`, **STOP** and
  classify the setup as unsuitable for this GREEN run. Do not rewrite the trip cause or durable state.
  Preserve the breaker-origin result as setup evidence; start a separately governed attempt only after
  identifying why the intended daily-loss path did not govern the trip.

## 0A. Enable + capture the authoritative session baseline (before session activity, on this box)

The baseline must be captured by **this box's** production runtime — the one that will process the breach
and run the canary — **not** by a predecessor instance.

1. Identify the deployed baseline-capture setting; confirm it is enabled for the backend that will handle
   account 3. If it is a startup-time setting, restart the container through the approved procedure
   **before** the baseline is captured (the one permitted restart), then re-record the final container
   identity + configuration. Record the configuration checksum.
2. Verify the baseline is captured for the **current** trading session and is immutable after capture.

A valid baseline record contains at least: `account_id=3`, session/trading date = current session,
baseline status = valid/authoritative, capture timestamp, source/provenance, the required equity/values,
and immutability/version evidence.

**STOP** — do not begin loss generation — if: capture is disabled; the baseline row is missing; the
baseline belongs to a previous session; provenance is invalid; it was manually inserted; it was modified
after session activity began; or two competing baselines exist. **Never "repair" the baseline after the
breach** — that would invalidate both the lock provenance and the recovery preflight.

## 0B. Reconcile account 3 before the breach

Read-only, broker vs the freshly-synced DB: broker positions/open-orders/recent-fills/account-status/
buying-power/equity/market-clock vs DB positions/open-orders/reservations/account-state/loss-control-state/
breaker-status/latest-control-event-sequence/session-baseline/limits. **Required:** no unexplained DB-only
or broker-only position; no stale open order or reservation; no `F`/`MSFT` quantity mismatch; no pending
recovery workflow; no unexplained state transition. Do not buy/adjust positions to match the frozen
baseline unless that establishment is an already-governed part of setup; if the account no longer matches,
**revise and re-freeze the manifest through review** — do not silently restore it.

## 0C. Freeze the limits (and provenance)

Export the complete effective limit set **before** any loss (`max_daily_loss`, `max_position_qty`,
`max_position_notional`, `max_gross_exposure`, `max_orders_per_day`, rate limits, velocity thresholds,
breaker thresholds, all overrides). Hash it. From here through countersignature,
`limits_before_sha256 == limits_after_sha256`. An unreachable breach is unreachable — **never** solved by
lowering controls.

## 0D. Generate a real daily loss through sanctioned orders (on this box)

A loss through the sanctioned order path that crosses the daily-loss threshold and drives
`NORMAL → REDUCTION_ONLY_DAILY_LOSS`. Every setup order goes through **`OrderRouter → RiskEngine → broker
adapter`** — no console trades, no direct API scripts outside the app path, no DB position edits, no
manual account-state mutation. Document the plan and **reserve order-count / rate / exposure / reservation
capacity for A2/A3 + the recovery path + reconciliation calls**.

**Avoid the wrong trip class.** After every cycle monitor `day_change`, `max_daily_loss`, durable state,
latest trip cause, breaker status, order count, rate/velocity metrics, open orders, reservations. **If
rate/velocity/breaker protection trips first: STOP** — do not continue, reclassify, or add operator
authority; preserve the setup evidence (that attempt cannot establish the owner-authorized A4 path). For
every order preserve: client order id; request; pre-order state; risk decision; broker response; fill;
post-fill state; resulting control events.

## 0E. Verify the correct lock, then STOP

Complete only when **all** hold: `day_change <= -effective max_daily_loss`; durable state
`= REDUCTION_ONLY_DAILY_LOSS`; trip cause `= DAILY_LOSS`; a state-transition event committed;
`state_version` advanced; state/event sequence consistent; new-risk refused under the lock; verified
reductions potentially admissible. Do not rely only on the legacy daily-loss value or breaker timestamp.
Once durable, **stop all setup trading** — do not test extra new-risk orders, run recovery, invoke the
evaluator, wait for/fake a session, alter positions, clear the breaker, or modify the baseline.

## 0F. Read-only twelve-check readiness assessment (after the lock exists)

Establishes only that the environment is **capable** of a meaningful run — **not** a substitute for A4. It
**reads** state, reconciles broker/DB facts, verifies configuration, reports likely blockers. It must
**not** create a preflight parent, approve recovery, move state, clear orders/reservations by direct
writes, or manufacture PASS rows — doing so would **consume the real A4 idempotency identity** and
contaminate the canary.

The registry is **dependency-ordered**; a dependent whose prerequisite did not pass is
`INCOMPLETE (BLOCKED_BY_<check>)`, **not** an independent `FAIL`; the aggregate is fail-closed:

| # | Check (implementation name) | Phase 0 status | Interpretation |
|---|---|---|---|
| 1 | `state_known_and_recoverable` | Confirmable | state recognized and eligible for recovery |
| 2 | `recovery_origin_proven` | **Pending — A4 only** | requires the committed `RECOVERY_REQUEST` event; cannot exist in Phase 0 |
| 3 | `broker_reachable` | Confirmable, **gating** | failure **blocks** checks 4–7 |
| 4 | `broker_account_active` | Confirmable iff broker reachable | else `INCOMPLETE: BLOCKED_BY_broker_reachable` |
| 5 | `positions_reconcile` | Confirmable iff broker reachable | else blocked |
| 6 | `open_orders_reconcile` | Confirmable iff broker reachable | else blocked |
| 7 | `reservations_reconcile` | Confirmable iff broker reachable | else blocked |
| 8 | `session_baseline_valid` | Confirmable, **gating** | must pass before loss generation; gates check 9 |
| 9 | `daily_loss_recomputed` | Confirmable iff baseline valid | else `INCOMPLETE: BLOCKED_BY_session_baseline_valid` |
| 10 | `trip_cause_classified` | Confirmable after lock | must resolve to `DAILY_LOSS` |
| 11 | `control_state_consistent` | **Partially** confirmable | full recovery-transition consistency proven at A4 (for a daily-loss origin it does NOT require a tripped-breaker column) |
| 12 | `no_unresolved_integrity_condition` | Confirmable | no unresolved integrity condition present |

Checks 2 and the transition portion of 11 remain **pending until A4**; the read-only inspection confirms
only the *inputs* (baseline present, positions reconcile, trip cause = `DAILY_LOSS`), never the transition.

## 0G. Freeze the formal-canary start boundary

Record the Phase 0 endpoint — **`READY_FOR_ADR0043_CANARY`** — only when: state
`= REDUCTION_ONLY_DAILY_LOSS`; trip cause `= DAILY_LOSS`; baseline valid/authoritative; `F`/`MSFT` legs
present; open orders + reservations reconciled; limits hash unchanged; owner self-recovery permitted;
checkpoint/evidence paths clean.

---

## Continuity record — formal-canary start

Re-capture the same fields as the Phase-0-start record and **compare**: `instance_id` / `boot_id` /
backend image digest / git commit / configuration checksum / broker account identity / session baseline
id/version must be **identical** (same runtime, no reprovision/image-swap/config-change). Record the
current database SHA-256 (expected different from Phase-0-start — orders/events were written; recorded, not
required equal). Store as `$EVIDENCE_DIR/continuity_canary.txt`. **STOP** if any immutable item changed.

---

# Formal canary — Phases B–K (same box, container, image, database)

## B. ENFORCE for the one execution only

The canary command injects `WORKBENCH_LOSS_CONTROL_MODE=ENFORCE` into the single execution; the manifest
requires refusal under OFF/SHADOW. Confirm the command receives exactly `WORKBENCH_LOSS_CONTROL_MODE=ENFORCE`
and `ADR0043_COMMIT_SHA=c8b3ac2…`. **Do not** globally flip every environment to ENFORCE unless separately
reviewed.

## C. Immediate pre-canary confirmation (read-only)

Confirm, read-only: `risk_loss_control_state` for account 3 is now `REDUCTION_ONLY_DAILY_LOSS` with
`state_version` present; `F ≥ 500`, `MSFT ≥ 20` at the broker. **Never** run `UPDATE risk_loss_control_state`,
`UPDATE risk_limits`, `UPDATE accounts SET circuit_breaker_tripped_at`, or `DELETE FROM risk_control_events`
— any need for such a change means the run is not valid. **Do not buy back a missing leg** (a locked account
cannot legitimately manufacture the precondition — the harness treats it as a refusal).

## D. Start full evidence capture

Record a pre-run UTC boundary and full backend logs (`_before`); record current **max ids** for the
decision ledger, control events, recovery preflights, preflight checks, orders (run anchors). Start
`script -q -f "/tmp/${ADR0043_RUN_ID}_terminal.log"`; inside it print `date -u`, `hostname`,
`git rev-parse HEAD`, `$COMPOSE ps`. **Do not edit the transcript; hash the original.**

## E. Run exactly the manifest command

```
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml exec \
  -e WORKBENCH_LOSS_CONTROL_MODE=ENFORCE \
  -e ADR0043_COMMIT_SHA="$(git rev-parse HEAD)" \
  -e ADR0043_IMAGE_DIGEST="$BACKEND_IMAGE_DIGEST" \
  backend \
  python -m scripts.adr0043_canary_run
```

> `ADR0043_IMAGE_DIGEST` **is** consumed — bound into the evidence document (`image_digest`), covered by
> the harness SHA-256 (cryptographically bound, not merely stored beside it). `ADR0043_DEPLOYED_AT` is
> available the same way. External capture of the immutable image id / ECR digest remains mandatory.

Capture the exit code immediately: `0` = passed, `1` = RED, `2` = `CanaryRefused`, other = operational
failure. **Do not rerun automatically on a nonzero result.**

## F. Real-time stop rules

**Prohibited during the run** (stop immediately if any is proposed): raising `max_daily_loss` or any limit;
editing loss-control state; clearing/changing the breaker directly; changing positions except through the
harness's sanctioned orders; resetting the Alpaca paper account; changing the system clock; passing a
fabricated `now`; injecting fake velocity; fabricating a session boundary; approving/editing preflight data
outside the sanctioned path; deleting a checkpoint/evidence file to force a restart; starting another
backend/harness process; modifying source or Compose files; **reprovisioning, copying the database, or
switching commits/images inside the continuity boundary**. A timed re-arm is not part of this canary and
must not be faked.

## G–H. Determine whether it is truly GREEN

Do not accept PASS alone — review the evidence and durable state.

- **A1 `state_authoritative`** — pre-order snapshot shows account 3 in `REDUCTION_ONLY_*` with
  `state_version`. Failure: state absent; `NORMAL`; only the legacy breaker column indicates a lock; state
  changed outside the sanctioned event stream.
- **A2 `verified_reduction_allowed`** — SELL 1 protected symbol **admitted** (not rejected by loss
  control), lock shown in the pre-order snapshot, deterministic `client_order_id` present.
  submitted/accepted/filled all count provided it passed risk admission.
- **A3 `new_risk_refused`** — BUY 1 protected symbol **rejected**, reason contains `LOSS_CONTROL_STOP`,
  durable audit trail exists. A broker rejection for buying power / market status / other unrelated reason
  does **not** prove A3.
- **A4 `reached_recovery_cooldown`** — **all** of: `aggregate_verdict = PASS`; parent status `= PASSED`;
  **exactly 12 persisted PASS checks**; committed `PREFLIGHT_PASS` event; resulting durable state
  `= RECOVERY_COOLDOWN`. Entering only `RECOVERY_PREFLIGHT`, or `FAIL`/`INCOMPLETE`, is **RED**.
- **A5 `evaluator_holds`** — evaluator actually invoked; `verdict = HOLD`; `transitioned_to = null`;
  durable state remains `RECOVERY_COOLDOWN`; **no `NORMAL`** and **no `COOLDOWN_COMPLETE`** during the run.
  `NO_OP` / `REGRESSED` / `INTEGRITY_STOP` / `COMPLETE` / `NORMAL` / `COOLDOWN_COMPLETE` are each **RED**.

## I. Preserve the evidence package

Copy `/app/data/adr0043_evidence_enforce.json` out **unmodified**; the printed harness digest, an
in-container `sha256sum`, and the host-copy `sha256sum` must **all match**. Copy the checkpoint
`/app/data/adr0043_canary_state.json` unmodified. Capture post-run logs (`_after`), `$COMPOSE ps`, and
`docker inspect` of the backend. Export (JSON/CSV, each hashed) every run-created/relevant row: acct-3
loss-control state; account + breaker state; the A2 order; the A3 rejected order; decision-ledger entries;
all control events since the anchor; the recovery-preflight parent; all 12 preflight checks; the transition
event bound to the preflight; any events showing `RECOVERY_COOLDOWN`; **proof of absence of `NORMAL` and
`COOLDOWN_COMPLETE` during the run**. Copy all box-side artifacts + both continuity records + the terminal
log to `$EVIDENCE_DIR/`. Build `SHA256SUMS.txt` (+ its own hash) and an optional reproducible `tar.gz`.

## J. Countersignature

Record: run id (operator + harness), UTC start/end, AWS instance id, AMI id, git commit, backend image
digest, Compose/config checksums, **both continuity records**, Alembic repo head + DB current revision,
account/user, canary exit code, evidence + checkpoint SHA-256, A1 result, A2 result + `client_order_id`, A3
result + `client_order_id`, A4 preflight id + 12/12 result, A5 evaluator verdict, final durable state,
whether `NORMAL` appeared, whether `COOLDOWN_COMPLETE` appeared, operator name, independent reviewer name,
verdict.

**Verdicts.** **GREEN** only when: A1–A5 all pass; exit code `0`; evidence digest matches everywhere; final
durable state `= RECOVERY_COOLDOWN`; no `NORMAL` during the run; no `COOLDOWN_COMPLETE` during the run;
**the continuity invariant held (immutables equal across both records)**; no runtime tuning or manual state
changes. **RED** — completed but ≥1 assertion failed. **REFUSED** — the harness correctly refused. **INVALID**
— operator intervention, evidence loss, wrong commit/image, concurrent execution, secret/manual DB editing,
a broken continuity boundary, or another procedural breach.

**Do not relabel RED / REFUSED / INVALID as GREEN after manually correcting the environment.** A new attempt
requires a **new documented run boundary** (a new fresh box, restarting at A0) and a clear explanation of
what changed. A Phase 0 failure is a **setup-readiness** failure — same discipline.

## K. After GREEN

Keep account 3 frozen until countersignature is complete: finish evidence copying; independently verify all
hashes; inspect A1–A5; confirm final state; countersign; preserve the package in durable storage. Then, and
only then, reclaim account 3 **only through sanctioned flows**: sanctioned risk-reducing orders to flatten
the legs; verify fills + no residual/open orders; run the audited recovery/reset path; verify the durable
event trail; confirm the final clean state; restore the intended clean paper-account duplicate; record the
new account/broker identity + credentials through approved secret management. **Do not** edit
`risk_loss_control_state`, delete events, null breaker fields manually, rewrite preflight records, reset the
paper balance before evidence preservation, or treat account 3 as a strategy book without a separate
governance decision.

> **Open governance item to resolve before reclamation.** The manifest describes account 3 as the
> **permanent risk-engine verification account** ("not converted into a strategy account"), while this
> section discusses reclamation. Preserve the canary evidence first, then make the intended post-GREEN role
> of account 3 an **explicit governance decision** before converting or replacing it.

---

## Compact go / no-go checklist

**Phase A (fresh box + provenance) — first:**

- [ ] New AWS instance provisioned for this attempt; instance/boot identity recorded
- [ ] Source exactly `c8b3ac2…`; clean git tree
- [ ] Backend image digest + Compose/config checksums recorded
- [ ] Exactly one Alembic head; DB current at that head
- [ ] Exactly one backend runtime; no live canary process; canary artifact paths absent (or a documented resume)
- [ ] Continuity record (Phase-0 start) captured

**Phase 0 (establish the lock on that same box):**

- [ ] Authoritative current-session baseline captured on THIS box, immutable
- [ ] Broker/DB reconciled (positions, orders, reservations); no stale/unexplained state
- [ ] Limits + provenance frozen; `limits_before_sha256` recorded
- [ ] Loss generated only through `OrderRouter → RiskEngine → broker adapter`
- [ ] Durable state `= REDUCTION_ONLY_DAILY_LOSS`, trip cause `= DAILY_LOSS` (NOT breaker)
- [ ] Read-only twelve-check readiness recorded (dependency-aware; A4-only rows marked pending)
- [ ] Phase 0 verdict `= READY_FOR_ADR0043_CANARY`

**Formal canary — on the same runtime:**

- [ ] Continuity record (canary start) captured; immutables equal to Phase-0-start
- [ ] ENFORCE + `ADR0043_COMMIT_SHA` + `ADR0043_IMAGE_DIGEST` passed only to the one command
- [ ] Pre-run DB + broker evidence captured; terminal + service logs recording

**GREEN only when:**

- [ ] A1 authoritative · A2 reduction admitted · A3 new risk refused with audit
- [ ] A4 full 12/12 PASS and `RECOVERY_COOLDOWN` · A5 exact `HOLD`, no transition
- [ ] No `NORMAL` at any point · no `COOLDOWN_COMPLETE` at any point · exit code `0`
- [ ] Evidence SHA-256 matches all copies · continuity invariant held · no state/limit/time/position manipulation
- [ ] Evidence package preserved · independent countersignature completed

Until all GREEN conditions are satisfied and countersigned:

- **ADR-0043 live operational validation: PENDING**
- **Account 3: NOT RECLAIMABLE**
