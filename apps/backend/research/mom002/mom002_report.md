# MOM-002 Broad Momentum — breadth sweep

Universe 150 · window 2019-01-01..2026-06-13 · IS/OOS split 2023-01-01 · store 1997-12-31..2026-06-16

Same construction as the live book: weekly rebalance, long-only, equal-weight, survivorship-free, last-price-to-cash delisting. Breadth N is the only variable.

| config | rebs | avg N | CAGR | Sharpe | MaxDD | Calmar | OOS Sharpe | avg turnover |
|---|---|---|---|---|---|---|---|---|
| Top-5 | 389 | 5.0 | 77.36% | 1.37 | -55.34% | 1.40 | 1.67 | 24.29% |
| Top-10 | 389 | 10.0 | 53.84% | 1.25 | -48.45% | 1.11 | 1.39 | 21.01% |
| Top-15 | 389 | 15.0 | 50.10% | 1.28 | -41.66% | 1.20 | 1.50 | 19.50% |
| Top-20 | 389 | 20.0 | 38.48% | 1.12 | -40.18% | 0.96 | 1.33 | 19.03% |

## Cross-config monthly-return correlation

```
        Top-5  Top-10  Top-15  Top-20
Top-5    1.00    0.96    0.93    0.90
Top-10   0.96    1.00    0.97    0.96
Top-15   0.93    0.97    1.00    0.99
Top-20   0.90    0.96    0.99    1.00
```

## Reading

**Breadth comparison — Top-5 vs Top-20 (full window):**
- Sharpe: Top-5 1.37 -> Top-20 1.12 (worsens with breadth)
- Max drawdown: Top-5 -55.34% -> Top-20 -40.18% (improves with breadth)
- Calmar: Top-5 1.40 -> Top-20 0.96 (worsens with breadth)
- CAGR: Top-5 77.36% -> Top-20 38.48% (worsens with breadth)
- OOS Sharpe: Top-5 1.67 -> Top-20 1.33 (worsens with breadth)

=> On this window, **Top-5 is the stronger risk-adjusted book** (higher Sharpe). Concentration was not penalised — the review's diversification concern is about *portfolio correlation*, not single-book Sharpe.

> Sector-cap arm (--max-sector-pct 0.3) was SKIPPED: the local store has no sector data. Re-run on the sector-populated store.