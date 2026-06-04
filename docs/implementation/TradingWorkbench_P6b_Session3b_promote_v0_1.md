# P6b Session 3b-promote — Promote Endpoint + Reject + Cooldown Cron + Lockout + UI + MCP

| Field | Value |
|---|---|
| Document version | **v0.1** (drafted against `TradingWorkbench_P6b_Session3a_gate_Results_v0.1.md` + the 11-question architecture-decision turn with three ADR-0007 corrections + eight confirms) |
| Date | 2026-06-04 |
| Phase | **P6b — Direction v0.2 deferred capabilities**, **§3b-promote** (action half of P6b Session 3; closes P6b §3 by adding the promote/reject endpoints, cooldown cron, lockout enforcement, UI sub-renders, and MCP additive fields on top of §3a's gate + lifecycle states) |
| Predecessor | `TradingWorkbench_P6b_Session3a_gate_Results_v0.1.md` (tag `p6b-session3a-gate-complete` pending PR + walk-away) |
| Successor | (P6b §3 closes after §3b-promote cross-session verification; remaining P6b sessions = §4 Mode-B LLM eval harness + §5 LLM-driven live opt-in, replanned after §3 closes per the Closure plan's phased split) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | **Promote endpoint** `POST /api/v1/proposals/{id}/promote` (per Q1 settled (a)) — EVIDENCE_READY → PROMOTING; re-checks parent is LIVE + not in lockout at click time (409 otherwise); writes `STRATEGY_PROPOSAL_TRANSITIONED` audit row with **evidence-bundle hash embedded in payload** (ADR 0007 requirement). **Reject-promotion endpoint** `POST /api/v1/proposals/{id}/reject-promotion` — accepts EVIDENCE_READY AND PROMOTING source states (per Q4 ADR correction); transitions → REJECTED (terminal); terminates the paper variant via existing `PaperVariantService.terminate_for_parent`; one endpoint serving both "Reject evidence" and "Cancel cooldown" UX moments (different button labels, same audit shape with from-state in payload). **Cooldown completion cron** at `app/jobs/promotion_completion.py` — 15-minute APScheduler sweep (per Q3 settled (b)) mirroring the existing `app/jobs/activation_completion.py` PENDING_LIVE → LIVE pattern; finds PROMOTING proposals where `promoting_at + ACTIVATION_COOLDOWN_HOURS` elapsed; transitions PROMOTING → PROMOTED; calls the mechanical-promote action. **Mechanical-promote action** — merges proposal's params into parent.params_json (same merge as `apply_proposal`), sets `parent.last_promoted_at`, terminates paper variant, writes `STRATEGY_PROPOSAL_TRANSITIONED` (PROMOTING→PROMOTED) + `STRATEGY_PROMOTED` marker (two commits per audit-hash-chain contract). **NO auto-promote — forbidden by ADR 0007** (Q6 killed): no envelope flag, no brief-pass chaining, no automation hook anywhere. The only "auto" remains the §2b-shipped `auto_validate_proposals` (auto-spawn variant, NOT auto-promote). **Lockout enforcement** (per Q5 ADR correction) — blocks `POST /proposals/{id}/validate` (spawn) and the §2b `_maybe_auto_validate_proposal` hook with HTTP 409 when `parent.last_promoted_at` is within `PROMOTION_LOCKOUT_DAYS` (= 30, hardcoded per ADR). **Does NOT block** REVIEWING→ACCEPTED; the user can still accept proposals during lockout, but starting a new evaluation cycle is gated. **VariantCard 4-state shell + sub-renders on proposal.state** (per Q8): EVALUATING → metrics+chart+Stop (existing §2c); EVIDENCE_READY → evidence summary + "Promote" button + "Reject" button (NEW); PROMOTING → "promoting — live at {promoting_at + 24h}" + "Cancel" button (NEW); PROMOTED → terminal "promoted {date}"; lockout-aware empty state ("In 30-day post-promotion lockout until {last_promoted_at + 30 days}"). **MCP additive fields** on existing `workbench_paper_variant_metrics` response (per Q9): `evidence_bundle` (§3a JSON), `proposal_state` (lifecycle), `eligible_for_promotion: bool` (= state == EVIDENCE_READY AND parent not in lockout), `parent_last_promoted_at`. Stay at 19 tools. **Schema:** `proposal.promoting_at: datetime \| None` column (set on PROMOTING transition, read by cooldown cron). Single Alembic revision (additive nullable column). Single PR. |
| Estimated wall time | 7-8h |
| Stopping point | `git tag p6b-session3b-promote-complete`. Then run §3b-promote.14 cross-session verification → tag `p6b-session3-promote-complete`. |
| Tests added | ~28 backend (endpoints + cron + lockout + mechanical-promote) + ~8 frontend (VariantCard sub-renders + lockout-aware empty + button mutations) + ~2 MCP (additive fields) |
| Out of scope | Auto-promote — **forbidden by ADR 0007**. Strategy-version archiving (ADR 0007's literal "old variant archived as a strategy version" model — flagged as **deferred deviation** below; v1 ships a pragmatic params-merge alternative that preserves intent via audit log + proposal record). Extended-evaluation feature (ADR 0007's STRATEGY_PROPOSAL_EXTENDED "double the evaluation window" path) — real ADR feature, not on the critical promote/reject path, defer to a follow-up session. Evidence-bundle CSV export (UI download nicety) — defer. Granular per-transition audit actions (ADR lists STRATEGY_PROPOSAL_CRITERIA_MET / _APPROVED / _REJECTED / _EXTENDED; P6 Decision 3 consolidated to STRATEGY_PROPOSAL_TRANSITIONED + STRATEGY_PROMOTED — keep that shape). Lockout configurability via envelope (ADR doesn't mark it user-tunable; hardcoded 30 days). Per-strategy override of cooldown duration. Cancellation grace window (no "first 5 minutes only" — ADR mandates the full 24h frictionless cancel). |

---

## ⚠ Review corrections (2026-06-04) — verified against shipped code

The architecture + the three ADR corrections are sound. The code sketches below carry real drift; these corrections **supersede the sketches** wherever they conflict (applied at implementation time).

### Blockers (would crash / break invariants)
- **B1 — `PaperVariantService.terminate` signature.** Shipped (§2a) is keyword-only `terminate(*, variant_strategy_id, reason, user_id)` — the sketches' `terminate(variant_id=…, reason=…)` is wrong (param name + missing `user_id`). → drop the `find_in_flight_variant` + `terminate` two-step and call **`terminate_for_parent(parent_strategy_id=parent.id, reason=…, user_id=…)`** (no-op if none), the §2c D8 pattern.
- **B2 — Mechanical-promote params merge.** `proposal.proposal_payload.get("params", {})` is doubly wrong: the field is **`proposal_payload_json`** and the shape is **`{"changes":[{"param","from","to"}]}`** (not `{"params":{}}`). → reuse **`app.services.proposal_evaluation._apply_changes`** (spawn already uses it): `new_params = _apply_changes(dict(parent.params_json or {}), proposal.proposal_payload_json.get("changes") or [])`.
- **B3 — One-row-per-commit ordering.** The promote/reject sketches `AuditLogger.write(TRANSITIONED)` then call `terminate` (which commits internally) → both audit rows flush in one commit, breaking the hash chain. → **terminate first** (own commits), **then** set state + write the transition audit + `commit()` (the §2c `apply_proposal` D8 ordering).
- **B4 — Cron registration uses `app.state.scheduler`** (unset at registration). → register inside the alpaca block via the in-scope **`scheduler.scheduler.add_job(...)`** local (see `activation_completion` in `lifespan.py` ~L248); pass the in-scope engine local.

### Architecture (resolve before executing)
- **A1 — Terminate the variant at PROMOTED, NOT at PROMOTING (resolve DEVIATION-#1 the other way).** The variant-comparison endpoint + MCP fields key on `find_in_flight_variant` (`status == PAPER_VARIANT`); terminating at PROMOTING makes the endpoint return `no_active_variant`, so the PROMOTING/PROMOTED UI sub-renders + MCP fields have **no data source**. Keep the paper variant alive (harmless paper orders) through the 24h cooldown — matches ADR's "old variant continues; new variant submits no orders" (the new *live* variant doesn't exist until params apply at PROMOTED) — and terminate it in `execute_mechanical_promote` at PROMOTED. So **the promote + reject(from-EVIDENCE_READY) endpoints do NOT terminate**; only mechanical-promote (PROMOTED) and reject-from-PROMOTING terminate. (Reject-from-EVIDENCE_READY does terminate, since that ends the evaluation.)
- **A2 — Broaden the proposal lookup.** §2c's `_spawn_proposal_id_for_parent` filters `state == EVALUATING` only → won't find EVIDENCE_READY/PROMOTING proposals. → new helper `_active_validation_proposal_for_parent(session, parent_id)` filtering `state IN (EVALUATING, EVIDENCE_READY, PROMOTING)`, used by both the additive fields and `spawn_proposal_id`.
- **A3 — `last_promoted_at` isn't on the frontend.** §3a added it as a model column only (not in `StrategyResponse` / `@/api/types`). → drive the lockout-aware empty state off the variant-comparison **`parent_last_promoted_at` additive field** (the card already fetches that endpoint), NOT `strategy.last_promoted_at`. No strategies-endpoint change.
- **A4 — No migration. Reuse `transitioned_at`.** `StrategyProposal.transitioned_at` already exists and is set on every transition; while `state == PROMOTING` nothing else transitions it, so it *is* the PROMOTING-entry time. The cron filters `state == PROMOTING AND transitioned_at + cooldown <= now`. **Drop `promoting_at` + the Alembic revision** → §3b is migration-free.

### Minor
- **`with_for_update(skip_locked=True)` is a no-op on SQLite.** Match `activation_completion`: collect eligible IDs in one session, then a **fresh session per item** with a `state == PROMOTING` re-check (SQLite single-writer + re-check handle the cancel race).
- **Cron actor = `AuditActorType.SYSTEM`** (scheduled job), not `AGENT`, for the PROMOTED transition + `STRATEGY_PROMOTED`.
- **`activation_completion` runs every 60s**, not 15-min — §3b uses 15-min per Q3 (fine), just not a cadence-clone.
- **Add `variantsApi.promote` / `.rejectPromotion`** to `src/api/variants.ts` (POST, `body: JSON.stringify({})`).
- Use the imported **`ACTIVATION_COOLDOWN_HOURS`** (not a hardcoded `24`) for the cooldown-expiry math.
- **Promote/cron audit actor:** promote + reject = `USER`; mechanical-promote (cron) = `SYSTEM`.

---

## How this differs from §3a-gate Results + the three ADR-0007 corrections

§3a Results' seven execution-time corrections + the three §3b ADR corrections shape this draft directly:

### §3a corrections carrying forward
- **AND duration gate + 1.20× drawdown** (§3a corrections #1 + #2): the gate that fires EVIDENCE_READY is calibrated correctly; §3b's promote endpoint trusts the §3a transition. No re-evaluation in §3b.
- **`VariantComparison += capital_base`** (§3a correction #4 additive): §3b's MCP additive fields surface this for the UI's display of "Initial equity: ${capital_base}" alongside the absolute-return criterion result.
- **`ProposalState` is in `app/db/models/strategy_proposal.py`, values UPPER** (§3a correction #3): §3b's state references use UPPER (`PROMOTING = "PROMOTING"`, etc.).
- **Brief site is `app/jobs/morning_brief_generation.py`** (§3a correction #5): not relevant to §3b directly, but the cooldown cron site `app/jobs/promotion_completion.py` follows the same `jobs/` directory convention.
- **Sticky-with-refresh state semantics** (§3a correction #6): MCP additive `evidence_bundle` field reads from `evaluation_results_json.evidence_bundle` which §3a keeps refreshed; promote endpoint embeds the current bundle's hash in audit at the click moment.
- **Transition payload uses UPPER states** (§3a correction #7): `payload={"from": "EVIDENCE_READY", "to": "PROMOTING", ...}`.

### Three ADR-0007 corrections (Q4, Q5, Q6)
- **🛑 Q6: NO auto-promote.** ADR 0007: "Auto-promotion without user approval. Promotion is always user-gated." Deleted from §3b scope entirely. No `auto_promote_validated` envelope key; no chained transition in §3a's brief-pass; no automation hook anywhere. The only "auto" preserved is §2b's `auto_validate_proposals` (auto-spawn variant; user still decides promote/reject).
- **⚠️ Q5: Lockout blocks VALIDATE not ACCEPT.** ADR 0007: "after a promotion, the strategy is locked in STABLE for at least 30 days before a new proposal can be initiated. The LLM may identify potential improvements during this lockout but cannot start a new evaluation cycle." The blocked door is `POST /proposals/{id}/validate` + the §2b `_maybe_auto_validate_proposal` auto-spawn hook. The LLM can still propose-draft; the user can still ACCEPT — what's gated is starting a new evaluation.
- **⚠️ Q4: Cancel target is REJECTED (terminal), not EVIDENCE_READY.** ADR 0007: cancel "reverts the variant to its prior state and the proposal returns to a 'rejected' terminal state." Frictionless cancel for the full 24h cooldown window (not a 5-min grace). The reject-promotion endpoint serves both Q4's cancel-during-cooldown and the EVIDENCE_READY-stage rejection; same audit shape with from-state in payload.

### Two design notes baked into v0.1
- **What "promote" mechanically does (v1, shipped-compatible deviation).** ADR 0007's literal model: "new params become the live variant; old variant archived as a strategy version." Shipped code has no strategy-versioning concept. v1 pragmatic-faithful: on PROMOTED, apply proposal's params to parent strategy params_json (same merge as `apply_proposal`), set parent.last_promoted_at, terminate paper variant, write STRATEGY_PROMOTED. During PROMOTING, parent keeps running OLD params (= ADR's "old variant continues; new variant submits no orders"). **Marked as DEVIATION in v0.1**: full strategy-version archiving is deferred; audit log + proposal record preserve the history ADR wants. Flag for review.
- **Promote precondition: parent must be LIVE and not in lockout at the click moment** (re-check, like §2a's IDLE guards) — 409 otherwise. Mirrors P5 §7 precondition pattern.

### 🚩 DEVIATION FLAGS (intentional, recorded for review)

Two interpretation choices in this v0.1 that diverge from ADR-literal — flagged here for your inspection rather than buried in the body:

1. **Variant termination at PROMOTING entry (not at PROMOTED).** Jay's design note (and ADR §80-89 read literally) says "old variant continues, new variant submits no orders" during cooldown — implying variant stays alive but engine-paused during PROMOTING, fully terminated at PROMOTED. v0.1 simplifies: variant terminated via `PaperVariantService.terminate(reason="promotion_started")` at PROMOTING entry. Semantically equivalent from user perspective (variant submits no orders either way; bundle preserved); implementation-friendly (no new "engine-paused-but-alive" state or `freeze_for_cooldown` method needed). **If you prefer literal interpretation**: replace the terminate call in §3b-promote.2 with `engine.unregister_strategy(variant.id)` (engine-pause only); add the full `PaperVariantService.terminate` call to §3b-promote.5 (mechanical_promote) before the params merge. Trade-off: cleaner ADR fidelity vs. one additional state to reason about (PAPER_VARIANT row alive but engine-unregistered for 24h).
2. **Full strategy-version archiving deferred.** Per Jay's design note — `apply_proposal`-style params merge in v1; audit log + proposal record preserve the history ADR wants. A future ADR-faithful follow-up session would add strategy-versioning if needed.

Plus all standing P6+P6b deviations applicable to §3b:
- `evaluation_results_json` merge-not-overwrite (§2b-rv non-negotiable): the new `evidence_bundle.approved_at` sub-key write on promote click uses reassignment-not-mutation.
- One audit row per transaction (§1a-drift hash-chain): each state transition + the STRATEGY_PROMOTED marker get separate commits.
- `func.json_extract(...)` Core for JSON queries.
- SQLite tz coercion (§2b-variant deviation #3): cooldown cron's `promoting_at + cooldown` comparison.
- MCP server `_TOOLS: list[Callable]` + module-level `_get` (§1b-drift correction): no new tools, but the existing `workbench_paper_variant_metrics` function gains additive fields in its response.
- Frontend Tailwind utility classes (§2c correction #5).
- Frontend `@/api/types` import path (§2c correction #4).

---

## ⚠ Posture

**§3b-promote closes P6b §3.** Four principles:

1. **Promotion is always user-gated.** The single most important §3b invariant. No `auto_promote_validated` envelope key exists; no automation hook fires promote anywhere. ADR 0007 forbids it; ADR 0006 reinforces it ("user is the deciding entity for AI-influenced changes"). The system enables informed user decision-making — it doesn't replace it. **A test guards: `test_no_auto_promote_envelope_flag_exists`.**

2. **Lockout protects against parameter churn at evaluation-cycle level, not proposal-acceptance level.** Surgical block on `/validate` (spawn) — pre-existing accepted proposals proceed, the LLM can propose-draft, the user can accept. What's gated is starting a new variant evaluation. 30-day window from `parent.last_promoted_at`, hardcoded constant per ADR text (not envelope-tunable).

3. **Cancel-during-PROMOTING → REJECTED (terminal).** Frictionless full-cooldown-window cancel per ADR. If the user changes mind after cancel: re-propose (cheap), and since cancel means promotion didn't happen, `last_promoted_at` is unset → no lockout → re-validate is fine. Clean lifecycle.

4. **Mechanical promote = params merge (not strategy-version archiving).** v1 deviation from ADR's literal model — flagged explicitly. Audit log + proposal record preserve the history; strategy-version archiving deferred to a future ADR-faithful follow-up. During PROMOTING, parent runs OLD params; merge happens only on PROMOTED transition.

Paper smoke from P1-P5 byte-identical. ADR-0002 `_router_token` discipline unaffected. `check_agent_no_db_access.sh` unaffected.

---

## Verification checklist — grep before pasting any code below

Per Retrospective Rec #5. With the §3a corrections in mind:

- [ ] **`ACTIVATION_COOLDOWN_HOURS = 24`** in `app/services/activation.py` per Q2 correction — it's HOURS not seconds. Confirm exact import path. The cooldown completion cron imports + reuses (no new constant).
- [ ] **`app/jobs/activation_completion.py`** structure — Q3 confirmed mirror pattern. Read its full shape: APScheduler registration site, sweep query, transition logic. `promotion_completion.py` clones the pattern verbatim with PROMOTING/PROMOTED swap.
- [ ] **`ProposalState`** in `app/db/models/strategy_proposal.py` (per §3a correction #3) — confirm `EVIDENCE_READY = "EVIDENCE_READY"`, `PROMOTING = "PROMOTING"`, `PROMOTED = "PROMOTED"`, `REJECTED = "REJECTED"` all UPPER.
- [ ] **`StrategyProposal` model** — does a `transitioned_at` column already exist? §3b sketch uses `promoting_at` specifically; check if a general `transitioned_at` is preferable per existing convention. Lean: scoped `promoting_at` to limit blast radius.
- [ ] **`PaperVariantService.terminate_for_parent(...)` signature** per §2b shipped — takes `(session, parent_strategy_id, reason: str)`. Reject-promotion and mechanical-promote-PROMOTED both call this.
- [ ] **`apply_proposal` service** — where does the params-merge logic live? §3b's mechanical promote reuses the same merge to maintain consistency. If `apply_proposal` is in `app/services/proposals.py` or similar, factor the merge into a shared helper.
- [ ] **`Strategy.last_promoted_at`** (§3a added) + **`Strategy.params_json` mutation idempotency** — confirm merge produces same result regardless of pre-existing state.
- [ ] **Frontend `Strategies/Detail.tsx` VariantCard mount site** per §2c shipped. The 4-state shell stays; sub-render logic is internal.
- [ ] **VariantCard plain `useState/useEffect` pattern** (§2c correction #4) — Strategies/Detail.tsx has no QueryClientProvider. Sub-renders use the same pattern.
- [ ] **`workbench_paper_variant_metrics` location** at `apps/mcp-workbench/src/mcp_workbench/server.py`. Additive response fields; tool count stays 19.
- [ ] **Build-server tool count test** asserts 19 (per §2b-variant shipped). No change.
- [ ] **`audit_immutability` invariant** — additive payload fields (evidence-bundle hash) are safe; the invariant tests hash-chain integrity, not payload schema. Confirm green.
- [ ] **§2b's `_maybe_auto_validate_proposal` hook location** — `app/api/v1/proposals.py` PATCH endpoint per §2b shipped. The lockout check inserts here before the spawn call. Also the manual `POST /validate` endpoint needs the same check.
- [ ] **Hashing import** — `hashlib.sha256` + `json.dumps(bundle, sort_keys=True)` for the evidence-bundle hash. Verify no dep is needed.

---

## Candid acknowledgment — what this session plan cannot predict

- **`promoting_at` column choice: scoped vs general `transitioned_at`.** v0.1 leans scoped (`promoting_at` only set on PROMOTING transition; null otherwise). General `transitioned_at` (updated on every state change) is more reusable but has wider blast radius. If existing codebase already has a generic transition-timestamp column, reuse. Verify at code-paste time.
- **Evidence-bundle hash semantics.** v1: `hashlib.sha256(json.dumps(bundle_dict, sort_keys=True).encode()).hexdigest()`. The hash is for tamper-evidence — anyone with the proposal row + audit row can verify the bundle hasn't been mutated post-promote. If ADR specifies a particular algorithm or canonicalization, adjust. v1 uses sort_keys=True for deterministic ordering.
- **Mechanical promote: params merge semantics.** Same as `apply_proposal`? Or proposal payload's params overwrite parent's params wholesale? §3a's evidence bundle includes `param_diff` (per ADR's evidence bundle requirements §66-74). The merge should reflect that diff exactly. Verify against `apply_proposal` semantics.
- **Promote precondition race.** Between user click and endpoint execution, parent could leave LIVE (D8 invalidation fires; variant terminates). v1: re-check at endpoint entry, return 409 if check fails. If race produces in-progress state (variant being terminated), endpoint sees variant gone → 409. UI refreshes on error.
- **Cooldown cron: variant termination on PROMOTED.** When PROMOTING → PROMOTED fires, the variant strategy is terminated. v1: cron calls `PaperVariantService.terminate_for_parent(session, parent_id, reason="promoted")`. The terminate handles engine unregister, audit row, etc. Per §2a shipped pattern.
- **Cooldown cron + manual cancel race.** User clicks cancel exactly when the cooldown cron is processing the proposal. Two paths could transition out of PROMOTING. v1: cancel endpoint locks the proposal row (`with_for_update`); cron's sweep skips rows that are no longer PROMOTING. Idempotent.
- **Variant params_json content.** The proposal's params_json IS the variant's params_json (per §2a's spawn logic). On promotion, we apply proposal.params_json to parent — same source. No drift between "what variant ran" and "what gets promoted."
- **30-day lockout interpretation.** v1: `parent.last_promoted_at + 30 days > now()` is the lockout condition. Strict greater-than means "exactly 30 days later, lockout expires." If ADR specifies "after 30 days" or "30 days or more," adjust the comparison operator. v1 uses `>=` for last_promoted_at + 30d ≤ now (lockout expired).
- **Reject-promotion variant termination idempotency.** If user clicks Reject during EVIDENCE_READY, variant terminates. If user clicks Reject during PROMOTING, variant ALSO terminates (cooldown was running on a variant that's no longer needed). Both paths: same terminate call. Already-terminated variant: terminate_for_parent is a no-op per §2a.
- **MCP `eligible_for_promotion` race.** Field computed at MCP-call time. If parent transitions out of LIVE between MCP call and agent action, the agent acts on stale field. Acceptable: agent's action (if any) hits the same 409 precondition. Document.
- **Lockout countdown in UI.** Lockout-aware empty state shows "until {last_promoted_at + 30 days}". Timezone presentation: convert to user's locale via standard `toLocaleString()`. The 30 days is calendar days, not business days (per ADR — verify).

---

## Goal

After §3b-promote ships:

- A user with an EVIDENCE_READY proposal sees the evidence summary in VariantCard with "Promote" and "Reject" buttons.
- Clicking Promote: 409s if parent isn't LIVE or is in lockout; else transitions EVIDENCE_READY → PROMOTING, sets `proposal.promoting_at = now`, writes audit row with `from`/`to`/`bundle_hash` payload.
- Within the next 15 minutes after `promoting_at + 24h`, the cooldown cron picks up the proposal, mutates `parent.params_json` (per the proposal's payload), sets `parent.last_promoted_at = now`, terminates the paper variant, transitions PROMOTING → PROMOTED, writes two audit rows (STRATEGY_PROPOSAL_TRANSITIONED + STRATEGY_PROMOTED), two commits.
- During PROMOTING, parent strategy runs OLD params; variant is terminated at PROMOTING entry (per v0.1 DEVIATION FLAG #1 — simplification; literal ADR has variant alive-but-engine-paused). The bundle preserves variant history.
- Re-clicking Promote during PROMOTING: 409 (proposal not in EVIDENCE_READY).
- Clicking Cancel during PROMOTING: transitions PROMOTING → REJECTED (terminal); variant remains terminated (was terminated on PROMOTING entry).
- Clicking Reject during EVIDENCE_READY: transitions EVIDENCE_READY → REJECTED; terminates variant.
- Attempting `POST /proposals/{id}/validate` on a strategy in 30-day lockout: 409 with message "Strategy in 30-day post-promotion lockout until {last_promoted_at + 30d}".
- The §2b `_maybe_auto_validate_proposal` hook: silently skips when parent in lockout (no error; logged).
- `workbench_paper_variant_metrics` returns four additive fields enabling the agent to see evidence bundle + lifecycle state + promotion eligibility + lockout date.
- All §2+§3a mechanics unchanged.
- All 13 CI invariants + 3 coverage gates green.
- Paper smoke from P1-P5 byte-identical.
- `p6b-session3b-promote-complete` tagged. After cross-session verification, `p6b-session3-promote-complete` tagged.

---

## §3b-promote.1 — Migration

Create `apps/backend/alembic/versions/[YYYY_MM_DD]_p6b_3b_promotion_timestamp.py`:

```python
"""P6b §3b: promoting_at timestamp on strategy_proposals.

Revision ID: [auto]
Revises: [§3a head]
Create Date: [auto]
"""
from alembic import op
import sqlalchemy as sa


revision = "[auto]"
down_revision = "[§3a head]"


def upgrade() -> None:
    with op.batch_alter_table("strategy_proposals") as batch_op:
        batch_op.add_column(
            sa.Column(
                "promoting_at", sa.DateTime(timezone=True), nullable=True,
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("strategy_proposals") as batch_op:
        batch_op.drop_column("promoting_at")
```

Update `app/db/models/strategy_proposal.py` (per §3a correction #3 — this is where `ProposalState` lives):

```python
class StrategyProposal(Base):
    # ... existing fields ...
    # NEW in P6b §3b (set on PROMOTING transition; read by cooldown cron).
    promoting_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, default=None,
    )
```

Also define the lockout constant in a new `app/services/promotion.py` (the action service):

```python
"""P6b §3b: promotion action service + lockout constant."""
# Per ADR 0007: "at least 30 days" — hardcoded, not envelope-tunable.
PROMOTION_LOCKOUT_DAYS = 30
```

**Verify before pasting:**
- `[§3a head]` revision ID from §3a's migration.
- SQLite `batch_alter_table` pattern matches §3a's migration (per §3a deviation: `batch_alter_table` was used for `last_promoted_at` add).

---

## §3b-promote.2 — Promote endpoint

Add to `apps/backend/app/api/v1/proposals.py::proposals_router`:

```python
"""POST /api/v1/proposals/{id}/promote

EVIDENCE_READY → PROMOTING.
Preconditions:
  - proposal.state == EVIDENCE_READY
  - parent strategy.status == LIVE
  - parent.last_promoted_at + 30 days < now (not in lockout)

Side effects (single commit per audit-hash-chain contract):
  - proposal.state = PROMOTING
  - proposal.promoting_at = now
  - terminate variant (per ADR: "new variant submits no orders" during cooldown)
  - audit STRATEGY_PROPOSAL_TRANSITIONED with bundle hash in payload

Per ADR 0007: promotion is always user-gated. No envelope flag exists.
"""
import hashlib
import json
from datetime import datetime, timedelta, UTC

from fastapi import HTTPException, Request

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.services.paper_variant import find_in_flight_variant, PaperVariantService
from app.services.promotion import PROMOTION_LOCKOUT_DAYS


def _bundle_hash(bundle: dict) -> str:
    """SHA-256 of canonicalized bundle JSON for audit tamper-evidence."""
    canonical = json.dumps(bundle, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _in_lockout(parent: Strategy, now: datetime) -> bool:
    """True iff parent is within 30-day post-promotion lockout window."""
    if parent.last_promoted_at is None:
        return False
    lockout_expires = parent.last_promoted_at + timedelta(days=PROMOTION_LOCKOUT_DAYS)
    return lockout_expires > now


@proposals_router.post(
    "/{proposal_id}/promote",
    response_model=dict,
)
async def promote_proposal(
    proposal_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """User-gated promotion: EVIDENCE_READY → PROMOTING with 24h cooldown.

    Per ADR 0007: always user-gated; never auto. No envelope flag.
    """
    proposal = await session.get(StrategyProposal, proposal_id)
    if proposal is None or proposal.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")

    # Precondition: state must be EVIDENCE_READY.
    if proposal.state != ProposalState.EVIDENCE_READY:
        raise HTTPException(
            status_code=400,
            detail=f"Proposal must be in EVIDENCE_READY to promote (current: {proposal.state})",
        )

    parent = await session.get(Strategy, proposal.strategy_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent strategy not found")

    # Precondition: parent must be LIVE.
    if parent.status != StrategyStatus.LIVE:
        raise HTTPException(
            status_code=409,
            detail=f"Parent strategy must be LIVE to promote (current: {parent.status})",
        )

    now = datetime.now(UTC)

    # Precondition: parent must NOT be in 30-day lockout.
    if _in_lockout(parent, now):
        lockout_expires = parent.last_promoted_at + timedelta(days=PROMOTION_LOCKOUT_DAYS)
        raise HTTPException(
            status_code=409,
            detail=f"Strategy in 30-day post-promotion lockout until {lockout_expires.isoformat()}",
        )

    # Read the current evidence bundle (refreshed by §3a's brief-pass).
    eval_state = dict(proposal.evaluation_results_json or {})
    bundle = eval_state.get("evidence_bundle")
    if bundle is None:
        # Defensive: EVIDENCE_READY state without bundle is an inconsistent
        # state (shouldn't happen if §3a's brief-pass is healthy).
        raise HTTPException(
            status_code=409,
            detail="Proposal lacks evidence bundle (re-evaluate via morning brief)",
        )

    bundle_hash = _bundle_hash(bundle)

    # Transition: EVIDENCE_READY → PROMOTING.
    proposal.state = ProposalState.PROMOTING
    proposal.promoting_at = now

    # Audit row with bundle hash embedded (ADR 0007 requirement).
    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
        target_type="strategy_proposal",
        target_id=proposal.id,
        payload={
            "proposal_id": proposal.id,
            "from": "EVIDENCE_READY",
            "to": "PROMOTING",
            "trigger": "user_promoted",
            "evidence_bundle_hash": bundle_hash,
            "cooldown_expires_at": (
                now + timedelta(hours=24)   # ACTIVATION_COOLDOWN_HOURS
            ).isoformat(),
        },
        user_id=current_user.id,
    )

    # Terminate variant (per ADR: "new variant submits no orders" during cooldown).
    engine = getattr(request.app.state, "strategy_engine", None)
    variant = await find_in_flight_variant(session, parent.id)
    if variant is not None:
        await PaperVariantService(session, engine).terminate(
            variant_id=variant.id,
            reason="promotion_started",
        )

    await session.commit()

    return {
        "status": "promoting",
        "proposal_id": proposal.id,
        "promoting_at": now.isoformat(),
        "cooldown_expires_at": (now + timedelta(hours=24)).isoformat(),
    }
```

**Verify before pasting:**
- `ACTIVATION_COOLDOWN_HOURS = 24` import from `app/services/activation.py` (per Q2 confirmation). Replace the inline `hours=24` with the imported constant.
- `PaperVariantService.terminate` signature per §2a — does it commit internally? Per §2b shipped, `terminate_for_parent` commits. If `.terminate(variant_id=...)` also commits, the audit row above + the terminate are two separate commits (correct per hash-chain contract).

---

## §3b-promote.3 — Reject-promotion endpoint

Same router. Handles both EVIDENCE_READY and PROMOTING source states.

```python
"""POST /api/v1/proposals/{id}/reject-promotion

Accepts source state ∈ {EVIDENCE_READY, PROMOTING}.
Transitions → REJECTED (terminal); terminates paper variant.
ADR 0007: frictionless cancel during the full 24h cooldown.
"""

@proposals_router.post(
    "/{proposal_id}/reject-promotion",
    response_model=dict,
)
async def reject_promotion(
    proposal_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """User-initiated rejection — handles both 'Reject evidence' (from
    EVIDENCE_READY) and 'Cancel cooldown' (from PROMOTING)."""
    proposal = await session.get(StrategyProposal, proposal_id)
    if proposal is None or proposal.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if proposal.state not in (ProposalState.EVIDENCE_READY, ProposalState.PROMOTING):
        raise HTTPException(
            status_code=400,
            detail=f"Proposal must be in EVIDENCE_READY or PROMOTING to reject (current: {proposal.state})",
        )

    from_state = proposal.state.value
    now = datetime.now(UTC)
    proposal.state = ProposalState.REJECTED

    # Audit row.
    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
        target_type="strategy_proposal",
        target_id=proposal.id,
        payload={
            "proposal_id": proposal.id,
            "from": from_state,
            "to": "REJECTED",
            "trigger": (
                "user_rejected_evidence"
                if from_state == "EVIDENCE_READY"
                else "user_cancelled_promotion"
            ),
        },
        user_id=current_user.id,
    )

    # Terminate variant if still in flight (terminate is idempotent).
    engine = getattr(request.app.state, "strategy_engine", None)
    parent = await session.get(Strategy, proposal.strategy_id)
    if parent is not None:
        variant = await find_in_flight_variant(session, parent.id)
        if variant is not None:
            await PaperVariantService(session, engine).terminate(
                variant_id=variant.id,
                reason=(
                    "evidence_rejected"
                    if from_state == "EVIDENCE_READY"
                    else "promotion_cancelled"
                ),
            )

    await session.commit()
    return {
        "status": "rejected",
        "proposal_id": proposal.id,
        "from_state": from_state,
    }
```

---

## §3b-promote.4 — Cooldown completion cron

Create `apps/backend/app/jobs/promotion_completion.py`, mirroring `app/jobs/activation_completion.py`.

```python
"""P6b §3b cooldown completion sweep.

Mirrors app/jobs/activation_completion.py (PENDING_LIVE → LIVE):
- 15-minute APScheduler sweep
- Finds PROMOTING proposals where promoting_at + 24h <= now
- Calls mechanical-promote action → transitions to PROMOTED
"""
from datetime import datetime, timedelta, UTC

import structlog
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.services.activation import ACTIVATION_COOLDOWN_HOURS
from app.services.promotion import execute_mechanical_promote


logger = structlog.get_logger(__name__)


async def run_promotion_completion_sweep(*, session_factory, engine) -> dict:
    """Singleton 15-minute sweep — finds and completes elapsed PROMOTING proposals."""
    now = datetime.now(UTC)
    cooldown = timedelta(hours=ACTIVATION_COOLDOWN_HOURS)
    promoted_count = 0
    errored_count = 0

    async with session_factory() as session:
        # Find PROMOTING proposals where cooldown elapsed.
        proposals = list((await session.execute(
            select(StrategyProposal)
            .where(StrategyProposal.state == ProposalState.PROMOTING)
            .where(StrategyProposal.promoting_at.isnot(None))
            .with_for_update(skip_locked=True)   # avoid race with manual cancel
        )).scalars().all())

        for proposal in proposals:
            if proposal.promoting_at + cooldown > now:
                continue   # still in cooldown

            try:
                await execute_mechanical_promote(
                    session, proposal=proposal, engine=engine,
                )
                promoted_count += 1
            except Exception as exc:
                logger.warning(
                    "promotion_completion_failed",
                    proposal_id=proposal.id, error=str(exc),
                )
                errored_count += 1
                await session.rollback()
                continue

    logger.info(
        "promotion_completion_sweep_done",
        promoted=promoted_count, errored=errored_count,
    )
    return {"promoted": promoted_count, "errored": errored_count}


def register_promotion_completion_job(
    workbench_scheduler, session_factory, engine,
) -> None:
    """Register the 15-minute completion cron."""
    workbench_scheduler.scheduler.add_job(
        run_promotion_completion_sweep,
        kwargs={"session_factory": session_factory, "engine": engine},
        trigger=CronTrigger(minute="*/15"),
        id="promotion_completion",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    logger.info("promotion_completion_job_registered")
```

Register in `app/lifespan.py` alongside other crons (inside alpaca-enabled block):

```python
from app.jobs.promotion_completion import register_promotion_completion_job

register_promotion_completion_job(
    app.state.scheduler, session_factory, app.state.strategy_engine,
)
```

**Verify before pasting:**
- `ACTIVATION_COOLDOWN_HOURS` exact name + path per Q2.
- Existing cron registration block in `lifespan.py` per §2a/§2b shipped.

---

## §3b-promote.5 — Mechanical promote action

Add to `app/services/promotion.py`:

```python
"""Mechanical promotion action — called by the cooldown completion cron.

v1 deviation from ADR 0007's literal model: applies proposal params to
parent strategy (same merge as apply_proposal); doesn't archive strategy
version. Audit log + proposal record preserve the history.
"""
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.services.paper_variant import find_in_flight_variant, PaperVariantService


async def execute_mechanical_promote(
    session: AsyncSession,
    proposal: StrategyProposal,
    engine,
) -> None:
    """PROMOTING → PROMOTED: merge params, set last_promoted_at, write audits.

    Caller manages transaction. Writes two audit rows in separate commits per
    audit-hash-chain contract: STRATEGY_PROPOSAL_TRANSITIONED first, then
    STRATEGY_PROMOTED marker.
    """
    parent = await session.get(Strategy, proposal.strategy_id)
    if parent is None:
        raise ValueError(f"Parent strategy {proposal.strategy_id} not found")

    if parent.status != StrategyStatus.LIVE:
        # Parent left LIVE during cooldown (manual deactivate); abort promote.
        # Transition proposal to REJECTED via the same exit path.
        raise ValueError(
            f"Parent strategy no longer LIVE (current: {parent.status}); "
            f"promotion aborted. Proposal must be manually rejected."
        )

    now = datetime.now(UTC)

    # 1) Merge proposal params into parent params_json.
    # v1: full overwrite from proposal payload's params (matches apply_proposal).
    # Per Candid Acknowledgment: verify against apply_proposal merge semantics.
    proposal_payload = proposal.proposal_payload or {}
    new_params = proposal_payload.get("params", {})
    existing_params = dict(parent.params_json or {})
    parent.params_json = {**existing_params, **new_params}

    # 2) Set last_promoted_at on parent (powers 30-day lockout).
    parent.last_promoted_at = now

    # 3) Transition proposal: PROMOTING → PROMOTED.
    proposal.state = ProposalState.PROMOTED

    # 4) Audit row 1: state transition.
    AuditLogger.write(
        session,
        actor_type=AuditActorType.AGENT,   # cron is system-driven
        actor_id="promotion_completion",
        action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
        target_type="strategy_proposal",
        target_id=proposal.id,
        payload={
            "proposal_id": proposal.id,
            "from": "PROMOTING",
            "to": "PROMOTED",
            "trigger": "cooldown_elapsed",
            "completed_at": now.isoformat(),
        },
        user_id=proposal.user_id,
    )
    await session.commit()   # commit 1

    # 5) Audit row 2: STRATEGY_PROMOTED marker (separate commit per hash-chain).
    AuditLogger.write(
        session,
        actor_type=AuditActorType.AGENT,
        actor_id="promotion_completion",
        action=AuditAction.STRATEGY_PROMOTED,
        target_type="strategy",
        target_id=parent.id,
        payload={
            "parent_strategy_id": parent.id,
            "proposal_id": proposal.id,
            "promoted_at": now.isoformat(),
            "new_params": new_params,
        },
        user_id=proposal.user_id,
    )
    await session.commit()   # commit 2
```

---

## §3b-promote.6 — Lockout enforcement (in `/validate` + auto-validate hook)

In `apps/backend/app/api/v1/proposals.py`, modify the existing `POST /proposals/{id}/validate` endpoint AND the `_maybe_auto_validate_proposal` helper from §2b shipped:

```python
"""Lockout enforcement at the spawn point (per Q5 ADR correction).

ADR 0007: lockout blocks starting a new evaluation cycle, not ACCEPT.
Hook fires in /validate (manual spawn) AND _maybe_auto_validate_proposal
(auto-spawn hook from §2b).
"""
from datetime import timedelta

from app.services.promotion import PROMOTION_LOCKOUT_DAYS


def _check_lockout(parent: Strategy) -> tuple[bool, str | None]:
    """Returns (in_lockout, expires_iso_or_none)."""
    if parent.last_promoted_at is None:
        return False, None
    now = datetime.now(UTC)
    lockout_expires = parent.last_promoted_at + timedelta(days=PROMOTION_LOCKOUT_DAYS)
    if lockout_expires > now:
        return True, lockout_expires.isoformat()
    return False, None


# Modify the existing POST /proposals/{id}/validate endpoint:
@proposals_router.post("/{proposal_id}/validate")
async def validate_proposal(...):
    # ... existing logic to look up proposal and parent ...
    
    # NEW in §3b: lockout check.
    in_lockout, expires_at = _check_lockout(parent)
    if in_lockout:
        raise HTTPException(
            status_code=409,
            detail=f"Strategy in 30-day post-promotion lockout until {expires_at}",
        )
    
    # ... existing spawn logic ...


# Modify §2b's _maybe_auto_validate_proposal helper:
async def _maybe_auto_validate_proposal(
    session: AsyncSession,
    proposal: StrategyProposal,
    current_user: CurrentUser,
    engine,
) -> None:
    """D5: auto-spawn paper variant on ACCEPT if envelope flag enabled.
    
    NEW in §3b: silently skip if parent in lockout (no error; logged).
    """
    profile = await TradingProfileService(session).get(current_user.id)
    envelope = profile.agent_envelope or {}
    if not envelope.get("auto_validate_proposals", False):
        return

    parent = await session.get(Strategy, proposal.strategy_id)
    if parent is None or parent.status != StrategyStatus.LIVE:
        return

    # NEW: lockout check (silent skip).
    in_lockout, expires_at = _check_lockout(parent)
    if in_lockout:
        logger.info(
            "auto_validate_skipped_lockout",
            strategy_id=parent.id, proposal_id=proposal.id,
            lockout_expires_at=expires_at,
        )
        return

    # ... existing spawn logic ...
```

---

## §3b-promote.7 — VariantCard sub-renders + lockout-aware empty state

Extend `apps/frontend/src/components/strategies/VariantCard.tsx` (per §2c shipped — `@/components/strategies/` path).

```typescript
"""Per Q8: 4-state shell preserved (loading / empty / eligible / active);
inside 'active', sub-render based on proposal.state.

NEW in §3b:
  - Lockout-aware empty state (read parent.last_promoted_at)
  - EVIDENCE_READY sub-render: evidence summary + Promote + Reject buttons
  - PROMOTING sub-render: countdown + Cancel button
  - PROMOTED sub-render: terminal display
"""
import { useState, useEffect } from "react";
import { variantsApi, proposalsApi } from "@/api/...";
import type { Strategy, Proposal } from "@/api/types";

// Existing imports + state from §2c.

export function VariantCard({ strategy }: Props) {
  // ... existing useState/useEffect from §2c ...

  // NEW: derive lockout state.
  const inLockout = strategy.last_promoted_at && (
    new Date(strategy.last_promoted_at).getTime() + 30 * 24 * 60 * 60 * 1000 > Date.now()
  );
  const lockoutExpiresAt = strategy.last_promoted_at
    ? new Date(new Date(strategy.last_promoted_at).getTime() + 30 * 24 * 60 * 60 * 1000)
    : null;

  // ... existing loading / state-machine logic ...

  // Lockout-aware empty state:
  if (!status?.comparison && !eligibleProposal) {
    if (inLockout && lockoutExpiresAt) {
      return (
        <div className="...">
          <h4>Validation</h4>
          <p>
            Strategy is in 30-day post-promotion lockout until{" "}
            {lockoutExpiresAt.toLocaleDateString()}. New validation cycles can
            start after that date.
          </p>
        </div>
      );
    }
    return (
      <div className="...">
        <h4>Validation</h4>
        <p>No active validation. Accept a proposal on this LIVE strategy to enable paper-variant validation.</p>
      </div>
    );
  }

  // ... existing eligible-proposal display ...

  // Active state: sub-render based on proposal.state.
  if (status?.comparison) {
    const proposal = status.comparison.proposal_state;   // from MCP additive field
    
    if (proposal === "EVALUATING") {
      return <EvaluatingDisplay comparison={status.comparison} onStop={onStop} />;
    }
    if (proposal === "EVIDENCE_READY") {
      return (
        <EvidenceReadyDisplay
          comparison={status.comparison}
          onPromote={onPromote}
          onReject={onReject}
          actionPending={actionPending}
        />
      );
    }
    if (proposal === "PROMOTING") {
      return (
        <PromotingDisplay
          comparison={status.comparison}
          promotingAt={status.comparison.promoting_at}
          onCancel={onCancel}
          actionPending={actionPending}
        />
      );
    }
    if (proposal === "PROMOTED") {
      return <PromotedDisplay comparison={status.comparison} />;
    }
  }
}

// New action handlers:
const onPromote = async () => {
  if (!confirm("Promote this proposal? 24-hour cooldown begins now.")) return;
  setActionPending(true);
  try {
    await variantsApi.promote(eligibleProposal?.id ?? status.comparison?.spawn_proposal_id);
    await refresh();
  } catch (e: any) {
    setActionError(e?.message ?? "Failed to promote");
  } finally {
    setActionPending(false);
  }
};

const onReject = async () => {
  if (!confirm("Reject this evidence? The proposal will be terminal.")) return;
  // ... same shape, calls variantsApi.rejectPromotion(...)
};

const onCancel = async () => {
  if (!confirm("Cancel the promotion? The proposal will be terminal.")) return;
  // ... same shape, calls variantsApi.rejectPromotion(...) — same endpoint
};

// Sub-render components:
function EvidenceReadyDisplay({comparison, onPromote, onReject, actionPending}) {
  const bundle = comparison.evidence_bundle;   // MCP additive field
  return (
    <div>
      <span>Evidence ready for review</span>
      <GateResultsTable gateResults={bundle?.gate_results} />
      <button onClick={onPromote} disabled={actionPending}>
        {actionPending ? "Promoting..." : "Promote"}
      </button>
      <button onClick={onReject} disabled={actionPending}>
        Reject
      </button>
    </div>
  );
}

function PromotingDisplay({comparison, promotingAt, onCancel, actionPending}) {
  const cooldownExpires = new Date(new Date(promotingAt).getTime() + 24*60*60*1000);
  return (
    <div>
      <span>Promotion in progress</span>
      <p>Live at {cooldownExpires.toLocaleString()}</p>
      <button onClick={onCancel} disabled={actionPending}>Cancel</button>
    </div>
  );
}

function PromotedDisplay({comparison}) {
  return <div>Promoted on {/* parent.last_promoted_at */}</div>;
}
```

(Sketch — Tailwind classes per §2c convention. Full implementation includes state-machine refinements.)

---

## §3b-promote.8 — MCP additive fields

In `apps/mcp-workbench/src/mcp_workbench/server.py`, extend the existing `workbench_paper_variant_metrics` function — backend endpoint extension first:

Extend `GET /api/v1/strategies/{id}/variant-comparison` response in `proposals.py`:

```python
# Existing endpoint from §2b/§2c; add four fields to the response dict:
async def get_variant_comparison(...):
    # ... existing logic ...
    
    # NEW in §3b additive fields:
    response["evidence_bundle"] = eval_state.get("evidence_bundle")
    response["proposal_state"] = proposal.state.value
    response["eligible_for_promotion"] = (
        proposal.state == ProposalState.EVIDENCE_READY
        and not _in_lockout(parent, datetime.now(UTC))
    )
    response["parent_last_promoted_at"] = (
        parent.last_promoted_at.isoformat()
        if parent.last_promoted_at else None
    )
    
    return response
```

MCP tool passes through (no MCP code change beyond the additive response shape). Tool count stays 19.

Update `apps/mcp-workbench/CLAUDE.md` decision-tree description for `workbench_paper_variant_metrics` to mention the new fields.

---

## §3b-promote.9 — Tests

### Backend (`apps/backend/tests/api/test_promote_endpoint.py`)

**Non-negotiable:**
- `test_no_auto_promote_envelope_flag_exists` — grep the codebase for `auto_promote`; should be zero hits (no flag anywhere).

**Endpoint:**
- `test_promote_evidence_ready_transitions_to_promoting`
- `test_promote_sets_promoting_at`
- `test_promote_writes_audit_with_bundle_hash`
- `test_promote_terminates_variant`
- `test_promote_409_when_parent_not_live`
- `test_promote_409_when_parent_in_lockout`
- `test_promote_400_when_proposal_not_evidence_ready`
- `test_promote_404_for_other_user`
- `test_promote_409_when_no_evidence_bundle` (defensive)

### Reject endpoint (`tests/api/test_reject_promotion_endpoint.py`)

- `test_reject_from_evidence_ready_transitions_to_rejected`
- `test_reject_from_promoting_transitions_to_rejected`
- `test_reject_terminates_variant`
- `test_reject_400_from_other_states`
- `test_reject_audit_payload_includes_from_state`

### Cooldown cron (`tests/services/test_promotion_completion.py`)

- `test_sweep_finds_elapsed_promoting`
- `test_sweep_skips_not_yet_elapsed`
- `test_sweep_calls_mechanical_promote`
- `test_sweep_handles_per_proposal_errors`
- `test_sweep_idempotent_on_already_promoted` (race)

### Mechanical promote (`tests/services/test_mechanical_promote.py`)

- `test_promote_merges_params_into_parent`
- `test_promote_sets_last_promoted_at`
- `test_promote_writes_two_audit_rows_two_commits`
- `test_promote_strategy_promoted_payload_includes_new_params`
- `test_promote_raises_when_parent_no_longer_live`

### Lockout (`tests/api/test_lockout_enforcement.py`)

- `test_validate_409_within_30_day_lockout`
- `test_validate_succeeds_after_30_days`
- `test_auto_validate_silently_skipped_in_lockout`
- `test_lockout_does_not_block_accept_transition` (Q5 correction guard)
- `test_lockout_does_not_block_propose_or_draft` (Q5 correction guard)

### MCP additive (`tests/api/test_variant_comparison_additive_fields.py`)

- `test_evidence_bundle_field_present_when_set`
- `test_proposal_state_field_present`
- `test_eligible_for_promotion_true_when_evidence_ready_no_lockout`
- `test_eligible_for_promotion_false_in_lockout`
- `test_parent_last_promoted_at_field_present`
- `test_existing_response_fields_unchanged_additive`

### Frontend (`apps/frontend/src/components/strategies/__tests__/VariantCard.test.tsx`)

- `renders evidence-ready sub-state with promote + reject buttons`
- `renders promoting sub-state with cancel button and countdown`
- `renders promoted sub-state as terminal`
- `renders lockout-aware empty state when parent in lockout`
- `promote click calls promote API and refreshes`
- `reject click calls reject-promotion API`
- `cancel click calls reject-promotion API` (same endpoint)
- `lockout countdown displays correctly`

---

## §3b-promote.10 — Manual smoke

```bash
# 0. Prerequisites
git describe --tags --abbrev=0   # expect: p6b-session3a-gate-complete

# 1. Migration round-trip
cd apps/backend && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && cd ../..

# 2. Bring up stack
docker compose up -d
sleep 30
./scripts/login_helper.sh

# 3. Need an EVIDENCE_READY proposal. From §3a smoke + brief eval:
PROP_ID=$(curl -s -b /tmp/cookies.txt \
  "http://127.0.0.1:8000/api/v1/proposals?state=EVIDENCE_READY&limit=1" \
  | jq -r '.items[0].id')

# 4. Test no-auto-promote (the load-bearing invariant)
docker compose exec backend uv run python -c "
import inspect
from app.services.promotion import *
from app.api.v1 import proposals
# Grep for 'auto_promote' — should fail
import subprocess
r = subprocess.run(['grep', '-rn', 'auto_promote', 'app/'], capture_output=True, text=True)
print('grep auto_promote:', r.stdout)
assert 'auto_promote' not in r.stdout, 'Auto-promote should not exist'
print('OK: no auto_promote in codebase')
"

# 5. Promote endpoint
curl -s -b /tmp/cookies.txt -X POST \
  "http://127.0.0.1:8000/api/v1/proposals/${PROP_ID}/promote" | jq
# Expect: {status: "promoting", promoting_at, cooldown_expires_at}

# 6. Verify state + audit
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT state, promoting_at FROM strategy_proposals WHERE id=${PROP_ID};"
# Expect: state=PROMOTING, promoting_at set

docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT json_extract(payload_json, '\$.evidence_bundle_hash') AS bundle_hash,
       json_extract(payload_json, '\$.to') AS to_state
FROM audit_log
WHERE action='STRATEGY_PROPOSAL_TRANSITIONED'
  AND json_extract(payload_json, '\$.to')='PROMOTING'
ORDER BY id DESC LIMIT 1;"
# Expect: bundle_hash set (64-char hex), to_state=PROMOTING

# 7. Re-promote 400
curl -s -b /tmp/cookies.txt -X POST \
  "http://127.0.0.1:8000/api/v1/proposals/${PROP_ID}/promote" | jq
# Expect: 400 (already PROMOTING)

# 8. Cancel (reject-promotion from PROMOTING)
curl -s -b /tmp/cookies.txt -X POST \
  "http://127.0.0.1:8000/api/v1/proposals/${PROP_ID}/reject-promotion" | jq
# Expect: {status: "rejected", from_state: "PROMOTING"}

# 9. Re-create an EVIDENCE_READY proposal for the cooldown test
# (set promoting_at = now - 25h to simulate elapsed cooldown):
docker compose exec backend uv run python -c "
import asyncio
from datetime import datetime, timedelta, UTC
from app.db.session import get_sessionmaker

async def main():
    factory = get_sessionmaker()
    async with factory() as session:
        # Find a PROMOTING proposal (or set one up); rewind promoting_at
        ...
"

# 10. Trigger the completion cron manually
docker compose exec backend uv run python -c "
import asyncio
from app.db.session import get_sessionmaker
from app.jobs.promotion_completion import run_promotion_completion_sweep

async def main():
    factory = get_sessionmaker()
    result = await run_promotion_completion_sweep(
        session_factory=factory, engine=None,
    )
    print(result)

asyncio.run(main())
"
# Expect: {promoted: 1, errored: 0}

# 11. Verify PROMOTED + last_promoted_at + audit
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT p.state, s.last_promoted_at
FROM strategy_proposals p JOIN strategies s ON p.strategy_id = s.id
WHERE p.id=${PROP_ID};"
# Expect: state=PROMOTED, last_promoted_at set

docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT action FROM audit_log
WHERE action IN ('STRATEGY_PROPOSAL_TRANSITIONED', 'STRATEGY_PROMOTED')
ORDER BY id DESC LIMIT 2;"
# Expect: both rows present (two commits)

# 12. Test lockout enforcement
# Try /validate on the just-promoted strategy:
STRAT_ID=$(curl -s -b /tmp/cookies.txt "http://127.0.0.1:8000/api/v1/proposals/${PROP_ID}" | jq -r '.strategy_id')
NEW_PROP_ID=$(...)   # create a new proposal on STRAT_ID
curl -s -b /tmp/cookies.txt -X POST \
  "http://127.0.0.1:8000/api/v1/proposals/${NEW_PROP_ID}/validate" | jq
# Expect: 409 with lockout message

# 13. MCP additive fields
curl -s -b /tmp/cookies.txt \
  "http://127.0.0.1:8000/api/v1/strategies/${STRAT_ID}/variant-comparison" \
  | jq '{evidence_bundle: (.comparison.evidence_bundle != null), proposal_state, eligible_for_promotion, parent_last_promoted_at}'

# 14. UI smoke
# - /strategies/{id}: VariantCard shows lockout-aware empty (after promote)
# - For a strategy with EVIDENCE_READY: card shows Promote + Reject
# - Click Promote: confirm dialog, transitions to PROMOTING display with countdown
# - Click Cancel: confirm, transitions to terminal REJECTED

# 15. LOAD-BEARING: paper smoke byte-identical
# ... standard smoke ...
```

---

## §3b-promote.11 — Notes & gotchas

1. **NO AUTO-PROMOTE. Ever.** ADR 0007 explicitly forbids. The test `test_no_auto_promote_envelope_flag_exists` greps the codebase. If a future contributor tries to add `auto_promote_validated`, the test fails. This is the load-bearing §3b invariant.

2. **Lockout blocks /validate, not /accept.** Q5 ADR correction. The LLM can still propose; the user can still accept; what's blocked is starting a new evaluation cycle. The lockout check fires in `POST /validate` AND in §2b's `_maybe_auto_validate_proposal` hook (silent skip).

3. **Cancel → REJECTED (terminal).** Q4 ADR correction. PROMOTING + EVIDENCE_READY both transition to REJECTED. Same audit shape, different `from_state` in payload, different trigger label.

4. **Mechanical promote = params merge, NOT strategy-version archiving.** v1 DEVIATION from ADR 0007's literal model. Flagged at top of doc for review. Audit log + proposal record preserve the history; full version-archiving deferred to a future ADR-faithful follow-up session.

5. **Evidence bundle hash in audit payload.** ADR 0007 requirement. SHA-256 of canonicalized bundle JSON; embedded in EVIDENCE_READY → PROMOTING audit row payload. Tamper-evidence for the promotion decision.

6. **Variant terminated on PROMOTING entry, not waited until PROMOTED.** Per ADR: "new variant submits no orders during cooldown." Mapped to v1: terminate the variant as soon as user clicks Promote. Variant's history is preserved in the evidence bundle (§3a captured at gate-pass). During cooldown, parent runs OLD params; on PROMOTED, parent params get merged with proposal's.

7. **Cooldown cron: 15-minute sweep, mirrors `activation_completion.py`.** Same APScheduler registration shape; same `with_for_update(skip_locked=True)` race protection.

8. **Cooldown elapsed = `promoting_at + ACTIVATION_COOLDOWN_HOURS <= now`.** Import the constant from `app/services/activation.py` per Q2 confirmation. Don't redefine.

9. **`PROMOTION_LOCKOUT_DAYS = 30` hardcoded** in `app/services/promotion.py`. Not envelope-configurable per ADR.

10. **Promote precondition re-check at endpoint entry.** Parent must be LIVE + not in lockout AT CLICK TIME, not just at EVIDENCE_READY transition. Race protection.

11. **One audit row per transaction.** Mechanical promote writes TWO audit rows (STRATEGY_PROPOSAL_TRANSITIONED + STRATEGY_PROMOTED) in TWO commits. Per §1a-drift hash-chain contract.

12. **VariantCard sub-rendering on `proposal.state` from MCP additive field.** No new card-level states; 4-state shell preserved. Sub-renders are internal.

13. **Lockout-aware empty state.** When `parent.last_promoted_at + 30d > now`, the card explains why no validation can start. Empty state ≠ silence here; it's an explanation.

14. **Frictionless cancel during full 24h cooldown.** No 5-minute grace; the whole cooldown is cancellable per ADR. Document.

15. **`apply_proposal` semantics unchanged.** §3b's mechanical promote uses the same merge as `apply_proposal` but is a separate code path triggered by cron, not user-clicked. The two paths coexist.

16. **MCP tool count stays at 19.** No new tools. The additive response fields flow through the existing passthrough.

17. **`audit_immutability` invariant additive-safe** for the new payload field (`evidence_bundle_hash`). Per §2b-rv pattern — invariant tests hash-chain integrity, not payload schema.

18. **`_router_token` discipline preserved.** §3b adds nothing to order-routing code.

19. **`check_workbench_mcp_readonly.sh` green.** No MCP code changes.

20. **`check_agent_no_db_access.sh` unaffected.** §3b adds nothing to `apps/agent/`.

21. **Walk-away ≥1h before merge.** The cron + mechanical-promote + lockout enforcement together require fresh re-read to catch edge cases.

22. **Standing cleanup-PR carry-forwards:** `check_p3_coverage.py --cov-report=xml` locally; explicit `git add` over `Docs/`.

23. **Evidence bundle completeness vs ADR 0007 §66-74.** ADR lists the full bundle as: param diff + LLM rationale + eval window + 4-criterion outcome + side-by-side metrics + trade-by-trade CSV + audit excerpt. §3a's `bundle_to_json` covers comparison + gate_results + window; param-diff + LLM-rationale are derivable from `proposal_payload` (already in the proposal row, not duplicated in bundle); trade-by-trade CSV is a UI export nicety deferred. The bundle hash in §3b's audit payload references whatever §3a captured; full-fidelity ADR bundle expansion is a §3a follow-up if needed.

---

## §3b-promote.12 — Commit and PR

Branch: `feat/p6b-session3b-promotion`. Single PR; walk-away ≥1 hour before merge.

Tag: `git tag -a p6b-session3b-promote-complete -m "P6b §3b-promote endpoint + reject + cooldown cron + lockout + UI + MCP"`.

After §3b-promote ships: run §3b-promote.14 cross-session verification and tag `p6b-session3-promote-complete` (rolls up §3a-gate + §3b-promote = P6b §3 complete).

---

## §3b-promote.13 — Verification Checklist (full session)

- [ ] §3b-p.1 Migration adds `proposal.promoting_at` column; round-trips cleanly; `PROMOTION_LOCKOUT_DAYS = 30` defined in `app/services/promotion.py`.
- [ ] §3b-p.2 Promote endpoint: state + LIVE + lockout preconditions; evidence-bundle hash embedded in audit payload; variant terminated on transition; single commit.
- [ ] §3b-p.3 Reject-promotion endpoint: handles both EVIDENCE_READY and PROMOTING source states; transitions to REJECTED; terminates variant; audit with from_state in payload.
- [ ] §3b-p.4 Cooldown cron mirrors `activation_completion.py`; 15-minute APScheduler; `with_for_update(skip_locked=True)` race protection; calls mechanical_promote.
- [ ] §3b-p.5 Mechanical promote: merges params; sets last_promoted_at; terminates variant; writes TWO audit rows in TWO commits.
- [ ] §3b-p.6 Lockout check in `/validate` AND `_maybe_auto_validate_proposal` (silent skip); does NOT block REVIEWING→ACCEPTED.
- [ ] §3b-p.7 VariantCard 4-state shell preserved; sub-renders on `proposal.state` for EVALUATING / EVIDENCE_READY / PROMOTING / PROMOTED; lockout-aware empty state.
- [ ] §3b-p.8 GET /variant-comparison response gains four additive fields; existing fields unchanged; MCP tool count stays 19.
- [ ] §3b-p.9 ~28 backend + ~8 frontend + ~2 MCP tests pass; non-negotiable `test_no_auto_promote_envelope_flag_exists` green.
- [ ] §3b-p.10 Manual smoke: promote → audit with bundle hash → cooldown cron → PROMOTED → lockout blocks /validate; paper smoke byte-identical.
- [ ] §3b-p.11 Notes & gotchas reviewed (especially "NO AUTO-PROMOTE" at the top).
- [ ] `_router_token` discipline preserved; ADR-0002 invariant green.
- [ ] `audit_immutability` invariant green.
- [ ] `check_agent_no_db_access.sh` unaffected; `check_workbench_mcp_readonly.sh` green.
- [ ] All 13 CI invariants + 3 coverage gates green; P3 gate verified locally with `--cov-report=xml`.
- [ ] §3b-p.12 PR merged; `p6b-session3b-promote-complete` tag pushed.
- [ ] §3b-p.14 P6b §3 cross-session verification passes; `p6b-session3-promote-complete` tag pushed.

---

## §3b-promote.14 — P6b §3 Cross-Session Verification

After §3b-promote merges, tag `p6b-session3-promote-complete` only after this passes.

```bash
git checkout main && git pull
git describe --tags --abbrev=0   # expect: p6b-session3b-promote-complete

# 1. All 13 CI invariants + 3 coverage gates green (full battery)
# (same battery as P6b §1 + §2 — repeat)

# 2. Full suite green (backend + agent + mcp-workbench + vitest)

# 3. Bring up stack
docker compose up -d && sleep 60

# 4. §3a gate: EVIDENCE_READY transition still fires in brief-pass
# (existing §3a smoke)

# 5. §3b gate: promote endpoint + cooldown + lockout end-to-end
./scripts/login_helper.sh
# Find EVIDENCE_READY proposal; promote; force cooldown; verify PROMOTED + lockout

# 6. All 9 P6+P6b audit actions present
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT DISTINCT action FROM audit_log
WHERE action IN (
  'STRATEGY_PROPOSAL_TRANSITIONED', 'AGENT_LLM_CALL_FAILED',
  'AGENT_BUDGET_REJECTED', 'AGENT_CADENCE_FIRED',
  'PROPOSAL_REVIEW_RECORDED', 'STRATEGY_DRIFT_DETECTED',
  'PAPER_VARIANT_SPAWNED', 'PAPER_VARIANT_TERMINATED',
  'STRATEGY_PROMOTED'
) ORDER BY action;"

# 7. Test no-auto-promote (load-bearing P6b §3 invariant)
grep -rn 'auto_promote' apps/ && echo "FAIL: auto-promote exists" || echo "OK: no auto-promote"

# 8. Paper smoke byte-identical
# ... standard ...

docker compose down

# 9. Tag rollup
git tag -a p6b-session3-promote-complete -m "P6b §3 complete — promotion gate + endpoint + cooldown + lockout"
git push origin p6b-session3-promote-complete
```

---

# Results template stub — fill at execution time

```markdown
# P6b Session 3b-promote — Results (go / no-go record)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | [YYYY-MM-DD] |
| Phase | P6b §3b-promote — Promote Endpoint + Reject + Cooldown + Lockout + UI + MCP |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Shipped as | PR **#[NN]** — branch `feat/p6b-session3b-promotion`; tag **`p6b-session3b-promote-complete`** then **`p6b-session3-promote-complete`** |
| Built against | `main` at `p6b-session3a-gate-complete` (`[SHA]`) |
| Verdict | **GO / NO-GO.** [Summary; P6b §3 closes.] |
| Method | Executed: full suite + new modules; mypy; ruff; migration round-trip; all CI invariants. |

## Gates — PASS (executed)

| § | Gate | Result |
|---|---|---|
| 3b-p.1 | Migration round-trip + PROMOTION_LOCKOUT_DAYS | [✅ / details] |
| 3b-p.2 | Promote endpoint + bundle hash audit + variant terminate | [✅ / details] |
| 3b-p.3 | Reject-promotion endpoint from both source states | [✅ / details] |
| 3b-p.4 | Cooldown completion cron (15-min sweep) | [✅ / details] |
| 3b-p.5 | Mechanical promote: params merge + audit rows | [✅ / details] |
| 3b-p.6 | Lockout in /validate + auto-validate hook | [✅ / details] |
| 3b-p.7 | VariantCard sub-renders + lockout-aware empty | [✅ / details] |
| 3b-p.8 | MCP additive fields | [✅ / details] |
| 3b-p.9 | ~28 backend + ~8 frontend + ~2 MCP tests; non-negotiable no-auto-promote test green | [✅ / details] |
| 3b-p.10 | Manual smoke; paper smoke byte-identical | [✅ / details] |
| 3b-p.14 | P6b §3 cross-session verification; `p6b-session3-promote-complete` tagged | [✅ / details] |
| — | NO AUTO-PROMOTE invariant: grep returns zero hits | [✅] |
| — | `_router_token`, `audit_immutability`, all 13 CI invariants green | [✅] |

## Deliberate deviations (as-built vs the v0.1 plan)

Pre-named candidates (from v0.1's Candid Acknowledgment):

- **[`promoting_at` vs generic `transitioned_at` column]** — [scoped held / general adopted.]
- **[Evidence-bundle hash semantics]** — [SHA-256 sort_keys held / different algorithm.]
- **[Mechanical promote merge semantics]** — [`apply_proposal`-aligned / required different merge.]
- **[Cooldown cron + manual cancel race]** — [`with_for_update(skip_locked)` worked / required different protection.]
- **[Lockout `>=` vs `>` comparison]** — [`>=` for expiry held / required strict `>`.]

Other deviations:

- **[Deviation N].** [What changed and why.]

## Strategy-version archiving — flagged DEVIATION

v1 mechanically promotes via params merge (consistent with `apply_proposal`); does NOT implement ADR 0007's literal "old variant archived as a strategy version" model. Audit log + proposal record preserve the history. Strategy-version archiving deferred to a future ADR-faithful session.

## Findings / punch list

- [ ] [Anything specific.]
- [ ] [Flaky test status.]

## Deferred gates — require a live stack

- [ ] **Real EVIDENCE_READY proposal → promote → 24h cooldown elapsed → PROMOTED + params live** end-to-end with real fills.
- [ ] **Post-merge CI run green** — pending PR.

## To close P6b §3 cleanly

1. Walk away ≥1 hour before opening PR.
2. Confirm post-merge CI green; tag `p6b-session3b-promote-complete`.
3. Run §3b-promote.14 cross-session verification on non-Norton stack.
4. Tag `p6b-session3-promote-complete`. **P6b §3 closes here.**
5. **Next: P6b §4 + §5** — Mode-B LLM eval harness + LLM-driven live opt-in (replanned post-§3 per Closure plan).

---

*P6b Session 3b-promote results v0.1 — recorded [DATE].*
```

---

*End of P6b Session 3b-promote v0.1. Drafted against §3a-gate Results' corrections + the 11-question architecture turn's settled answers (Q1 promote endpoint, Q2 ACTIVATION_COOLDOWN_HOURS reuse, Q3 15-min sweep mirroring activation_completion.py, Q4 cancel → REJECTED terminal, Q5 lockout blocks /validate not /accept, Q6 NO AUTO-PROMOTE forbidden by ADR, Q7 single PR with reject path addition, Q8 4-state shell sub-renders, Q9 MCP additive fields, Q10 transitions + STRATEGY_PROMOTED marker with bundle hash, Q11 last_promoted_at on PROMOTED). Ships the promote endpoint with bundle hash audit, the reject-promotion endpoint serving both EVIDENCE_READY and PROMOTING cancel paths, the 15-minute cooldown completion cron, the mechanical promote action (params merge + last_promoted_at + variant terminate + STRATEGY_PROMOTED marker), the lockout enforcement at the spawn point (/validate + auto-validate hook), the VariantCard sub-renders with lockout-aware empty state, and the four MCP additive fields on the existing tool. NO auto-promote anywhere (load-bearing ADR invariant; grep-guarded). Strategy-version archiving deferred as flagged DEVIATION. Together with §3a-gate, closes P6b §3 via cross-session verification → `p6b-session3-promote-complete`. Next: P6b §4 + §5 (Mode-B LLM eval harness + LLM-driven live opt-in), replanned post-§3 per the Closure plan's phased split.*
