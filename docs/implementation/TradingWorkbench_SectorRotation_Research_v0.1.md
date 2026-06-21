# Trading Workbench — Sector Rotation: Research Plan & Pre-Registration (v0.1)

| Field | Value |
|---|---|
| Document | **Sector Rotation research program** — plan + **pre-registered** acceptance criteria, for owner review *before* any result is seen. |
| Date | 2026-06-21 |
| Status | **DRAFT for review.** No code/run yet — this freezes the hypothesis, construction, gate, and benchmarks first (the discipline that made the multi-factor + Range Trader verdicts trustworthy). |
| Strategy | **Sector Rotation** — a sector-level relative-strength / momentum signal; the next Tier-B *investment philosophy* (Strategy Roadmap §3.2). |
| Why it's different | Momentum chooses **WHAT** (which stocks); sector rotation chooses **WHERE** (which sectors). A genuinely different philosophy, not another momentum variant — broadens the platform beyond single-name stock selection. |
| Governing | **ADR 0014** (backtests = ground-truth) · the Strategy Roadmap evidence gate · ADR 0019 (Research Engine, read-only). |
| Data | The **survivorship-free SEP store** (`factor_data_full.duckdb`, 1997–2026) + the **Sharadar `tickers.sector` classification already in the store** (21,719 names, 11 sectors). No new data dependency. |

---

## 1. Hypothesis (frozen)

> **A sector-level relative-strength signal — rotate into the strongest-momentum sectors — earns a
> standalone out-of-sample edge AND/OR diversifies single-name momentum.**

Two distinct questions, both pre-registered so neither is moved after seeing results:
- **H1 (standalone):** sector rotation beats an equal-weight benchmark out-of-sample (Sharpe edge whose
  bootstrap CI excludes zero).
- **H2 (diversifier):** sector rotation is low-correlated with single-name momentum AND a
  momentum+sector blend improves on momentum-alone (the "WHAT × WHERE" complementarity).

A **negative** result is a success (recorded, declined) — the Evidence Engineering moat.

## 2. The signal (frozen definition)

For each weekly rebalance date `as_of`:
1. **Sector momentum** = for each of the 11 Sharadar sectors, the **equal-weight average of its
   constituent stocks' 12-1 momentum** (the production lookback: 12-month return skipping the last
   month), over the liquid universe at `as_of`. Point-in-time and survivorship-free (uses
   `universe_asof` + `tickers.sector` + SEP).
2. **Rank sectors** by sector momentum (highest = strongest).

## 3. Construction (frozen, reuses the factor-agnostic backtest)

The platform's `run_momentum_backtest(score_fn=...)` already holds the top-quantile of a per-ticker
score. Sector rotation maps cleanly:

- **`sector_momentum_score(store, as_of)`** → each ticker is scored by **its sector's momentum rank**
  (every stock in the strongest sector gets the top score). The backtest then holds the **top-quantile
  tickers = an equal-weight basket of the strongest sectors' stocks** — i.e. *rotate into the strong
  sectors, hold their names equally*.
- Same harness as Momentum/multi-factor: weekly rebalance, top-quintile, equal-weight, survivorship-free,
  turnover cost. Only the **score** changes (sector momentum vs single-name momentum) — clean A/B.

**Pre-registered parameters (frozen):** lookback **12-1** · **top-quintile (20%)** sectors' stocks ·
equal-weight · weekly rebalance · turnover cost **10 bps** · universe **top-200 liquid** (headline) +
a survivorship-free-breadth appendix · window **1998–2026**.

> Open question O1 (below): "top-quintile of stocks-in-strong-sectors" vs "hold the **top-3 sectors**
> as equal-weight baskets." The plan defaults to the former (reuses the harness exactly); the latter is
> a cleaner "pure rotation" but needs a small basket-backtest. **Owner to pick before the run.**

## 4. Pre-registered evidence gate (frozen BEFORE results)

| Criterion | Bar |
|---|---|
| **Standalone edge (H1)** | bootstrap 95% CI of **ΔSharpe vs equal-weight** excludes 0 (and positive) |
| **Significance** | paired circular-block bootstrap (2000 resamples, seed 17) — same method as the P14 multi-factor re-test |
| **Consistency** | positive ΔSharpe in **≥ ⌈(W/2)⌉+1** walk-forward windows (not one lucky regime) |
| **Diversification (H2)** | corr(sector-rotation, single-name-momentum) **< 0.5**; and momentum+sector blend ΔSharpe vs momentum-alone CI excludes 0 |
| **Cost-robust** | edge survives 5/10/20/50 bps turnover cost |
| **Honest defaults** | equal-weight, no in-sample tuning, no factor-timing |

**Verdict:** **VALIDATED** (→ governance → paper as Strategy #2 candidate) only if H1 *or* H2 clears its
bar decisively; **REJECTED** if both CIs span zero; **INCONCLUSIVE** if borderline (wide CI) — recorded
honestly either way.

## 5. Method (what the run will produce)

Mirrors the P14 multi-factor re-test (`scripts/multifactor_retest.py`) — a new
`scripts/sector_rotation_research.py`:
1. **Factor-correlation** — sector-rotation score vs single-name momentum (monthly cross-sections).
2. **Full-window backtest** — sector rotation vs momentum vs equal-weight (CAGR/Sharpe/maxDD/Calmar) +
   **paired Sharpe-difference bootstrap** (the decisive H1 test).
3. **Walk-forward** sub-windows (consistency).
4. **Blend test (H2)** — momentum + sector composite via the composite engine; ΔSharpe vs momentum-alone.
5. **Cost sweep** 5/10/20/50 bps.
6. **Evidence package** (`script → JSON → Markdown`, seeded/reproducible) + governance verdict.

## 6. Benchmarks

- **Equal-weight universe** (primary — H1).
- **Momentum v1.1** (the production book — H2 complementarity).
- **SPY** best-effort (the data gap noted in P12 §1 still applies).

## 7. Open questions for the owner (resolve before the run)

- **O1 — construction:** top-quintile of strong-sectors' stocks (reuses the harness) **vs** hold the
  **top-3 sectors** as equal-weight baskets (purer rotation, small new backtest). *Recommend the
  former for v1; add the latter as a variant if v1 is promising.*
- **O2 — sector momentum horizon:** 12-1 (matches production) vs a shorter rotation horizon (3-1 / 6-1).
  *Recommend 12-1 for v1 (consistency with the validated book); pre-register one, don't sweep.*
- **O3 — universe:** top-200 liquid (headline) — confirm, or broaden.

## 8. Out of scope (v1)

- Sector **ETF** rotation (XLF/XLE/…) — would need ETF price data; the in-store sector classification
  avoids that. A possible later variant.
- Risk-parity / vol-weighted sector sizing (a later increment if v1 validates).
- Macro/regime-conditioned rotation (a different, larger hypothesis).
- Live/paper activation — gated on a VALIDATED verdict + governance, then its own account (P5 §7).

## 9. Why this is the right next strategy

Per the owner's review: build **diverse philosophies**, and Sector Rotation is the favorite —
institutions use it, customers grasp it instantly, and it's genuinely orthogonal to single-name
momentum. Whatever the verdict, it strengthens the platform story: *the platform can discover, validate,
**reject**, and operate diverse strategy classes under one governance framework.*
