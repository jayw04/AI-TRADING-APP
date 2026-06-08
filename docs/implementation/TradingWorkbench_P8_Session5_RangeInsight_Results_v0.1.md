# P8 Session 5 — Range Insight Computation — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-08 |
| Phase | P8 — Discovery screener + Range Insight (§5 of 7 — **opens P8b**) |
| Plan doc | `TradingWorkbench_P8_Session5_RangeInsight_v0_1.md` |
| Predecessor | `p8-session4-scheduled-scanning-complete` (§4 — closed P8a) |
| Tag | **`p8-session5-range-insight-complete`** (moved onto the §5 todo commit) |
| Shipped as | PR **#78** — branch `feat/p8-session5-range-insight`; squash-merged `5478592` |
| Verdict | **GO.** A per-symbol descriptive range panel is computable + served. ruff + mypy(202) + all 10 invariants + 3 coverage gates green; no migration. |

## What shipped

- **`app/services/range_insight.py`** — `range_insight_from_bars(symbol, bars, now)` (pure core) + `compute_range_insight(symbol, *, bar_cache, now)` (fetches ~120 days of daily bars, delegates). Returns a `RangeInsight` dataclass:
  - **ATR(20)** (mean of the last 20 valid true ranges) + `atr20_pct = atr20/last_close`;
  - **typical moves** — per-day `high−open` (`typical_move_up`) and `open−low` (`typical_move_down`), each `MoveStats(mean, median, p80)`;
  - **support/resistance** = window low/high;
  - **80% band** — `Band(anchor + p10(h−o), anchor + p90(h−o))` for today's high; `Band(anchor − p90(o−l), anchor − p10(o−l))` for today's low; `anchor = today.open` if a today bar exists else the last completed close (`anchor_source`);
  - **`intraday_range`** = today's `high−low` if a today bar exists, else null;
  - **classification** via the Kaufman **efficiency ratio** (`<0.3` range_bound, `>0.5` trending, else mixed).
  - Today's partial bar is **excluded from the distributions/ATR/S-R/ER** (it feeds only the anchor + intraday range). Never raises — `status` ∈ {`ok`, `insufficient_data`}. `DISCLAIMER` ("Statistical descriptions of recent behavior, not forecasts.") is in every payload.
- **`GET /api/v1/range-insight/{symbol}`** (`app/api/v1/range_insight.py`, auth-gated, registered after `scanner.router`) — `app.state.bar_cache` absent → 503; otherwise 200 with `RangeInsightResponse` (the Pydantic mirror via `asdict`).

## Decisions settled (owner, 2026-06-08 — AskUserQuestion)

1. **Thin data (Direction Q3): floor + low-confidence caveat.** `WINDOW=20`, `MIN_BARS=10`: `<10` completed bars → `insufficient_data` (numeric fields null, but `bars_used`/`as_of`/`disclaimer` set); `10–19` → compute, `low_confidence=true`; `≥20` → compute, `low_confidence=false`.
2. **80% band: absolute price, anchored** (today's open → last-close fallback), so the pre-market cron and an early panel both produce numbers.
3. **Classification: efficiency ratio** (robust on a 20-day series; the Direction allows Hurst or ER).

## Verification

- **8 tests:** core — uniform full window (exact ATR 5.0 / pct 0.05 / support 98 / resistance 103 / moves 3 & 2 / bands / range_bound); 12-bar low-confidence; `<10` insufficient (disclaimer still present); today-bar → `anchor_source="today_open"` + `intraday_range=10` + the distributions exclude today; a ramp → `trending` + ER>0.5; empty → insufficient. Endpoint — 200 shape with a fake `app.state.bar_cache`; 503 without.
- ruff + mypy **(202)** clean; all **10 shell invariants** + **3 coverage gates** (risk 0.904/P2/P3) green. **No migration / no new audit action / no frontend.**
- CI on PR #78: **all jobs green first try** (Python backend 5m55s).
- One unrelated **full-suite flake** locally — `test_proposal_review_sampling.py::test_sampling_per_user_isolated` (IntegrityError) — passes in isolation **and** alongside the §5 tests (25/25); the known intermittent test-isolation flake family, not triggered by §5 (which touches nothing in proposals). It did **not** recur on CI.

## Notes / carry-forward

- **Today's partial bar is split out** — `hist` (completed days) drives every statistic; the today bar feeds only the anchor + `intraday_range`. This keeps an incomplete intraday `high−open` out of the distributions.
- **Pre-market path** — no today bar → anchor = last close, `intraday_range = null`. The §4 cron's 7:30 ET window hits this.
- **Endpoint contract is 200-or-503** — a thin/unknown symbol returns 200 `insufficient_data`, not an error; only a missing bar cache (infra) is a 503. §6 renders the disclaimer + the low-confidence note.
- Live confirmation (real `data.alpaca.markets` daily bars) is **Norton-deferred** to a non-Norton stack; the math is unit-covered with synthetic bars.

## Next

**P8 §6 — Range Insight panel UI** (Charts right rail). A frontend `src/api/rangeInsight.ts` + a panel component mounted in the Charts view: renders ATR, typical moves, support/resistance, the 80% high/low bands, today's range, the classification, the **low-confidence note** (for `10–19` bars / `insufficient_data`), and the **disclaimer verbatim**. Then §7 — the range-trading template + "Apply template" flow (prefilling params from a symbol's Range Insight), which **picks up P7's reserved `authoring_method="template"`**.
