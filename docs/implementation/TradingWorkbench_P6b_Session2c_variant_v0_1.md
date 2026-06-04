# P6b Session 2c-variant — Variant UI Surfaces

| Field | Value |
|---|---|
| Document version | **v0.1** (drafted against `TradingWorkbench_P6b_Session2b_variant_Results_v0.1.md` + the 6-question UI architecture turn) |
| Date | 2026-06-04 |
| Phase | **P6b — Direction v0.2 deferred capabilities**, **§2c-variant** (UI half of P6b Session 2; closes P6b §2 by adding the strategy-detail variant card + Dashboard variants widget on top of §2b's comparison data layer) |
| Predecessor | `TradingWorkbench_P6b_Session2b_variant_Results_v0.1.md` (tag `p6b-session2b-variant-complete` pending PR + walk-away) |
| Successor | (P6b §2 closes after §2c-variant cross-session verification; next planning conversation = P6b §3 [promotion gate, ADR 0007] — out of scope) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | **Strategy-detail `VariantCard`** at `apps/frontend/src/pages/Strategies/Detail.tsx`: full surface per Q2 settled — inline metrics table (live vs variant + deltas) + equity-curve chart (Q3 Lightweight Charts) + manual "Validate proposal" + "Stop validation" buttons (Q4+Q5 settled, both shown when conditions met). Plain `useState/useEffect` pattern matching `DriftCard` (no QueryClientProvider in Strategies/Detail.tsx tree per §1b-drift Results deviation #1). **Dashboard variants widget** at `apps/frontend/src/components/dashboard/VariantsCard.tsx` (Q1 settled): react-query like `MorningBriefCard`; renders only when ≥1 in-flight variant exists for the user; each entry links to `/strategies/{parent_id}`. **Two small backend extensions**: (a) GET `/api/v1/strategies/{id}/variant-comparison` response additively includes `live_equity_curve` + `variant_equity_curve` arrays (series for chart rendering) + `spawn_proposal_id` (needed by Stop button); (b) new GET `/api/v1/variants` endpoint returns user-scoped list of in-flight variants for the Dashboard widget (avoids `useQueries` fan-out per §1b-drift Results lesson). **Lightweight Charts** (Apache 2.0, no licensing constraint per the TradingView clarification turn) installed as frontend dep. Frontend `variantsApi` client extends with three methods (getComparison, validate, stop) + types. Manual buttons call existing §2a endpoints `POST /proposals/{id}/validate` and `POST /proposals/{id}/stop-validation`. **No new audit action** (all writes go through §2a's existing actions). **No frontend QueryClientProvider** added (variant card is plain useState; Dashboard widget reuses existing Dashboard provider). **No new migration**. Single PR. |
| Estimated wall time | 6-7h (~1.5h backend additions, ~3h card + chart, ~1h widget, ~1.5h tests + smoke) |
| Stopping point | `git tag p6b-session2c-variant-complete`. Then run P6b §2 cross-session verification → tag `p6b-session2-variant-complete`. |
| Tests added | ~10 backend (endpoint extensions + new variants endpoint) + ~8 frontend (vitest) |
| Out of scope | Variant comparison historical timeline (variant-now vs variant-week-ago — P6+ once first-quarter data justifies). Equity-curve chart interactions beyond basic hover (zoom, range selection — P6+). Variants-overview-as-page (`/variants` route — Dashboard widget is the v1 surface; expand only if widget gets crowded). Comparison narrative ("Variant is outperforming live on Sharpe by X%" prose summary — P6+ if review feedback wants it). Per-variant audit-log surface (visible via existing audit-log views; no dedicated UI). Drift card + variant card consolidation on strategy detail (both exist; ordering / collapse-by-default — P6+ UX polish). EVALUATING / EVIDENCE_READY / PROMOTING / PROMOTED lifecycle states (§3). 4-criterion promotion gate UI (§3). |

---

## ⚠ Review corrections (2026-06-04) — verified against shipped code at `p6b-session2b-variant-complete`

This v0.1 was drafted before grepping the live frontend + the §2b backend. The sketches below carry drift that would not compile / would fail to install. These corrections **supersede the sketches** wherever they conflict (applied at implementation time).

1. **NO `lightweight-charts`.** The repo uses **pnpm** (not `npm`), the lib is **not installed**, and **Norton SSL blocks the pnpm registry** (the standing `pnpm add` blocker) — so it **cannot be installed locally**. The codebase already draws equity curves with a **zero-dependency inline SVG** (`apps/frontend/src/pages/Strategies/BacktestResultsView.tsx::EquityCurveChart` — `viewBox`, a `<path d=…>`, Tailwind). → §2c's chart is a **two-series inline SVG** (`VariantEquityChart`) modeled on it. **§2c.5 (install step) is deleted; no new frontend dependency.** All `createChart`/`IChartApi`/`ResizeObserver`/`addLineSeries` code is dropped.
2. **Backend serializer names** — §2b shipped `_variant_comparison_dict` / `_variant_side_metrics_dict` (NOT `_comparison_to_response` / `_metrics_to_dict`); the endpoint is `variant_comparison(strategy_id, request, …)` building the dict inline. §2c **extends those**.
3. **`VariantComparison` has no equity-curve fields** — extend the §2b dataclass with `live_equity_curve` / `variant_equity_curve: list[tuple[datetime, Decimal]]` (default `()`), populate them in `compare_variant_to_parent` (the curves are already computed there as `parent_curve`/`variant_curve` — just thread through). This is the doc's own Option A.
4. **`spawn_proposal_id`: there is NO `Strategy.spawn_proposal_id` column.** A variant is a clone with `parent_strategy_id`; the proposal linkage lives on the proposal: spawn sets the proposal `state=EVALUATING` + `evaluation_results_json.paper_variant.variant_strategy_id = variant.id`. → derive it by querying the **EVALUATING `StrategyProposal` for the parent** (the one whose `paper_variant.variant_strategy_id == variant.id`). NOT a column read, NOT audit-log derivation.
5. **New-endpoint imports** — `from app.api.deps import …` does not exist. Use the **drift.py pattern**: `from app.auth.stub import CurrentUser, get_current_user` + `from app.db.session import get_session`. Router has **no prefix**; route is `@router.get("/variants")`; register `api_router.include_router(variants.router)`. Serialize `parent.status.value` (StrEnum). Variant rows carry `user_id` (cloned from parent) — filter on it directly.
6. **Frontend `Strategy` + `ACTIVE_STRATEGY_STATUSES` import from `@/api/types`** (not `@/api/strategies`). `ACTIVE_STRATEGY_STATUSES = ["paper","live"]`.
7. **Component locations** — `VariantCard` → `@/components/strategies/VariantCard.tsx` (where **DriftCard lives**, not `pages/Strategies/components/`). Dashboard widget → `@/components/strategies/VariantsCard.tsx`. DriftCard is mounted **inside** the `ACTIVE_STRATEGY_STATUSES.includes(strategy.status)` guard in `pages/Strategies/Detail.tsx` (line ~158) — mount VariantCard right after it, passing the whole `strategy` (it needs both `id` and `status`).
8. **Tailwind, not semantic CSS classes.** The sketch's `className="variant-card" / "comparison-table" / "error" / "dashboard-card"` don't exist (no stylesheet). Rewrite all JSX with **Tailwind utilities** matching DriftCard (`rounded border border-neutral-800 bg-neutral-950 p-3`, `text-[11px]`, neutral palette) and the Dashboard cards.
9. **`apiFetch` POST** needs `body: JSON.stringify({})` (caller stringifies; cf. `driftApi.check`). Imported from `./client` within `src/api`.
10. **TS metric nullability** — `VariantSideMetrics` fields (`win_rate`, `avg_return_per_trade`, `sharpe_ratio`, `max_drawdown`) are **non-null `number`** (the §2b dataclass returns 0.0, never None). Only the **delta** fields are `number | null` (`_pct_delta` → None on a zero/None denominator). Win-rate delta (`win_rate_delta_pp`) is always a number in §2b but type it `number | null` for safety.
11. **react-query** — `useQuery` exposes `isLoading` (not `isPending`); `isPending` is for `useMutation`. The widget uses `useQuery` → `isLoading`. The widget lives under the root `QueryClientProvider` (`main.tsx`); the VariantCard does NOT (Detail.tsx has no provider) → plain `useState/useEffect` like DriftCard.
12. **No MCP change** (count stays 19); **no migration**; **no new audit action**; spawn/stop reuse §2a's `POST /proposals/{id}/validate` + `/stop-validation`.

---

## How this differs from §2b-variant Results

Five §2b-variant execution-time deviations + their implications for §2c:

- **`VariantSideMetrics` is the comparison shape, not `BacktestMetrics`.** §2c's frontend types match this exactly — `trade_count`, `win_rate`, `avg_return_per_trade`, `sharpe_ratio` (nullable), `max_drawdown` (nullable). The TypeScript interfaces mirror the §2b dataclass.
- **Envelope key: `auto_validate_proposals` (not `auto_spawn_variant`).** §2c's UI strings use "validate" / "validation" vocabulary throughout — button labels, tooltips, status badges, widget headers. **Bake this in everywhere.**
- **`find_in_flight_variant` is a module-level helper** (§2b deviation #2). §2c's new GET `/variants` endpoint reuses it directly.
- **`spawn_proposal_id` discoverability** — to call `POST /proposals/{id}/stop-validation`, the frontend needs the spawn proposal_id. §2b's GET /variant-comparison response likely doesn't include it (verify at code-paste time). §2c adds it additively to the response, and includes it in the new /variants endpoint response per-entry.
- **SQLite tz coercion** (§2b deviation #3) — not directly relevant to §2c (no new datetime SQL queries), but the new /variants endpoint filters by `Strategy.status == PAPER_VARIANT` (no datetime predicate) so no tz handling needed.

Plus all standing P6+P6b deviations applicable to frontend:
- `@tanstack/react-query` v5 object API (per §2b-rv) — Dashboard widget uses it; VariantCard does NOT (matches DriftCard pattern per §1b-drift Results deviation #1).
- Frontend imports via `@/` alias (per §2b-rv).
- Endpoints on `proposals.py::strategies_router` (per §1b coverage-gate lesson) — the equity-curve extension is on the existing endpoint there; the new /variants endpoint goes in a new file `app/api/v1/variants.py` (off P2-gated `strategies.py`, mirroring the §1b-drift `drift.py` pattern).

---

## ⚠ Posture

**§2c-variant closes P6b §2.** Three principles:

1. **UI vocabulary is "validation," not "variant" or "spawn."** Users see "Validate proposal" buttons, "Stop validation" buttons, "Validation in progress" badges, "Active validations" widget headers. The word "variant" is implementation jargon; "validation" is the user concept. Per §2b's `auto_validate_proposals` envelope key rename.

2. **VariantCard uses plain `useState/useEffect`, not react-query.** Strategies/Detail.tsx has no QueryClientProvider in its tree (per §1b-drift Results deviation #1 — same reason DriftCard avoided react-query). Manually manage loading + data + error state. Refresh on button-click mutations.

3. **Dashboard widget uses react-query but renders nothing when empty.** Same pattern as the §1b-drift BriefDriftSection — empty state in the brief surface is silence, not "no active variants." Empty state is meaningful UX in the strategy-detail card (where the user is asking about THIS strategy) but noise in the Dashboard (where they're scanning).

Paper smoke from P1-P5 byte-identical. ADR-0002 `_router_token` discipline unaffected. `check_agent_no_db_access.sh` unaffected.

---

## Verification checklist — grep before pasting any code below

Per Retrospective Rec #5.

- [ ] **`Strategies/Detail.tsx` location and structure** — confirmed in §1b-drift Results. Check whether it currently imports `DriftCard`; the new `VariantCard` mounts in the same area.
- [ ] **No QueryClientProvider in Strategies/Detail.tsx tree** — per §1b-drift Results deviation #1. Confirm; if a provider has been added since, VariantCard can use react-query like the widget.
- [ ] **`components/dashboard/MorningBriefCard.tsx` location** — confirmed in §1b-drift; the new `VariantsCard` is its neighbor. Find the Dashboard's component list and add the import.
- [ ] **Dashboard has QueryClientProvider** — confirmed in §1b-drift Results deviation #1 (MorningBriefCard uses react-query). VariantsCard reuses.
- [ ] **`@tanstack/react-query` v5 object API** — `useQuery({queryKey, queryFn})`, `useMutation({mutationFn, onSuccess})`, `isPending`, `invalidateQueries({queryKey})`. Verify version in `apps/frontend/package.json`.
- [ ] **`lightweight-charts` install path** — `npm install lightweight-charts` (or `pnpm`/`yarn` depending on the repo). Apache 2.0; no domain restriction; ships v4.x as of 2026.
- [ ] **`GET /variant-comparison` current response shape at `p6b-session2b-variant-complete` HEAD** — confirm whether it includes `spawn_proposal_id` and/or equity curves. If absent, §2c adds them additively (response field additions; existing clients unaffected).
- [ ] **`Strategy` model — does it have `spawn_proposal_id` column?** Per §2a, the PAPER_VARIANT row was created from a proposal; check whether the linkage is via a direct FK column or only via audit-log payload. §2c uses whatever exists; if only audit-log, §2c may need to derive at endpoint-time (acceptable for v1).
- [ ] **`POST /proposals/{id}/validate` and `POST /proposals/{id}/stop-validation` endpoints** — confirmed shipped in §2a Results gates `2a-v.4`. Frontend `variantsApi.validate` / `.stop` hit these.
- [ ] **Proposals API: how to find an ACCEPTED-but-not-APPLIED proposal for a strategy?** Per §1a + §1b shipped: `GET /api/v1/proposals?strategy_id=X&state=ACCEPTED`. The VariantCard fetches this on render to decide whether to show "Validate" button.
- [ ] **`Strategy.status` lowercase StrEnum values** — per §1a-drift correction: `live`, `paper`, `idle`, `paper_variant`. The VariantCard checks `parent.status === "live"` for Spawn button visibility.
- [ ] **`Strategy.parent_strategy_id` and `Strategy.status === "paper_variant"`** — per §2a Model (a) settled. The /variants endpoint filters by these.

---

## Candid acknowledgment — what this session plan cannot predict

- **`spawn_proposal_id` discoverability.** If §2a's Strategy row carries a direct FK column (`spawn_proposal_id`), it's a trivial read. If not, the GET /variant-comparison endpoint must derive it from audit-log (query PAPER_VARIANT_SPAWNED rows with `target_id == str(variant_id)`, read `payload.proposal_id`). Acceptable but slower; verify at code-paste time. If audit-log-derived, cache within the endpoint call.
- **Equity-curve data on every comparison fetch.** Adding `live_equity_curve` + `variant_equity_curve` to the response increases payload size — ~22 points × 2 series × 30 bytes ≈ 1.3KB extra per call. Trivial in dev; if production fetches get frequent (every page-load of strategy-detail), consider lazy-loading: separate endpoint for curves only, or `?include=curves` query param. v1 lean: include unconditionally; profile if hot.
- **Lightweight Charts version pinning.** v4.x is current as of 2026; the install pins via package-lock. v5 may release during P6b lifecycle with API changes. Pin exact version (`"lightweight-charts": "4.x.x"`); document for §3+.
- **Chart resize behavior.** Lightweight Charts needs explicit resize handling (`chart.resize()`) on container size changes. If the VariantCard collapses/expands or the detail page reflows, the chart may render at stale dimensions. Mitigate with a ResizeObserver in the component lifecycle. Test in vitest with jsdom (limited; visual test in smoke).
- **"Validate proposal" button — which proposal to validate?** When a strategy has multiple ACCEPTED-but-not-APPLIED proposals (rare but possible), which one does the button validate? v1 lean: most recent by `generated_at`. UI shows the proposal summary/changes in a confirmation modal before submitting. Alternative: show all eligible proposals as a list of validate buttons. v1 lean: most-recent + modal confirm; defer the list UX.
- **Spawn button visibility race.** Parent could transition LIVE → IDLE between page-load and click. Backend's IDLE-check (§2a) rejects with 409 / 400. Frontend handles by refetching state on error. Acceptable; don't try to prevent every race.
- **Manual Stop button + D8 invalidation race.** User clicks Stop; concurrently, parent transitions out of ACTIVE (D8 triggers terminate). Both end up calling `terminate_for_parent`. §2a's terminate is idempotent (the second call no-ops because variant.status no longer PAPER_VARIANT after first call). v1 acceptable.
- **`VariantsCard` polling vs websocket.** v1: react-query default `staleTime` (5min) + manual invalidate on navigation. No polling; no websocket. If users expect "live updating" variant metrics, P6+ adds polling. Document.
- **Chart color coding.** Convention: variant = blue (advisory / new); live = gray (baseline / known). Both colors should be color-blind-safe (Blue + neutral gray works for most CVD types). Document in `Notes & gotchas`.
- **Dashboard widget ordering.** Where does VariantsCard sit relative to MorningBriefCard? Both top-of-fold, both advisory. Suggestion: VariantsCard above MorningBriefCard (validations are more time-sensitive than the brief). v1 lean: above. Push back if you want the brief on top.
- **Empty-state messaging on the variant card.** When parent is LIVE but no in-flight variant AND no ACCEPTED unapplied proposal: "No active validation. Accept a proposal to enable validation." vs. just rendering nothing. v1 lean: render the empty state with the message (matches DriftCard pattern of always-render on strategy detail).

---

## Goal

After §2c-variant ships:

- A user on `/strategies/{id}` sees the VariantCard alongside DriftCard with three possible states:
  - **No active variant + no eligible proposal**: render empty message "No active validation."
  - **No active variant + has ACCEPTED unapplied proposal**: render "Validate this proposal" button + proposal summary; click → confirms → calls `POST /proposals/{id}/validate`; card refreshes to show in-flight state.
  - **Active in-flight variant**: render metrics table (live vs variant + deltas) + equity-curve chart (two-series, color-coded) + "Stop validation" button + spawn date + trade counts; click Stop → confirms → calls `POST /proposals/{id}/stop-validation`; card refreshes to empty/eligible state.
- A user viewing the Dashboard sees a VariantsCard listing each in-flight variant with strategy name + spawn date + variant trade count + quick "View" link to strategy detail. Empty state: card renders nothing.
- The proposal agent's data view (via MCP tool from §2b) is unchanged — agent sees the same comparison.
- All §2b mechanics unchanged — no service-module breaks; no migration; no new audit action; no new lifecycle states.
- All 13 CI invariants + 3 coverage gates green.
- Paper smoke from P1-P5 byte-identical.
- `p6b-session2c-variant-complete` tagged. After cross-session verification, `p6b-session2-variant-complete` tagged.

---

## §2c-variant.1 — Backend extensions

### 1a — Extend GET `/variant-comparison` response (additive)

In `apps/backend/app/api/v1/proposals.py::strategies_router`, extend the `_comparison_to_response` serializer to include the equity-curve series + spawn_proposal_id:

```python
def _comparison_to_response(comp, *, spawn_proposal_id: int) -> dict:
    """Serialize VariantComparison; extended in §2c-variant with equity
    curves + spawn_proposal_id for the UI."""
    return {
        "parent_strategy_id": comp.parent_strategy_id,
        "variant_strategy_id": comp.variant_strategy_id,
        "spawn_proposal_id": spawn_proposal_id,    # NEW in §2c
        "window_start": comp.window_start.isoformat(),
        "window_end": comp.window_end.isoformat(),
        "live_metrics": _metrics_to_dict(comp.live_metrics),
        "variant_metrics": _metrics_to_dict(comp.variant_metrics),
        "deltas": comp.deltas,
        "live_trade_count": comp.live_trade_count,
        "variant_trade_count": comp.variant_trade_count,
        # NEW in §2c: equity-curve series for chart rendering.
        "live_equity_curve": [
            {"ts": ts.isoformat(), "equity": float(eq)}
            for ts, eq in comp.live_equity_curve
        ],
        "variant_equity_curve": [
            {"ts": ts.isoformat(), "equity": float(eq)}
            for ts, eq in comp.variant_equity_curve
        ],
    }
```

This requires `VariantComparison` to carry the equity-curve series — extending §2b's dataclass to include them. Two paths:

**Option A (preferred):** Extend `VariantComparison` dataclass with `live_equity_curve: list[tuple[datetime, Decimal]]` + `variant_equity_curve: list[tuple[datetime, Decimal]]`. Update `compare_variant_to_parent` to return them (they're already computed via `reconstruct_equity_curve` calls; just thread through). Small additive change.

**Option B (fallback):** Recompute equity curves inside `_comparison_to_response`. Wasteful (duplicates `reconstruct_equity_curve` work); avoid.

Lean: A. Backend change: ~15 lines in paper_variant.py.

For `spawn_proposal_id`: per verification checklist, find via `Strategy.spawn_proposal_id` column OR audit-log query for `PAPER_VARIANT_SPAWNED with target_id == str(variant.id)`. If column exists, trivial read. Sketch assuming column:

```python
# In the endpoint, after looking up the in-flight variant:
spawn_proposal_id = variant.spawn_proposal_id   # if column exists
# Or, if audit-log-derived:
# audit_row = (await session.execute(
#     select(AuditLog)
#     .where(AuditLog.action == AuditAction.PAPER_VARIANT_SPAWNED)
#     .where(AuditLog.target_type == "strategy")
#     .where(AuditLog.target_id == str(variant.id))
#     .order_by(AuditLog.id.desc()).limit(1)
# )).scalar_one_or_none()
# payload = json.loads(audit_row.payload_json) if audit_row else {}
# spawn_proposal_id = payload.get("proposal_id")
```

### 1b — New endpoint GET `/api/v1/variants`

Create `apps/backend/app/api/v1/variants.py` (mirror of §1b-drift's `drift.py` placement):

```python
"""GET /api/v1/variants — user-scoped list of in-flight paper variants.

Renders the Dashboard VariantsCard. One call instead of useQueries fan-out
across all user strategies (per §1b-drift Results lesson).
"""
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_session
from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
# Per §2b deviation #2: find_in_flight_variant is module-level in paper_variant.py
# but here we list ALL variants, so use a direct query.

router = APIRouter(prefix="/variants", tags=["variants"])


@router.get("", response_model=dict)
async def list_in_flight_variants(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return user's in-flight paper variants with summary info."""
    # Find PAPER_VARIANT strategies whose parent belongs to current_user.
    rows = (await session.execute(
        select(Strategy)
        .where(Strategy.status == StrategyStatus.PAPER_VARIANT)
        .where(Strategy.user_id == current_user.id)
    )).scalars().all()

    items = []
    for variant in rows:
        # Look up parent strategy (might be archived/idle; we still surface).
        parent = await session.get(Strategy, variant.parent_strategy_id)
        items.append({
            "variant_strategy_id": variant.id,
            "parent_strategy_id": variant.parent_strategy_id,
            "parent_strategy_name": parent.name if parent else None,
            "parent_strategy_status": parent.status if parent else None,
            "spawn_proposal_id": variant.spawn_proposal_id,   # if column exists
            "spawned_at": variant.created_at.isoformat() if variant.created_at else None,
        })

    return {"items": items}
```

Register in `apps/backend/app/api/v1/__init__.py`:

```python
from app.api.v1 import variants
api_router.include_router(variants.router)
```

**Verify before pasting:**
- `Strategy.user_id` exists on PAPER_VARIANT rows (it should — the variant is owned by the user who accepted the proposal).
- `Strategy.spawn_proposal_id` column existence (verification checklist item).
- `Strategy.name` field exists; if not, use `Strategy.code_path` or similar identifier.

---

## §2c-variant.2 — Frontend API client

Create `apps/frontend/src/api/variants.ts`:

```typescript
import { apiFetch } from "./client";

export interface VariantSideMetrics {
  trade_count: number;
  win_rate: number;
  avg_return_per_trade: number;
  sharpe_ratio: number | null;
  max_drawdown: number | null;
}

export interface VariantDeltas {
  sharpe_delta_pct: number | null;
  max_drawdown_delta_pct: number | null;
  win_rate_delta_pp: number | null;
  avg_return_delta_pct: number | null;
}

export interface EquityCurvePoint {
  ts: string;       // ISO datetime
  equity: number;
}

export interface VariantComparison {
  parent_strategy_id: number;
  variant_strategy_id: number;
  spawn_proposal_id: number;
  window_start: string;
  window_end: string;
  live_metrics: VariantSideMetrics;
  variant_metrics: VariantSideMetrics;
  deltas: VariantDeltas;
  live_trade_count: number;
  variant_trade_count: number;
  live_equity_curve: EquityCurvePoint[];
  variant_equity_curve: EquityCurvePoint[];
}

export interface VariantStatusResponse {
  status: "no_active_variant" | "variant_active";
  strategy_id: number;
  variant_strategy_id?: number;
  comparison?: VariantComparison;
}

export interface InFlightVariantSummary {
  variant_strategy_id: number;
  parent_strategy_id: number;
  parent_strategy_name: string | null;
  parent_strategy_status: string | null;
  spawn_proposal_id: number;
  spawned_at: string | null;
}

export const variantsApi = {
  getComparison: (strategyId: number) =>
    apiFetch<VariantStatusResponse>(
      `/api/v1/strategies/${strategyId}/variant-comparison`,
    ),

  listInFlight: () =>
    apiFetch<{ items: InFlightVariantSummary[] }>(`/api/v1/variants`),

  validate: (proposalId: number) =>
    apiFetch(`/api/v1/proposals/${proposalId}/validate`, {
      method: "POST",
    }),

  stopValidation: (proposalId: number) =>
    apiFetch(`/api/v1/proposals/${proposalId}/stop-validation`, {
      method: "POST",
    }),
};
```

---

## §2c-variant.3 — Strategy-detail VariantCard

Create `apps/frontend/src/pages/Strategies/components/VariantCard.tsx`:

```typescript
import { useState, useEffect, useRef } from "react";
import { createChart, IChartApi, ISeriesApi } from "lightweight-charts";
import {
  variantsApi, VariantStatusResponse, VariantComparison,
} from "@/api/variants";
import { proposalsApi, Proposal } from "@/api/proposals";   // existing
import type { Strategy } from "@/api/strategies";

interface Props {
  strategy: Strategy;
}

/**
 * VariantCard — three-state component (matching DriftCard's plain
 * useState/useEffect pattern per §1b-drift Results deviation #1).
 *
 * States:
 *   - "loading": fetching
 *   - "active": in-flight variant; shows table + chart + Stop button
 *   - "eligible": no variant + eligible proposal; shows Validate button
 *   - "empty": no variant + no eligible proposal; shows empty message
 */
export function VariantCard({ strategy }: Props) {
  const [status, setStatus] = useState<VariantStatusResponse | null>(null);
  const [eligibleProposal, setEligibleProposal] = useState<Proposal | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const [statusResp, proposalsResp] = await Promise.all([
        variantsApi.getComparison(strategy.id),
        proposalsApi.list({ strategy_id: strategy.id, state: "ACCEPTED" }),
      ]);
      setStatus(statusResp);
      // Find most recent ACCEPTED proposal not yet APPLIED.
      const eligible = (proposalsResp.items ?? [])
        .filter((p) => p.state === "ACCEPTED")
        .sort((a, b) =>
          new Date(b.generated_at).getTime() - new Date(a.generated_at).getTime(),
        )[0] ?? null;
      setEligibleProposal(eligible);
    } catch (e) {
      // Best-effort — leave previous state
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, [strategy.id]);

  const onValidate = async (proposalId: number) => {
    if (!confirm("Spawn paper variant to validate this proposal?")) return;
    setActionPending(true);
    setActionError(null);
    try {
      await variantsApi.validate(proposalId);
      await refresh();
    } catch (e: any) {
      setActionError(e?.message ?? "Failed to start validation");
    } finally {
      setActionPending(false);
    }
  };

  const onStop = async (proposalId: number) => {
    if (!confirm("Stop validation and terminate the paper variant?")) return;
    setActionPending(true);
    setActionError(null);
    try {
      await variantsApi.stopValidation(proposalId);
      await refresh();
    } catch (e: any) {
      setActionError(e?.message ?? "Failed to stop validation");
    } finally {
      setActionPending(false);
    }
  };

  // Only render the card meaningfully for active strategies.
  // (Matches DriftCard's status filter via ACTIVE_STRATEGY_STATUSES.)
  const isActive = strategy.status === "live" || strategy.status === "paper";
  if (!isActive) return null;

  if (loading) {
    return (
      <div className="variant-card">
        <h4>Validation</h4>
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div className="variant-card">
      <h4>Validation</h4>
      {actionError && <p className="error">{actionError}</p>}

      {status?.status === "variant_active" && status.comparison ? (
        <ActiveVariantDisplay
          comparison={status.comparison}
          actionPending={actionPending}
          onStop={onStop}
        />
      ) : eligibleProposal && strategy.status === "live" ? (
        <EligibleProposalDisplay
          proposal={eligibleProposal}
          actionPending={actionPending}
          onValidate={onValidate}
        />
      ) : (
        <p className="empty">
          No active validation. Accept a proposal on this LIVE strategy to
          enable paper-variant validation.
        </p>
      )}
    </div>
  );
}

function EligibleProposalDisplay({
  proposal, actionPending, onValidate,
}: {
  proposal: Proposal;
  actionPending: boolean;
  onValidate: (proposalId: number) => void;
}) {
  return (
    <div className="eligible-proposal">
      <p>Accepted proposal awaiting validation:</p>
      <p className="proposal-summary">{proposal.proposal_payload.summary ?? "Proposal #" + proposal.id}</p>
      <button
        onClick={() => onValidate(proposal.id)}
        disabled={actionPending}
        className="validate-button"
      >
        {actionPending ? "Starting..." : "Validate this proposal"}
      </button>
    </div>
  );
}

function ActiveVariantDisplay({
  comparison, actionPending, onStop,
}: {
  comparison: VariantComparison;
  actionPending: boolean;
  onStop: (proposalId: number) => void;
}) {
  return (
    <div className="active-variant">
      <div className="variant-header">
        <span className="status-badge">Validating</span>
        <span className="spawn-date">
          Since {new Date(comparison.window_start).toLocaleDateString()}
        </span>
        <button
          onClick={() => onStop(comparison.spawn_proposal_id)}
          disabled={actionPending}
          className="stop-button"
        >
          {actionPending ? "Stopping..." : "Stop validation"}
        </button>
      </div>

      <MetricsTable comparison={comparison} />
      <EquityCurveChart comparison={comparison} />
    </div>
  );
}

function MetricsTable({ comparison }: { comparison: VariantComparison }) {
  const lm = comparison.live_metrics;
  const vm = comparison.variant_metrics;
  const d = comparison.deltas;

  const fmtPct = (v: number | null) =>
    v === null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  const fmtPp = (v: number | null) =>
    v === null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)} pp`;

  return (
    <table className="comparison-table">
      <thead>
        <tr><th>Metric</th><th>Live</th><th>Variant</th><th>Delta</th></tr>
      </thead>
      <tbody>
        <tr>
          <td>Trade count</td>
          <td>{comparison.live_trade_count}</td>
          <td>{comparison.variant_trade_count}</td>
          <td>—</td>
        </tr>
        <tr>
          <td>Win rate</td>
          <td>{(lm.win_rate * 100).toFixed(1)}%</td>
          <td>{(vm.win_rate * 100).toFixed(1)}%</td>
          <td>{fmtPp(d.win_rate_delta_pp)}</td>
        </tr>
        <tr>
          <td>Avg return / trade</td>
          <td>{(lm.avg_return_per_trade * 100).toFixed(2)}%</td>
          <td>{(vm.avg_return_per_trade * 100).toFixed(2)}%</td>
          <td>{fmtPct(d.avg_return_delta_pct)}</td>
        </tr>
        <tr>
          <td>Sharpe ratio</td>
          <td>{lm.sharpe_ratio?.toFixed(2) ?? "—"}</td>
          <td>{vm.sharpe_ratio?.toFixed(2) ?? "—"}</td>
          <td>{fmtPct(d.sharpe_delta_pct)}</td>
        </tr>
        <tr>
          <td>Max drawdown</td>
          <td>{lm.max_drawdown !== null ? (lm.max_drawdown * 100).toFixed(1) + "%" : "—"}</td>
          <td>{vm.max_drawdown !== null ? (vm.max_drawdown * 100).toFixed(1) + "%" : "—"}</td>
          <td>{fmtPct(d.max_drawdown_delta_pct)}</td>
        </tr>
      </tbody>
    </table>
  );
}

function EquityCurveChart({ comparison }: { comparison: VariantComparison }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const liveSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const variantSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      height: 220,
      layout: {
        background: { color: "transparent" },
        textColor: "#888",
      },
      grid: {
        vertLines: { color: "rgba(128,128,128,0.1)" },
        horzLines: { color: "rgba(128,128,128,0.1)" },
      },
      timeScale: { timeVisible: false, secondsVisible: false },
    });

    const liveSeries = chart.addLineSeries({
      color: "#888",      // gray for live (baseline)
      lineWidth: 2,
      title: "Live",
    });
    const variantSeries = chart.addLineSeries({
      color: "#4A90E2",    // blue for variant
      lineWidth: 2,
      title: "Variant",
    });

    chartRef.current = chart;
    liveSeriesRef.current = liveSeries;
    variantSeriesRef.current = variantSeries;

    // Resize handler.
    const observer = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
    };
  }, []);

  useEffect(() => {
    if (!liveSeriesRef.current || !variantSeriesRef.current) return;

    // Convert ISO timestamps to Lightweight-Charts time format (Unix seconds).
    const toLcData = (pts: { ts: string; equity: number }[]) =>
      pts.map((p) => ({
        time: Math.floor(new Date(p.ts).getTime() / 1000) as any,
        value: p.equity,
      }));

    liveSeriesRef.current.setData(toLcData(comparison.live_equity_curve));
    variantSeriesRef.current.setData(toLcData(comparison.variant_equity_curve));

    chartRef.current?.timeScale().fitContent();
  }, [comparison]);

  return <div ref={containerRef} className="equity-curve-chart" />;
}
```

Mount in `Strategies/Detail.tsx`:

```typescript
import { VariantCard } from "./components/VariantCard";

// In the page body, alongside DriftCard:
<DriftCard strategyId={strategy.id} />
<VariantCard strategy={strategy} />
```

**Verify before pasting:**
- `proposalsApi.list` signature — per §1b shipped, returns `{items: Proposal[]}`. The state filter may be uppercase ("ACCEPTED") or lowercase; verify.
- `Strategy` type fields — `id`, `status`, `name`. Confirm at code-paste time.
- `Proposal.state` and `Proposal.proposal_payload.summary` — confirmed per §1b / §2b-rv shipped.
- Lightweight Charts API surface — `createChart`, `addLineSeries`, `setData`, `IChartApi`, `ISeriesApi`. v4.x.

---

## §2c-variant.4 — Dashboard VariantsCard

Create `apps/frontend/src/components/dashboard/VariantsCard.tsx`:

```typescript
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { variantsApi } from "@/api/variants";

export function VariantsCard() {
  const { data, isLoading } = useQuery({
    queryKey: ["variants", "in-flight"],
    queryFn: () => variantsApi.listInFlight(),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) return null;
  const items = data?.items ?? [];
  if (items.length === 0) return null;

  return (
    <div className="dashboard-card variants-card">
      <h3>Active Validations ({items.length})</h3>
      <p className="meta">
        Paper variants validating accepted proposals against live behavior.
      </p>
      {items.map((v) => (
        <Link
          key={v.variant_strategy_id}
          to={`/strategies/${v.parent_strategy_id}`}
          className="variant-summary"
        >
          <div className="strategy-name">
            {v.parent_strategy_name ?? `Strategy #${v.parent_strategy_id}`}
          </div>
          <div className="meta">
            <span>Since {v.spawned_at ? new Date(v.spawned_at).toLocaleDateString() : "—"}</span>
            <span>Parent: {v.parent_strategy_status ?? "—"}</span>
          </div>
        </Link>
      ))}
    </div>
  );
}
```

Mount in the Dashboard above MorningBriefCard (per Candid Acknowledgment lean):

```typescript
import { VariantsCard } from "@/components/dashboard/VariantsCard";

// In the Dashboard render:
<VariantsCard />
<MorningBriefCard ... />
```

---

## §2c-variant.5 — Lightweight Charts install

```bash
cd apps/frontend
npm install lightweight-charts@^4.0.0
# Pin exact version in package.json:
#   "lightweight-charts": "4.x.x"
```

The library is Apache 2.0, no domain restriction (confirmed in the TradingView clarification turn earlier in this conversation). Bundle size: ~50KB gzipped — acceptable for a frontend dep.

Document the pin reason in `Notes & gotchas`.

---

## §2c-variant.6 — Tests

### Backend (`apps/backend/tests/api/test_variant_comparison_extended.py`)

- `test_response_includes_live_equity_curve`
- `test_response_includes_variant_equity_curve`
- `test_response_includes_spawn_proposal_id`
- `test_existing_response_fields_unchanged` — additive change doesn't break existing clients

### Backend (`apps/backend/tests/api/test_variants_endpoint.py`)

- `test_list_in_flight_returns_user_variants_only`
- `test_list_in_flight_excludes_terminated_variants`
- `test_list_in_flight_returns_empty_when_none`
- `test_list_in_flight_includes_parent_name_and_status`
- `test_list_in_flight_includes_spawn_proposal_id`
- `test_other_user_variants_not_returned`

### Frontend (`apps/frontend/src/pages/Strategies/__tests__/VariantCard.test.tsx`)

- `renders nothing for non-active strategies`
- `renders loading state initially`
- `renders empty state when no variant and no eligible proposal`
- `renders Validate button when ACCEPTED proposal exists and parent LIVE`
- `renders active state with metrics + buttons when in-flight variant exists`
- `clicking Validate calls validate API and refreshes`
- `clicking Stop calls stopValidation API and refreshes`

### Frontend (`apps/frontend/src/components/dashboard/__tests__/VariantsCard.test.tsx`)

- `renders nothing when no in-flight variants`
- `renders one entry per in-flight variant`
- `each entry links to /strategies/{parent_id}`

**Verify test paths.** Established per §1b-drift / §2b-rv conventions.

---

## §2c-variant.7 — Manual smoke

```bash
# 0. Prerequisites
git describe --tags --abbrev=0   # expect: p6b-session2b-variant-complete

# 1. Install lightweight-charts and bring up stack
cd apps/frontend && npm install lightweight-charts@^4.0.0 && cd ../..
docker compose up -d
sleep 30
./scripts/login_helper.sh

# 2. Need a strategy with an in-flight variant. If §2b smoke left one:
STRAT_ID=$(curl -s -b /tmp/cookies.txt "http://127.0.0.1:8000/api/v1/strategies" \
  | jq -r '.items[] | select(.status=="live") | .id' | head -1)
# Verify variant exists:
curl -s -b /tmp/cookies.txt "http://127.0.0.1:8000/api/v1/strategies/${STRAT_ID}/variant-comparison" | jq

# If no variant: spawn one
PROP_ID=$(curl -s -b /tmp/cookies.txt \
  "http://127.0.0.1:8000/api/v1/proposals?strategy_id=${STRAT_ID}&state=ACCEPTED" \
  | jq -r '.items[0].id')
curl -s -b /tmp/cookies.txt -X POST \
  "http://127.0.0.1:8000/api/v1/proposals/${PROP_ID}/validate" | jq

# 3. Test extended response — equity curves present
curl -s -b /tmp/cookies.txt \
  "http://127.0.0.1:8000/api/v1/strategies/${STRAT_ID}/variant-comparison" \
  | jq '.comparison | {has_live_curve: (.live_equity_curve|length>=0), has_variant_curve: (.variant_equity_curve|length>=0), spawn_proposal_id}'
# Expect: both length present, spawn_proposal_id non-null

# 4. Test new /variants endpoint
curl -s -b /tmp/cookies.txt "http://127.0.0.1:8000/api/v1/variants" | jq
# Expect: {"items": [{variant_strategy_id, parent_strategy_id, parent_strategy_name, parent_strategy_status, spawn_proposal_id, spawned_at}, ...]}

# 5. Test isolation — other user's variants not returned
# (Create user B; query /variants as user A → no user B variants)

# 6. UI smoke
# - Open / (Dashboard): VariantsCard renders above MorningBriefCard, listing in-flight variants
# - Click a variant entry → navigates to /strategies/{parent_id}
# - On /strategies/{id}: VariantCard renders next to DriftCard
#   - For in-flight variant: see metrics table + equity-curve chart + "Stop validation" button
#   - For LIVE strategy with no variant + ACCEPTED proposal: see "Validate this proposal" button
#   - For IDLE strategy: VariantCard doesn't render (matches DriftCard isActive filter)
# - Click "Stop validation" → confirm dialog → variant terminates → card returns to eligible/empty state
# - Click "Validate this proposal" on an eligible state → confirm → variant spawns → card flips to active state

# 7. Equity-curve chart visual smoke
# - Verify chart renders two lines (gray = live, blue = variant)
# - Verify resize works when browser window resizes
# - Verify hover shows date + value

# 8. LOAD-BEARING: paper smoke byte-identical
PAPER_ACC=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts \
  | jq -r '.items[] | select(.mode=="paper") | .id')
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{\"account_id\":${PAPER_ACC},\"symbol\":\"AAPL\",\"side\":\"buy\",\"type\":\"market\",\"qty\":\"1\",\"tif\":\"day\",\"source\":\"manual\"}" \
  | jq '{status}'
# Expect: status=accepted
```

**Norton-deferred posture.** Backend steps 3-5 work fully. UI steps 6-7 are interactive. Step 7's "live data accumulation" (variant gathering real fills) is the deferred gate from §2b — the chart will render whatever the backend has.

---

## §2c-variant.8 — Notes & gotchas

1. **UI vocabulary: "validation," not "variant."** Buttons say "Validate" / "Stop validation"; the badge says "Validating"; the card header says "Validation"; the Dashboard widget says "Active Validations." The word "variant" is implementation jargon visible only in tooltips/hover-text and developer surfaces. Per §2b's `auto_validate_proposals` envelope rename.

2. **VariantCard uses plain `useState/useEffect`** (matches DriftCard pattern). Strategies/Detail.tsx has no QueryClientProvider in its tree per §1b-drift Results deviation #1. If a provider is added later, the card could be refactored to react-query for cache sharing with VariantsCard.

3. **VariantsCard uses react-query** (matches MorningBriefCard pattern). Dashboard has the provider. Empty state renders `null` (no widget when no variants) — matches the silence-when-empty Dashboard convention.

4. **Lightweight Charts is Apache 2.0** — no domain restriction, no licensing application, can ship in the public GitHub repo. Per the TradingView clarification turn. Pin exact version to avoid v5 breaking-change surprises.

5. **Chart resize via ResizeObserver.** Needed because Lightweight Charts doesn't auto-resize on container changes. Lifecycle: create observer on mount, disconnect on unmount, observer fires `chart.applyOptions({width: ...})` on container resize.

6. **Chart colors: gray (live) + blue (variant).** Color-blind-safe convention; visual distinction without relying on hue-discrimination alone. Document for §3 if it adds more series.

7. **"Validate this proposal" button confirms before submitting.** `confirm()` dialog prevents accidental clicks; matches §2a's manual-spawn UX intent.

8. **"Stop validation" button also confirms.** Termination is irreversible — the variant terminates and any audit-log evidence stays, but the in-flight evaluation ends.

9. **Eligible-proposal selection: most recent ACCEPTED-but-not-APPLIED.** When a strategy has multiple, v1 picks the latest by `generated_at`. UI doesn't surface "validate proposal X vs Y" — keeps surface simple. P6+ can add list UX if needed.

10. **Backend additive change: equity-curve series in response.** Existing clients (the MCP tool from §2b) keep working — they read `live_metrics`, `variant_metrics`, `deltas` and ignore the new fields. Tests confirm the additive shape (`test_existing_response_fields_unchanged`).

11. **`spawn_proposal_id` discoverability.** Two paths depending on schema: direct column read (if `Strategy.spawn_proposal_id` exists per §2a) or audit-log derivation. Verification-checklist item; either works.

12. **Race conditions are best-effort.** Spawn-click vs parent-deactivate-by-D8: backend handles via IDLE-check. Stop-click vs D8-on-apply: both call same `terminate_for_parent` (idempotent). UI refreshes on error.

13. **No new audit action.** Spawn calls existing `POST /validate` which writes §2a's `PAPER_VARIANT_SPAWNED` + `STRATEGY_PROPOSAL_TRANSITIONED`. Stop calls existing `POST /stop-validation` which writes §2a's `PAPER_VARIANT_TERMINATED` + `STRATEGY_PROPOSAL_TRANSITIONED`. Total P6+P6b audit actions stays at 8.

14. **MCP build-server tool count unchanged.** No new MCP tools in §2c-variant — count stays at 19.

15. **`check_workbench_mcp_readonly.sh` green.** No MCP changes.

16. **`_router_token` discipline preserved.** §2c adds nothing to order-routing code.

17. **`check_agent_no_db_access.sh` unaffected.** §2c adds nothing to `apps/agent/`.

18. **Walk-away ≥1h before merge.** Per Retrospective Rec #6. The chart-integration is the trickiest part (Lightweight Charts API + lifecycle); fresh re-read catches subtle bugs.

19. **The §1b flaky test** has not resurfaced through 9 prior sessions. Watch for `test_engine.py::test_user_exception...` (§2b Results noted it).

20. **Standing cleanup-PR carry-forwards:** `check_p3_coverage.py --cov-report=xml` locally; explicit `git add` over `Docs/`.

---

## §2c-variant.9 — Commit and PR

Branch: `feat/p6b-session2c-variant-ui`. Single PR; walk-away ≥1 hour before merge.

Tag: `git tag -a p6b-session2c-variant-complete -m "P6b §2c-variant UI surfaces"`.

After §2c-variant ships: run §2c-variant.11 cross-session verification and tag `p6b-session2-variant-complete` (rolls up §2a + §2b + §2c = P6b §2 complete).

---

## §2c-variant.10 — Verification Checklist (full session)

- [ ] §2c-v.1a GET /variant-comparison response includes `live_equity_curve`, `variant_equity_curve`, `spawn_proposal_id`; existing fields unchanged (additive).
- [ ] §2c-v.1b GET /variants endpoint returns user-scoped in-flight variants; isolated per-user; new file `app/api/v1/variants.py` registered.
- [ ] §2c-v.2 `apps/frontend/src/api/variants.ts` types + methods (`getComparison`, `listInFlight`, `validate`, `stopValidation`).
- [ ] §2c-v.3 `VariantCard.tsx`: three states render correctly; plain useState/useEffect; mounted in Strategies/Detail.tsx alongside DriftCard.
- [ ] §2c-v.4 `VariantsCard.tsx`: react-query; renders nothing when empty; mounted in Dashboard above MorningBriefCard.
- [ ] §2c-v.5 Lightweight Charts installed in frontend with exact-version pin; bundle size acceptable.
- [ ] §2c-v.6 ~10 backend + ~8 frontend tests pass; full suite green; mypy/ruff clean; vitest green.
- [ ] §2c-v.7 Manual smoke: backend endpoints + UI cards + chart rendering all exercised; paper smoke byte-identical.
- [ ] §2c-v.8 Notes & gotchas reviewed; UI vocabulary consistent ("validation" everywhere).
- [ ] `_router_token` discipline preserved; ADR-0002 invariant green.
- [ ] `audit_immutability` invariant green (no schema changes).
- [ ] `check_agent_no_db_access.sh` unaffected.
- [ ] `check_workbench_mcp_readonly.sh` green.
- [ ] All 13 CI invariants + 3 coverage gates green; P3 gate verified locally with `--cov-report=xml`.
- [ ] §2c-v.9 PR merged; `p6b-session2c-variant-complete` tag pushed.
- [ ] §2c-v.11 P6b §2 cross-session verification passes; `p6b-session2-variant-complete` tag pushed.

---

## §2c-variant.11 — P6b §2 Cross-Session Verification

After §2c-variant merges and `p6b-session2c-variant-complete` is tagged, run this to confirm §2a + §2b + §2c hang together end-to-end. Tag `p6b-session2-variant-complete` only after all steps pass.

```bash
git checkout main && git pull
git describe --tags --abbrev=0
# Expect: p6b-session2c-variant-complete

# 1. All 13 CI invariants + 3 coverage gates green
bash apps/backend/scripts/check_audit_immutability.sh
bash apps/backend/scripts/check_broker_isolation.sh
bash apps/backend/scripts/check_mcp_readonly.sh
bash apps/backend/scripts/check_no_env_credentials.sh
bash apps/backend/scripts/check_no_llm_in_order_path.sh
bash apps/backend/scripts/check_strategy_isolation.sh
bash apps/backend/scripts/check_workbench_mcp_readonly.sh
bash apps/backend/scripts/check_agent_no_db_access.sh
uv run --directory apps/backend python scripts/check_risk_coverage.py
uv run --directory apps/backend python scripts/check_p2_coverage.py
uv run --directory apps/backend python scripts/check_p3_coverage.py --cov-report=xml
cd apps/backend && uv run pytest tests/test_adr_0002_invariant.py tests/test_mcp_readonly.py -q && cd ../..

# 2. Full suite green
cd apps/backend && uv run pytest -q && cd ../..
cd apps/agent && uv run pytest -q && cd ../..
cd apps/mcp-workbench && uv run pytest -q && cd ../..

# 3. Bring up the full stack
docker compose up -d
sleep 60

# 4. §2a gate: spawn + terminate still work
./scripts/login_helper.sh
STRAT_ID=$(...)
# (existing §2a smoke: spawn via /validate, verify variant row, terminate via /stop-validation)

# 5. §2b gate: comparison endpoint + MCP tool
curl -s -b /tmp/cookies.txt "http://127.0.0.1:8000/api/v1/strategies/${STRAT_ID}/variant-comparison" | jq '.status'
docker compose exec mcp-workbench uv run python -c "
import asyncio
from mcp_workbench.server import workbench_paper_variant_metrics
print(asyncio.run(workbench_paper_variant_metrics(strategy_id=${STRAT_ID})))
"

# 6. §2c gate: extended response + new endpoint + UI surfaces
curl -s -b /tmp/cookies.txt "http://127.0.0.1:8000/api/v1/strategies/${STRAT_ID}/variant-comparison" \
  | jq '.comparison.live_equity_curve, .comparison.variant_equity_curve, .comparison.spawn_proposal_id' | head
curl -s -b /tmp/cookies.txt "http://127.0.0.1:8000/api/v1/variants" | jq
# UI smoke: open browser, verify Dashboard widget + Strategy detail card

# 7. All 8 P6+P6b audit actions present
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT DISTINCT action FROM audit_log
WHERE action IN (
  'STRATEGY_PROPOSAL_TRANSITIONED', 'AGENT_LLM_CALL_FAILED',
  'AGENT_BUDGET_REJECTED', 'AGENT_CADENCE_FIRED',
  'PROPOSAL_REVIEW_RECORDED', 'STRATEGY_DRIFT_DETECTED',
  'PAPER_VARIANT_SPAWNED', 'PAPER_VARIANT_TERMINATED'
) ORDER BY action;"

# 8. LOAD-BEARING: paper smoke byte-identical
PAPER_ACC=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts \
  | jq -r '.items[] | select(.mode=="paper") | .id')
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{\"account_id\":${PAPER_ACC},\"symbol\":\"AAPL\",\"side\":\"buy\",\"type\":\"market\",\"qty\":\"1\",\"tif\":\"day\",\"source\":\"manual\"}" \
  | jq '{status, broker_order_id}'

docker compose down

# 9. Tag the rollup
git tag -a p6b-session2-variant-complete -m "P6b §2 complete — paper-variant runner end-to-end"
git push origin p6b-session2-variant-complete
```

---

# Results template stub — fill at execution time

```markdown
# P6b Session 2c-variant — Results (go / no-go record)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | [YYYY-MM-DD] |
| Phase | P6b §2c-variant — Variant UI Surfaces (companion to `TradingWorkbench_P6b_Session2c_variant_v0_1.md`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Shipped as | PR **#[NN]** — branch `feat/p6b-session2c-variant-ui`; tag **`p6b-session2c-variant-complete`** then **`p6b-session2-variant-complete`** |
| Built against | `main` at `p6b-session2b-variant-complete` (`[SHA]`) |
| Verdict | **GO / NO-GO.** [Summary; P6b §2 closes with this session.] |
| Method | Executed: backend pytest + new modules; mypy; ruff; frontend tsc + eslint + vitest; lightweight-charts installed; all CI invariants. |

## Gates — PASS (executed)

| § | Gate | Result |
|---|---|---|
| 2c-v.1a | Variant-comparison response extended with equity curves + spawn_proposal_id | [✅ / details] |
| 2c-v.1b | GET /variants endpoint; user-scoped; isolated | [✅ / details] |
| 2c-v.2 | Frontend variantsApi types + methods | [✅ / details] |
| 2c-v.3 | VariantCard: three states + chart + buttons | [✅ / details] |
| 2c-v.4 | Dashboard VariantsCard | [✅ / details] |
| 2c-v.5 | Lightweight Charts installed with pinned version | [✅ / details] |
| 2c-v.6 | ~10 backend + ~8 frontend tests pass | [✅ / details] |
| 2c-v.7 | Manual smoke; chart renders; paper smoke byte-identical | [✅ / details] |
| — | `_router_token` discipline preserved | [✅] |
| — | `audit_immutability` invariant green (no schema changes) | [✅] |
| — | All 13 CI invariants + 3 coverage gates green | [✅] |
| 2c-v.11 | P6b §2 cross-session verification; `p6b-session2-variant-complete` tagged | [✅ / details] |

## Deliberate deviations (as-built vs the v0.1 plan)

Pre-named candidates (from v0.1's Candid Acknowledgment):

- **[`spawn_proposal_id` discoverability]** — [direct column read worked / audit-log derivation needed.]
- **[Equity-curve in response — eager vs lazy]** — [eager acceptable / required lazy split endpoint.]
- **[Lightweight Charts version pin]** — [v4.x worked / required older version.]
- **[Chart resize handling]** — [ResizeObserver worked / required different approach.]
- **[Multiple eligible proposals]** — [most-recent default worked / required list UX.]
- **[Spawn race vs deactivate]** — [error refresh acceptable / required preemptive guard.]
- **[Empty state messaging]** — [render-empty-message held / required render-nothing.]
- **[VariantsCard above vs below MorningBriefCard]** — [above held / swapped.]

Other deviations:

- **[Deviation N].** [What changed and why.]

## Findings / punch list

- [ ] [Anything specific.]
- [ ] [Flaky test status.]

## Deferred gates — require a live stack

- [ ] **Variant accumulating real fills with chart rendering live data** — pending live stack.
- [ ] **Equity-curve chart visual confirmation across browser sizes.**
- [ ] **Post-merge CI run green** — pending PR.

## To close P6b §2 cleanly

1. Walk away ≥1 hour before opening PR.
2. Confirm post-merge CI green; tag `p6b-session2c-variant-complete`.
3. Run §2c-v.11 cross-session verification on non-Norton stack.
4. Tag `p6b-session2-variant-complete`. **P6b §2 closes here.**
5. **Next: P6b §3** — promotion gate + EVALUATING/EVIDENCE_READY/PROMOTING/PROMOTED lifecycle states + 4-criterion gate (ADR 0007). Planning conversation TBD.

---

*P6b Session 2c-variant results v0.1 — recorded [DATE].*
```

---

*End of P6b Session 2c-variant v0.1. Drafted against §2b-variant Results' 5 execution-time deviations + the 6-question UI architecture turn's settled answers (Q1 Dashboard widget, Q2 full surface table+chart+buttons, Q3 Lightweight Charts, Q4 Spawn button shown, Q5 Stop button shown, Q6 single PR). Ships the strategy-detail VariantCard with three-state rendering + equity-curve chart + manual Validate/Stop buttons, the Dashboard VariantsCard with empty-on-zero behavior, two small backend additive extensions (equity-curve series + spawn_proposal_id in the comparison response, new /variants user-scoped listing endpoint), and Lightweight Charts integration. No new audit action, no new migration, no new lifecycle states, no MCP changes. Together with §2a and §2b, closes P6b §2 via cross-session verification → `p6b-session2-variant-complete`. Next: P6b §3 (promotion gate, ADR 0007, ~5h) — planning conversation TBD; the equity-curve primitive shipped in §2b unblocks §3's 4-criterion gate.*
