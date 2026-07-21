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
lock, never fakes elapsed time or a session boundary, and never relaxes limits. Establishing a
canary-eligible locked state is **Phase 0** below.

**The overriding rule:** never change limits, authority configuration, trip-cause classification,
session baseline, positions, or durable state to make any check pass. If the environment does not
legitimately produce a lock or a GREEN, that is a real result to preserve and explain — not a defect
to engineer around.

---

## Milestone sequence

| Phase | Purpose |
|---|---|
| 0A | Enable + capture authoritative session baseline (before session activity) |
| 0B | Reconcile broker / account / positions / orders / reservations |
| 0C | Freeze limits, config, provenance; fix the authority path |
| 0D | Generate a real daily loss through sanctioned orders |
| 0E | Verify durable `REDUCTION_ONLY_DAILY_LOSS` + `DAILY_LOSS` cause |
| 0F | Read-only twelve-check readiness assessment (after the lock exists) |
| 0G | Freeze the formal-canary start boundary |
| A–K | Fresh-box formal canary: provision → preflight → execute → verify → preserve → countersign |
| — | Countersigned GREEN → **then** account-3 governance / reclaim decision |

A **Phase 0 failure is a setup-readiness failure, not an ADR-0043 canary failure** (the formal canary
has not begun). Preserve and explain it; never work around it by changing limits, authority, cause,
baseline, positions, or state.

---

# Phase 0 — Establish a canary-eligible locked state

## 0C-prime. Freeze the recovery-authority path first

For the first ADR-0043 live validation:

- **Trip origin:** `DAILY_LOSS` · **Expected locked state:** `REDUCTION_ONLY_DAILY_LOSS`
- **Recovery requester:** user 3, the account owner · **Additional operator authority:** *not required*.

The canary requests recovery as the owner (user 3). Per the authority matrix, the owner can
self-authorize a `PREFLIGHT_PASS` **only** for a daily-loss origin; a `REDUCTION_ONLY_BREAKER` origin
lands `AUTHORIZATION_REQUIRED` and the owner's `approve()` is refused → **A4 is RED**.

- **Do NOT** add user 3 to `WORKBENCH_RISK_OPERATOR_USER_IDS` merely to help A4 pass — that changes the
  authority configuration under test. The daily-loss path proves the ordinary owner self-recovery
  without broadening privileges.
- **If account 3 enters `REDUCTION_ONLY_BREAKER`** instead of `REDUCTION_ONLY_DAILY_LOSS`, **STOP** and
  classify the setup as unsuitable for this GREEN run. Do not rewrite the trip cause or durable state.
  Preserve the breaker-origin result as setup evidence, then start a separately governed attempt only
  after identifying why the intended daily-loss path did not govern the trip.

## 0A. Enable + capture the authoritative session baseline (before session activity)

The baseline must be captured by the **production** mechanism, not inserted after the breach.

1. Identify the exact deployed baseline-capture setting; confirm it is enabled for the backend process
   that will handle account 3. Restart/redeploy only through the approved procedure if it is a
   startup-time setting. Record the configuration checksum.
2. Verify the baseline is captured for the **current** trading session and is immutable after capture.

A valid pre-run baseline record contains at least: `account_id=3`, session/trading date = current
session, baseline status = valid/authoritative, capture timestamp, source/provenance, the equity/values
the implementation requires, and immutability/version evidence.

**STOP** — do not begin loss generation — if: capture is disabled; the baseline row is missing; the
baseline belongs to a previous session; provenance is invalid; it was manually inserted; it was
modified after session activity began; or two competing baselines exist. **Do not "repair" the baseline
after the breach** — that would invalidate both the lock provenance and the recovery preflight.

## 0B. Reconcile account 3 before the breach

Capture and compare (read-only), broker vs database:

- **Broker:** positions; open orders; recent fills; account status; buying power; equity; market
  clock/session.
- **Database:** positions/holdings; open orders; reservations; account state; loss-control state;
  breaker status; latest control-event sequence; session baseline; applicable limits.

