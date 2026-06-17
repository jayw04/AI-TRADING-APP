# Factor research — 2016-01-04..2026-06-16 (200 names, IS/OOS split 2023-01-01)

## Dataset & universe version

- **git commit**: `871a60e`
- **SEP snapshot**: 1997-12-31..2026-06-16, 1254 distinct tickers
- **fundamentals rows**: 5762
- **universe**: top-200 by trailing dollar volume (PIT, survivorship-free; derived from SEP)
- **latest ingests**: fmp_fundamentals:JCI=2026-06-17 14:20:13.309631; fmp_fundamentals:AMT=2026-06-17 14:20:13.001461; fmp_fundamentals:TEAM=2026-06-17 14:20:12.700913; fmp_fundamentals:FTNT=2026-06-17 14:20:12.397316

| factor | win | mean IC | IC-IR | t | IC>0 | LS Sharpe | LS ann.ret |
|---|---|---|---|---|---|---|---|
| mom_12_1 | IS | 0.020 | 0.09 | 0.77 | 0.53 | 0.26 | 0.05 |
| mom_12_1 | OOS | 0.041 | 0.20 | 1.27 | 0.56 | 0.94 | 0.30 |
| mom_6_1 | IS | 0.015 | 0.08 | 0.69 | 0.59 | 0.25 | 0.04 |
| mom_6_1 | OOS | 0.004 | 0.02 | 0.14 | 0.51 | 0.42 | 0.12 |
| mom_12 | IS | 0.017 | 0.07 | 0.63 | 0.53 | 0.24 | 0.05 |
| mom_12 | OOS | 0.060 | 0.30 | 1.92 | 0.63 | 1.33 | 0.43 |
| lowvol_6m | IS | -0.014 | -0.05 | -0.47 | 0.46 | -0.39 | -0.11 |
| lowvol_6m | OOS | -0.089 | -0.29 | -1.84 | 0.39 | -1.98 | -0.93 |
| reversal_1m | IS | 0.013 | 0.07 | 0.68 | 0.49 | 0.07 | 0.01 |
| reversal_1m | OOS | -0.079 | -0.41 | -2.60 | 0.34 | -1.45 | -0.45 |
| earnings_yield | IS | -0.013 | -0.07 | -0.66 | 0.40 | -0.46 | -0.09 |
| earnings_yield | OOS | -0.041 | -0.19 | -1.21 | 0.44 | -1.78 | -0.69 |
| fcf_yield | IS | 0.009 | 0.05 | 0.49 | 0.51 | -0.09 | -0.02 |
| fcf_yield | OOS | -0.053 | -0.25 | -1.60 | 0.41 | -1.92 | -0.66 |
| sales_yield | IS | -0.014 | -0.07 | -0.61 | 0.42 | -0.02 | -0.00 |
| sales_yield | OOS | 0.001 | 0.00 | 0.03 | 0.46 | -0.82 | -0.24 |
| roe | IS | 0.008 | 0.05 | 0.48 | 0.49 | -0.26 | -0.05 |
| roe | OOS | -0.038 | -0.25 | -1.58 | 0.41 | -1.82 | -0.62 |
| gross_profitability | IS | 0.037 | 0.20 | 1.87 | 0.60 | 0.32 | 0.05 |
| gross_profitability | OOS | -0.017 | -0.11 | -0.69 | 0.41 | -1.47 | -0.34 |
| roic | IS | 0.016 | 0.10 | 0.91 | 0.55 | -0.27 | -0.05 |
| roic | OOS | -0.031 | -0.17 | -1.12 | 0.41 | -1.79 | -0.62 |
| debt_to_equity | IS | 0.015 | 0.12 | 1.13 | 0.58 | 0.35 | 0.04 |
| debt_to_equity | OOS | 0.001 | 0.01 | 0.07 | 0.49 | 0.87 | 0.17 |

## Factor stability — rolling 12-month IC

% of trailing-12m windows with positive mean IC, and the most recent value. A stable edge stays positive; a vanished one decays toward/through zero.

| factor | rolling-12m IC >0 | min | max | last |
|---|---|---|---|---|
| mom_12_1 | 70% | -0.085 | 0.102 | 0.102 |
| mom_6_1 | 56% | -0.079 | 0.105 | 0.066 |
| mom_12 | 71% | -0.077 | 0.123 | 0.123 |
| lowvol_6m | 29% | -0.200 | 0.191 | -0.117 |
| reversal_1m | 46% | -0.165 | 0.096 | -0.102 |
| earnings_yield | 28% | -0.136 | 0.110 | -0.010 |
| fcf_yield | 29% | -0.116 | 0.136 | -0.049 |
| sales_yield | 44% | -0.133 | 0.131 | 0.056 |
| roe | 52% | -0.112 | 0.097 | -0.046 |
| gross_profitability | 66% | -0.113 | 0.130 | -0.065 |
| roic | 61% | -0.120 | 0.125 | -0.025 |
| debt_to_equity | 68% | -0.058 | 0.076 | -0.007 |

## Long-short return correlation

```
                     mom_12_1  mom_6_1  mom_12  lowvol_6m  reversal_1m  earnings_yield  fcf_yield  sales_yield   roe  gross_profitability  roic  debt_to_equity
mom_12_1                 1.00     0.62    0.96      -0.10        -0.27           -0.30      -0.25        -0.52 -0.08                 0.08 -0.03            0.39
mom_6_1                  0.62     1.00    0.61      -0.03        -0.15           -0.11      -0.11        -0.24 -0.03                 0.04 -0.01            0.19
mom_12                   0.96     0.61    1.00      -0.14        -0.45           -0.37      -0.30        -0.55 -0.14                -0.00 -0.09            0.38
lowvol_6m               -0.10    -0.03   -0.14       1.00         0.04            0.83       0.87         0.47  0.88                 0.56  0.88           -0.53
reversal_1m             -0.27    -0.15   -0.45       0.04         1.00            0.21       0.13         0.16  0.17                 0.26  0.17           -0.04
earnings_yield          -0.30    -0.11   -0.37       0.83         0.21            1.00       0.94         0.70  0.90                 0.44  0.86           -0.55
fcf_yield               -0.25    -0.11   -0.30       0.87         0.13            0.94       1.00         0.66  0.89                 0.52  0.89           -0.51
sales_yield             -0.52    -0.24   -0.55       0.47         0.16            0.70       0.66         1.00  0.44                -0.05  0.42           -0.67
roe                     -0.08    -0.03   -0.14       0.88         0.17            0.90       0.89         0.44  1.00                 0.67  0.97           -0.40
gross_profitability      0.08     0.04   -0.00       0.56         0.26            0.44       0.52        -0.05  0.67                 1.00  0.72            0.11
roic                    -0.03    -0.01   -0.09       0.88         0.17            0.86       0.89         0.42  0.97                 0.72  1.00           -0.36
debt_to_equity           0.39     0.19    0.38      -0.53        -0.04           -0.55      -0.51        -0.67 -0.40                 0.11 -0.36            1.00
```