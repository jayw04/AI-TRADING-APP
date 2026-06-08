# Trading Workbench — P8 §6: Range Insight Panel UI

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-08 |
| Phase | P8 — Discovery screener + Range Insight (§6 of 7 — P8b) |
| Predecessor | `p8-session5-range-insight-complete` (§5) |
| Successor | `TradingWorkbench_P8_Session7_*` (range-trading template — §7, closes P8) |
| Direction | `TradingWorkbench_P8_Direction_v0.1.md` |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | A collapsible Range Insight panel in the Charts right rail, rendering the §5 statistics + the low-confidence note + the disclaimer verbatim. Frontend only. |
| Estimated wall time | 2–3 hours |
| Tag on completion | `p8-session6-range-insight-panel-complete` |
| Out of scope | See §"What this session does NOT do" |

## Why this session exists

§5 computes Range Insight and serves it at `GET /api/v1/range-insight/{symbol}`. §6 puts a face on it: a panel in the Charts right rail that shows, for the charted symbol, how it typically moves and where it has found support — alongside the chart the trader is already looking at. It renders the §5 disclaimer verbatim (Decision 2) and the low-confidence caveat, so the UI never overstates what the numbers mean.

## What this session ships

1. `src/api/rangeInsight.ts` — `rangeInsightApi.get(symbol)` + the TS types mirroring `RangeInsightResponse`.
2. `src/components/charts/RangeInsightPanel.tsx` — a self-contained, collapsible panel (`symbol` prop) that fetches on symbol change and renders the stats / low-confidence note / insufficient-data / 503 / disclaimer. Reusable (§7's template flow embeds it).
3. `src/pages/Charts/index.tsx` — the chart area becomes a flex row: the chart (`flex-1`) + the panel.
4. Tests: ok-stats + classification + disclaimer; low-confidence note; insufficient-data; 503; collapse/reopen.

## Prerequisites

- §5 complete — `GET /api/v1/range-insight/{symbol}`. Frontend `apiFetch`/`ApiError`; the Charts page (`symbol` state).

## Decisions settled for §6 (owner, 2026-06-08 — AskUserQuestion)

- **Panel layout: a collapsible right rail, open by default.** The chart keeps `flex-1`; the panel is a `w-80` column that collapses to a narrow vertical reopen strip (`w-8`) to reclaim chart width. Visible by default (matches the Direction's "open GOOG → see the panel"), collapsible when the trader wants the full chart. The panel **owns its own open/width state** (not the Charts page) so it stays self-contained, reusable, and testable without the TradingView widget.

## Detailed work

### §6.1 — `rangeInsight.ts`

`rangeInsightApi.get(symbol) → apiFetch<RangeInsight>(\`/api/v1/range-insight/${encodeURIComponent(symbol)}\`)`. Types: `MoveStats`, `Band`, `RangeInsight` (every `RangeInsightResponse` field; numeric fields nullable; `status: "ok" | "insufficient_data"`).

### §6.2 — `RangeInsightPanel.tsx`

Plain `useState/useEffect`; refetch on `symbol` change (a cancelled-flag effect). States:
- **collapsed** → a `w-8` vertical reopen button (`aria-label="Show Range Insight"`).
- **open** → a `w-80` card: header (title + symbol + a `▸` collapse button, `aria-label="Collapse Range Insight"`) and a body:
  - **loading** → "Loading…"; **error** → a 503 maps to "Market data is unavailable…", else a generic message.
  - **`insufficient_data`** → "Not enough history for {symbol} ({bars_used} days)…".
  - **`ok`** → a classification chip (range-bound / trending / mixed, colour-coded); an amber **low-confidence note** when `low_confidence`; rows for **ATR(20)** `$x (y%)`, **typical move** `+$up / −$down` (means), **support / resistance**, **today's high 80%** band, **today's low 80%** band, and **range so far today** (only when `intraday_range !== null`).
  - the **`disclaimer`** rendered verbatim at the foot (whenever data loaded).
- Number formatting: `fmt` → `toFixed(2)` (or "—" for null); `pct` → `(x*100).toFixed(1)%`.

### §6.3 — Charts mount

```tsx
<div className="flex flex-1 min-h-0 gap-3">
  <div className="flex-1 min-h-0 ...overflow-hidden"><TVChart symbol={symbol} interval={interval} /></div>
  <RangeInsightPanel symbol={symbol} />
</div>
```

The panel is keyed to the Charts `symbol`, so the quick-symbol buttons / symbol input drive it for free.

## Manual smoke

1. Nav → Charts. The Range Insight panel shows on the right for AAPL (needs `app.state.bar_cache`; Norton blocks live Alpaca, so a thin/uncached symbol shows "Not enough history", not an error).
2. Click a quick symbol → the panel refetches for it.
3. Collapse the panel (`▸`) → the chart goes full-width; the narrow reopen strip restores it.

## Walk-away discipline

Frontend-only, no backend / order-path touch → **≥1 hour**.

## What this session does NOT do

- **No backend change** — §5's endpoint is unchanged.
- **No range-trading template / "Apply template"** — §7 (closes P8); §7 reuses this panel.
- **No chart overlay of the bands** — the bands are listed in the panel, not drawn on the price chart (a future nicety).
- **No new dependency** — zero-dep (Norton blocks `pnpm add`); pure Tailwind + an inline `[writing-mode:vertical-rl]` for the collapsed label.
- **No order-path / risk / audit / migration / LLM.**

## Notes & gotchas

1. **The panel owns its width/collapse**, not Charts — so it renders + tests in isolation (no TradingView widget in jsdom) and §7 can drop it into the template-apply flow unchanged.
2. **Disclaimer is always rendered** when data loaded (ok *or* insufficient) — the §5 contract guarantees it; §6 never strips it.
3. **503 vs insufficient** — a missing bar cache surfaces as "Market data is unavailable" (the endpoint's 503); a thin symbol is a normal 200 `insufficient_data` rendered as a calm "not enough history" line, never an error.
4. **Refetch is cancel-safe** — the effect's `active` flag prevents a slow response for a previous symbol from clobbering the current one.
