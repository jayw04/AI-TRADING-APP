# Trading Workbench — P8 §5: Range Insight Computation

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-08 |
| Phase | P8 — Discovery screener + Range Insight (§5 of 7 — **opens P8b**) |
| Predecessor | `p8-session4-scheduled-scanning-complete` (§4 — closes P8a) |
| Successor | `TradingWorkbench_P8_Session6_*` (Range Insight panel UI — §6) |
| Direction | `TradingWorkbench_P8_Direction_v0.1.md` (Decision 2; open Q3) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | A per-symbol statistical range panel computed from cached daily bars — ATR, typical open→high/low moves, support/resistance, an 80% confidence band for today's high/low, today's range so far, and a range-bound vs trending classification. Descriptive, not predictive. Backend only (the panel UI is §6). |
| Estimated wall time | 4–5 hours |
| Tag on completion | `p8-session5-range-insight-complete` |
| Out of scope | See §"What this session does NOT do" |

## Why this session exists

§5 opens P8b. A trader eyeing a range-trading setup needs a sober description of a symbol's recent behavior — *how far it typically moves, where it has found support, what a normal day's range looks like* — without the platform pretending to predict where it will go. Range Insight is exactly that: statistical summaries of the last ~20 days, computed deterministically from cached bars, carrying an explicit "these describe recent behavior, not forecasts" disclaimer (Direction Decision 2). §5 is the computation + a read endpoint; the Charts-rail panel (§6) and the range-trading template (§7) consume it.

## What this session ships

1. `app/services/range_insight.py` — `compute_range_insight(symbol, *, bar_cache, now)` + a pure core `range_insight_from_bars(symbol, bars, now)` returning a `RangeInsight` dataclass. Never raises; `status` reports insufficiency.
2. `app/api/v1/range_insight.py` + `schemas/range_insight.py` — `GET /api/v1/range-insight/{symbol}` (auth-gated; 503 if no bar cache).
3. Tests: the core over synthetic bars (full window, the 10–19 low-confidence band, <10 insufficient, the pre-market last-close anchor vs a today-bar open anchor, classification range-bound/trending) + the endpoint (shape + 503).

## Prerequisites

- §4 complete. `app.state.bar_cache` (`BarCache.get_bars(symbol, "1Day", start, end)` → `pd.DataFrame[t,o,h,l,c,v]`); `app/utils/time.EASTERN` / `today_eastern`.

## Decisions settled for §5 (owner, 2026-06-08 — AskUserQuestion)

- **Thin data (Direction Q3): floor + low-confidence caveat.** `< MIN_BARS (10)` completed daily bars → `status="insufficient_data"` (numeric fields null). `10–19` → compute with `low_confidence=true` + `bars_used`. `≥ 20` → compute, `low_confidence=false`. (`WINDOW = 20`.)
- **80% band: absolute price, anchored.** Anchor = today's open if a today bar exists, else the last completed close. Bands = `anchor + [p10, p90]` of the daily `(high−open)` distribution (high band) and `anchor − [p90, p10]` of `(open−low)` (low band). `intraday_range` = today's `high−low` if a today bar exists, else `null`.
- **Classification: efficiency ratio.** Kaufman ER over the window (`|close_last − close_first| / Σ|Δclose|`): `< 0.3` range-bound, `> 0.5` trending, else mixed. (Direction allows Hurst or ER; ER is robust on a 20-day series.)

## Detailed work

### §5.1 — `range_insight.py`

```python
WINDOW = 20          # ideal daily-bar window
MIN_BARS = 10        # below this → insufficient_data
DISCLAIMER = "Statistical descriptions of recent behavior, not forecasts."

@dataclass(frozen=True)
class MoveStats: mean: float; median: float; p80: float
@dataclass(frozen=True)
class Band: low: float; high: float

@dataclass(frozen=True)
class RangeInsight:
    symbol: str
    status: str                  # "ok" | "insufficient_data"
    bars_used: int
    low_confidence: bool
    as_of: datetime | None       # last bar timestamp
    anchor: float | None
    anchor_source: str | None    # "today_open" | "last_close"
    last_close: float | None
    atr20: float | None
    atr20_pct: float | None      # atr20 / last_close
    typical_move_up: MoveStats | None     # high − open
    typical_move_down: MoveStats | None   # open − low
    support: float | None        # window low
    resistance: float | None     # window high
    high_band: Band | None       # 80% band for today's high
    low_band: Band | None        # 80% band for today's low
    intraday_range: float | None # today high − low, else None
    classification: str | None   # "range_bound" | "trending" | "mixed"
    efficiency_ratio: float | None
    disclaimer: str

def range_insight_from_bars(symbol, bars, now) -> RangeInsight: ...
async def compute_range_insight(symbol, *, bar_cache, now) -> RangeInsight: ...
```

