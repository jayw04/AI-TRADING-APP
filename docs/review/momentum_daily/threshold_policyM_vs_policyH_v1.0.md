# momentum-daily — Inception-Threshold Analysis: Policy M (≥0.60) vs Policy H (=0.98) — v1.0
**Purpose:** adjudicate `initial_seed_investable_gross` (plan §4) — should a fresh flat book seed when the
graduated regime reaches **mid (≥0.60)** or only when **clearly-above (=0.98)**?
**Date:** 2026-07-21. **Status:** **INTERIM finding — Step 6 threshold decision DEFERRED** pending **Step 5B (actual-book test)**. Committed as analysis evidence; the production `initial_seed_investable_gross` remains **UNLOCKED**.

## Methodology
- **Data:** `factor_data_full.duckdb` (`apps/backend/data/`, read-only), the same store the Stage 2-4 validation used.
- **Window:** 2005-01-03 .. 2026-06-12 (5,395 trading days; 5,196 with a valid 200-day MA — first 199 warm-up days excluded, where the harness fails open to gross 1.0).
- **Regime series:** reconstructed by **reusing the Stage 4 harness verbatim** — `backtest_momentum_stage4.py::build_market_proxy` (broad **equal-weight market proxy**, disclosed SPY substitution — SPY absent from SEP) and `gross_series(proxy, "C")` (graduated: `rel = idx/ma − 1`; gross = 0.98 if `rel>0.02`, 0.15 if `rel<−0.02`, else 0.60; `C_GROSS/C_BAND/MA_DAYS` at `backtest_momentum_stage4.py:56-62`). No regime logic reimplemented.
- **Forward outcomes:** measured on the proxy index level (`idx`); return = `idx[i+h]/idx[i]−1`, maxDD = worst peak-to-trough over `[i, i+h]`.
- **Inception episodes:** an *entry* into a state = a session whose gross differs from the prior session's. 0.60 entries = 123; 0.98 entries = 80.

## Results
### State distribution (n=5,196 post-warmup)
| gross | days | share |
|---|---|---|
| 0.98 (clearly above) | 3,706 | 71.3% |
| 0.60 (mid, ±2% band) | 671 | 12.9% |
| 0.15 (clearly below) | 819 | 15.8% |

### 0.60 (mid) inception episodes (n=123; 79 descending from 0.98, 44 ascending from 0.15)
| measure | value |
|---|---|
| P(→ 0.15 within 5 sessions) | 22.8% |
| P(→ 0.15 within 10 sessions) | 32.5% |
| P(→ 0.98 within 5 sessions) | 48.0% |
| P(→ 0.98 within 10 sessions) | 57.7% |
| dwell at 0.60 | median 3 · mean 5.5 · p90 12 sessions |
| exit resolution | 64% up (→0.98) · 36% down (→0.15) |

### Forward proxy outcomes (mean ret / median ret / mean maxDD)
| horizon | seed @ 0.60 (n=123) | seed @ 0.98 (n=80) |
|---|---|---|
| 10d | +0.20% / +0.82% / −3.27% | +0.97% / +1.33% / −2.27% |
| 21d | +0.88% / +1.33% / −4.98% | +1.82% / +2.27% / −3.51% |

### Policy H waiting cost (from each 0.60 entry, n=123)
| measure | value |
|---|---|
| sessions waited until next 0.98 | median 7 · mean 36.6 · never-reached 0 |
| proxy return during the wait (0.60→0.98) | mean +0.07% · median +1.14% (positive = missed upside) |
| waits with negative interim return (H avoided a drawdown) | 21/123 = 17% |

## Two-sided cost summary
- **Policy M (seed at ≥0.60):** captures inception ~7 sessions earlier (median), but **~1 in 3 mid-state seeds whipsaw to 0.15 within 10 sessions** (seed a book then de-gross 60%→15% within days — churn + transaction cost), with **lower forward return and deeper drawdown** than 0.98 seeds.
- **Policy H (seed only at =0.98):** waits median ~7 sessions, missing ~1.1% median upside, but seeds into a confirmed uptrend with ~2× forward return and shallower drawdown; 17% of the time the wait avoids a drawdown. **Tail risk:** mean wait 36.6 sessions — in a chronically choppy regime, 0.98 could delay inception materially.

