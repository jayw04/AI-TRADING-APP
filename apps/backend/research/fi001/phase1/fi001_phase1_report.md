# FI-001 Phase 1 — Measurement

Universe 150 - 2019-01-01..2026-06-13 - store 1997-12-31..2026-06-16. Books built with identical construction (weekly, long-only, equal-weight, survivorship-free); only the score function varies.

## Books
| book | rebalances | CAGR | Sharpe | MaxDD |
|---|---|---|---|---|
| momentum | 389 | 31.6% | 1.044 | -38.3% |
| low_vol | 389 | 12.2% | 0.833 | -30.2% |
| trend | 389 | 24.9% | 1.131 | -29.8% |

**Diversification score:** 29 / 100 (100 = well diversified; higher = better; uses avg *positive* pairwise correlation).

**Stress window** = momentum's worst drawdown (2025-01-23..2025-04-08).

## Pairwise interaction

| pair | full corr | stress corr (mom DD) | rolling-63 mean | rolling-63 min..max | holdings overlap |
|---|---|---|---|---|---|
| momentum <-> low_vol | 0.52 | 0.213 | 0.48 | -0.162..0.947 | 0.064 |
| momentum <-> trend | 0.898 | 0.893 | 0.888 | 0.662..0.989 | 0.187 |
| low_vol <-> trend | 0.703 | 0.544 | 0.625 | -0.056..0.977 | 0.13 |

## Reading (against the frozen H1/H3 priors)

- H1 priors: MOM<->LOW ~ -0.15 (real diversifier), MOM<->SEC ~ +0.38, MOM<->TREND ~ +0.87 (redundant). Compare `full corr` above.
- H3: `stress corr` vs `full corr` shows whether diversification SURVIVES momentum's worst drawdown (a pair whose stress corr jumps toward +1 diversifies least when it matters most).

> Sector arm SKIPPED: store has 0 tickers with sector data (run on the sector-populated box store).