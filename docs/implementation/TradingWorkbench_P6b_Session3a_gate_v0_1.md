# P6b Session 3a-gate — Promotion Gate + Lifecycle States + Evidence Bundle

| Field | Value |
|---|---|
| Document version | **v0.1** (drafted against `TradingWorkbench_P6b_Session2c_variant_Results_v0.1.md` + the 11-question architecture-decision turn) |
| Date | 2026-06-04 |
| Phase | **P6b — Direction v0.2 deferred capabilities**, **§3a-gate** (data + lifecycle half of P6b Session 3 per Q6 split; §3b-promote adds the promotion endpoint + UI + cooldown cron + lockout enforcement + MCP extension) |
| Predecessor | `TradingWorkbench_P6b_Session2c_variant_Results_v0.1.md` (tag `p6b-session2-variant-complete` at `f500708`; rollup landed on the in-suite stand-in basis) |
| Successor | `TradingWorkbench_P6b_Session3b_promote_v0.1.md` (drafted only after §3a-gate ships per Retrospective Rec #10) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | **Lifecycle states migration** — adds three values to `ProposalState` enum: `EVIDENCE_READY`, `PROMOTING`, `PROMOTED`. Adds `last_promoted_at: datetime \| None` column to `Strategy` (nullable; powers §3b's 30-day lockout — §3a defines but doesn't enforce). Single Alembic revision (additive enum values + nullable column; SQLite tested with up→down→up round-trip). **4-criterion promotion gate** at `app/services/promotion_gate.py` (per Q1 settled (c) morning-brief integration) — pure evaluator over an existing `VariantComparison`: (a) **duration gate** (≥30d OR ≥50 trades per ADR 0007); (b) **Sharpe margin** (variant Sharpe ≥ baseline × 1.05 per "≥5% relative" lean; verify against ADR text); (c) **absolute return** (variant cumulative pnl > 0 strict); (d) **drawdown divergence** (variant's worst 7-business-day equity drop ≤ 0.20 × \|baseline max_drawdown\|; skip-passes when baseline max_drawdown is 0). Each criterion returns a `GateCriterionResult` with `passed: bool` + per-criterion `details` dict for the evidence bundle. **Evidence bundle** at proposal's `evaluation_results_json.evidence_bundle` sub-key (per Q7 lean — same column as §2a's `paper_variant` sub-key; merge-write reassignment pattern per §2b-rv): captured_at + comparison snapshot + per-criterion gate results + composite `all_criteria_passed` bool. **Updated on each gate-pass evaluation** (fresh data on each cycle); EVIDENCE_READY transition fires ONCE (sticky; subsequent passes just refresh the bundle). **Morning-brief integration** — adds a per-user gate-evaluation pass after the existing per-strategy drift loop (§1a-drift integration point reused): for each user's EVALUATING proposals, look up the variant via `evaluation_results_json.paper_variant.variant_strategy_id`, evaluate the gate, merge-write the bundle, transition `EVALUATING → EVIDENCE_READY` when first passes. Single-commit-per-transition per audit hash-chain contract. **New audit action `STRATEGY_PROMOTED`** added to enum (total 8 → 9); written by §3b's promotion endpoint, NOT by §3a (§3a only writes existing `STRATEGY_PROPOSAL_TRANSITIONED` rows for EVALUATING → EVIDENCE_READY). **No promotion endpoint** (§3b). **No cooldown cron** (§3b). **No lockout enforcement** (§3b — column exists, reads happen there). **No UI** (§3b — VariantCard fourth state). **No MCP extension** (§3b — additive fields on `workbench_paper_variant_metrics`). **No auto-promote envelope wiring** (§3b). Single PR. |
| Estimated wall time | 5-6h |
| Stopping point | `git tag p6b-session3a-gate-complete` |
| Tests added | ~22 backend (migration round-trip + gate criteria + bundle generation + transition + brief integration) |
| Out of scope | Promotion endpoint + UI (§3b). Cooldown cron + PROMOTING → PROMOTED transition (§3b). 30-day lockout enforcement on ACCEPT/PROPOSE (§3b — `last_promoted_at` column is empty container in §3a). Auto-promote envelope flag wiring (§3b). MCP additive fields (§3b). VariantCard fourth state rendering (§3b). Failed-gate state machine (per Q2 settled (a) — variant stays in EVALUATING; §2a's 90-day expiry is the safety net). Live Sharpe via §2b's equity-curve primitive — already shipped in §2b; §3a consumes via `compare_variant_to_parent`. ADR 0007 threshold tuning per-user (envelope flag `promotion_thresholds` sub-key honored with defaults; per-strategy override is P6+). Per-criterion threshold UI editor (P6+). Stratified gate criteria for crypto / non-equity (v1 equities-only per §2b's posture). Variant re-eval after EVIDENCE_READY de-transition (per Candid Ack: sticky EVIDENCE_READY; live data degradation doesn't roll back). |

---

## ⚠ Review corrections (2026-06-04) — verified against shipped code + ADR 0007

This v0.1 was drafted before grepping the live modules + re-reading ADR 0007. The sketches carry real drift, including **two load-bearing threshold bugs vs ADR 0007**. These corrections **supersede the sketches** wherever they conflict (applied at implementation time).

1. **`ProposalState` lives in `app/db/models/strategy_proposal.py`, NOT `app/db/enums.py`; values are UPPER** (`DRAFT="DRAFT"`, `EVALUATING="EVALUATING"`, …). → add `EVIDENCE_READY = "EVIDENCE_READY"`, `PROMOTING = "PROMOTING"`, `PROMOTED = "PROMOTED"`. The `state` column is `SQLEnum(ProposalState, native_enum=False, length=16)` — `EVIDENCE_READY` is 14 chars, fits; **no length change**.
2. **DURATION GATE = AND, not OR** (ADR 0007 §"promotion criteria": "≥30 calendar days OR ≥50 trades … **whichever is later**", Why = "**either floor alone is misleading**"). → `days_passed AND trades_passed`. The doc's OR lean (and the Closure-plan shorthand) is wrong against the canonical ADR.
3. **DRAWDOWN-DIVERGENCE THRESHOLD = 1.20× the live max-dd, NOT 0.20×** (ADR 0007: variant "has not exceeded the **live variant's** maximum drawdown **by more than 20%** in any rolling 7-day sub-window"). → `passed = worst_7d_dd ≤ |live_max_dd| × (1 + max_pct/100)` (default 20 → **1.20×**). The doc's `≤ 0.20 × |dd|` is 5× too strict. Also: compute each window's drawdown with a **running-peak** walk (proper peak→trough drop), not naive `max−min` (which counts a trough-before-peak as a drawdown). The baseline is `comparison.live_metrics.max_drawdown` (the LIVE side over the window — correct source; just rename from "baseline" for clarity).
4. **Sharpe margin = relative ×1.05** ✓ (ADR confirms "exceeds … by ≥5%"). **Absolute return = strict `> 0`** ✓ AND ADR says it is **not user-configurable** ("refuses to lower the absolute floor below positive return") — so it must NOT read from the envelope. Keep duration / sharpe-margin / drawdown thresholds envelope-tunable; hardcode the positive-return floor.
5. **`VariantSideMetrics.sharpe_ratio` / `max_drawdown` are non-null `float`** (§2b returns 0.0, never None) — the doc's `is None` skip branches are dead. Drop them (treat as floats). Note the negative-baseline-Sharpe edge: `live_sharpe ≤ 0` makes `×1.05` lenient; acceptable per ADR's literal formula, documented.
6. **Absolute return uses `final_equity − capital_base`, not `final − first_curve_point`.** ADR = "absolute return over the window is positive"; the window starts at `capital_base`, but `variant_equity_curve[0]` is the first business day's EOD (may already include day-0 pnl). → **add `capital_base: Decimal` to `VariantComparison`** (additive, populated in `compare_variant_to_parent` where it's already computed) and use `final_equity − capital_base > 0`.
7. **Migration**: `down_revision = "c5e1a2b3f4d6"` (confirmed head — the §2a paper-variant migration). Use **`op.batch_alter_table("strategies")`** (SQLite-safe) + the modern template (`revision: str = …`), mirroring `c5e1a2b3f4d6`. The enum values are **app-level only (no DDL)** — exactly as that migration documents for `PAPER_VARIANT`/`EVALUATING`. Migration adds only `last_promoted_at`.
8. **`AuditAction` is in `app/audit/logger.py`** ✓. Add `STRATEGY_PROMOTED = "STRATEGY_PROMOTED"` (defined §3a, written §3b).
9. **Brief integration site = `app/jobs/morning_brief_generation.py`** (after the existing drift `try` at ~line 64), **NOT `app/services/morning_brief.py`**. `bar_cache` IS in scope there (a `run_morning_brief_generation` param) → pass it to the gate. `run_promotion_gate_for_user` lives in **`app/services/promotion_gate.py`** (like drift's `run_drift_detection_for_user` lives in `drift_detection.py`); the smoke's `from app.services.morning_brief import run_promotion_gate_for_user` → `from app.services.promotion_gate import …`. Read the envelope via **`TradingProfileService(session).get(user_id).agent_envelope`** (the drift pattern), NOT a nonexistent `_get_user_envelope`.
10. **Select `state IN (EVALUATING, EVIDENCE_READY)`**, not just EVALUATING — Posture #3 / Candid-Ack say the bundle keeps refreshing on already-EVIDENCE_READY proposals. EVALUATING + gate-pass → transition + audit; EVIDENCE_READY → bundle refresh only (no transition, no audit). The doc's EVALUATING-only query would never refresh sticky proposals (and would fail `test_brief_evidence_ready_proposal_updates_bundle_but_no_transition`).
11. **Audit transition payload uses UPPER states** (`"from": "EVALUATING"`, `"to": "EVIDENCE_READY"`) to match the §2a/§1b `STRATEGY_PROPOSAL_TRANSITIONED` convention. `actor_type=AGENT`, `actor_id="promotion_gate"`.
12. **Evidence-bundle home**: follow Q7 — `evaluation_results_json.evidence_bundle` sub-key with the **merge-write** pattern (preserve `paper_variant`/`status`/`verdict`/`baseline_metrics`/`variant_metrics`/`human_review`). NOTE: a purpose-built but **empty `evidence_bundle_json` column** exists on `StrategyProposal` — left unused per the settled Q7 decision (a future consolidation, not this session).

---

## How this differs from §2c-variant Results

§2c-variant's five execution-time deviations: items #2 (`spawn_proposal_id` derivation from `evaluation_results_json.paper_variant.variant_strategy_id`) and #5 (Tailwind not semantic CSS classes) carry forward most directly. The first **defines the cross-table linkage §3a depends on**: variant lookup goes `proposal.evaluation_results_json.paper_variant.variant_strategy_id` → `Strategy` row. The second is moot for §3a (no frontend).

§2c-variant deviation #1 (no `lightweight-charts`) shapes a §3a precaution: **before sketching anything that imports a Python package, verify it's already in `pyproject.toml`.** Norton-blocked `uv add` is a constraint; if the gate evaluator needs a new dep (it shouldn't — pure math over existing primitives), that's a planning-time question, not a paste-time one.

Plus all standing P6+P6b deviations applicable to §3a:
- `AuditAction` at `app/audit/logger.py`; `AuditLogger.write` sync staticmethod; single-commit caller per §1a-drift.
- `func.json_extract(...)` Core for JSON queries (per §1a/§2b-bt/§2b-rv); evaluation_results_json filters use this.
- **Merge-not-overwrite** for `evaluation_results_json` sub-key writes (per §2b-rv non-negotiable): `eval = {**(row.evaluation_results_json or {}), "evidence_bundle": new}`. The existing `paper_variant` sub-key (§2a) MUST be preserved across §3a writes.
- `audit_immutability` invariant is additive-enum-safe (per §2b-rv confirmation). `STRATEGY_PROMOTED` enum addition triggers no allowlist edit.
- SQLite tz coercion (§2b-variant Results deviation #3) — applies to any datetime comparison in §3a; the drawdown-divergence check walks equity-curve timestamps and `variant.created_at`. Use `_aware()` helper.
- Strategy.status lowercase StrEnum (§1a-drift correction); `ACTIVE_STRATEGY_STATUSES` frozenset (§1a-drift); `PAPER_VARIANT` value (§2a).
- `find_in_flight_variant` module-level helper (§2b-variant Results deviation #2).
- `VariantComparison` shape per §2c shipped — includes `live_equity_curve` + `variant_equity_curve` (§2c-variant added these additively).

---

## ⚠ Posture

**§3a-gate is the policy layer of P6b §3.** Three principles:

1. **The gate evaluates; §3b acts.** §3a defines the lifecycle states, computes the 4-criterion verdict, generates the evidence bundle, and transitions EVALUATING → EVIDENCE_READY when criteria first pass. It does NOT promote, does NOT enforce lockout, does NOT expose MCP fields. Promotion is §3b's writing surface; §3a is read-only on the policy decision (audit row for transition, but no STRATEGY_PROMOTED).

2. **Evidence bundle is the single source of truth.** Stored at `proposal.evaluation_results_json.evidence_bundle`. Updated on every gate-pass evaluation during morning-brief generation — never stale. §3b reads it; UI consumes it via the existing variant-comparison response; MCP tool surfaces it via additive fields in §3b. The bundle is captured at gate-evaluation time, not at promotion time — so the user (and §3b) see the most recent assessment when they decide to promote.

3. **EVIDENCE_READY is sticky.** Once a variant's gate passes and the proposal transitions, it doesn't roll back on subsequent failing evaluations. The bundle still updates with fresh data each cycle (so the user sees current state at promotion time), but the lifecycle state stays EVIDENCE_READY. Rationale: rollback would create flicker between EVALUATING / EVIDENCE_READY across days as criteria narrowly hover at threshold; advisory framing means "we've seen this pass at least once — your call to promote."

Paper smoke from P1-P5 byte-identical. ADR-0002 `_router_token` discipline unaffected. `check_agent_no_db_access.sh` unaffected.

---

## Verification checklist — grep before pasting any code below

Per Retrospective Rec #5.

- [ ] **`ProposalState` enum location** at `app/db/enums.py` — confirmed via prior sessions. Add `EVIDENCE_READY = "evidence_ready"`, `PROMOTING = "promoting"`, `PROMOTED = "promoted"`. Lowercase StrEnum convention per §1a-drift.
- [ ] **Alembic migration directory and naming convention** — `alembic/versions/`; revision file names use timestamp + slug per existing pattern. New revision adds enum values + `last_promoted_at` column.
- [ ] **`Strategy` model** at `app/db/models/strategy.py` — add `last_promoted_at: Mapped[datetime | None] = mapped_column(nullable=True)`. Confirm SQLAlchemy 2.0 `Mapped[]` syntax matches existing columns.
- [ ] **Migration round-trip** — `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` on a fresh SQLite DB. SQLite enum-value adds are migration-safe; column add is straightforward.
- [ ] **`AuditAction` location** at `app/audit/logger.py`; add `STRATEGY_PROMOTED = "STRATEGY_PROMOTED"`. Per §1a deviation #1.
- [ ] **`compare_variant_to_parent` signature** at `app/services/paper_variant.py` per §2b shipped — `(session, variant_strategy_id, bar_cache=None) → VariantComparison | None`. §3a gate evaluator calls this for current comparison.
- [ ] **`VariantComparison` shape** per §2c shipped — confirm `live_equity_curve` / `variant_equity_curve` are list-of-tuples (datetime, Decimal). The drawdown-divergence check walks variant_equity_curve.
- [ ] **`find_in_flight_variant`** at `app/services/paper_variant.py` (module-level per §2b deviation #2) — `(session, parent_strategy_id) → Strategy | None`. §3a brief integration uses this through the proposal's `evaluation_results_json.paper_variant.variant_strategy_id`.
- [ ] **Morning brief generation integration point** — same site §1a-drift hooked into. Confirm whether drift loop and gate-eval loop can share the per-user strategy iteration, or run sequentially. Lean: sequential (drift first, then gate), each with own try/except per strategy.
- [ ] **Active strategy filter** — `ACTIVE_STRATEGY_STATUSES` frozenset per §1a-drift. Gate evaluation only applies to strategies with in-flight variants; PAPER_VARIANT itself is not in the active set, but parent strategies are. **The gate evaluates the variant of the parent**, so iteration is over the user's non-variant active strategies, and each checks for an in-flight variant.
- [ ] **`evaluation_results_json` shape** — confirm current sub-keys: `status`, `verdict`, `baseline_metrics`, `variant_metrics` (from §2b-backtest), `human_review` (from §2b-rv), `paper_variant` (from §2a). §3a adds `evidence_bundle`. Merge-write must preserve all five existing sub-keys.
- [ ] **`audit_immutability` invariant test** — confirm green after `STRATEGY_PROMOTED` enum addition. Per §2b-rv confirmation, hash-chain test ignores enum membership; safe.

---

## Candid acknowledgment — what this session plan cannot predict

- **Sharpe margin: ≥5% relative or ≥5% absolute?** v0.1 leans relative (`variant.sharpe ≥ baseline.sharpe × 1.05`). If ADR 0007 specifies absolute (`variant.sharpe ≥ baseline.sharpe + 0.05`), the implementation flips one line. The relative formulation handles edge cases better (a strategy with Sharpe 0.1 doesn't need to hit 0.15 to pass relative-5%, only 0.105 — sane). Absolute formulation is harsher in low-Sharpe regimes. Verify against ADR text.
- **7-day worst-case divergence calculation.** v0.1 implementation: walk variant's equity curve with a rolling 7-business-day window; track the max equity-drop within any window (worst peak-to-trough in 7 days). Compare ratio: (worst_7day_drop / |baseline.max_drawdown|) ≤ 0.20. If baseline.max_drawdown is 0 (no observed drawdown in the baseline backtest), the divergence check trivially passes (no denominator). Document. If ADR specifies different methodology (e.g., comparing 7-day windows synchronously across variant and live), revisit.
- **Absolute return: strict `> 0` or `≥ 0`?** v0.1 strict — even-money outcomes don't qualify. If ADR specifies `≥ 0`, easy flip.
- **`duration_gate` semantics.** v0.1: `(days_since_spawn ≥ min_days) OR (variant_trade_count ≥ min_trades)` — either is sufficient. Some ADR frameworks use AND. Lean OR per the Closure plan's "(≥30d OR ≥50 trades)" phrasing.
- **EVIDENCE_READY stickiness.** Per Posture principle #3: once transitioned, doesn't roll back. If you'd prefer rollback (EVIDENCE_READY → EVALUATING on failing eval), document; the implementation cost is small but semantic implications are bigger (UI states flicker; user sees "ready, not ready, ready" across days).
- **Evidence bundle refresh on already-EVIDENCE_READY proposals.** v0.1: bundle UPDATES even when proposal is already EVIDENCE_READY (fresh data on each cycle). Alternative: freeze at first transition (avoids confusion about "which bundle did I act on"). Lean: update, since user might act days after transition and wants current state.
- **Brief integration: where in the brief flow?** Per §1a-drift Results: drift detection runs after brief save (own try). §3a's gate eval can also run after, in its own try. Sequential per-user passes don't share strategy iteration overhead meaningfully (each pass is read-mostly).
- **Variant max equity vs equity-curve normalization.** §2b's curves are absolute equity (capital_base + cumulative pnl). The 7-day rolling drawdown uses `(peak - trough) / peak` semantics (matches §1a-drift's max_drawdown formula). Both sides use the same capital_base per §2b's invariant; absolute drawdown ratios are then meaningful.
- **Race: variant terminated mid-gate-eval.** D8 invalidation (§2b) terminates an in-flight variant on parent status change. If brief gen is iterating and terminate fires concurrently, the gate eval may see a variant in mid-terminate state. v1 lean: catch exceptions per-proposal; failing one doesn't fail the brief. Document.
- **Multiple EVALUATING proposals per strategy.** §2a's concurrency guard allows only one in-flight variant per parent. So at most one EVALUATING proposal per strategy. The iteration is safe.
- **Bundle size.** Including equity curves (~22 points × 2 series × ~30 bytes ≈ 1.3KB) on every proposal's `evaluation_results_json` for EVIDENCE_READY-and-onward proposals. Acceptable for current scale; if proposal rows balloon, P6+ can move bundles to a separate `evidence_bundles` table.

---

## Goal

After §3a-gate ships:

- Three new lifecycle states (`EVIDENCE_READY`, `PROMOTING`, `PROMOTED`) defined in the `ProposalState` enum. Migration round-trips cleanly.
- A `Strategy.last_promoted_at` column exists, nullable, ready for §3b's lockout reads.
- A new `STRATEGY_PROMOTED` audit action defined (§3b writes; §3a doesn't yet).
- A 4-criterion gate evaluator at `app/services/promotion_gate.py` computes per-criterion verdicts + composite all-passed.
- Evidence bundles generated at `evaluation_results_json.evidence_bundle` with full snapshot.
- The morning brief generation flow gains a per-user gate-evaluation pass: for each EVALUATING proposal, evaluate the gate, merge-write the bundle, transition to EVIDENCE_READY when first passes. Audit row per transition (existing `STRATEGY_PROPOSAL_TRANSITIONED`).
- All §2 mechanics unchanged — paper-variant spawn/terminate untouched; comparison endpoint untouched (§3b extends additively).
- All 13 CI invariants + 3 coverage gates green.
- Paper smoke from P1-P5 byte-identical.

---

## §3a-gate.1 — Migration

Create `apps/backend/alembic/versions/[YYYY_MM_DD]_p6b_3a_promotion_lifecycle.py`:

```python
"""P6b §3a: promotion lifecycle states + last_promoted_at column.

Revision ID: [auto-generated]
Revises: [previous head]
Create Date: [auto]
"""
from alembic import op
import sqlalchemy as sa


revision = "[auto]"
down_revision = "[previous head]"


def upgrade() -> None:
    # 1. Add three new values to ProposalState enum.
    # SQLite enum is TEXT — values are runtime-validated by SQLAlchemy.
    # No ALTER TYPE needed; the StrEnum addition in app/db/enums.py is
    # the canonical change. The migration declares intent + tests round-trip.
    # (For PostgreSQL deployments, add ALTER TYPE ... ADD VALUE statements.)

    # 2. Add Strategy.last_promoted_at column.
    op.add_column(
        "strategies",
        sa.Column("last_promoted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("strategies", "last_promoted_at")
    # ProposalState enum values: no downgrade (StrEnum is code-managed).
```

Update `app/db/enums.py`:

```python
class ProposalState(StrEnum):
    DRAFT = "draft"
    REVIEWING = "reviewing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EVALUATING = "evaluating"   # set by §2a spawn
    APPLIED = "applied"
    # NEW in P6b §3a:
    EVIDENCE_READY = "evidence_ready"
    PROMOTING = "promoting"
    PROMOTED = "promoted"
```

Update `app/db/models/strategy.py`:

```python
class Strategy(Base):
    # ... existing fields ...
    # NEW in P6b §3a (set by §3b's promotion endpoint):
    last_promoted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, default=None,
    )
```

**Verify before pasting:**
- Existing migration head reference for `down_revision`.
- SQLAlchemy `Mapped` / `mapped_column` syntax matches other columns in `Strategy`.

---

## §3a-gate.2 — Promotion gate evaluator service

Create `apps/backend/app/services/promotion_gate.py`:

```python
"""4-criterion promotion gate evaluator per ADR 0007.

Pure evaluator over an existing VariantComparison. Returns an
EvidenceBundle with per-criterion verdicts + composite all-passed.

Per P6b §3a settled decisions:
- Q1: morning-brief integration (sibling pass after drift loop).
- Q7: bundle at evaluation_results_json.evidence_bundle (merge-write).
- Carrying leans: relative Sharpe margin; strict positive return;
  7-day rolling drawdown; OR duration gate.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.paper_variant import (
    VariantComparison, compare_variant_to_parent,
)


# Threshold defaults (tunable via agent_envelope_json.promotion_thresholds).
DEFAULT_MIN_DAYS = 30
DEFAULT_MIN_TRADES = 50
DEFAULT_SHARPE_MARGIN_REL_PCT = 5      # variant.sharpe ≥ baseline.sharpe × 1.05
DEFAULT_DD_DIVERGENCE_MAX_PCT = 20     # variant worst-7day ≤ 0.20 × |baseline.max_dd|
DEFAULT_DD_WINDOW_DAYS = 7             # rolling window for variant drawdown check


@dataclass(frozen=True)
class GateCriterionResult:
    name: str
    passed: bool
    details: dict[str, Any]


@dataclass(frozen=True)
class GateResults:
    duration: GateCriterionResult
    sharpe_margin: GateCriterionResult
    absolute_return: GateCriterionResult
    drawdown_divergence: GateCriterionResult

    @property
    def all_passed(self) -> bool:
        return (
            self.duration.passed
            and self.sharpe_margin.passed
            and self.absolute_return.passed
            and self.drawdown_divergence.passed
        )


@dataclass(frozen=True)
class EvidenceBundle:
    captured_at: datetime
    comparison: VariantComparison
    gate_results: GateResults

    @property
    def all_criteria_passed(self) -> bool:
        return self.gate_results.all_passed


def _read_thresholds(envelope: dict[str, Any] | None) -> dict[str, Any]:
    e = (envelope or {}).get("promotion_thresholds") or {}
    return {
        "min_days": e.get("min_days", DEFAULT_MIN_DAYS),
        "min_trades": e.get("min_trades", DEFAULT_MIN_TRADES),
        "sharpe_margin_relative_pct": e.get(
            "sharpe_margin_relative_pct", DEFAULT_SHARPE_MARGIN_REL_PCT,
        ),
        "drawdown_divergence_max_pct": e.get(
            "drawdown_divergence_max_pct", DEFAULT_DD_DIVERGENCE_MAX_PCT,
        ),
        "drawdown_window_days": e.get("drawdown_window_days", DEFAULT_DD_WINDOW_DAYS),
    }


def _check_duration(
    comparison: VariantComparison, thresholds: dict[str, Any],
) -> GateCriterionResult:
    """(≥min_days OR ≥min_trades) — either sufficient."""
    days_elapsed = (comparison.window_end - comparison.window_start).days
    trades = comparison.variant_trade_count
    days_passed = days_elapsed >= thresholds["min_days"]
    trades_passed = trades >= thresholds["min_trades"]
    return GateCriterionResult(
        name="duration",
        passed=days_passed or trades_passed,
        details={
            "actual_days": days_elapsed,
            "actual_trades": trades,
            "min_days": thresholds["min_days"],
            "min_trades": thresholds["min_trades"],
            "days_passed": days_passed,
            "trades_passed": trades_passed,
        },
    )


def _check_sharpe_margin(
    comparison: VariantComparison, thresholds: dict[str, Any],
) -> GateCriterionResult:
    """variant.sharpe ≥ baseline.sharpe × (1 + margin_pct/100)."""
    live_sharpe = comparison.live_metrics.sharpe_ratio
    variant_sharpe = comparison.variant_metrics.sharpe_ratio
    margin_pct = thresholds["sharpe_margin_relative_pct"]

    if live_sharpe is None or variant_sharpe is None:
        return GateCriterionResult(
            name="sharpe_margin", passed=False,
            details={
                "live_sharpe": live_sharpe, "variant_sharpe": variant_sharpe,
                "required_margin_pct": margin_pct,
                "skip_reason": "sharpe_unavailable_on_at_least_one_side",
            },
        )

    required = live_sharpe * (1 + margin_pct / 100)
    passed = variant_sharpe >= required
    return GateCriterionResult(
        name="sharpe_margin", passed=passed,
        details={
            "live_sharpe": live_sharpe, "variant_sharpe": variant_sharpe,
            "required_variant_sharpe": required,
            "required_margin_pct": margin_pct,
        },
    )


def _check_absolute_return(
    comparison: VariantComparison,
) -> GateCriterionResult:
    """Strict variant.total_pnl > 0 — even-money doesn't qualify."""
    # The total_pnl isn't on VariantSideMetrics directly; derive from the
    # equity curve's last point minus capital_base, or from variant_metrics
    # if that field exists. Verify which is canonical at code-paste time.
    curve = comparison.variant_equity_curve
    if not curve:
        return GateCriterionResult(
            name="absolute_return", passed=False,
            details={"skip_reason": "no_equity_curve"},
        )
    final_equity = curve[-1][1]
    initial_equity = curve[0][1]    # capital_base at day 0
    total_pnl = Decimal(str(final_equity)) - Decimal(str(initial_equity))
    passed = total_pnl > Decimal("0")
    return GateCriterionResult(
        name="absolute_return", passed=passed,
        details={
            "variant_total_pnl": float(total_pnl),
            "initial_equity": float(initial_equity),
            "final_equity": float(final_equity),
        },
    )


def _check_drawdown_divergence(
    comparison: VariantComparison, thresholds: dict[str, Any],
) -> GateCriterionResult:
    """variant's worst N-business-day equity drop ≤ max_pct × |baseline.max_dd|.

    "Drop" is computed as the worst peak-to-trough within any N-day window
    on the variant's equity curve, expressed as a fraction of the rolling
    peak: (peak - trough) / peak.

    Trivially passes when baseline.max_drawdown is 0 (no denominator).
    """
    baseline_dd = comparison.live_metrics.max_drawdown
    max_pct = thresholds["drawdown_divergence_max_pct"]
    window_days = thresholds["drawdown_window_days"]

    if baseline_dd is None or baseline_dd == 0:
        return GateCriterionResult(
            name="drawdown_divergence", passed=True,
            details={
                "baseline_max_drawdown": baseline_dd,
                "skip_reason": "baseline_drawdown_zero_or_unavailable",
            },
        )

    # Walk variant's equity curve with N-business-day rolling windows.
    curve = comparison.variant_equity_curve
    if len(curve) < 2:
        return GateCriterionResult(
            name="drawdown_divergence", passed=True,
            details={
                "skip_reason": "insufficient_variant_equity_data",
            },
        )

    worst_window_drop = 0.0
    for i, (start_ts, _) in enumerate(curve):
        window_end_target = start_ts + timedelta(days=window_days)
        # Slice points within the window starting at i.
        window_points = []
        for j in range(i, len(curve)):
            if curve[j][0] > window_end_target:
                break
            window_points.append(curve[j])
        if len(window_points) < 2:
            continue
        peak = max(float(eq) for _, eq in window_points)
        trough = min(float(eq) for _, eq in window_points)
        if peak <= 0:
            continue
        drop = (peak - trough) / peak
        if drop > worst_window_drop:
            worst_window_drop = drop

    # baseline_dd is negative (e.g., -0.15 = -15%). Take absolute value.
    abs_baseline_dd = abs(float(baseline_dd))
    ratio_pct = (worst_window_drop / abs_baseline_dd) * 100 if abs_baseline_dd > 0 else 0
    passed = ratio_pct <= max_pct
    return GateCriterionResult(
        name="drawdown_divergence", passed=passed,
        details={
            "baseline_max_drawdown": float(baseline_dd),
            "variant_worst_window_drop": worst_window_drop,
            "ratio_pct": ratio_pct,
            "max_ratio_pct": max_pct,
            "window_days": window_days,
        },
    )


async def evaluate_promotion_gate(
    session: AsyncSession,
    variant_strategy_id: int,
    envelope: dict[str, Any] | None = None,
    bar_cache=None,
) -> EvidenceBundle | None:
    """Compute the 4-criterion gate + evidence bundle for a given variant.

    Returns None if the variant has no comparison data (no parent, no
    matching baseline, etc — same conditions as compare_variant_to_parent).
    """
    comparison = await compare_variant_to_parent(
        session, variant_strategy_id, bar_cache=bar_cache,
    )
    if comparison is None:
        return None

    thresholds = _read_thresholds(envelope)

    return EvidenceBundle(
        captured_at=datetime.now(UTC),
        comparison=comparison,
        gate_results=GateResults(
            duration=_check_duration(comparison, thresholds),
            sharpe_margin=_check_sharpe_margin(comparison, thresholds),
            absolute_return=_check_absolute_return(comparison),
            drawdown_divergence=_check_drawdown_divergence(comparison, thresholds),
        ),
    )
```

**Verify before pasting:**
- `VariantComparison` fields: `live_metrics`, `variant_metrics`, `variant_equity_curve`, `window_start`, `window_end`, `variant_trade_count`. Match exact §2b/§2c shipped names.
- `VariantSideMetrics.sharpe_ratio` / `max_drawdown` types (float | None per the dataclass).
- `compare_variant_to_parent` exact signature + the `bar_cache=None` param per §2b shipped.

---

## §3a-gate.3 — Evidence bundle serializer

In `app/services/promotion_gate.py`, add a JSON-serialization helper:

```python
def bundle_to_json(bundle: EvidenceBundle) -> dict[str, Any]:
    """Serialize EvidenceBundle for evaluation_results_json storage.

    Output shape consumed by §3b's UI and MCP extensions.
    """
    return {
        "captured_at": bundle.captured_at.isoformat(),
        "all_criteria_passed": bundle.all_criteria_passed,
        "comparison": {
            "window_start": bundle.comparison.window_start.isoformat(),
            "window_end": bundle.comparison.window_end.isoformat(),
            "live_metrics": _metrics_dict(bundle.comparison.live_metrics),
            "variant_metrics": _metrics_dict(bundle.comparison.variant_metrics),
            "deltas": bundle.comparison.deltas,
            "live_trade_count": bundle.comparison.live_trade_count,
            "variant_trade_count": bundle.comparison.variant_trade_count,
            # Equity curves included so §3b's UI doesn't need a separate fetch.
            "live_equity_curve": [
                {"ts": ts.isoformat(), "equity": float(eq)}
                for ts, eq in bundle.comparison.live_equity_curve
            ],
            "variant_equity_curve": [
                {"ts": ts.isoformat(), "equity": float(eq)}
                for ts, eq in bundle.comparison.variant_equity_curve
            ],
        },
        "gate_results": {
            "duration": _criterion_dict(bundle.gate_results.duration),
            "sharpe_margin": _criterion_dict(bundle.gate_results.sharpe_margin),
            "absolute_return": _criterion_dict(bundle.gate_results.absolute_return),
            "drawdown_divergence": _criterion_dict(bundle.gate_results.drawdown_divergence),
        },
    }


def _metrics_dict(m) -> dict[str, Any]:
    return {
        "trade_count": m.trade_count,
        "win_rate": m.win_rate,
        "avg_return_per_trade": m.avg_return_per_trade,
        "sharpe_ratio": m.sharpe_ratio,
        "max_drawdown": m.max_drawdown,
    }


def _criterion_dict(c: GateCriterionResult) -> dict[str, Any]:
    return {
        "name": c.name,
        "passed": c.passed,
        "details": c.details,
    }
```

---

## §3a-gate.4 — Morning-brief integration

Extend the existing morning-brief generation site (where §1a-drift's `run_drift_detection_for_user` plugs in — per §1a Results, this is in `run_morning_brief_generation` after `save()`, own try).

```python
"""In app/services/morning_brief.py (or wherever the brief-generation
orchestrator lives — verify path):

After the existing drift detection pass for the user, run the promotion-gate
evaluation pass. Same per-strategy try/except posture: errors per proposal
don't fail the brief.
"""
from app.services.promotion_gate import (
    bundle_to_json, evaluate_promotion_gate,
)
from app.db.enums import ProposalState
from app.db.models.strategy_proposal import StrategyProposal
from app.audit import AuditAction, AuditActorType, AuditLogger
from sqlalchemy import select, func


async def run_promotion_gate_for_user(
    session: AsyncSession,
    user_id: int,
    bar_cache=None,
) -> dict[str, int]:
    """Per-user gate-evaluation pass.

    For each EVALUATING proposal, evaluate gate, merge-write bundle,
    transition to EVIDENCE_READY if first pass.

    Per audit hash-chain contract: one row per transaction. Each transition
    commits separately. Bundle updates without transition share the same
    commit boundary (no audit row written for bundle-only updates).
    """
    # Find user's EVALUATING proposals.
    evaluating_proposals = list((await session.execute(
        select(StrategyProposal)
        .where(StrategyProposal.user_id == user_id)
        .where(StrategyProposal.state == ProposalState.EVALUATING)
    )).scalars().all())

    transitions_fired = 0
    bundles_updated = 0
    skips = 0

    for proposal in evaluating_proposals:
        try:
            paper_variant_subkey = (proposal.evaluation_results_json or {}).get(
                "paper_variant"
            ) or {}
            variant_strategy_id = paper_variant_subkey.get("variant_strategy_id")
            if variant_strategy_id is None:
                skips += 1
                continue

            envelope = await _get_user_envelope(session, user_id)
            bundle = await evaluate_promotion_gate(
                session, variant_strategy_id, envelope=envelope,
                bar_cache=bar_cache,
            )
            if bundle is None:
                skips += 1
                continue

            # MERGE-WRITE evidence bundle (preserve other sub-keys).
            existing_eval = dict(proposal.evaluation_results_json or {})
            existing_eval["evidence_bundle"] = bundle_to_json(bundle)
            proposal.evaluation_results_json = existing_eval
            bundles_updated += 1

            # Sticky transition: only fire if currently EVALUATING and gate passes.
            if bundle.all_criteria_passed:
                proposal.state = ProposalState.EVIDENCE_READY
                AuditLogger.write(
                    session,
                    actor_type=AuditActorType.AGENT,
                    actor_id="promotion_gate",
                    action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
                    target_type="strategy_proposal",
                    target_id=proposal.id,
                    payload={
                        "proposal_id": proposal.id,
                        "from": "evaluating",
                        "to": "evidence_ready",
                        "trigger": "gate_passed",
                        "captured_at": bundle.captured_at.isoformat(),
                    },
                    user_id=user_id,
                )
                await session.commit()
                transitions_fired += 1
            else:
                # No transition; the bundle update flushes with the next commit
                # (which may be in the caller). For atomicity, commit here too.
                await session.commit()

        except Exception as exc:
            logger.warning(
                "promotion_gate_eval_failed",
                user_id=user_id, proposal_id=proposal.id, error=str(exc),
            )
            await session.rollback()
            continue

    return {
        "transitions_fired": transitions_fired,
        "bundles_updated": bundles_updated,
        "skips": skips,
    }
```

Then in the existing morning-brief generation orchestrator, add after the drift detection pass:

```python
# After: await run_drift_detection_for_user(...)
try:
    gate_result = await run_promotion_gate_for_user(
        session, user_id, bar_cache=bar_cache,
    )
    logger.info(
        "promotion_gate_pass_complete",
        user_id=user_id, **gate_result,
    )
except Exception as exc:
    logger.warning(
        "promotion_gate_pass_failed_continuing_brief",
        user_id=user_id, error=str(exc),
    )
```

**Verify before pasting:**
- Exact location/name of the drift-detection-for-user invocation in the brief flow (§1a-drift Results).
- `_get_user_envelope` helper — there's surely an existing pattern from §1a, §2b's auto_validate. Reuse the established import.

---

## §3a-gate.5 — New `STRATEGY_PROMOTED` audit action

Add to `app/audit/logger.py::AuditAction`:

```python
class AuditAction(StrEnum):
    # ... existing 8 P6+P6b actions ...
    # NEW in P6b §3a (written by §3b's promotion endpoint):
    STRATEGY_PROMOTED = "STRATEGY_PROMOTED"
```

Total P6+P6b agent audit actions: 8 → 9. Per §2b-rv confirmation, `audit_immutability` invariant additive-enum-safe — re-run after addition.

§3a does NOT write `STRATEGY_PROMOTED` rows. §3b owns that audit point.

---

## §3a-gate.6 — Tests

### Migration (`apps/backend/tests/test_migration_p6b_3a.py`)

- `test_migration_upgrades_cleanly_on_empty_db`
- `test_migration_round_trips` — up → down → up
- `test_proposalstate_enum_includes_new_values`
- `test_strategy_last_promoted_at_nullable_default_none`

### Gate evaluator (`apps/backend/tests/services/test_promotion_gate.py`)

**Per-criterion:**
- `test_duration_passes_when_days_exceed_min`
- `test_duration_passes_when_trades_exceed_min`
- `test_duration_passes_when_both_exceed`
- `test_duration_fails_when_neither_exceeds`
- `test_sharpe_margin_passes_at_relative_5_pct_above_baseline`
- `test_sharpe_margin_fails_when_variant_below_required`
- `test_sharpe_margin_skip_when_sharpe_unavailable_either_side`
- `test_absolute_return_passes_when_total_pnl_positive`
- `test_absolute_return_fails_when_total_pnl_zero_or_negative`
- `test_absolute_return_skip_when_no_equity_curve`
- `test_drawdown_divergence_passes_at_20_pct_ratio`
- `test_drawdown_divergence_fails_above_20_pct`
- `test_drawdown_divergence_skip_when_baseline_dd_zero`
- `test_drawdown_divergence_rolling_window_finds_worst_drop`

**Composite:**
- `test_all_passed_only_when_all_four_pass`
- `test_threshold_envelope_overrides_defaults`

### Bundle serialization (`apps/backend/tests/services/test_evidence_bundle_serialization.py`)

- `test_bundle_to_json_includes_all_fields`
- `test_bundle_to_json_serializes_equity_curves`
- `test_bundle_to_json_serializes_decimal_to_float`

### Morning-brief integration (`apps/backend/tests/services/test_morning_brief_promotion_gate.py`)

**Non-negotiable:**
- `test_brief_preserves_existing_eval_subkeys_on_bundle_write` (merge-not-overwrite invariant — same shape as §2b-rv)

**Per-state:**
- `test_brief_evaluating_proposal_transitions_to_evidence_ready_when_gate_passes`
- `test_brief_evaluating_proposal_stays_evaluating_when_gate_fails`
- `test_brief_evidence_ready_proposal_updates_bundle_but_no_transition` (sticky)
- `test_brief_skips_proposal_without_paper_variant_subkey`
- `test_brief_continues_on_per_proposal_exception` (resilience)
- `test_brief_writes_one_audit_row_per_transition` (hash-chain contract)
- `test_brief_no_audit_for_bundle_only_updates`

**Verify test paths.** Established per §1a-drift / §2b.

---

## §3a-gate.7 — Manual smoke

```bash
# 0. Prerequisites
git describe --tags --abbrev=0   # expect: p6b-session2-variant-complete

# 1. Run migration up + down + up
cd apps/backend
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
cd ../..

# 2. Bring up stack
docker compose up -d
sleep 30
./scripts/login_helper.sh

# 3. Need an EVALUATING proposal with an in-flight variant.
# Use existing §2 data; or spawn one via /validate.
PROP_ID=$(curl -s -b /tmp/cookies.txt \
  "http://127.0.0.1:8000/api/v1/proposals?state=EVALUATING&limit=1" \
  | jq -r '.items[0].id')
echo "Testing gate on proposal ${PROP_ID}"

# 4. Manually invoke the gate evaluation (don't wait for tomorrow's brief)
docker compose exec backend uv run python -c "
import asyncio
from app.db.session import get_sessionmaker
from app.services.morning_brief import run_promotion_gate_for_user

async def main():
    factory = get_sessionmaker()
    async with factory() as session:
        result = await run_promotion_gate_for_user(session, user_id=1)
        print(result)

asyncio.run(main())
"
# Expect: {transitions_fired, bundles_updated, skips}

# 5. Verify evidence bundle was written (merge, not overwrite — load-bearing!)
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT id, state,
       json_extract(evaluation_results_json, '\$.paper_variant.variant_strategy_id') AS variant_id,
       json_extract(evaluation_results_json, '\$.evidence_bundle.all_criteria_passed') AS gate_passed,
       json_extract(evaluation_results_json, '\$.evidence_bundle.captured_at') AS captured_at
FROM strategy_proposals WHERE id=${PROP_ID};"
# Expect: variant_id (preserved from §2a), evidence_bundle present (from §3a)

# 6. If gate passed: verify state transitioned to EVIDENCE_READY
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT state FROM strategy_proposals WHERE id=${PROP_ID};"

# 7. Verify audit row for transition
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT action, target_id,
       json_extract(payload_json, '\$.from') AS from_state,
       json_extract(payload_json, '\$.to') AS to_state,
       json_extract(payload_json, '\$.trigger') AS trigger
FROM audit_log
WHERE action='STRATEGY_PROPOSAL_TRANSITIONED'
  AND json_extract(payload_json, '\$.trigger')='gate_passed'
ORDER BY id DESC LIMIT 1;"

# 8. Re-run gate evaluation — bundle should update but no new transition
# (sticky EVIDENCE_READY semantics)
docker compose exec backend uv run python -c "
import asyncio
from app.db.session import get_sessionmaker
from app.services.morning_brief import run_promotion_gate_for_user

async def main():
    factory = get_sessionmaker()
    async with factory() as session:
        result = await run_promotion_gate_for_user(session, user_id=1)
        print(result)
asyncio.run(main())
"
# Expect: transitions_fired=0, bundles_updated possibly >0 (re-eval refreshes)

# 9. Test STRATEGY_PROMOTED enum exists (§3b will write; §3a defines)
docker compose exec backend uv run python -c "
from app.audit import AuditAction
print('STRATEGY_PROMOTED' in [a.name for a in AuditAction])
"
# Expect: True

# 10. Test last_promoted_at column exists
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "PRAGMA table_info(strategies);" | grep last_promoted_at
# Expect: row showing last_promoted_at column

# 11. LOAD-BEARING: paper smoke byte-identical
PAPER_ACC=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts \
  | jq -r '.items[] | select(.mode=="paper") | .id')
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{\"account_id\":${PAPER_ACC},\"symbol\":\"AAPL\",\"side\":\"buy\",\"type\":\"market\",\"qty\":\"1\",\"tif\":\"day\",\"source\":\"manual\"}" \
  | jq '{status}'
# Expect: status=accepted
```

**Norton-deferred posture.** Steps 1-10 work fully offline. Step 11 is the standard paper-smoke gate. Live BarCache → Alpaca data path is mocked in tests; gate evaluation works on whatever variant equity-curve data exists (empty/flat in Norton dev — expected; the gate logic still runs).

---

## §3a-gate.8 — Notes & gotchas

1. **Three principles, in priority order:**
   - **The gate evaluates; §3b acts.** §3a never writes `STRATEGY_PROMOTED`. §3a writes only `STRATEGY_PROPOSAL_TRANSITIONED` for EVALUATING → EVIDENCE_READY.
   - **Evidence bundle is single source of truth.** Updated on every gate-pass evaluation (fresh data each cycle); §3b's UI + MCP read it.
   - **EVIDENCE_READY is sticky.** No rollback. Bundle refresh continues; lifecycle state stays.

2. **`evaluation_results_json` merge-not-overwrite is the load-bearing invariant.** §3a writes the `evidence_bundle` sub-key alongside §2a's `paper_variant` and §2b-bt's `status`/`verdict`/`baseline_metrics`/`variant_metrics`. **Reassignment-not-mutation** pattern per §2b-rv non-negotiable: `existing = dict(proposal.evaluation_results_json or {})` → `existing["evidence_bundle"] = ...` → `proposal.evaluation_results_json = existing`. The non-negotiable test (`test_brief_preserves_existing_eval_subkeys_on_bundle_write`) guards.

3. **One audit row per transaction.** Per §1a-drift hash-chain contract carried through §2a/§2b-rv. EVIDENCE_READY transition = one `STRATEGY_PROPOSAL_TRANSITIONED` row + commit. Bundle-only updates (no transition) flush in their own commit too. Multiple proposals iterated in `run_promotion_gate_for_user` produce multiple commits, NOT one batch commit.

4. **`STRATEGY_PROMOTED` enum value added but unused in §3a.** §3b's promotion endpoint will write it. `audit_immutability` invariant re-verified post-addition; per §2b-rv hash-chain confirmation, additive enums are safe.

5. **`last_promoted_at` column added but unread in §3a.** §3b's 30-day lockout enforcement reads it.

6. **Brief integration sibling pass after drift, not interleaved.** Per §1a-drift Results: drift runs after `save()` in own try. §3a's gate-eval runs after drift in own try. Sequential simplifies failure isolation; no shared state.

7. **Per-criterion `details` dict captures everything needed for UI explanation.** §3b's UI shows "Why did this pass / fail?" by walking the details. v1 keeps the dict shape flat; if UI needs structured access, P6+ formalizes a per-criterion typed result.

8. **Sharpe margin: relative not absolute** in v0.1. If ADR 0007 specifies absolute, one-line flip (`>= live_sharpe + 0.05` instead of `>= live_sharpe * 1.05`). Verify against ADR text at code-paste time.

9. **Drawdown divergence: 7-day rolling worst peak-to-trough** on variant's equity curve. Compare ratio against |baseline.max_drawdown|. If baseline never drew down (max_dd=0), trivially passes. If variant has insufficient data (<2 curve points), trivially passes.

10. **Duration gate is OR not AND.** Either ≥30d or ≥50 trades suffices. Per Closure plan phrasing.

11. **Bundle equity curves: included.** ~1.3KB extra per `evaluation_results_json` write. Acceptable for current scale. P6+ may move to separate `evidence_bundles` table if row sizes grow.

12. **Race: variant terminated mid-eval.** D8 invalidation may terminate a variant while the gate iteration walks it. The per-proposal try/except catches; failed eval doesn't fail brief.

13. **Variant gate eval is per-user inside brief, but per-strategy within.** The brief is per-user; `run_promotion_gate_for_user` iterates the user's EVALUATING proposals. Each proposal's gate-eval calls `compare_variant_to_parent` which internally walks fills. Cost: O(N_proposals × N_fills) per user; for typical N_proposals=1-2 active validations, trivial.

14. **No new MCP tools, no new endpoints in §3a.** §3b adds the promote endpoint + MCP additive fields. §3a is pure backend service + lifecycle + migration.

15. **`_router_token` discipline preserved.** §3a adds nothing to order-routing code.

16. **`check_agent_no_db_access.sh` unaffected.** §3a adds nothing to `apps/agent/`.

17. **`check_workbench_mcp_readonly.sh` green.** No MCP changes.

18. **Walk-away ≥1h before merge.** Per Retrospective Rec #6. The gate evaluator is the methodologically heaviest part — fresh re-read catches edge cases (especially drawdown rolling-window semantics).

19. **The §1b flaky test** has not resurfaced through 10 prior sessions. Watch.

20. **Standing cleanup-PR carry-forwards:** `check_p3_coverage.py --cov-report=xml` locally; explicit `git add` over `Docs/`.

---

## §3a-gate.9 — Commit and PR

Branch: `feat/p6b-session3a-promotion-gate`. Single PR; walk-away ≥1 hour before merge.

Tag: `git tag -a p6b-session3a-gate-complete -m "P6b §3a-gate promotion gate + lifecycle states + evidence bundle"`.

After §3a-gate ships: draft `TradingWorkbench_P6b_Session3b_promote_v0_1.md` against this Results doc. **Do not** draft §3b-promote speculatively before §3a-gate ships (Retrospective Rec #10).

---

## §3a-gate.10 — Verification Checklist (full session)

- [ ] §3a-g.1 Migration adds three `ProposalState` enum values + `Strategy.last_promoted_at` column; round-trips cleanly.
- [ ] §3a-g.2 `promotion_gate.py` service: 4-criterion evaluator with per-criterion `GateCriterionResult`; composite `EvidenceBundle.all_criteria_passed`; threshold reads from `agent_envelope_json.promotion_thresholds` with defaults.
- [ ] §3a-g.3 `bundle_to_json` serializer: full snapshot including equity curves; consumed by §3b's UI + MCP additions.
- [ ] §3a-g.4 Morning brief gains `run_promotion_gate_for_user` pass: per-user, per-EVALUATING-proposal; merge-write bundle; transition to EVIDENCE_READY on first gate-pass; one audit row per transition.
- [ ] §3a-g.5 `AuditAction.STRATEGY_PROMOTED` added; `audit_immutability` invariant green.
- [ ] §3a-g.6 ~22 backend tests pass; full suite green; mypy/ruff clean; non-negotiable merge-preserve invariant test passing.
- [ ] §3a-g.7 Manual smoke: migration round-trip + gate eval + EVIDENCE_READY transition + bundle inspection + paper smoke byte-identical.
- [ ] §3a-g.8 Notes & gotchas reviewed.
- [ ] `_router_token` discipline preserved; ADR-0002 invariant green.
- [ ] `audit_immutability` invariant green with `STRATEGY_PROMOTED` addition.
- [ ] `check_agent_no_db_access.sh` unaffected.
- [ ] `check_workbench_mcp_readonly.sh` green.
- [ ] All 13 CI invariants + 3 coverage gates green; P3 gate verified locally with `--cov-report=xml`.
- [ ] §3a-g.9 PR merged; `p6b-session3a-gate-complete` tag pushed.

---

# Results template stub — fill at execution time

```markdown
# P6b Session 3a-gate — Results (go / no-go record)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | [YYYY-MM-DD] |
| Phase | P6b §3a-gate — Promotion Gate + Lifecycle States + Evidence Bundle |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Shipped as | PR **#[NN]** — branch `feat/p6b-session3a-promotion-gate`; tag **`p6b-session3a-gate-complete`** |
| Built against | `main` at `p6b-session2-variant-complete` (`f500708`) |
| Verdict | **GO / NO-GO.** [Summary; P6b §3a-gate shipped; §3b-promote to follow.] |
| Method | Executed: full backend suite + new modules; mypy; ruff; migration round-trip; all CI invariants. |

## Gates — PASS (executed)

| § | Gate | Result |
|---|---|---|
| 3a-g.1 | Migration round-trip + enum + column | [✅ / details] |
| 3a-g.2 | 4-criterion gate evaluator + per-criterion results | [✅ / details] |
| 3a-g.3 | Bundle serialization | [✅ / details] |
| 3a-g.4 | Morning-brief gate-eval pass + transition + audit | [✅ / details] |
| 3a-g.5 | `STRATEGY_PROMOTED` enum added; audit_immutability green | [✅ / details] |
| 3a-g.6 | ~22 backend tests pass; merge-preserve invariant green | [✅ / details] |
| 3a-g.7 | Manual smoke; paper smoke byte-identical | [✅ / details] |
| — | `_router_token` discipline preserved | [✅] |
| — | `audit_immutability` invariant green | [✅] |
| — | All 13 CI invariants + 3 coverage gates green | [✅] |

## Deliberate deviations (as-built vs the v0.1 plan)

Pre-named candidates (from v0.1's Candid Acknowledgment):

- **[Sharpe margin: relative vs absolute]** — [relative ×1.05 held / required absolute +0.05 per ADR text.]
- **[7-day divergence calc methodology]** — [rolling worst peak-to-trough held / required different semantics.]
- **[Absolute return strict vs ≥]** — [`> 0` held / changed to `≥ 0`.]
- **[Duration OR vs AND]** — [OR held / required AND per ADR text.]
- **[EVIDENCE_READY stickiness]** — [confirmed sticky / required rollback semantics.]
- **[Bundle refresh on already-EVIDENCE_READY]** — [update held / required freeze.]
- **[Brief integration site]** — [drift-sibling worked / required different placement.]
- **[Race handling on terminated variant mid-eval]** — [try/except held / required pre-check.]

Other deviations:

- **[Deviation N].** [What changed and why.]

## Findings / punch list

- [ ] [Anything specific.]
- [ ] [Flaky test status.]

## Deferred gates — require a live stack

- [ ] **Real variant accumulating fills + gate evaluating against real data** end-to-end.
- [ ] **Mon-Fri 09:00 ET brief run with gate fires + transition** on a live stack.
- [ ] **Post-merge CI run green** — pending PR.

## To close §3a-gate cleanly

1. Walk away ≥1 hour before opening PR.
2. Confirm post-merge CI green; tag `p6b-session3a-gate-complete`.
3. **Next: §3b-promote** — endpoint + UI fourth state + cooldown cron + lockout enforcement + MCP additive fields — draft against this Results doc.

---

*P6b Session 3a-gate results v0.1 — recorded [DATE].*
```

---

*End of P6b Session 3a-gate v0.1. Drafted against §2c-variant Results' 5 execution-time deviations + the 11-question architecture-decision turn's settled answers (Q1 morning-brief cadence, Q2 stay-in-EVALUATING failure mode, Q3 envelope-flag promotion approval, Q4 PROMOTING-as-cooldown-state, Q5 full proposal lockout, Q6 split into §3a-gate + §3b-promote) + 5 carrying leans (bundle at evaluation_results_json sub-key, STRATEGY_PROMOTED audit action only, MCP additive extension, P5§7 cooldown reuse, UI fourth state on VariantCard). Ships the migration (3 new lifecycle states + last_promoted_at column), 4-criterion gate evaluator (duration / sharpe-margin / absolute-return / drawdown-divergence), evidence bundle (`evaluation_results_json.evidence_bundle` sub-key with merge-write), morning-brief integration with EVALUATING → EVIDENCE_READY transition, and `STRATEGY_PROMOTED` audit action definition. Strategy.last_promoted_at column exists but unread; STRATEGY_PROMOTED enum exists but unwritten — both consumed by §3b. No promotion endpoint, no UI, no cooldown cron, no MCP extension — all §3b. The §2b equity-curve primitive that §1a-drift deferred is now the substrate for the 4-criterion gate's Sharpe + drawdown checks.*
