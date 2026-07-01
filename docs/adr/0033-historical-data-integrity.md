# ADR 0033 — Historical Data Integrity (bar-cache completeness) — **Foundational**

| Field | Value |
|---|---|
| Date | 2026-06-30 |
| Status | **Draft** (awaiting owner review; recommended in `docs/design/Strategy Review.md` and the 2026-07-01 review during RNG-001) |
| Class | **Foundational** — a data-integrity guarantee every research result depends on (peer of ADR 0002 OrderRouter for the *research* path), not a one-off implementation fix |
| Phase | Cross-phase (market-data layer; research reproducibility) |
| Supersedes | — |
| Related | 0017 (OS trust store for Alpaca TLS), 0032 (paper-stack on EC2 — the always-on box fetches incrementally, which *masks* this bug), gotcha_barcache_10k_truncation_poison; discovered during RNG-001 (`docs/design/Range_BuySell_Formula_Study.md`) |

*Escalated from a Range-research finding to a **Foundational platform ADR** because the defect is in the shared market-data layer, not in any strategy, and because **without trustworthy historical data no other research matters** — a silent data gap contaminates every backtest built on it. It already biased a multi-week research program's results; any future long-window backtest is exposed until the decision below is implemented. This ADR is the guarantee of research-data trustworthiness; treat it with the weight of a foundational decision, not a bug ticket.*

## Context

`app/market_data/bar_cache.py` caches Alpaca bars in per-bucket parquet files: daily buckets for intraday ("fine") timeframes, monthly for daily. On a cache miss, `_fetch_and_write` computes the **min/max span of all missing buckets** and issues **one** `get_stock_bars` request for that whole span with `limit=10000`.

Two properties combine into a silent data-integrity failure:

1. **Truncation.** `limit=10000` caps the *total* rows the Alpaca SDK returns across pagination. A cold multi-year 5-minute fetch (~59k bars/symbol/3yr) is silently truncated to the first ~126 sessions. No error is raised — the caller receives a short, plausible DataFrame.
2. **Cache poisoning.** `_fetch_and_write` then splits the returned frame into per-day buckets and, for every *missing* day whose slice is empty, writes a `.empty` marker. Days beyond the truncation point get `.empty` markers even though real data exists. `.empty` markers **block re-fetch** (they read as "known-empty" — the mechanism that correctly skips holidays), so the gap becomes **permanent** until markers are manually cleared.

Observed impact (2026-06-30): the Range Top-5 + SPY 5-minute caches held ~250 **non-contiguous** sessions (H2-2023 + part of 2025) with **2024 and 2026 almost entirely marked bogus-empty**. The RNG-001 Phase-1 and Phase-3 backtests ran on this biased ⅓ sample and had to be recomputed after a manual month-by-month rebuild (`scripts/research/rebuild_5min_cache.py`). The live EC2 paper box (ADR 0032) is largely **immune** because it fetches incrementally in small same-day ranges that never approach 10k rows — which is exactly why the bug hid for so long: it only bites long *cold* research fetches.

The question: how does the platform guarantee that a backtest silently receives **complete** data for its requested window, or **fails loudly** if it cannot?

## Decision

1. **Never mark a bucket `.empty` outside the actually-returned data range.** In `_fetch_and_write`, after a fetch, compute `[df.t.min(), df.t.max()]`; only write `.empty` markers for missing buckets that fall *within* that returned range (a genuine holiday/no-trade day). Missing buckets *beyond* the returned range are left absent (re-fetchable), never poisoned.
2. **Chunk cold fetches so no single request can truncate.** When the missing span implies more than a safety threshold of rows (e.g. > ~8,000, below the 10k page), split the span into sub-requests (monthly for intraday) and fetch each. Equivalent to what `rebuild_5min_cache.py` does manually; move it into the cache so callers get it for free.
3. **Coverage assertion for research reads.** Provide a cache-completeness check (expected vs present trading sessions for a `(symbol, timeframe, window)`) that research/backtest entry points call, logging a `bar_coverage_gap` warning (or failing, per caller) rather than silently backtesting on a partial series.

The `.empty`-poisoning fix (1) is the load-bearing correctness change; (2) and (3) are defense-in-depth.

## Rationale

- **Fail loud, not silent.** The core sin was a *silent* wrong answer. Between "raise/log on a gap" and "return a plausible-but-partial frame," a research platform must choose the former — a loud failure costs an afternoon; a silent one cost a multi-week program's credibility until caught.
- **Fix the poisoning first.** Truncation alone would self-heal (a later fetch could fill the gap); it is the `.empty` poisoning that makes the damage *permanent*. Scoping markers to the returned range is a small, targeted change that removes the permanence.
- **Chunking over raising the limit.** Simply raising `limit` (or removing it) delegates pagination to the SDK for unbounded spans — larger blast radius, memory risk, and still no completeness guarantee. Deterministic monthly chunking is already proven by the manual rebuild and keeps each request small and cache-friendly.
- **Minimal disturbance to the live path.** The live box is unaffected by the bug and must not regress; all three changes are in the cache-fill path and are behavior-preserving for the small incremental fetches the box makes.

## Implementation notes

- File: `apps/backend/app/market_data/bar_cache.py`, `_fetch_and_write` (marker scoping) and the fetch-span logic (chunking). `_alpaca_fetch_bars` keeps `limit=10000` per *sub-request*.
- Marker scoping: guard the `.empty` write with `b_start >= df["t"].min() and b_end <= df["t"].max()` (only genuine in-range gaps).
- Coverage check: a helper `assert_coverage(symbol, timeframe, start, end)` comparing present buckets against an exchange trading calendar; used by research harnesses in `scripts/research/`.
- Migration: a one-time sweep to clear existing bogus `.empty` markers (the `rebuild_5min_cache.py` marker-clear step generalized). No schema change.
- Tests: a truncation-simulation unit test (fetch returns a capped frame → assert no out-of-range `.empty` written and the gap remains re-fetchable); a coverage-assertion test.

## Consequences

- **Positive.** Backtests receive complete data or a loud gap; the permanent-poisoning failure mode is eliminated; the manual rebuild tool becomes a fallback, not a routine necessity.
- **Negative.** Cold multi-year fetches issue more requests (one per month) and take longer wall-clock; slightly more code in the hot cache-fill path. Norton-SSL flakiness on the laptop makes long cold fetches retry-prone (mitigated by per-chunk retry, as the rebuild tool already does).
- **Neutral.** Cache-on-disk layout is unchanged; the live box's behavior is unchanged (its fetches never triggered the bug).

## Alternatives considered (not chosen)

- **Raise/remove `limit`.** Rejected: unbounded SDK pagination, memory risk, and still no completeness guarantee; doesn't fix poisoning.
- **Do nothing; rely on the manual rebuild tool.** Rejected: leaves a live footgun that silently biases any future long-window study and depends on a human remembering to run a tool.
- **Fetch the full window uncached each backtest.** Rejected: defeats the cache's purpose and multiplies Alpaca load; the cache is correct in design, only its miss-fill is buggy.

## Re-evaluation triggers

- The market-data provider changes its pagination/limit semantics (e.g. a different `limit` cap or token behavior).
- A second silent-data-gap incident surfaces despite (1)–(3) → the coverage assertion is not being called at all read sites; make it mandatory in the backtester itself.
- The platform adds a new intraday timeframe or a non-Alpaca data source → re-verify the chunking threshold and calendar.
