# Trading Workbench — P8 Q4: Scan → Apply-Template Combined Flow

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-08 |
| Phase | P8 — Discovery screener + Range Insight (post-§7 addition; Direction open Q4) |
| Predecessor | `p8-session7-range-template-complete` (§7 — closed P8) |
| Successor | — |
| Direction | `TradingWorkbench_P8_Direction_v0.1.md` (open Q4) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Surface an "Apply range template" action directly on scan-result rows (the Discovery results table + the Opportunities discovery-matches widget), reusing the §7 endpoint. Frontend only. |
| Estimated wall time | 1–2 hours |
| Tag on completion | `p8-q4-scan-apply-template-complete` |
| Out of scope | See §"What this session does NOT do" |

## Why this session exists

The Direction flagged a "scan + apply template combined flow" (Q4) as an optional post-§7 addition: once a scan surfaces a range-bound candidate, the trader should be able to adopt the range-trading template for it **without leaving the scan** to go find it in Charts. §7 built the apply endpoint + the Charts-panel button; Q4 wires the same one-click apply onto the places scan candidates already appear.

## What this session ships

1. **Discovery results table** — an "apply template" button per matched row (next to `+ watchlist`); on success it **stays on the page** and the row shows a "✓ view" link to the new strategy, so the trader can work through several candidates.
2. **Opportunities "Discovery matches" widget** — an "apply" action per row that creates the strategy and **navigates** to it (a dashboard quick-action).

Both reuse the §7 `strategyTemplatesApi.applyRange(symbol)`; no backend change.

## Prerequisites

- §7 complete — `POST /api/v1/range-template/apply` + `strategyTemplatesApi.applyRange`. The §3 Discovery results table + the §4 Opportunities `DiscoveryMatchesWidget`.

## Decisions settled for Q4 (owner, 2026-06-08 — AskUserQuestion)

- **Post-apply UX (Discovery table): stay on the page + inline per-row feedback.** Apply → the row's button becomes a "✓ view" link to `/strategies/{id}` (the rest of the results stay), so the trader can apply to multiple scan candidates without re-running the scan. (Errors show a small "apply failed" line; the per-row state clears when a new scan runs.)
- **Placement: both surfaces.** The Discovery results table (primary scan-authoring surface, with the stay-and-feedback behavior) **and** the Opportunities discovery-matches widget (a dashboard quick-action that navigates to the new strategy).

## Detailed work

### Q4.1 — Discovery results table

`applyTemplate(symbol)` sets a per-symbol `applied[symbol]` state (`applying` → `done{id}` / `error`). The matched-row action cell renders `+ watchlist` plus, conditionally, either an "apply template" button (`applying…` while pending) or — once `done` — a `✓ view` `<Link to={/strategies/{id}}>`. `handleRun` clears `applied` so stale badges don't carry across runs.

### Q4.2 — Opportunities widget

`DiscoveryMatchesWidget` gains `useNavigate` + a per-row `applying` flag; each row's "apply" button calls `applyRange(symbol)` then `navigate('/strategies/{id}')`, sitting beside the existing "View → /discovery" link.

## Manual smoke

1. Discovery → run a scan → on a matched row click **apply template** → the row shows "✓ view"; the results stay; apply another row.
2. Click "✓ view" → lands on the new IDLE template strategy.
3. Dashboard → Opportunities → "Discovery matches" → **apply** on a row → lands on the new strategy.

## Walk-away discipline

Frontend-only, reuses an existing endpoint → **≥1 hour**.

## What this session does NOT do

- **No backend change** — reuses `POST /range-template/apply` from §7.
- **No bulk "apply to all matches"** — per-row apply only (a multi-select bulk action is a future nicety).
- **No new scan→strategy linkage** — the applied strategy is a normal template strategy (prefilled from the symbol's Range Insight, not from the scan criterion).
- **No order-path / risk / migration / audit / LLM.**

## Notes & gotchas

1. **Two surfaces, two post-apply behaviors by design** — the Discovery table *stays* (triage many candidates); the Opportunities widget *navigates* (a quick one-off from the dashboard). Settled with the owner.
2. **Per-row state clears on re-run** — `handleRun` resets `applied` so a fresh scan starts clean.
3. **The apply is independent of the scan criterion** — a symbol matched on `RSI14 < 35` still gets the template prefilled from its *Range Insight* (ATR / support / resistance), exactly like the §7 Charts-panel apply.
