# GAPPER-001 — Shadow Ledger (Forward Observation) · early read 2026-07-08

**Status: Backtest Pending — 20/40 valid accrual days. NOT a validated trading signal.**

The shadow ledger applies the **locked v0.2 primary design** to the cached intraday bars and logs, per
candidate per day, whether it triggered (30-min OR-high break by 11:00 ET, above VWAP, market & sector
positive), entry/exit, and gross same-day-close bps → the daily equal-weight book (≤5). It is **forward
observation only** — no bootstrap, no CI, no promotion. Raw records: `data/gapper_shadow_ledger/
shadow_<date>.json` on the box; the 16:40 ET daily job appends going forward.

## Backfill (20 days, from the cached bars)

| | |
|---|---|
| Candidates observed | 72 |
| **Triggered** (full primary rule) | **21 (29% trigger rate)** |
| Active / idle days | 11 / 9 |
| Daily book gross range | **−514 bps … +563 bps** |
| Mean daily book gross (idle-included) | **≈ 21 bps** |
| Implied breakeven | **≈ 11 bps/side** |

## Honest interpretation (descriptive — NOT a verdict)

- The early signal is **thin and very noisy**: the ~21 bps mean daily book gross implies a breakeven of
  only ~11 bps/side — **below** the v0.2 promotion threshold (breakeven ≥ 20 bps/side) — and the
  day-to-day swings (±500 bps) are dominated by **1–2 position days**, exactly the **concentration risk**
  v0.2 §5 criterion 4 guards against (no single date > 25% of P&L).
- This is **inconclusive, not a rejection**: 20 days / 21 triggers is far below the ≥40-date / ≥100-event
  sample gate, so no CI is computed and no verdict is drawn. It is a *watchlist observation*.
- **Cost caveat:** the entry bid/ask spread is not observable from OHLCV bars, so the half-spread entry
  model + 25 bps spread gate (v0.2 §7) are deferred to a quote-data source; this ledger uses the
  pre-registered **slippage grid** as the cost model.

## What this means for the sprint

GAPPER-001 remains **Active Accrual / Shadow Paper** — the pipeline is now complete (candidate report →
intraday auto-cache → shadow ledger, all forward-wired) and honestly labelled. The early observation is
**not encouraging**, but the discipline holds: the **CI-gated replay at ≥40 dates / ≥100 events** (≈ early
August) decides, under the metric locked blind — not this small-sample peek.