**Required:** no unexplained DB-only or broker-only position; no stale open order or reservation; no
`F`/`MSFT` quantity mismatch; no pending recovery workflow; no unexplained state transition.

Do not buy or adjust positions to match the frozen baseline unless that establishment is itself an
already-governed part of the canary-account setup. If the account no longer matches the frozen baseline,
the correct response may be to **revise and re-freeze the manifest through review** — not silently
restore it.

## 0C. Freeze the limits (and provenance)

Export the complete effective limit set **before** generating any loss: `max_daily_loss`,
`max_position_qty`, `max_position_notional`, `max_gross_exposure`, `max_orders_per_day`, rate limits,
velocity thresholds, breaker thresholds, and all account/global overrides. Hash the export. From here
through countersignature, `limits_before_sha256 == limits_after_sha256`. An unreachable breach is treated
as unreachable — **never** solved by lowering controls.

## 0D. Generate a real daily loss through sanctioned orders

The goal is not merely negative P&L — it is a loss through the sanctioned order path that crosses the
existing daily-loss threshold and causes the state machine to persist `NORMAL → REDUCTION_ONLY_DAILY_LOSS`.

Every setup order goes through **`OrderRouter → RiskEngine → broker adapter`**. No broker-console trades,
no direct Alpaca scripts outside the app path, no DB position edits, no manual account-state mutation.

Document the setup plan: instruments; max quantity admitted under current limits; expected round trips;
order-rate constraints; expected spread/slippage; **remaining order-count capacity reserved for A2/A3
plus the recovery path and reconciliation calls**; protected instruments that must not be churned; max
setup duration; stop conditions.

**Avoid creating the wrong trip class.** After every controlled cycle, monitor `day_change`,
`max_daily_loss`, current durable state, latest trip cause, breaker status, order count, rate/velocity
metrics, open orders, reservations. **If rate/velocity/breaker protection trips first: STOP** — do not
continue loss generation, do not reclassify the event, do not add operator authority; preserve the setup
evidence. That attempt cannot legitimately establish the intended owner-authorized A4 path.

For every order preserve: deterministic/traceable client order id; request; pre-order state; risk
decision; broker response; fill; post-fill account state; resulting control events.

## 0E. Verify the correct lock, then STOP

The breach is complete only when **all** hold: `day_change <= -effective max_daily_loss`; durable state
`= REDUCTION_ONLY_DAILY_LOSS`; trip cause `= DAILY_LOSS`; a state-transition event committed;
`state_version` advanced; state/event sequence consistent; new-risk orders refused under the lock;
verified reductions remain potentially admissible. Do not rely only on the legacy daily-loss value or
the breaker timestamp.

Once `REDUCTION_ONLY_DAILY_LOSS` is durable: **stop all setup trading.** Do not test extra new-risk
orders manually, do not run recovery manually, do not invoke the cooldown evaluator, do not wait for or
fake another session, do not alter positions, do not clear the breaker, do not modify the baseline.

## 0F. Read-only twelve-check readiness assessment (after the lock exists)

This establishes only that the environment is **capable** of a meaningful run — it is **not** a
substitute for A4. It must **read** state, reconcile broker/DB facts, verify configuration, and report
likely blockers. It must **not** create a preflight parent, approve recovery, move state, clear
orders/reservations by direct writes, or manufacture PASS rows — doing so would **consume the real A4
idempotency identity** and contaminate the canary.

The check registry is **dependency-ordered**; interpret results with that structure (a dependent whose
prerequisite did not pass is recorded `INCOMPLETE (BLOCKED_BY_<check>)`, **not** an independent `FAIL`;
the aggregate is fail-closed):

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
| 11 | `control_state_consistent` | **Partially** confirmable | full recovery-transition consistency is proven at A4 (for a daily-loss origin it does NOT require a tripped-breaker column) |
| 12 | `no_unresolved_integrity_condition` | Confirmable | no unresolved integrity condition present |

