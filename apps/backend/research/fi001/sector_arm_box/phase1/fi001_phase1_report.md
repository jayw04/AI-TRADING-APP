# FI-001 Phase 1 — Measurement

Universe 150 - 2019-01-01..2026-06-12 - store 1997-12-31..2026-06-12. Books built with identical construction (weekly, long-only, equal-weight, survivorship-free); only the score function varies.

## Books
| book | rebalances | CAGR | Sharpe | MaxDD |
|---|---|---|---|---|
| momentum | 80 | 51.9% | 1.18 | -38.3% |
| low_vol | 106 | 8.7% | 0.796 | -11.4% |
| trend | 106 | 40.0% | 1.522 | -23.2% |
| sector | 106 | 28.9% | 1.048 | -28.9% |

**Diversification score:** 48 / 100 (100 = well diversified; higher = better; uses avg *positive* pairwise correlation).

**Stress window** = momentum's worst drawdown (2025-01-23..2025-04-08).

## Pairwise interaction

| pair | full corr | stress corr (mom DD) | rolling-63 mean | rolling-63 min..max | holdings overlap |
|---|---|---|---|---|---|
| momentum <-> low_vol | 0.222 | 0.265 | 0.151 | -0.162..0.77 | 0.026 |
| momentum <-> trend | 0.895 | 0.866 | 0.87 | 0.662..0.949 | 0.161 |
| momentum <-> sector | 0.685 | 0.442 | 0.666 | -0.09..0.951 | 0.119 |
| low_vol <-> trend | 0.391 | 0.599 | 0.369 | -0.056..0.855 | 0.082 |
| low_vol <-> sector | 0.222 | 0.637 | 0.227 | -0.12..0.722 | 0.02 |
| trend <-> sector | 0.734 | 0.684 | 0.664 | -0.06..0.973 | 0.152 |

## Reading (against the frozen H1/H3 priors)

- H1 priors: MOM<->LOW ~ -0.15 (real diversifier), MOM<->SEC ~ +0.38, MOM<->TREND ~ +0.87 (redundant). Compare `full corr` above.
- H3: `stress corr` vs `full corr` shows whether diversification SURVIVES momentum's worst drawdown (a pair whose stress corr jumps toward +1 diversifies least when it matters most).