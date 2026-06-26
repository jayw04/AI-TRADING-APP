# Strategy Research Report — Range Trader rejection → Factor research

| Field | Value |
|---|---|
| Document version | **v1.1** (capstone research report) — for review |
| Date | 2026-06-17 (v1.1); 2026-06-16 (v1.0) |
| Phase | P10 — strategy research |
| Scope | The full research arc: RangeTrader (researched & rejected) → factor research (momentum confirmed) → momentum 12m upgrade shipped → FMP fundamentals unblocked → Value/Quality tested (no OOS edge here); recommendations. |
| Related | `..._RangeTrader_5c_TestResults_v0.1.md` (v0.3); `..._FMP_vs_SF1_Eval_v0.1.md`; `research/factor_report.md`, `factor_rankings.json`, `momentum_12m_backtest.md`, `factor_value_quality_findings.md`; PRs #128–#148 |
| Headline | **The validation framework keeps doing its job.** It rejected RangeTrader, identified **momentum** as the one OOS edge (now upgraded to 12-month and shipped), and — once fundamentals were unblocked — found that **Value and Quality have no OOS edge on our tradeable (mega-cap) universe**, so the multi-factor book is deferred rather than built on a non-edge. |

---

> ## ⚑ v1.1 update (2026-06-17) — what changed since v1.0
>
> v1.0 closed with two open questions: should we upgrade momentum to 12-month, and
> should we buy fundamentals data to test the multi-factor thesis? Both are now
> **resolved**, plus a third finding that reframes the roadmap:
>
> 1. **Momentum 6-1 → 12-month: SHIPPED** (PR #143, merged). Book-level backtest
>    confirmed the study — OOS Sharpe 1.85 vs 6-1's 1.40, lower drawdown *and*
>    lower turnover. The production book now defaults to the 12-month window. (v1.0
>    recommendation #1 — done.) Evidence: `research/momentum_12m_backtest.md`.
> 2. **The data blocker dissolved — no purchase needed.** v1.0 said Value/Quality
>    were blocked by the SF1 subscription. On investigation, the **existing FMP key**
>    already returns full quarterly+annual fundamentals back to 1986 with SEC filing
>    dates (PIT-ready) on FMP's `/stable` API. We built the FMP provider + PIT
>    fundamentals store + ingestion + Value/Quality factors (PRs #146–#148). v1.0
>    recommendation #2 (buy SF1) is **moot**.
> 3. **Value & Quality were tested — and have NO robust OOS edge on our universe.**
>    On the top-200 liquid names (2016–22 IS / 2023–26 OOS), every value/quality
>    factor is negative or flat OOS; only momentum survives. This is a *universe +
>    regime* result (mega-caps in a growth/momentum regime), not "value is dead" —
>    but it means **the multi-factor book is deferred**, not built. See §5.4 and
>    `research/factor_value_quality_findings.md`.
>
> Net: the momentum book (12-month) is the validated strategy; the next no-data work
> is **R3 risk overlays + a momentum-crash study**; multi-factor revisits only on a
> broadened (small/mid-cap) universe. Sections below are the v1.0 record; §5.4, §6,
> and §8 carry the v1.1 revisions.

## 1. Executive summary

Over this research cycle we (a) took the **Range Trader** intraday mean-reversion strategy through a full pre-registered backtest gate and **rejected it** (no robust out-of-sample edge), and (b) pivoted to **factor research** on our Sharadar equity universe to find a durable edge using the validation discipline we'd built.

**What we found:**
- **Momentum is the only factor with a real, out-of-sample edge** on our universe. **12-month momentum is the strongest** variant — and notably **better than the 6-1 momentum the production `momentum_portfolio` currently uses**, on Sharpe *and* drawdown, in-sample and out-of-sample.
- **Low-volatility and short-term reversal have negative edge** here (2016–2026, momentum-led regime).
- **Value and Quality were tested (v1.1) and have no robust OOS edge on our universe** — see §5.4. The SF1 "blocker" turned out to be moot: the existing FMP subscription already provides PIT fundamentals, so we built the layer and ran the study. Every value/quality factor is negative or flat out-of-sample on the top-200 liquid names; only momentum survives. This is a universe + regime result (mega-caps, growth/momentum regime), so the multi-factor book is **deferred**, not built.
- **Options were assessed and deferred** — no historical option data for our OOS discipline, and equity-only infrastructure; a 3–6 month platform project before any strategy.

**Top recommendations (v1.1 — detail in §6):**
1. ✅ **DONE — momentum book upgraded 6-1 → 12-month** (PR #143, merged). Study- and book-validated; lower turnover too.
2. **Add the P10 risk overlays** (vol-target, regime filter, sector/position caps, drawdown) + a **momentum-crash study** — the highest-value next work, and it needs no new data.
3. **Multi-factor book: deferred.** Value/Quality showed no OOS edge on the tradeable universe; revisit only after broadening the universe to small/mid-caps (now an ingest + a flag away). Do *not* blend value/quality into the momentum book on the current universe — it would dilute the one working signal.
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
| Sharadar **SF1 fundamentals** | ❌ subscription sample only | AAPL returns 2 rows; not used |
| **FMP fundamentals** (v1.1) | ✅ **full quarterly+annual, 1986→2026** | existing FMP key on the `/stable` API; SEC filing/accepted dates = PIT-ready; ingested for 197/200 names (5,762 statements) |

**v1.0's SF1 gap dissolved (v1.1).** The Value/Quality blocker was assumed to be the SF1 subscription. In fact the **already-owned FMP subscription** returns full fundamentals (income/balance/cash-flow/ratios/key-metrics) with filing dates on FMP's `/stable` API — deeper than the SF1 sample and enough for a PIT study. We built `FMPProvider` + a PIT `fundamentals` store + `ingest_fmp.py` + the Value/Quality factors (PRs #146–#148) and ran the study (§5.4). A factor is just `(close, as_of) → Series`, as designed. (Full source comparison: `..._FMP_vs_SF1_Eval_v0.1.md`.)

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
- **No fundamentals** → at v1.0 momentum was the only style we could test; §5.4 (v1.1) closes that gap.

### 5.4 Value & Quality study (v1.1) — no OOS edge on our universe

With FMP fundamentals ingested (PIT, 197/200 names), we ran the same IS/OOS study on Value (earnings/FCF/sales yield) and Quality (ROE, gross profitability, ROIC, −debt/equity). Full write-up: `research/factor_value_quality_findings.md`.

| Factor | OOS IC | OOS LS-Sharpe | Verdict |
|---|---|---|---|
| **mom_12** | +0.060 | **+1.33** | ✅ the edge |
| debt_to_equity (low-lev) | +0.001 | +0.87 | flat / noise |
| gross_profitability | −0.017 | −1.47 | ❌ IS t=1.87 → collapses OOS |
| roic | −0.031 | −1.79 | ❌ negative |
| roe | −0.038 | −1.82 | ❌ negative |
| earnings_yield | −0.041 | −1.78 | ❌ negative |
| fcf_yield | −0.053 | −1.92 | ❌ negative |

- **Value and Quality are negative or flat OOS.** Gross profitability had a real *in-sample* signal (t 1.87) that **collapsed out-of-sample** — the RangeTrader curve-fit signature; the gate caught it.
- **Cause = universe + regime.** Top-200-by-liquidity = mega-caps; 2023–26 was an extreme growth/momentum regime where cheap/defensive lost. Value/quality factors are highly inter-correlated (0.8–0.97), correlated with low-vol (also negative OOS), and **negatively correlated with momentum** here — they are momentum's opposite on this universe, not a diversifier.
- **So a momentum + value + quality composite would *dilute* momentum** on the current universe. A fair value/quality test needs breadth (small/mid-caps), where these factors historically pay — now just a re-ingest + the `--with-fundamentals` flag away.

---

*(v1.1 — revised; v1.0's #1 shipped, #2 became moot.)*

1. ✅ **DONE — momentum book upgraded 6-1 → 12-month** (PR #143, merged). The book-level backtest confirmed the study (OOS Sharpe 1.85 vs 6-1's 1.40, lower drawdown, lower turnover); the production default is now the 12-month window. Operational note: the deployed paper book picks it up on its next Monday rebalance.
2. **Add the P10 risk overlays + a momentum-crash study** — now the highest-value work, and it needs no new data. Overlays: vol-targeting (10–15% annual), market-regime filter (SPY > 200DMA), sector caps (20–25%), position caps (5–10%), drawdown control. The crash study (worst-20 drawdowns, rolling 3/6m, SPY/QQQ correlation, recovery) is a pre-live must, since the OOS window flatters momentum.
3. **Multi-factor book — deferred** (was v1.0 #2, "buy SF1"). Fundamentals are no longer the gate (FMP already provides them), but Value/Quality showed **no OOS edge on the tradeable universe** (§5.4). Revisit only after broadening the universe to small/mid-caps — the infrastructure (FMP provider, PIT store, factors, study path) all shipped, so a broadened re-test is an ingest + a flag. Do **not** blend value/quality into the momentum book on the current universe.
4. **Do not pursue options** now. No historical chains/greeks for OOS validation; equity-only OrderRouter/risk/backtester. Revisit only after the equity platform + data are mature (a 3–6 month platform project).

---

## 7. Reusable infrastructure delivered (all merged unless noted)

The strategies were researched; the **infrastructure succeeded** and is reusable for every future strategy:

- **§5c pre-registration gate** + bar-count drift metric (#135–#138) — GO/NO-GO/INCONCLUSIVE with IS/OOS + robustness + evidence JSON.
- **Intraday-oscillation screener** (#139).
- **VWAP±σ dynamic-level strategy variant** with same-day re-entry (#140).
- **Factor research engine** + first study (#142, merged); `--with-fundamentals` study path (#148).
- **Survivorship-free Sharadar price pipeline** + 2016 backfill.
- **FMP fundamentals layer (v1.1):** `FMPProvider` (#146), PIT `fundamentals` store + `ingest_fmp.py` (#147), Value/Quality factor definitions (#148) — reusable for a broadened-universe re-test.
- **Per-user paper-account isolation** (#130) + provisioning (#131) — usable for any second strategy.

---

## 8. Open decisions for the owner (v1.1)

1. **Risk overlays + momentum-crash study** — approve as the next build? (No new data; the path to paper→live for the momentum book.)
2. **Broadened-universe Value/Quality re-test** — worth ingesting small/mid-cap fundamentals to give value/quality a fair test, or shelve the multi-factor thesis for now? (Mega-cap result is in §5.4.)
3. **Merge the open R2 stack** — #144 (daily-loss breaker baseline, draft), #146 → #147 → #148 (FMP provider → store/ingestion → factors/study).
4. **Deploy note** — the daily-loss breaker fix (#144) and any further core-code changes need a backend restart to take effect (not hot-reloaded, unlike the strategy file).

*(Resolved since v1.0: momentum 6-1→12m upgrade — shipped (#143); Sharadar SF1 purchase — moot, FMP already provides fundamentals.)*

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

# v1.1 — FMP fundamentals ingest, then the combined Value/Quality study
WORKBENCH_FACTOR_DATA_DB_PATH=apps/backend/data/factor_data.duckdb \
  .venv/Scripts/python.exe scripts/ingest_fmp.py --tickers-file data/fmp_universe.txt --period annual
WORKBENCH_FACTOR_DATA_DB_PATH=apps/backend/data/factor_data.duckdb \
  .venv/Scripts/python.exe scripts/factor_research.py --n 200 --start 2016-01-01 \
    --split 2023-01-01 --with-fundamentals --report-dir research/
```

Needs Nasdaq Data Link (SEP) + FMP (`/stable`) reachable — truststore beats Norton (ADR 0017). FMP fundamentals come from the existing key; Sharadar SF1 is not used.