Two rows are provable **only during A4** and must remain explicitly pending in Phase 0: check 2
(`recovery_origin_proven`) and the transition-dependent portion of check 11 (`control_state_consistent`).
The read-only inspection can confirm the *inputs* (baseline present, positions reconcile, trip cause =
`DAILY_LOSS`), never the transition itself.

## 0G. Freeze the formal-canary start boundary

Record the Phase 0 endpoint verdict — **`READY_FOR_ADR0043_CANARY`** — only when: state
`= REDUCTION_ONLY_DAILY_LOSS`; trip cause `= DAILY_LOSS`; baseline valid/authoritative; protected legs
present; open orders + reservations reconciled; limits hash unchanged; owner self-recovery permitted;
checkpoint/evidence paths clean. Then proceed to the formal canary.

---

# Phase A — Provision a fresh box

## 1. Establish the immutable run identity (operator side)

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
> `a3_client_order_id`).

Do not reuse a run identity for a different EC2 instance or a reset account.

## 2. Provision from the approved deployment path

New, attributable runtime: no reused checkpoint/lock, no stale evidence, no unreviewed local code, no
manually edited DB, no hidden harness process. **Never run the canary from the laptop** — the manifest
requires execution on the deployed box through the production Compose stack.

Record instance identity immediately (`hostname`, `boot_id`, `kernel`, and — where instance metadata is
enabled — `instance_id`, `ami_id`, `instance_type`) into `$EVIDENCE_DIR/instance_identity.txt`. A metadata
failure is **documented, not bypassed**.

## 3. Check out exactly `c8b3ac2`

```
git fetch --prune origin && git checkout main
git reset --hard c8b3ac24b839d7b19c40979a9e4be859151dbab7 && git clean -fd
git rev-parse HEAD          # must equal c8b3ac2…; tree must be clean
```

Capture `HEAD` + `git status --porcelain=v1` + `git show -s --format=fuller HEAD` and copy to
`$EVIDENCE_DIR/git_state.txt`. **STOP** if HEAD differs, the tree is dirty, there are unreviewed
deployment overrides, or the running container later reports code inconsistent with this revision.

---

# Phase B — Freeze deployment provenance

## 4–5. Compose / image / config provenance

`COMPOSE="sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml"`. Record: `$COMPOSE
version`, `config --services`, `config --images`, `sha256sum docker-compose.yml docker-compose.prod.yml`,
and the **actual** running container image ids (`docker inspect … {{.Config.Image}} {{.Image}}`),
especially the backend (`image_name`, `image_id`, `created`, `started`, `restart_count`). If the image is
in ECR with a repository **digest**, preserve that digest — do not rely on a mutable tag like `latest`.
For config, hash the source-controlled files and a **redacted** env representation (mask
`SECRET|TOKEN|PASSWORD|KEY|CREDENTIAL`); manually inspect the redacted file before copying; **no
plaintext credentials in the evidence package**.

---

# Phase C — Verify the deployed database

## 6. Alembic migration head

```
$COMPOSE exec -T backend alembic heads     # exactly one (head)
$COMPOSE exec -T backend alembic current   # must equal the repository head
```

**STOP** if more than one head, the DB is behind, an unknown revision is present, or anyone proposes
`alembic stamp head` merely to pass — `stamp head` is valid only when the schema is independently known
to match, never to manufacture readiness. Copy both records to `$EVIDENCE_DIR/`.

---

# Phase D — Deployment preflight

## 7. One backend runtime, no live canary, lock inspected not deleted

Confirm exactly one intended backend container; no `scripts.adr0043_canary_run` process; and inspect
`/app/data/adr0043_canary.lock`. **Do not auto-delete a lock.** If one exists, inspect its PID, whether
that PID is alive, container restart time/logs, whether the run is genuinely resumable — and **document
the decision**. The harness refuses concurrent runs because two processes recreate the double-reservation
failure condition.

## 8. ENFORCE only for the one execution

