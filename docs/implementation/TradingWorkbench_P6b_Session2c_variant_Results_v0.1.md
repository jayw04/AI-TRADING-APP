# P6b Session 2c-variant — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-04 |
| Phase | P6b — §2c-variant (variant UI surfaces; closes the code side of P6b §2) |
| Plan doc | `TradingWorkbench_P6b_Session2c_variant_v0_1.md` (with the 2026-06-04 review-corrections section) |
| Predecessor | `p6b-session2b-variant-complete` (`12da27e`) |
| Successor | P6b §3 (promotion gate, ADR 0007) — out of scope |
| Tag on completion | `p6b-session2c-variant-complete` |
| Outcome | Shipped: variant-comparison response extended (equity curves + spawn_proposal_id), new `GET /api/v1/variants`, frontend `variantsApi`, strategy-detail `VariantCard` (3 states + **zero-dep inline-SVG** chart), Dashboard `VariantsCard`. Full backend suite green; full vitest 119 green; ruff/mypy/tsc/eslint clean; no-LLM / mcp-readonly / agent-no-DB / audit-immutability invariants green. |

## What shipped

- **Backend (additive, no migration):** `VariantComparison` gains `live_equity_curve` / `variant_equity_curve` (threaded from the already-computed curves in `compare_variant_to_parent`). `GET /strategies/{id}/variant-comparison` now also returns `spawn_proposal_id` + the two curve arrays. New `app/api/v1/variants.py` → `GET /api/v1/variants` (user-scoped in-flight `PAPER_VARIANT` list with parent name/status + spawn proposal id), registered like `drift.py`.
- **Frontend:** `src/api/variants.ts` (types + `comparison`/`listInFlight`/`validate`/`stopValidation`). `components/strategies/VariantCard.tsx` — three states (empty / eligible-with-Validate / active-with-metrics-table-+-chart-+-Stop), plain `useState/useEffect` (DriftCard pattern), mounted in `Strategies/Detail.tsx` inside the active-status guard. `components/strategies/VariantsCard.tsx` — react-query Dashboard widget, renders `null` when empty, mounted above `MorningBriefCard`.
- **Tests:** 8 backend (extended response + `/variants`) + 7 frontend vitest (VariantCard 5, VariantsCard 2).

## Key deviations from the plan sketch (the review-corrections, as-built)

1. **No `lightweight-charts`.** The repo is pnpm + the registry is Norton-blocked + the lib isn't installed → it can't be added locally. Built the equity chart as a **two-series inline SVG** (`VariantEquityChart`) modeled on the existing `BacktestResultsView` chart. **Zero new frontend dependency.** This is the single biggest correction.
2. **`spawn_proposal_id` is derived, not a column.** No `Strategy.spawn_proposal_id` exists; it's the parent's EVALUATING proposal (spawn sets `state=EVALUATING` + `evaluation_results_json.paper_variant.variant_strategy_id`). Both the comparison endpoint and `/variants` derive it the same way; resolves to `null` if no EVALUATING proposal (the variant row stays the source of truth).
3. **Serializer names / dataclass.** Extended the shipped `_variant_comparison_dict` / `VariantComparison` (the doc named `_comparison_to_response` / `_metrics_to_dict`, which don't exist).
4. **Imports + placement.** `/variants` uses the `drift.py` import pattern (`app.auth.stub` + `app.db.session`), no router prefix. Frontend `Strategy`/`ACTIVE_STRATEGY_STATUSES` from `@/api/types`; `VariantCard`/`VariantsCard` under `@/components/strategies/`.
5. **Tailwind, not semantic CSS classes.** Rewrote all JSX with Tailwind utilities matching DriftCard / the Dashboard cards (the sketch's `className="variant-card"` etc. don't exist).

## Verification

- Backend: `pytest` full suite green (2 steady skips, 0 failures); ruff + mypy(162) clean.
- Frontend: `tsc --noEmit` clean; `eslint` clean; `vitest run` 119/119 (23 files).
- Invariants: no-LLM-in-order-path, workbench-MCP-readonly, agent-no-DB-access, audit-immutability all green. No MCP change (tool count stays 19); no migration; no new audit action; no order-path code.

## Deferred (live, non-Norton stack)

- The equity-curve chart rendering **real accumulated fills** (the `BarCache → data.alpaca.markets` path is Norton-blocked; backend tests mock it, so curves are empty/flat in dev).
- Visual confirmation of the SVG chart across browser sizes.
- Post-merge CI green; then the §2 cross-session rollup → `p6b-session2-variant-complete`.

## Next

P6b §3 — EVIDENCE_READY/PROMOTING/PROMOTED lifecycle + the ADR-0007 4-criterion promotion gate (the §2b equity-curve primitive is its metrics substrate). Planning conversation TBD.
