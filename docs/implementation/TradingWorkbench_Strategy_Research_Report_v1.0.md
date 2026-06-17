# Strategy Research Report — Range Trader rejection → Factor research

| Field | Value |
|---|---|
| Document version | v1.0 (capstone research report) — for review |
| Date | 2026-06-16 |
| Phase | P10 — strategy research |
| Scope | The full research arc: RangeTrader (researched & rejected) → factor research (momentum confirmed; value/quality blocked on data); recommendations. |
| Related | `..._RangeTrader_5c_TestResults_v0.1.md` (v0.3, RangeTrader evidence); `research/factor_report.md` + `factor_rankings.json` (factor study); PRs #128–#142 |
| Headline | **No new strategy is activation-ready.** The validation framework worked: it rejected a weak idea (RangeTrader) and identified the one factor with a real OOS edge (**momentum**). Two concrete, low-risk wins are recommended; the multi-factor thesis is blocked by a data subscription. |

---

## 1. Executive summary

Over this research cycle we (a) took the **Range Trader** intraday mean-reversion strategy through a full pre-registered backtest gate and **rejected it** (no robust out-of-sample edge), and (b) pivoted to **factor research** on our Sharadar equity universe to find a durable edge using the validation discipline we'd built.

**What we found:**
- **Momentum is the only factor with a real, out-of-sample edge** on our universe. **12-month momentum is the strongest** variant — and notably **better than the 6-1 momentum the production `momentum_portfolio` currently uses**, on Sharpe *and* drawdown, in-sample and out-of-sample.
- **Low-volatility and short-term reversal have negative edge** here (2016–2026, momentum-led regime).
- **Value and Quality could not be tested** — our Nasdaq Data Link / Sharadar subscription returns only a tiny sample of SF1 fundamentals (2 annual rows per name, stale to 2023). The multi-factor thesis is **blocked by a data subscription, not by code.**
- **Options were assessed and deferred** — no historical option data for our OOS discipline, and equity-only infrastructure; a 3–6 month platform project before any strategy.

**Top recommendations (detail in §6):**
1. **Upgrade the momentum book: 6-1 → 12-month signal** (study- and portfolio-validated; small change, live-book improvement).
2. **Acquire a full Sharadar SF1 subscription** to unlock Value/Quality and the multi-factor book (the data is the gate, the code is ready to plug in).
3. **Add the P10 risk overlays** (vol-target, regime filter, sector/position caps, drawdown) to harden the production book toward live.
4. **Do not pursue options** until the equity platform + data are mature.

---

## 2. Part 1 — Range Trader: researched & rejected

Range Trader (single-symbol intraday fade-the-range) went through the full §5c pre-registered gate. Summary (full evidence in the §5c TestResults doc, v0.3):

- **Trade-count problem identified and fixed.** Fixed levels over a long window only enter when price visits a static level → ~13–23 trades (INCONCLUSIVE). An **intraday-oscillation screener** + a **VWAP±σ dynamic-level variant with same-day re-entry** raised this to **63–98 trades**.
- **Edge measured, OOS-tested, failed.** Every configuration that cleared the in-sample bar collapsed out-of-sample — best case PLTR partial-exit **IS PF 1.37 → OOS PF 0.92** (deep-entry IS 1.24 → OOS 0.85). That is the curve-fit signature the OOS criterion exists to catch.
- **Rejected and archived.** Not activated. The gate did its job — many workflows would have shipped on the 1.37 in-sample number.

This is the *correct* outcome of a disciplined process, and it directly motivated the factor-research pivot (the framework is now strong enough to test factors rigorously).

---

## 3. Part 2 — Factor research methodology

