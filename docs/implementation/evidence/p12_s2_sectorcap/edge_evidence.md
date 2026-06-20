# Edge Evidence — 1.1 - Momentum + Sector caps (30%) (EXP-20260620-214254)

_Generated 2026-06-20T21:42:54.975908+00:00 · git 103537c · seed 17 · dataset 9e1108db7b41293a · 1282.06s on Jay-Work_

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
| CAGR | +9.92% | +7.74% |
| Sharpe | 0.46 | 0.43 |
| Sortino | 0.44 | — |
| Max drawdown | -72.7% | -69.2% |
| Calmar | 0.14 | — |
| Ann. vol | 30.6% | 24.3% |

**Statistical confidence** — Sharpe 0.46 (95% CI 0.11..0.83, p=0.004); ann. return p=0.004. _equal-weight is the primary benchmark (full history); SPY best-effort_

### P12 §2 — Sector-cap book (cap 30%)

- Capped book: CAGR +9.92% · Sharpe 0.46 · maxDD -72.7%. compare to the §1 baseline (same window/seed/n).

### Cost sensitivity

| bps | CAGR | Sharpe | maxDD |
|---|---|---|---|
| 10 | +10.03% | 0.46 | -72.7% |

### Walk-forward (stability: **moderately stable**)

| Window | Rebalances | CAGR | Sharpe | maxDD |
|---|---|---|---|---|
| GFC + 2009 reversal | 157 | -14.67% | -0.25 | -64.8% |
| 2010-2013 (2011 shock) | 157 | +17.32% | 0.90 | -20.7% |
| 2013-2016 (incl 2015) | 157 | +5.99% | 0.41 | -23.5% |
| 2016-2019 (calm) | 157 | +14.01% | 0.87 | -25.1% |
| 2019-2022 (COVID) | 157 | +12.25% | 0.50 | -49.2% |
| 2022-2024 (rate shock) | 105 | +20.98% | 1.00 | -23.5% |
| 2024-2026 (AI momentum) | 102 | +30.10% | 0.87 | -38.3% |

### Outliers
- Worst month: {'period': '2000-03', 'ret': -0.3642360842696859}
- Worst year: {'period': '2008', 'ret': -0.5128465706925958}
- Largest drawdown: -72.7%

## Limitations
- Live top-200 universe is survivorship-biased (today's names) — read book-vs-equal-weight (same-universe) as the cleaner alpha signal; broad survivorship-free run is the appendix.
- equal-weight is the primary benchmark (full history); SPY best-effort
- Open research debt: Full-history SPY series (SPY not in SEP store); Capacity / market-impact study; Dividend-adjustment validation; Liquidity model.

## Decision
Baseline established — **no enable/disable this session** (§1 measures; §2 decides). Confidence: _(set on read)_.

## Recommendation
Carry this baseline into §2 (vol-scaling / sector-caps lift) using the same harness.
