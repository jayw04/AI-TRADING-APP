# Edge Evidence — 1.0 - Momentum (6-1, weekly top-quintile, equal-weight) (EXP-20260620-193645)

_Generated 2026-06-20T19:36:45.597555+00:00 · git a85724a · seed 17 · dataset 9e1108db7b41293a · 5953.12s on Jay-Work_

## Objective
Does the live momentum book carry a real, OOS, survivorship-free edge vs equal-weight / cash / SPY, robust to cost?

## Dataset
- Store `C:\LLM-RAG-APP\ai-trading-app\apps\backend\data\factor_data_full.duckdb@9e1108db7b41293a`; window 1997-12-31..2026-06-12; universe live200 (n=200).
- Health: 38,991,296 SEP rows, 14,150 tickers, covers_window=True, ok=True.

## Methodology
Weekly long-only top-quintile 6-1 momentum, equal-weight; equal-weight-universe baseline (ADR 0014); block bootstrap (95% CI + recentered-null p-value); walk-forward across regimes; cost-sensitivity sweep.

## Results

| Metric | Book | Equal-weight |
|---|---|---|
| CAGR | +10.73% | +7.74% |
| Sharpe | 0.48 | 0.43 |
| Sortino | 0.46 | — |
| Max drawdown | -76.4% | -69.2% |
| Calmar | 0.14 | — |
| Ann. vol | 31.1% | 24.3% |

**Statistical confidence** — Sharpe 0.48 (95% CI 0.13..0.85, p=0.003); ann. return p=0.003. _equal-weight is the primary benchmark (full history); SPY best-effort_

### Cost sensitivity

| bps | CAGR | Sharpe | maxDD |
|---|---|---|---|
| 5 | +11.43% | 0.50 | -76.1% |
| 10 | +10.85% | 0.48 | -76.4% |
| 20 | +9.70% | 0.45 | -77.1% |
| 50 | +6.31% | 0.35 | -81.8% |

### Walk-forward (stability: **moderately stable**)

| Window | Rebalances | CAGR | Sharpe | maxDD |
|---|---|---|---|---|
| GFC + 2009 reversal | 157 | -14.80% | -0.25 | -65.6% |
| 2010-2013 (2011 shock) | 157 | +17.10% | 0.89 | -21.1% |
| 2013-2016 (incl 2015) | 157 | +6.01% | 0.41 | -23.4% |
| 2016-2019 (calm) | 157 | +14.11% | 0.88 | -24.1% |
| 2019-2022 (COVID) | 157 | +13.16% | 0.51 | -48.6% |
| 2022-2024 (rate shock) | 105 | +22.14% | 1.04 | -22.4% |
| 2024-2026 (AI momentum) | 102 | +39.15% | 1.01 | -38.5% |

### Outliers
- Worst month: {'period': '2000-11', 'ret': -0.30918825784016934}
- Worst year: {'period': '2008', 'ret': -0.5108961667919023}
- Largest drawdown: -76.4%

## Limitations
- Live top-200 universe is survivorship-biased (today's names) — read book-vs-equal-weight (same-universe) as the cleaner alpha signal; broad survivorship-free run is the appendix.
- equal-weight is the primary benchmark (full history); SPY best-effort
- Open research debt: Full-history SPY series (SPY not in SEP store); Capacity / market-impact study; Dividend-adjustment validation; Liquidity model.

## Decision
Baseline established — **no enable/disable this session** (§1 measures; §2 decides). Confidence: _(set on read)_.

## Recommendation
Carry this baseline into §2 (vol-scaling / sector-caps lift) using the same harness.
