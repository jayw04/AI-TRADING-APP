# Runbook — Momentum-Daily Cold-Start Repair: Deploy, Init, Rollback

**Scope.** Deploying the cold-start repair (7-A deployment lifecycle + `initial_seed`,
7-B operational-hold guard + enforcement, ADR 0044) to the live paper box `ec2-paper`,
then initializing the deployment lifecycle for strategy **11** (momentum-daily) and
verifying enforcement — all while the strategy stays **PAUSED** and its operational
hold stays **ACTIVE**.

**This runbook does NOT clear the hold and does NOT activate the strategy.** Those are
later, separately-adjudicated steps (see the "After this runbook" section).

**Migration note.** This change adds **no Alembic migration** — the hold lives in
`strategy_state['operational_hold']` and the lifecycle in `strategy_state['deployment']`
(both JSON keys on the existing table). After merging `origin/main`, the single Alembic
head is `e7b3f2a9c4d1` (from main's ADR-0043 work); `alembic upgrade head` on the box is
the normal boot step, not new to this PR.

---

## 0. Preconditions (before touching the box)

- [ ] PR merged to `main`; note the **exact merge commit** `<MERGE_SHA>`.
- [ ] Local suite green on the merged tree; ruff clean.
- [ ] You are deploying **`<MERGE_SHA>`**, not a local worktree state.

## 1. Deploy the reviewed commit

Follow the canonical box deploy recipe in the `aws_migration_phase1` memory
(git-archive `origin/main` from the **repo root**, re-assert `.env`/`data` symlinks,
`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build backend`,
confirm `alembic current` == `e7b3f2a9c4d1`, resume-on-boot clean). Then:

- [ ] **Verify the deployed artifact digest BEFORE any state mutation.**
      Record the running image digest and confirm it corresponds to `<MERGE_SHA>`:
      ```
      ssh workbench 'sudo docker inspect --format "{{.Image}}" workbench-backend'
      ssh workbench 'sudo docker image inspect <that-image> --format "{{index .RepoDigests 0}} {{.Config.Labels}}"'
      ```
- [ ] Confirm the new audit action exists in the deployed code (proves 7-B is live):
      ```
      ssh workbench 'sudo docker exec workbench-backend python -c \
        "from app.audit.logger import AuditAction; \
         print(AuditAction.STRATEGY_ACTIVATION_BLOCKED_BY_HOLD.value)"'
      ```
      Expect: `STRATEGY_ACTIVATION_BLOCKED_BY_HOLD`.

## 2. Initialize the deployment lifecycle for strategy 11 (SEPARATE command)

Lifecycle init and the retrospective hold formalization are **separate commands with
separate verification**. Init **writes only** `strategy_state['deployment']`; it **reads
`operational_hold` solely for verification** (to echo it) and **never mutates it**. If
init fails, the existing hold — and activation blocking — is untouched.

- [ ] **Dry run first** (default; no write):
      ```
      ssh workbench 'sudo docker exec workbench-backend \
        python scripts/init_deployment_lifecycle.py --strategy-id 11'
      ```
      Expected planned write (exit 0, `mode=DRY-RUN`):
      ```json
      {
        "schema_version": 1,
        "_rev": 0,
        "state": "NEVER_DEPLOYED",
        "has_ever_deployed": false,
        "first_deployed_at": null,
        "active_seed_attempt": null,
        "last_seed_attempt": null
      }
      ```
      The output also echoes the current `operational_hold` **read-only** — confirm it is
      present and ACTIVE and that the script states it will not modify it.
      - If the script prints `deployment blob ALREADY EXISTS` (exit 3): a lifecycle blob is already
        present — **stop**, do not force; investigate why (init is one-shot).
- [ ] **Apply** (only after the dry run is reviewed):
      ```
      ssh workbench 'sudo docker exec workbench-backend \
        python scripts/init_deployment_lifecycle.py --strategy-id 11 --apply'
      ```
      Expect `mode=APPLY`, `WROTE strategy_state['deployment'] = …`, exit 0.

## 3. Verify enforcement while held (SEPARATE verification)

- [ ] Confirm strategy 11 is still **not registered / PAUSED** and the hold is **ACTIVE**.
- [ ] Confirm every activation path rejects it. A start attempt must 409:
      ```
      # via the API as user 4 (or the in-container ActivationService), expect refusal;
      # a STRATEGY_ACTIVATION_BLOCKED_BY_HOLD row should appear in audit_log.
      ```
- [ ] Confirm `operational_hold` is byte-unchanged from before step 2 (init did not touch it).

## 4. Emit the retrospective `STRATEGY_HOLD_PLACED` (SEPARATE command, do NOT double-hold)

⚠ The operational hold is **already effective as a persisted marker**; this step only
adds the *formal audit event* using the new action. It must **not** create a second
logical hold. Only run this **after** the code is deployed (step 1) and the new action
exists on the box.

**Sanctioned mechanism:** `scripts/formalize_existing_operational_hold.py`. This is the
*only* correct path — `HoldService.place()` on the existing identical active hold is an
idempotent no-op and writes no audit; a raw audit insert bypasses the service boundary
and hash chain; placing another hold violates "no second logical hold". The script emits
exactly one `STRATEGY_HOLD_PLACED` (`source=RETROSPECTIVE_FORMALIZATION`, `retrospective=
true`, `effective_at=2026-07-20T22:48:22Z`), validates the live hold against the operator-
asserted `(rev, reason_code, effective_at)`, **never mutates the hold blob**, dedups on
`(strategy_id, hold_rev, source)`, and proves the blob byte-identical before/after.

First read the live hold to get its exact `_rev` and `effective_at`:
```
ssh workbench "sudo docker exec workbench-backend sqlite3 /app/data/workbench.sqlite \
  \"SELECT value FROM strategy_state WHERE strategy_id=11 AND key='operational_hold';\""
```
Then **dry run** (default; validates + plans, writes nothing), substituting the observed
`<REV>` and confirming `effective_at`:
```
ssh workbench 'sudo docker exec workbench-backend \
  python scripts/formalize_existing_operational_hold.py \
    --strategy-id 11 --expected-rev <REV> \
    --expected-reason-code AWAITING_COLD_START_FIX \
    --expected-effective-at 2026-07-20T22:48:22Z \
    --evidence-ref "snapshot_sha256=8fa766f3…" \
    --evidence-ref "audit=STRATEGY_UNREGISTERED#5733" \
    --evidence-ref "run=605" \
    --evidence-ref "plan=momentum_daily_coldstart_repair_plan_v1.0" \
    --approval-ref "<adjudication ref>"'
```
Expect `WOULD WRITE …`, `hold blob BYTE-IDENTICAL before/after: YES`, exit 0. If it
prints `REFUSED` (exit 5), the live hold does not match the asserted rev/reason/effective
or is unreadable — **stop and reconcile**, do not force. Then re-run with `--apply`; expect
`WROTE … audit id <N>`, byte-identical YES, exit 0. A second `--apply` is a no-op
(`already formalized`, exit 0, no second event).

**Verification query** (exactly one retrospective event, hold untouched):
```
ssh workbench "sudo docker exec workbench-backend sqlite3 /app/data/workbench.sqlite \
  \"SELECT id, action, json_extract(payload_json,'\$.source'), json_extract(payload_json,'\$.rev') \
    FROM audit_log WHERE action='STRATEGY_HOLD_PLACED' \
    AND json_extract(payload_json,'\$.strategy_id')=11 \
    AND json_extract(payload_json,'\$.source')='RETROSPECTIVE_FORMALIZATION';\""
# expect exactly ONE row at the observed <REV>; and confirm the hold blob is unchanged:
ssh workbench "sudo docker exec workbench-backend sqlite3 /app/data/workbench.sqlite \
  \"SELECT value FROM strategy_state WHERE strategy_id=11 AND key='operational_hold';\""
```
It does **not** clear or extend the hold.

## 5. Acceptance + drift gates

- [ ] Run the acceptance matrix (hold-active → all activation paths blocked; hold-cleared
      → normal path restored) and the live-class drift audit.

---

## Rollback

This change is **additive and reversible**:

- **Code:** redeploy the previous image/commit via the same recipe. 7-B adds no
  migration, so no `alembic downgrade` is required (the single head `e7b3f2a9c4d1`
  predates this PR and stays). Reverting the code removes hold *enforcement*, but
  strategy 11 remains PAUSED (unregistered), so no activation can occur regardless.
- **State written by init (step 2):** the `strategy_state['deployment']` row is inert to
  the old code (old code never reads it). If you want a clean revert, delete exactly that
  one row (leave `operational_hold` alone):
  ```sql
  DELETE FROM strategy_state WHERE strategy_id = 11 AND key = 'deployment';
  ```
  (Do this only via an authorized maintenance path; never touch `operational_hold` or the
  append-only `audit_log`.)
- **Never roll back by editing `audit_log`** — the retrospective `STRATEGY_HOLD_PLACED`
  event, once written, is immutable by design.

## After this runbook (NOT part of this deployment)

Clear the hold only after documented adjudication → observe the 24-hour cooldown →
activate under operator observation → verify exactly one `initial_seed`. The account is
**not** activated until the acceptance and drift gates are complete.