The canary command injects `WORKBENCH_LOSS_CONTROL_MODE=ENFORCE` into the single execution; the manifest
requires refusal under OFF/SHADOW. Confirm the command receives exactly `WORKBENCH_LOSS_CONTROL_MODE=ENFORCE`
and `ADR0043_COMMIT_SHA=c8b3ac2…`. **Do not** globally flip every environment to ENFORCE unless that was
separately reviewed.

## 9. Read-only account-3 state

Capture (read-only) and hash a deterministic export of: `accounts_state` (account 3); `accounts`
(id/user/broker/mode/label/`circuit_breaker_tripped_at`); `risk_loss_control_state` (**state must be a
`REDUCTION_ONLY_*` value with `state_version` present**); `risk_limits` (user 3 / GLOBAL / paper);
`risk_recovery_preflight` history; recent `risk_control_events`. **Never** run `UPDATE
risk_loss_control_state`, `UPDATE risk_limits`, `UPDATE accounts SET circuit_breaker_tripped_at`, or
`DELETE FROM risk_control_events`. Any need for such a change means the run is not valid.

## 10. Protected broker positions

`F ≥ 500`, `MSFT ≥ 20`, read-only, recorded (symbol, qty, avg entry, market value, account identity,
timestamp). **Do not buy back a missing leg** — the manifest treats a missing protected leg as a refusal
condition (a locked account cannot legitimately manufacture the precondition).

## 11. Checkpoint / evidence state

Inspect (EXISTS/ABSENT + `ls -l` + `sha256sum`) `/app/data/adr0043_canary_state.json`,
`/app/data/adr0043_canary.lock`, `/app/data/adr0043_evidence_enforce.json`. A fresh run expects these
**absent**. **Do not remove a checkpoint merely to get a clean run** — decide whether it is a genuine
interrupted execution that should resume, an already-completed run the harness should verify, or an
unrelated/stale environment. The harness rebinds deterministic A2/A3 orders by identity, reuses the A4
idempotency key, and verifies a completed run without repeating side effects. **A contradictory
checkpoint should produce a refusal — a valid safety outcome, not something to work around.**

---

# Phase E — Start full evidence capture

## 12–13. Log boundary + terminal recorder

Record a pre-run UTC boundary and full backend logs (`_before`). Record current **max ids** for the
decision ledger, control events, recovery preflights, preflight checks, and orders (run anchors). Start
`script -q -f "/tmp/${ADR0043_RUN_ID}_terminal.log"`; inside it print `date -u`, `hostname`,
`git rev-parse HEAD`, `$COMPOSE ps`. **Do not edit the transcript afterward; hash the original.**

---

# Phase F — Execute the frozen canary

## 14. Run exactly the manifest command

```
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml exec \
  -e WORKBENCH_LOSS_CONTROL_MODE=ENFORCE \
  -e ADR0043_COMMIT_SHA="$(git rev-parse HEAD)" \
  -e ADR0043_IMAGE_DIGEST="$BACKEND_IMAGE_DIGEST" \
  backend \
  python -m scripts.adr0043_canary_run
```

> `ADR0043_IMAGE_DIGEST` **is** consumed — `adr0043_canary_lib.py` binds it into the evidence document
> (`image_digest`), so it is covered by the harness SHA-256 (cryptographically bound, not merely stored
> beside the run). `ADR0043_DEPLOYED_AT` is available the same way if wanted. External capture of the
> immutable image id / ECR digest remains mandatory regardless.

Capture the exit code immediately: `0` = passed, `1` = RED, `2` = `CanaryRefused`, other = operational
failure. **Do not rerun automatically on a nonzero result.**

---

# Phase G — Real-time stop rules

**Prohibited during the run** (stop immediately if any is proposed): raising `max_daily_loss` or any
limit; editing loss-control state; clearing/changing the breaker directly; changing positions except
through the harness's sanctioned orders; resetting the Alpaca paper account; changing the system clock;
passing a fabricated `now`; injecting fake velocity; fabricating a session boundary; manually
approving/editing preflight data outside the sanctioned path; deleting a checkpoint/evidence file to
force a restart; starting another backend/harness process; modifying source or Compose files; switching
commits or images. **A timed re-arm is not part of this canary and must not be faked.**

