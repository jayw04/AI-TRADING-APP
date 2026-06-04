# P6b Session 3a-gate — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-04 |
| Phase | P6b — §3a-gate (promotion gate + lifecycle states + evidence bundle, ADR 0007) |
| Plan doc | `TradingWorkbench_P6b_Session3a_gate_v0_1.md` (+ the 2026-06-04 review-corrections section) |
| Predecessor | `p6b-session2-variant-complete` (`f500708`) |
| Successor | `TradingWorkbench_P6b_Session3b_promote_v0_1.md` (draft against this Results doc — Rec #10) |
| Tag on completion | `p6b-session3a-gate-complete` |
| Verdict | **GO.** Shipped offline-green: migration round-trips (CLI), 4-criterion gate + bundle + brief-pass, full backend suite + mypy + ruff + coverage gates + invariants all green. |

## What shipped

- **Schema:** `ProposalState` += `EVIDENCE_READY` / `PROMOTING` / `PROMOTED` (UPPER, fit `length=16`); `Strategy.last_promoted_at` (nullable, defined §3a / read §3b); `AuditAction.STRATEGY_PROMOTED` (defined §3a / written §3b). Alembic `d7f4a9c2e1b8` (down-rev `c5e1a2b3f4d6`; `batch_alter_table` adds `last_promoted_at`; enum values app-level, no DDL). **Up→down→up round-trip verified via the CLI.**
- **`app/services/promotion_gate.py`** — pure 4-criterion evaluator over a `VariantComparison` + `EvidenceBundle` + `bundle_to_json` + the morning-brief pass `run_promotion_gate_for_user`.
- **Brief integration:** a sibling `try` after the drift pass in `app/jobs/morning_brief_generation.py`, passing `bar_cache`.
- **`VariantComparison` += `capital_base`** (additive) — the correct anchor for the absolute-return criterion.
- **Tests:** 33 backend (schema, per-criterion gate, composite/envelope, bundle serialization, brief orchestration incl. the merge-preserve non-negotiable).

## Key corrections applied vs the v0.1 plan (the review caught two ADR-0007 threshold bugs)

1. **Duration gate = AND, not OR.** ADR 0007: "≥30 days OR ≥50 trades, *whichever is later*" + "either floor alone is misleading" → **both** required. (The doc's OR lean and the Closure-plan shorthand were wrong against the canonical ADR.)
2. **Drawdown-divergence threshold = 1.20× the live max-dd, not 0.20×.** ADR 0007: variant "has not exceeded the live variant's max drawdown *by more than 20%*" → `worst_7d_dd ≤ |live_max_dd| × 1.20`. The doc's `≤ 0.20×|dd|` was 5× too strict. Also: each window's drawdown is a proper **running-peak** walk, not naive `max−min`.
3. **`ProposalState` is in `app/db/models/strategy_proposal.py` (not `app/db/enums.py`), values UPPER.**
4. **Absolute-return floor is `final_equity − capital_base > 0` and is NOT envelope-configurable** (ADR fixes it at "positive"). Added `capital_base` to `VariantComparison` for the correct measure.
5. **Brief site = `app/jobs/morning_brief_generation.py`** (not `services/morning_brief.py`); `run_promotion_gate_for_user` lives in `promotion_gate.py`; envelope via `TradingProfileService(session).get(user_id).agent_envelope`.
6. **Select `state IN (EVALUATING, EVIDENCE_READY)`** — EVALUATING+pass → transition+audit; EVIDENCE_READY → bundle refresh only (sticky; no transition/audit). The doc's EVALUATING-only query never refreshed sticky proposals.
7. Sharpe margin ×1.05 ✓; metrics are non-null floats (dropped dead None-branches); transition audit payload uses UPPER states. A purpose-built but **unused `evidence_bundle_json` column** exists — left unused per the settled Q7 sub-key decision (future consolidation).

## Verification

- `pytest` full suite green (0 failed, ~3 steady skips); mypy(163) + ruff clean; migration up→down→up via CLI; 3 coverage gates (risk 0.904 / P2 / P3); invariants green (audit-immutability with the new enum, no-LLM, workbench-mcp-readonly, agent-no-DB, strategy-isolation).

## Deferred (live, non-Norton stack)

- A real EVALUATING variant accumulating fills → gate evaluating against real equity curves → EVIDENCE_READY transition end-to-end.
- The Mon–Fri 09:00 ET brief run firing the gate pass.
- Post-merge CI green (pending PR).

## Next

**P6b §3b-promote** — the promotion endpoint + cooldown cron (PROMOTING → PROMOTED) + 30-day lockout enforcement (reads `last_promoted_at`) + writes `STRATEGY_PROMOTED` + VariantCard fourth state + MCP additive fields + auto-promote envelope wiring. Draft against this Results doc.
