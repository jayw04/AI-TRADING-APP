# P8 Q4 — Scan → Apply-Template Combined Flow — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-08 |
| Phase | P8 — Discovery screener + Range Insight (post-§7; Direction Q4) |
| Plan doc | `TradingWorkbench_P8_Q4_ScanApplyTemplate_v0_1.md` |
| Predecessor | `p8-session7-range-template-complete` (§7 — closed P8) |
| Tag | **`p8-q4-scan-apply-template-complete`** |
| Shipped as | PR **#81** — branch `feat/p8-q4-scan-apply-template`; squash-merged `ce6eb23` |
| Verdict | **GO.** Apply-from-scan works on both scan surfaces. Frontend vitest + tsc + eslint green; backend untouched. Closes Direction Q4. |

## What shipped

- **Discovery results table** (`src/pages/Discovery/index.tsx`) — an **"apply template"** button per matched row beside `+ watchlist`. `applyTemplate(symbol)` tracks a per-symbol `applied` state (`applying` → `done{id}` / `error`); on success the button becomes a **"✓ view"** `<Link to={/strategies/{id}}>` and the trader **stays on the page** (results intact) to apply to more candidates. `handleRun` clears `applied` on a new scan; an error shows a small "apply failed" line.
- **Opportunities "Discovery matches" widget** (`DiscoveryMatchesWidget.tsx`) — an **"apply"** action per row (`useNavigate` + a per-row `applying` flag) that calls `applyRange(symbol)` then `navigate('/strategies/{id}')`, beside the existing "View" link.

Both reuse the §7 `strategyTemplatesApi.applyRange(symbol)`; **no backend change**.

## Decisions settled (owner, 2026-06-08 — AskUserQuestion)

1. **Post-apply UX (Discovery table): stay + inline per-row feedback** (triage multiple scan candidates without re-running).
2. **Placement: both surfaces** — the Discovery results table (stay-and-feedback) and the Opportunities discovery-matches widget (navigates, a dashboard quick-action).

## Verification

- **2 new frontend tests:** Discovery — apply on a scan match → `applyRange("AAPL")` + stays on the page + a `/strategies/7` "view" link; widget — apply → `applyRange("AAPL")` + `navigate('/strategies/5')`.
- Frontend **vitest 152** (+2, 30 files) + tsc + eslint clean. **No backend change** (the §7 endpoint is unchanged) → backend stays as-merged-green; no order-path / risk / migration / audit / LLM.
- CI on PR #81: all jobs green first try (Python backend 6m0s). Merged on "merge on green".

## Notes / carry-forward

- **Two surfaces, two post-apply behaviors by design** — the Discovery table *stays* (triage many); the Opportunities widget *navigates* (a one-off quick action). Settled with the owner.
- **Apply is independent of the scan criterion** — a symbol matched on `RSI14 < 35` still gets the template prefilled from its *Range Insight*, exactly like the §7 Charts-panel apply.
- Bulk "apply to all matches" is deliberately out of scope (a future nicety).

## P8 wrap

Q4 was the last flagged P8 item. **P8 is fully closed**: §1–7 (the Discovery → Range Insight arc) + Q4 (scan → apply). Remaining work is the standing **live cross-session verification** on a non-Norton + credentialed stack (the §4 scan cron at 7:30 ET, Range Insight + the range template vs real daily bars, and the prior P6 live items), plus P9+ when directed.
