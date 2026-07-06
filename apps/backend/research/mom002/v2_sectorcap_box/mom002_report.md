# MOM-002 Broad Momentum — breadth sweep

Universe 150 · window 2019-01-01..2026-06-12 · IS/OOS split 2023-01-01 · store 1997-12-31..2026-06-12

Same construction as the live book: weekly rebalance, long-only, equal-weight, survivorship-free, last-price-to-cash delisting. Breadth N is the only variable.

| config | rebs | avg N | CAGR | Sharpe | MaxDD | Calmar | OOS Sharpe | avg turnover |
|---|---|---|---|---|---|---|---|---|
| Top-5 | 80 | 5.0 | 171.82% | 1.70 | -55.34% | 3.10 | 1.70 | 22.05% |
| Top-10 | 80 | 10.0 | 110.52% | 1.51 | -48.45% | 2.28 | 1.51 | 18.33% |
| Top-15 | 80 | 15.0 | 98.53% | 1.52 | -41.66% | 2.37 | 1.52 | 15.47% |
| Top-20 | 80 | 20.0 | 71.58% | 1.32 | -40.18% | 1.78 | 1.32 | 17.37% |
| Top-5 +sec30 | 80 | 5.0 | 179.47% | 1.73 | -55.36% | 3.24 | 1.73 | 22.05% |
| Top-10 +sec30 | 80 | 10.0 | 74.66% | 1.22 | -51.30% | 1.46 | 1.22 | 18.33% |
| Top-15 +sec30 | 80 | 15.0 | 69.63% | 1.24 | -42.45% | 1.64 | 1.24 | 15.47% |
| Top-20 +sec30 | 80 | 20.0 | 55.54% | 1.15 | -41.09% | 1.35 | 1.15 | 17.37% |

## Cross-config monthly-return correlation

```
              Top-5  Top-10  Top-15  Top-20  Top-5+sec30  Top-10+sec30  Top-15+sec30  Top-20+sec30
Top-5          1.00    0.98    0.96    0.94         1.00          0.97          0.95          0.93
Top-10         0.98    1.00    0.98    0.97         0.98          0.99          0.94          0.94
Top-15         0.96    0.98    1.00    0.99         0.96          0.98          0.98          0.98
Top-20         0.94    0.97    0.99    1.00         0.94          0.97          0.98          0.99
Top-5+sec30    1.00    0.98    0.96    0.94         1.00          0.97          0.95          0.93
Top-10+sec30   0.97    0.99    0.98    0.97         0.97          1.00          0.97          0.97
Top-15+sec30   0.95    0.94    0.98    0.98         0.95          0.97          1.00          0.98
Top-20+sec30   0.93    0.94    0.98    0.99         0.93          0.97          0.98          1.00
```

## Reading

**Breadth comparison — Top-5 vs Top-20 (full window):**
- Sharpe: Top-5 1.70 -> Top-20 1.32 (worsens with breadth)
- Max drawdown: Top-5 -55.34% -> Top-20 -40.18% (improves with breadth)
- Calmar: Top-5 3.10 -> Top-20 1.78 (worsens with breadth)
- CAGR: Top-5 171.82% -> Top-20 71.58% (worsens with breadth)
- OOS Sharpe: Top-5 1.70 -> Top-20 1.32 (worsens with breadth)

=> On this window, **Top-5 is the stronger risk-adjusted book** (higher Sharpe). Concentration was not penalised — the review's diversification concern is about *portfolio correlation*, not single-book Sharpe.