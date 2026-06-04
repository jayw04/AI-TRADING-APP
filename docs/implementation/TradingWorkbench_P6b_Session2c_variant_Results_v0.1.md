# P6b Session 2c-variant — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-04 |
| Phase | P6b — §2c-variant (variant UI surfaces; closes the code side of P6b §2) |
| Plan doc | `TradingWorkbench_P6b_Session2c_variant_v0_1.md` (with the 2026-06-04 review-corrections section) |
| Predecessor | `p6b-session2b-variant-complete` (`12da27e`) |
| Successor | P6b §3 (promotion gate, ADR 0007) — out of scope |
| Tags | `p6b-session2c-variant-complete` (`6c6388e`, §2c feat) → **`p6b-session2-variant-complete`** (`f500708`, the §2 rollup) |
| Shipped as | PR **#60** — branch `feat/p6b-session2c-variant-ui`; merged `6c6388e` |
| Verdict | **GO.** §2c merged + the §2c-v.11 cross-session rollup passed on the in-suite stand-in basis → **P6b §2 closed.** |
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

## P6b §2 rollup (§2c-v.11 cross-session verification) — 2026-06-04

Run after §2c merged + the post-merge CI on `f500708` went green. Confirms §2a + §2b + §2c hang together. Executed on the **in-suite stand-in basis** (offline battery + merge-CI green) — the same precedent as `p5-complete` / `p5.5-complete` / `p6-session2b-complete`, chosen by Jay via AskUserQuestion ("Tag now (stand-in)"). Tag **`p6b-session2-variant-complete`** pushed at `f500708`.

**Verified GREEN (code-level cohesion):**

| Gate | Result |
|---|---|
| 8 shell CI invariants | all pass (audit-immutability, broker-isolation, mcp-readonly, no-env-creds, no-LLM-in-order-path, strategy-isolation, workbench-mcp-readonly, agent-no-db) |
| 3 coverage gates | risk branch 0.904 ✓, P2 ✓, P3 ✓ (via `pytest --cov=app --cov-branch --cov-report=xml` then the gate scripts) |
| Full backend suite | **850 tests — 848 passed / 2 skipped / 0 failed** (incl. `tests/test_adr_0002_invariant.py` + every §2a/§2b/§2c variant test) |
| Agent suite | 22 passed |
| mcp-workbench suite | 26 passed (run via `../mcp-server/.venv/...python -m pytest` with `PYTHONPATH=src` — mcp-workbench has no own venv; Norton blocks a fresh `mcp` install) |
| Frontend vitest | 119/119 (confirmed in §2c + the post-merge CI Frontend job) |
| Post-merge CI on `f500708` | all jobs green |

**Deferred to a non-Norton + credentialed stack** (the live half of §2c-v.11 — recorded, **not run** here):

- [ ] `docker compose up` + a real Alpaca **paper order** (byte-identical smoke).
- [ ] The `BarCache → data.alpaca.markets` equity-curve chart rendering **real accumulated fills** (backend tests mock the fetch → dev curves are empty/flat).
- [ ] The 8 P6+P6b audit actions present in a live DB after a spawn→terminate cycle.
- [ ] Visual confirmation of the SVG chart across browser sizes + the UI smoke (Dashboard widget, detail card).

**Probe finding (this session, win32 + Norton):** Docker **is** installed (29.4.3) and `curl` reaches `paper-api`/`data.alpaca.markets` (HTTP 401 — the TLS handshake succeeds via the **Windows cert store**, which trusts Norton's MITM root). But the Python Alpaca SDK validates against **certifi**, which is the layer Norton's SSL inspection breaks — so the live market-data path still isn't exercisable here (the standing Norton-SSL-Alpaca blocker). curl-reachable ≠ SDK-reachable.

## Next

**P6b §3** (P6b §2 is now closed) — EVIDENCE_READY / PROMOTING / PROMOTED lifecycle + the ADR-0007 4-criterion promotion gate (≥30d-or-50-trades, ≥5% Sharpe margin, positive absolute return, no 7-day worst-case divergence beyond 20% of live max-dd) + evidence bundle + promote-with-P5§7-cooldown + STRATEGY_PROMOTED + 30-day post-promotion lockout. **The §2b equity-curve primitive is its metrics substrate.** Planning conversation TBD. Still pending on a non-Norton stack: `§1b.12 → p6-session1-complete` + the §2-variant live smoke above.