`scripts/factor_research.py` (PR #142) applies the same discipline to factor selection. At a monthly rebalance cadence, for each factor:

- **IC** — cross-sectional Spearman rank correlation between the factor and the next-month forward return (mean IC, IC-IR = mean/std, t-stat, % of months > 0).
- **Long-short** — top-quintile minus bottom-quintile forward return (annualized return, vol, Sharpe, hit-rate).
- **Decay** — mean IC at 1 / 3 / 6 / 12-month forward horizons.
- **Correlation** — between factors' long-short return series (diversification).
- **IS vs OOS split** at 2023-01-01 — the load-bearing check.

Pure metric functions are unit-tested; the engine reads the survivorship-free price store.

---

## 4. Data foundation (and the blocker)

| Dataset | Status | Notes |
|---|---|---|
| SEP daily prices | ✅ backfilled to **2016** for top-200 liquid names (~1.0M rows) | survivorship-free; the study's price base |
| TICKERS / ACTIONS | ✅ present | universe metadata, corporate actions |
| **SF1 fundamentals** | ❌ **subscription sample only** | AAPL returns **2 rows** (MRY, 2022 & 2023, stale to 2023-09-30); ARQ/quarterly = 0 rows |

**The SF1 gap is the key constraint.** A point-in-time Value/Quality study needs years of quarterly fundamentals across the universe; we have a 2-row annual sample per name. So **Value (EV/EBIT, FCF/earnings yield) and Quality (ROIC, ROE, gross profitability, D/E) cannot be researched** until a full SF1 subscription is in place. The engine is built to accept them as soon as the data exists (a factor is just `(close, as_of) → Series`).

> Real factor store: `apps/backend/data/factor_data.duckdb` (the repo-root `data/` copy is stale).

---

## 5. Findings

### 5.1 Factor study — IS/OOS (200 names, 2016–2026, split 2023-01-01)

| Factor | IS IC | OOS IC | OOS t-stat | OOS LS-Sharpe |
|---|---|---|---|---|
| **mom_12** | 0.017 | **0.060** | **1.92** | **1.33** |
| mom_12_1 | 0.020 | 0.041 | 1.27 | 0.94 |
| mom_6_1 | 0.015 | 0.004 | 0.14 | 0.42 |
| lowvol_6m | −0.014 | −0.089 | −1.84 | −1.98 |
| reversal_1m | 0.013 | −0.079 | −2.60 | −1.45 |

- **Momentum is the only OOS-positive factor**, and *stronger OOS than IS* (not curve-fit).
- **Low-vol and reversal are negative** on this universe/period (high-beta led).
- `mom_12` ≈ `mom_12_1` (LS-return corr 0.96 — effectively one factor); both ⟂ low-vol/reversal.

### 5.2 Momentum as a long-only book (production-relevant) — top-quintile, equal-weight

| Variant | IS Sharpe | IS maxDD | OOS Sharpe | OOS maxDD | OOS CAGR |
|---|---|---|---|---|---|
| mom_6_1 *(current production signal)* | 1.06 | −26% | 1.89 | −28% | 69.9% |
| mom_12_1 | 1.07 | −22% | 1.91 | −25% | 84.7% |
| **mom_12** | **1.13** | **−20%** | **2.16** | **−21%** | 99.4% |
| Equal-weight universe (benchmark) | 1.07 | −27% | 2.12 | −10% | 43.8% |

**`mom_12` dominates on Sharpe and drawdown, IS and OOS; the production book's 6-1 is the worst momentum variant.** This is the clearest actionable result of the study.

### 5.3 Caveats (read before acting)

- **Single OOS regime.** OOS = 2023–2026, an extreme momentum / mega-cap-tech bull. The eye-popping OOS CAGRs (70–99%) are **not** sustainable forward expectations and are regime-driven.
- **Universe selection bias.** The 200 names are *today's* top-by-dollar-volume (recent winners) → mild look-ahead in universe construction inflates absolute returns. The **relative** ranking (12m > 12-1 > 6-1) is the robust takeaway, not the absolute CAGRs.
- **Costs.** The long-only comparison is gross of trading costs/turnover; a 12-month signal turns over less than 6-1 (a *plus* for the switch).
- **No fundamentals** → momentum is the *only* style we could test; absence of a value/quality result is a data limitation, not evidence they don't work.

---

## 6. Recommendations (prioritized)

1. **Upgrade the momentum book's signal from 6-1 to 12-month** (`momentum_portfolio.py`). Study + long-only portfolio test both rank 12m > 12-1 > 6-1 on Sharpe and drawdown, IS and OOS; lower turnover too. Small, validated change to the production book — the highest ROI, lowest risk action. (Implement as a param + re-run the book's own backtest before flipping.)
2. **Acquire a full Sharadar SF1 subscription** (Nasdaq Data Link). This is the single gate to the multi-factor thesis: with real fundamentals we can test Value + Quality and, if they confirm, build a momentum + quality + value composite — the diversified book the roadmap targets. The ingestion + accessor + factor code is a small, ready build once the data flows.
3. **Add the P10 risk overlays** to the momentum book: vol-targeting (10–15% annual), market-regime filter (SPY > 200DMA), sector caps (20–25%), position caps (5–10%), drawdown control. This improves *production readiness* (paper → live) more than raw return.
4. **Do not pursue options** now. No historical chains/greeks for OOS validation; equity-only OrderRouter/risk/backtester. Revisit only after the equity platform + data are mature (a 3–6 month platform project).

---

## 7. Reusable infrastructure delivered (all merged unless noted)

The strategies were researched; the **infrastructure succeeded** and is reusable for every future strategy:

- **§5c pre-registration gate** + bar-count drift metric (#135–#138) — GO/NO-GO/INCONCLUSIVE with IS/OOS + robustness + evidence JSON.
- **Intraday-oscillation screener** (#139).
- **VWAP±σ dynamic-level strategy variant** with same-day re-entry (#140).
- **Factor research engine** + first study (#142, open).
- **Survivorship-free Sharadar price pipeline** + 2016 backfill.
- **Per-user paper-account isolation** (#130) + provisioning (#131) — usable for any second strategy.

---

## 8. Open decisions for the owner

1. **Momentum 6-1 → 12m upgrade** — approve building + backtesting it on the production book?
2. **Sharadar SF1 subscription** — worth the cost to unlock value/quality + the multi-factor book? (Without it, factor research is momentum-only.)
3. **Risk-overlay roadmap** — prioritize now (toward paper→live) or after the factor work?
4. **Merge the open PRs** — #141 (RangeTrader archive), #142 (factor engine).

---

## 9. Appendix — reproduction

```bash
cd apps/backend
# factor study (price factors; IS/OOS)
WORKBENCH_FACTOR_DATA_DB_PATH=apps/backend/data/factor_data.duckdb \
  .venv/Scripts/python.exe scripts/factor_research.py --n 200 --start 2016-01-01 \
    --split 2023-01-01 --report-dir research/
# deeper SEP backfill (idempotent; per-ticker; ~1M rows/day NDL cap)
.venv/Scripts/python.exe scripts/ingest_sharadar.py \
    --tickers-file data/factor_universe_top200.txt --datasets sep --from 2016-01-01
```

Needs Nasdaq Data Link (SEP) reachable — truststore beats Norton (ADR 0017). SF1 needs a fuller subscription than the current key provides.