- **Today bar** = the last row whose `t` (ET date) == `now`'s ET date. `hist` = the completed bars (today excluded). Stats use `hist.tail(WINDOW)`; `bars_used = len(stats)`.
- **`< MIN_BARS`** → `insufficient_data` with all numeric fields `None` (but `bars_used`, `disclaimer`, `as_of` set).
- **ATR(20)**: true range `max(h−l, |h−prev_c|, |l−prev_c|)` averaged over the last 20 (`atr20_pct = atr20 / last_close`).
- **Moves**: per day `high−open` and `open−low` over the window → `MoveStats(mean, median, p80)` via pandas `.quantile`.
- **S/R**: `support = stats.low.min()`, `resistance = stats.high.max()`.
- **Bands**: `anchor = today.open if today_bar else hist.last.close`; high band `[anchor + p10(h−o), anchor + p90(h−o)]`; low band `[anchor − p90(o−l), anchor − p10(o−l)]`.
- **ER**: over the window's closes. Never raises (guards a zero denominator → `mixed`).
- `compute_range_insight` fetches `bar_cache.get_bars(symbol, "1Day", now − ~120d, now)` and delegates; empty → `insufficient_data`.

### §5.2 — Endpoint

`GET /api/v1/range-insight/{symbol}` (auth-gated). Reads `request.app.state.bar_cache` (absent → 503), `compute_range_insight`, returns `RangeInsightResponse` (Pydantic mirror; nested `MoveStats`/`Band` as sub-models). Registered after `scanner.router`.

### §5.3 — Tests

Core: full window (all fields, `low_confidence=false`); 12 bars (`low_confidence=true`, `bars_used=12`); 6 bars (`insufficient_data`); a today bar → `anchor_source="today_open"` + non-null `intraday_range`; no today bar → `anchor_source="last_close"`, `intraday_range=None`; a flat oscillating series → `range_bound`, a steady ramp → `trending`. Endpoint: 200 shape with a fake `app.state.bar_cache`; 503 without.

## Manual smoke

```
curl -s localhost:8000/api/v1/range-insight/AAPL -H "Authorization: Bearer $TOK" \
  | jq '{status, bars_used, low_confidence, atr20, support, resistance, classification, high_band, intraday_range}'
# Norton blocks live Alpaca → use a cached-fixture stack; the endpoint returns
# {status:'insufficient_data'} (not a 5xx) when the symbol has no cached bars.
```

## Walk-away discipline

Read-only computation + one endpoint, no order-path / risk / audit touch → **≥1 hour**.

## What this session does NOT do

- **No panel UI / Charts integration** — §6 (this session has no frontend).
- **No range-trading template** — §7.
- **No prediction / forecasting** — descriptive statistics only (Decision 2); the `disclaimer` ships in the payload.
- **No intraday-bar fetch** — Range Insight is daily-bar based; "today's range so far" comes from today's daily bar (`high−low`), which the cache updates through the session.
- **No persistence / new table / migration / audit action** — computed on read.
- **No new CI invariant; no order-path / risk; no LLM.**

## Notes & gotchas

1. **Exclude today's partial bar from the distributions** — today's `high−open` is incomplete intraday, so the move stats / ATR / S-R / ER use `hist` (completed days only); today's bar feeds only the anchor + `intraday_range`.
2. **Pre-market has no today bar** → anchor falls back to the last completed close; `intraday_range = null`. The §4 cron and an early-morning panel both hit this path.
3. **Never raise** — a degenerate series (zero variance, one bar) returns `insufficient_data` or `mixed`, never an exception; the endpoint stays 200 (except the 503 no-bar-cache infra case).
4. **The disclaimer is part of the contract** — always present, even on `insufficient_data`; §6 renders it verbatim.
