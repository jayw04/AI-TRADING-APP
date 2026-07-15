# Momentum-Daily — Stage 2 Pre-Registration: Rebalance Policy

| | |
|---|---|
| Program | Momentum Portfolio v1.1 — Workstream B (`momentum-daily`, strategy id=11, user 4) |
| Stage | **Stage 2 — Rebalance policy** (proposal v1.1 §5, §9) |
| Status | **FROZEN before any Stage-2 backtest is run** |
| Predecessor | Stage 1 (Workstream A correctness fixes) — DONE (`311b072`), delta = A1+A3, semantic-only |
| Data | `factor_data_full.duckdb` (Sharadar SEP, survivorship-free PIT; span 1997-12-31 → 2026-06-15, 14,150 tickers) |
| Harness | `apps/backend/scripts/backtest_momentum_stage2.py` (this branch) |

This document freezes every parameter, variant definition, metric, window, and prior expectation **before the
Stage-2 backtests run**. No threshold is re-fit after seeing results within the stage; sensitivity analysis is
reported, never silently adopted (§9). The purpose of Stage 2 is to isolate the **rebalance policy** — everything
else is held identical across the four variants.

---

## 1. Held identical across all four variants (the controls)

| Dimension | Frozen value | Source |
|---|---|---|
| Universe | Top-**200** PIT-liquid US names, survivorship-free (`universe_asof(store, d, n=200)`) | §10 |
| Signal | 12-1 momentum: lookback **252d**, skip **21d**; winsorized cross-sectional z-score ranking | §4.3, §10 |
| Eligibility | `raw_momentum > 0` **AND** `zscore >= 0` (the A1 dual filter) | §4.1 |
| Name count | **5** (equal weight) | §3 / §10 (Stage 3 tests 5/8/10) |
| Sizing | **Equal weight**, fully invested, long-only | §9 (Stage 3 tests inverse-vol hybrid) |
| Sector cap | **OFF** | §9 (Stage 3 dimension) |
| Regime filter | **OFF / always risk-on** | §9 (Stage 4 dimension); matches the Stage-1 harness, which omits the regime filter to isolate its own change |
| Turnover cost | **10 bps one-way** | Stage-1 harness |
| Initial equity | **$100,000** | Stage-1 harness |
| Backtest window | **2005-01-01 → 2026-06-13** (last store trading day), ≥273 trading-day warm-up before the first rebalance | new (captures the 2008 / 2020 / 2022 crash windows required by §9) |

**Why regime is OFF in Stage 2.** The proposal defers the regime filter to Stage 4 (§7), where the Stage-3 winner
is frozen and the four regime variants are compared. Isolating rebalance policy cleanly requires holding regime
fixed; OFF is the most conservative choice and matches the Stage-1 regression harness, which likewise omits the SPY
200-day filter to avoid confounding. Consequence: variant C's `regime_change` trigger (#4) is inert here — that is
correct, because **no** variant applies a regime overlay, so the comparison of the remaining policy machinery is fair.

---

## 2. The four variants (rebalance policy is the ONLY thing that differs)

| Variant | Policy | Trade rule | Prior expectation (§9) |
|---|---|---|---|
| **A — Weekly** | Corrected weekly baseline (live v0.9 cadence) | Rebalance to equal-weight top-5 eligible on the **last trading day of each ISO week** | Useful simple benchmark |
| **B — Trade-on-change** | Most reactive | Evaluate **daily**; rebalance to the new top-5 whenever the top-5 eligible **set changes** | Highest turnover; likely loses after costs |
| **C — Daily conditional (§5.1)** | The recommended structure | Evaluate **daily**; trade **only** when a §5.1 trigger fires (below) | **Most promising** |
| **D — Biweekly** | Slow scheduled | Rebalance to equal-weight top-5 eligible on the last trading day of **every second ISO week** | May work surprisingly well for a slow 12-1 signal |

A, B, D fully rebalance to the current top-5 eligible at their cadence/trigger (no hysteresis — hysteresis is part of
what makes **C** trade less, exactly as the Stage-1 harness modelled the weekly book as a plain top-5).

### Variant C — the six §5.1 triggers (frozen thresholds)

Trade only when at least one fires; log which one (mechanical attribution):

1. `exit_rank_breach` — a holding is rank **> 10** (`hold_rank`) for **2 consecutive** evaluations (`exit_confirm_closes`).
2. `candidate_displacement` — a non-held name is rank **≤ 5** (`entry_rank`) **and** beats the weakest holding by **≥ 0.30** z-score (`replace_score_advantage`).
3. `raw_momentum_negative` — a holding's **raw** momentum turns **≤ 0** → reduce/exit.
4. `regime_change` — inert in Stage 2 (regime OFF).
5. `weight_drift` — a position's weight drifts **> 4 pp** (`weight_drift_pct`) from target → weight-maintenance rebalance.
6. `scheduled_backstop` — no completed review in **10 trading days**.

When a trigger fires, the new target book is computed by the momentum_daily selection core (`_eligible` → hold-band
carry `pos ≤ hold_rank` with 2-close exit confirmation → fill to `entry_rank ≤ 5` → 0.30-advantage displacement),
then re-weighted equal. These thresholds are the registered `momentum_daily` defaults — **not tuned here**.

---

## 3. Metric set (§9) — computed identically for all four variants

Net **CAGR**, **Sharpe**, **Calmar** (CAGR / |max drawdown|), **max drawdown**, **annualized turnover**, **average
holding period** (calendar days per completed name-holding), **worst single-name gap loss** (largest one-day adverse
sleeve return of any held name), and **returns within the designated momentum-crash windows**:

- **2008 GFC** — 2008-06-01 → 2009-06-30
- **2020 COVID** — 2020-02-15 → 2020-06-30
- **2022 drawdown** — 2022-01-01 → 2022-12-31

All eight metrics are reported for every variant. **No variant is adopted on CAGR alone** (§9). No single-metric
maximization; the winner is chosen on the full set with special weight on Sharpe / Calmar / max-drawdown and
crash-window behavior.

## 4. Winner selection rule (frozen)

The variant carried into **Stage 3** is the one that is **best on the full metric set**, weighting risk-adjusted
return (Sharpe, Calmar) and drawdown control (max drawdown, crash-window performance) above raw CAGR, and penalizing
turnover only where it materially erodes net risk-adjusted return. Ties or near-ties resolve toward the **lower-turnover,
lower-drawdown** variant (conservative-default discipline). The winner and the rationale are recorded in the Stage-2
evidence report; the choice is made once, from the frozen metric set, and is not revisited by re-running with tweaked
thresholds.

## 5. Prior expectations (pre-registered hypotheses)

Restated from §9 so post-hoc surprise is auditable: **A** a useful benchmark; **B** highest turnover, likely loses
after costs; **C** most promising; **D** may work surprisingly well for a slow signal. A result that contradicts these
is reported as a finding, not smoothed over.

---

*Frozen: 2026-07-15. Any change after the first Stage-2 run requires a new version with an explicit change log and
re-run; results computed under this version are not silently re-attributed to a later one.*
