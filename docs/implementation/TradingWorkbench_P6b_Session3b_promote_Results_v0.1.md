# P6b Session 3b-promote — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-04 |
| Phase | P6b — §3b-promote (promote/reject + cooldown cron + lockout + UI + MCP, ADR 0007) |
| Plan doc | `TradingWorkbench_P6b_Session3b_promote_v0_1.md` (+ the 2026-06-04 review-corrections section) |
| Predecessor | `p6b-session3a-gate-complete` (`d1ba2c4`) |
| Tag on completion | `p6b-session3b-promote-complete` |
| Verdict | **GO.** Shipped offline-green: promote/reject endpoints, cooldown cron, mechanical promote, lockout, UI sub-renders, MCP additive fields. Full backend + frontend suites + mypy + ruff + tsc + eslint + coverage gates + invariants all green. No migration. |

## What shipped

- **`POST /proposals/{id}/promote`** — EVIDENCE_READY → PROMOTING; re-checks LIVE + not-in-lockout + bundle present; embeds the **evidence-bundle SHA-256 hash** in the audit payload (ADR 0007). Does **not** terminate the variant (A1 — kept alive through cooldown).
- **`POST /proposals/{id}/reject-promotion`** — one endpoint for "Reject evidence" (EVIDENCE_READY) and "Cancel cooldown" (PROMOTING); → REJECTED; terminates the variant (`terminate_for_parent`, terminate-first ordering).
- **`app/jobs/promotion_completion.py`** — 15-min sweep mirroring `activation_completion` (collect ids, fresh session per item, Python-side elapsed check on `transitioned_at`). Registered in `lifespan.py` (alpaca block) via `scheduler.scheduler.add_job` with `strategy_engine`.
- **`app/services/promotion.py`** — `PROMOTION_LOCKOUT_DAYS = 30`, `in_lockout` / `lockout_expires_at`, and `execute_mechanical_promote` (PROMOTING → PROMOTED: terminate variant, **`_apply_changes` merge** of the proposal's `changes`, set `last_promoted_at`, two-commit `STRATEGY_PROPOSAL_TRANSITIONED` + `STRATEGY_PROMOTED`, `SYSTEM` actor).
- **Lockout enforcement** — 409 on `POST /validate`; silent skip in `_maybe_auto_validate_proposal`. Does **not** block ACCEPT/propose.
- **`/variant-comparison` additive fields** — broadened the proposal lookup to `EVALUATING | EVIDENCE_READY | PROMOTING`; added `proposal_state`, `evidence_bundle`, `eligible_for_promotion`, `parent_last_promoted_at` (the last also on the `no_active_variant` branch). Flows through `workbench_paper_variant_metrics` unchanged (tool count stays 19).
- **VariantCard sub-renders** — EVIDENCE_READY (gate checklist + Promote + Reject), PROMOTING (Cancel + cooldown note), lockout-aware empty state (off `parent_last_promoted_at`). `variantsApi.promote` / `.rejectPromotion` added.
- **Tests** — 24 backend + 3 new frontend (incl. the `test_no_auto_promote_in_codebase` grep guard).

## Corrections applied vs the v0.1 plan

- **B1** `terminate_for_parent(parent_strategy_id, reason, user_id)` (not the wrong `terminate(variant_id=…)`).
- **B2** mechanical merge uses `_apply_changes` on `proposal_payload_json["changes"]` (not the nonexistent `proposal_payload["params"]`).
- **B3** terminate-first → one audit row per commit.
- **B4** cron registered via the in-scope `scheduler.scheduler` (not `app.state.scheduler`).
- **A1** variant terminated at **PROMOTED**, not PROMOTING — otherwise the variant-keyed endpoint goes dark during cooldown and the PROMOTING/PROMOTED UI has no data.
- **A2** broadened the proposal lookup to the three active-validation states.
- **A3** lockout-empty driven off the `parent_last_promoted_at` additive field (no frontend `Strategy.last_promoted_at`).
- **A4** **no migration** — reused `transitioned_at` as the cooldown anchor.
- Minors: no `with_for_update` (SQLite no-op); `SYSTEM` cron actor; `ACTIVATION_COOLDOWN_HOURS` import; the no-auto-promote guard is a pure-Python scan (Windows-portable).

## Verification

- `pytest` full suite green (0 failed, ~3 steady skips); mypy(165) + ruff clean; `vitest run` 122/122; tsc + eslint clean; 3 coverage gates (risk 0.904 / P2 / P3); invariants green (audit-immutability, no-LLM, workbench-mcp-readonly, agent-no-DB, strategy-isolation). **No migration; no new audit action** (STRATEGY_PROMOTED defined §3a); tool count 19; no order-path code.

## Deferred (live, non-Norton stack)

- Real EVIDENCE_READY → promote → 24h cooldown elapsed → PROMOTED with params live, end-to-end with real fills + the 15-min cron firing.
- Browser UI smoke of the four sub-renders.
- Post-merge CI green (pending PR), then the §3 cross-session rollup → `p6b-session3-promote-complete`.

## Next

P6b §3 closes after the §3b cross-session rollup. Then **P6b §4 + §5** (Mode-B LLM eval harness + LLM-driven live opt-in, replanned post-§3 per the Closure plan). The "extended evaluation" ADR feature + strategy-version archiving remain explicitly deferred.
