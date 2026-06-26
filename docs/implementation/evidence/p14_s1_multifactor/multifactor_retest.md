# P14 Factor Lab — SF1 multi-factor re-test (EXP-20260621-155951-sf1mf)

_git f13cad5 · SF1 survivorship-free PIT, 2016+ (ADR 0023) · window 2017-01-01..2026-03-31 · n=200 · 500.14s_

> The decisive re-run of the P12 §3 question on survivorship-free point-in-time SF1 fundamentals (2016+), which the thin FMP data could not settle.

## 1. Factor-correlation matrix (avg cross-section)

- corr(momentum, SF1-value) = **-0.091**
- corr(momentum, SF1-quality) = **-0.005**
- (averaged over 111 monthly cross-sections)

_Near-zero/low correlation = genuine diversifier; strongly negative = momentum's opposite._

## 2. Full-window backtest + paired Sharpe-difference bootstrap (decisive)

| Book | CAGR | Sharpe | maxDD | Calmar |
|---|---|---|---|---|
| Momentum (v1.1 base) | +16.20% | 0.64 | -51.4% | 0.31 |
| Multi-factor (mom+SF1 value+quality) | +13.43% | 0.68 | -40.4% | 0.33 |

**ΔSharpe = +0.04; paired 95% CI [-0.345, 0.477].** A CI excluding 0 is the real-edge signal.

## 3. Walk-forward consistency

Multi-factor beat momentum in **3/5** sub-windows.

| Window | Momentum Sharpe | Multi-factor Sharpe | ΔSharpe |
|---|---|---|---|
| 2017-01-01..2018-11-07 | 0.9 | 0.72 | -0.19 |
| 2018-11-07..2020-09-12 | 0.7 | 0.44 | -0.26 |
| 2020-09-12..2022-07-19 | 0.16 | 0.6 | +0.44 |
| 2022-07-19..2024-05-24 | 1.11 | 1.15 | +0.04 |
| 2024-05-24..2026-03-31 | 0.65 | 0.85 | +0.20 |

## Verdict: **Inconclusive** → keep v1.1; dSharpe CI spans 0

_Per ADR 0014/0023, either outcome is a win: a real edge → a v2.0 multi-factor candidate; momentum stands → keep v1.1, the SF1 spend bought an honest answer. ~10-year SF1 depth (2016+) is the standing caveat (ADR 0023)._