## Decision status: DEFERRED
**Threshold decision: DEFERRED.** Reason: the proxy/regime evidence favors 0.98, but the economically material long-tail cash risk under Policy H (mean wait 36.6 sessions) requires **actual momentum-book inception testing (Step 5B)** before the production threshold is locked. The production default remains **unlocked**; this document is committed as analysis evidence with an interim finding only.

## Interim finding (proxy-based — NOT a locked decision)
**Predeclared rule:** *retain 0.60 unless mid-state inception produces materially higher early reversal, turnover, or drawdown **without** compensating return; move to 0.98 only through an explicitly adjudicated validation result.*

**→ Interim signal favors Policy H (0.98), but is NOT decisive.** On proxy evidence the move-to-0.98 condition appears met: mid-state (0.60) inception shows higher early reversal (22.8%/32.5% whipsaw to 0.15), worse drawdown (−3.3%/−5.0% vs −2.3%/−3.5%), and no compensating return (lower: +0.9% vs +1.8% at 21d). The whipsaw rate is a return-independent regime fact (robust). **However**, this measures the *market proxy*, not the concentrated 5-name book, and the 36.6-session mean wait is an economic cost the proxy cannot price — so the decision is deferred to Step 5B (below), which runs the actual strategy under both policies.

## Step 5B — required actual-book test (next)
Run the real selection + portfolio construction (`select_n`/`weigh` + gross scaling + turnover cost, reused verbatim from the Stage 4 harness), changing ONLY inception eligibility — Policy M seeds at first `gross ≥ 0.60`; Policy H stays cash until first `gross == 0.98`, then both use identical warm-book logic. For each 0.60 inception episode record M/H entry dates + portfolios, wait sessions, book return/DD/MFE during the wait, whipsaw turnover+cost under M, candidate-set change before H enters, and non-deployment within 10/21/42/63 sessions. Key outputs: median & tail P&L difference through first common deployed state, 95th-pct drawdown difference, missed-upside distribution under H, whipsaw turnover/cost under M, probability/duration of prolonged cash under H, subperiod/regime-episode stability. **Adjudication rule — lock 0.98 only if:** (1) M has materially worse inception drawdown/loss; (2) M creates meaningful avoidable turnover/cost; (3) M's early entry gives no compensating median/tail upside; (4) H's prolonged-cash cases do not create comparable/larger missed gains; (5) results are stable across regime episodes and major subperiods. If H reduces drawdown but materially sacrifices upside or frequently parks in cash for very long periods, a governed intermediate policy (e.g. 0.60-persistence) *may* merit consideration — but only if both approved candidates prove unsatisfactory.

## Caveats (bearing on adjudication)
1. **Proxy, not book P&L.** Forward return/DD use the broad-EW market proxy (the regime gauge), not the momentum book's actual holdings/gross-scaled return. The whipsaw/transition statistics are exact; the return/DD comparison is a market-environment proxy. A stronger test would seed the *actual* book at 0.60 vs 0.98 inceptions and compare book P&L (candidate for the §8 drift-audit rerun).
2. **Long right tail on the wait** — median 7 but mean 36.6 sessions; Policy H can occasionally strand a fresh book in cash for a long stretch. This is the main argument for retaining 0.60.
3. **Discrete regime** — the choice is genuinely mid-or-above (≥0.60) vs above-only (=0.98); no continuum to tune.
4. **Sample:** 123 mid-entries over 21 years — adequate but outcome variance is non-trivial.

## Reproducibility
- Driver: reuses `backtest_momentum_stage4.py::build_market_proxy` + `gross_series(proxy,"C")` (read-only, offline).
- Regime series artifact: `regime_series_2005_2026.csv` (date, gross, proxy idx) in this folder.