---

# Phase H — Determine whether it is truly GREEN

Do not accept the word PASS alone — review the evidence and durable state.

- **A1 `state_authoritative`** — pre-order snapshot shows account 3 in `REDUCTION_ONLY_*` with
  `state_version` present. Failure: state row absent; `NORMAL`; only the legacy breaker column indicates
  a lock; state changed outside the sanctioned event stream.
- **A2 `verified_reduction_allowed`** — SELL 1 protected symbol **admitted** (not rejected by loss
  control), pre-order snapshot shows the lock, deterministic `client_order_id` present. Submitted/
  accepted/filled all count provided it passed risk admission.
- **A3 `new_risk_refused`** — BUY 1 protected symbol **rejected**, reason contains `LOSS_CONTROL_STOP`,
  durable audit trail exists. A broker rejection for buying power / market status / another unrelated
  reason does **not** prove A3.
- **A4 `reached_recovery_cooldown`** — **all** of: `aggregate_verdict = PASS`; parent preflight status
  `= PASSED`; **exactly 12 persisted PASS checks**; committed `PREFLIGHT_PASS` event; resulting durable
  state `= RECOVERY_COOLDOWN`. Entering only `RECOVERY_PREFLIGHT`, or `FAIL`/`INCOMPLETE`, is **RED**.
- **A5 `evaluator_holds`** — evaluator actually invoked; `verdict = HOLD`; `transitioned_to = null`;
  durable state remains `RECOVERY_COOLDOWN`; **no `NORMAL`** and **no `COOLDOWN_COMPLETE`** during the
  run. `NO_OP` / `REGRESSED` / `INTEGRITY_STOP` / `COMPLETE` / `NORMAL` / `COOLDOWN_COMPLETE` are each
  **RED**. The live canary proves HOLD, not a completed timed re-arm.

---

# Phase I — Preserve the evidence package

## 17–21. Copy, hash, export, manifest

Copy `/app/data/adr0043_evidence_enforce.json` out **unmodified**; the printed harness digest, an
in-container `sha256sum`, and the host-copy `sha256sum` must **all match**. Copy the checkpoint
`/app/data/adr0043_canary_state.json` unmodified. Capture post-run logs (`_after`), `$COMPOSE ps`, and
`docker inspect` of the backend. Export (JSON/CSV, each hashed) every run-created/relevant row: acct-3
loss-control state; account + breaker state; the A2 order; the A3 rejected order; decision-ledger entries;
all control events since the anchor; the recovery-preflight parent; all 12 preflight checks; the
transition event bound to the preflight; any events showing `RECOVERY_COOLDOWN`; **proof of absence of
`NORMAL` and `COOLDOWN_COMPLETE` during the run**. Copy all box-side artifacts + the terminal log to
`$EVIDENCE_DIR/`. Build `SHA256SUMS.txt` (+ its own hash) and an optional reproducible `tar.gz` (sorted,
zeroed mtime/owner); preserve both the directory and the archive.

---

# Phase J — Countersignature

The countersignature records: run id (operator + harness), UTC start/end, AWS instance id, AMI id, git
commit, backend image digest, Compose/config checksums, Alembic repo head + DB current revision,
account/user, canary exit code, evidence + checkpoint SHA-256, A1 result, A2 result + `client_order_id`,
A3 result + `client_order_id`, A4 preflight id + 12/12 result, A5 evaluator verdict, final durable state,
whether `NORMAL` appeared, whether `COOLDOWN_COMPLETE` appeared, operator name, independent reviewer name,
verdict.

**Verdicts.** **GREEN** only when: A1–A5 all pass; exit code `0`; evidence digest matches everywhere;
final durable state `= RECOVERY_COOLDOWN`; no `NORMAL` during the run; no `COOLDOWN_COMPLETE` during the
run; no runtime tuning or manual state changes occurred. **RED** — the canary completed but one or more
assertions failed. **REFUSED** — the harness correctly refused on an invalid precondition or
contradictory evidence. **INVALID** — operator intervention, evidence loss, wrong commit/image,
concurrent execution, secret/manual DB editing, or another procedural breach makes the result unusable.

**Do not relabel RED / REFUSED / INVALID as GREEN after manually correcting the environment.** A new
attempt requires a **new documented run boundary** and a clear explanation of what changed. (A Phase 0
failure is a **setup-readiness** failure — same discipline: preserve, explain, never work around.)

---

# Phase K — After GREEN

## 23. Keep account 3 frozen until countersignature is complete

Even after the terminal prints PASS: finish evidence copying; independently verify all hashes; inspect
A1–A5; confirm final state; countersign; preserve the package in durable storage. The reclaim boundary is
reached **only** after the live GREEN run — until that point account 3 remains frozen.

## 24. Reclaim account 3 only through sanctioned flows

After countersigned GREEN: submit sanctioned risk-reducing orders to flatten the protected legs; verify
fills + no residual/open orders; run the audited recovery/reset path; verify the durable event trail;
confirm the final clean state; restore the intended clean paper-account duplicate; record the new
account/broker identity + credentials through the approved secret-management process. **Do not** edit
`risk_loss_control_state`, delete events, null breaker fields manually, rewrite preflight records, reset
the paper balance before evidence preservation, or treat account 3 as a strategy book without a separate
governance decision.

> **Open governance item to resolve before reclamation.** The manifest describes account 3 as the
> **permanent risk-engine verification account** ("not converted into a strategy account"), while this
> section discusses reclamation. Preserve the canary evidence first, then make the intended post-GREEN
> role of account 3 an **explicit governance decision** before converting or replacing it.

---

## Compact go / no-go checklist

**Phase 0 — proceed only when every box is checked:**

- [ ] Authoritative session baseline enabled + captured for the current session, immutable
- [ ] Broker/DB reconciled (positions, orders, reservations); no stale/unexplained state
- [ ] Limits + config + provenance frozen; `limits_before_sha256` recorded
- [ ] Loss generated only through `OrderRouter → RiskEngine → broker adapter`
- [ ] Durable state `= REDUCTION_ONLY_DAILY_LOSS`, trip cause `= DAILY_LOSS` (NOT breaker)
- [ ] Read-only twelve-check readiness recorded (dependency-aware; A4-only rows marked pending)
- [ ] Order-count / rate / exposure / reservation capacity reserved for A2/A3 + recovery
- [ ] Phase 0 verdict `= READY_FOR_ADR0043_CANARY`

**Formal canary — proceed only when every box is checked:**

- [ ] Fresh AWS instance · source exactly `c8b3ac2…` · clean git tree
- [ ] Backend image digest recorded · Compose/config checksums recorded
- [ ] One Alembic head · DB current at that head
- [ ] Exactly one backend runtime · no live canary process · no unexplained lock/checkpoint/evidence
- [ ] ENFORCE passed only to the formal canary command
- [ ] Account 3 durable state `REDUCTION_ONLY_DAILY_LOSS` · `F`/`MSFT` legs present · limits unchanged
- [ ] Pre-run DB + broker evidence captured · terminal + service logs recording

**GREEN only when:**

- [ ] A1 durable state authoritative · A2 verified reduction admitted · A3 new risk refused with audit
- [ ] A4 full 12/12 PASS and `RECOVERY_COOLDOWN` · A5 exact `HOLD`, no transition
- [ ] No `NORMAL` at any point · no `COOLDOWN_COMPLETE` at any point · exit code `0`
- [ ] Evidence SHA-256 matches all copies · no state/limit/time/position/evidence manipulation
- [ ] Evidence package preserved · independent countersignature completed

Until all GREEN conditions are satisfied and countersigned:

- **ADR-0043 live operational validation: PENDING**
- **Account 3: NOT RECLAIMABLE**
