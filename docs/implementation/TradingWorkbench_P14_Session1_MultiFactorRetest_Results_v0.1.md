# Trading Workbench — P14 §1: SF1 Multi-Factor Re-Test — Results (v0.1)

| Field | Value |
|---|---|
| Document | **P14 §1 Results** — the decisive SF1 re-run of the P12 §3 multi-factor question. |
| Date | 2026-06-21 |
| Phase | **P14 — Factor Lab** (first study; follows the SF1 acquisition, ADR 0023) |
| Experiment | `EXP-20260621-155951-sf1mf` · git `f13cad5` · seed 17 · reproducible |
| Data | **SF1 survivorship-free, point-in-time, 2016+** (ADR 0023; ~9,300 names, 1.03M rows) |
| Window | 2017-01-01 → 2026-03-31 · n=200 liquidity universe · 5 walk-forward sub-windows · 2000-resample paired bootstrap |
| Governing ADRs | 0014 (backtests = ground-truth), 0023 (SF1 = primary fundamental source) |
| Artifacts | `docs/implementation/evidence/p14_s1_multifactor/multifactor_retest.{json,md}`; harness `scripts/multifactor_retest.py` |

---

## Executive verdict

> **Inconclusive → keep v1.1 (momentum + vol-scaling). The SF1 multi-factor book is a real
> *drawdown* improver, not a statistically decisive *alpha* improver — so it is NOT a v2.0
> momentum-replacement.** The diversification signal P12 §3 saw is genuine, but on
> survivorship-free, multi-regime data its Sharpe advantage is not significant.

This is the honest answer SF1 was bought to produce. P12 §3 on thin FMP data *looked* strong
(multi-factor Sharpe 1.23 vs 1.00) but couldn't be trusted; on proper data the edge shrinks to
non-significant. **The platform validated *and* declined a strategy on evidence — exactly the
"honest no" the Evidence Engineering thesis sells.**

## 1. The diversification is real (factor correlations)

Averaged over **111 monthly cross-sections** (SF1 data):

| | momentum | value | quality |
|---|---|---|---|
| **momentum** | 1.00 | **−0.091** | **−0.005** |
| **value** | −0.091 | 1.00 | 0.027 |
| **quality** | −0.005 | 0.027 | 1.00 |

SF1 value and quality are **near-uncorrelated with momentum and with each other** — genuine
*independent* diversifiers, not momentum's opposite. This confirms (on better data) the P12 §3
signal: there *is* something to blend.

## 2. The decisive test (full-window + paired bootstrap)

| Book | CAGR | Sharpe | max DD | Calmar |
|---|---|---|---|---|
| **Momentum (v1.1 base)** | **+16.20%** | 0.64 | **−51.4%** | 0.31 |
| **Multi-factor (mom + SF1 value + quality)** | +13.43% | **0.68** | **−40.4%** | **0.33** |

- **ΔSharpe = +0.04, paired 95% CI [−0.345, +0.477] → spans zero.** The Sharpe improvement is **not
  statistically significant** (the decisive bar: CI must exclude 0).
- The multi-factor book **trades ~2.8pp of CAGR for ~11pp less drawdown** (−51.4% → −40.4%) at a
  marginally-better-but-noisy Sharpe. It behaves like a **second drawdown tool** (the role
  vol-scaling already fills in v1.1), not a return enhancer.

## 3. Walk-forward consistency (regime-dependent)

Multi-factor beat momentum in **3 of 5** sub-windows — and the split is regime-telling:

| Window | Momentum Sharpe | Multi-factor Sharpe | ΔSharpe |
|---|---|---|---|
| 2017-01 → 2018-11 | 0.90 | 0.72 | −0.19 |
| 2018-11 → 2020-09 | 0.70 | 0.44 | −0.26 |
| 2020-09 → 2022-07 | 0.16 | 0.60 | **+0.44** |
| 2022-07 → 2024-05 | 1.11 | 1.15 | +0.04 |
| 2024-05 → 2026-03 | 0.65 | 0.85 | +0.20 |

It **helps most when momentum struggles** (the 2020-09→2022-07 momentum-Sharpe-0.16 window: +0.44) and
**lags in strong-momentum runs** (2017-2020). That is the signature of a diversifier, not a dominator —
consistent with the non-significant full-window result.

## Decision

1. **Production book stays Momentum v1.1 (momentum + vol-scaling @ 15%).** No v2.0 multi-factor
   strategy is warranted: the Sharpe edge is not significant (ADR 0014 bar not cleared).
2. **The SF1 + Factor Lab investment paid off** — not with a new strategy, but with a *decisive answer*
   that the FMP data could not give, plus a reusable SF1-backed factor engine (composite + as-of joins)
   the platform keeps.
3. **Research debt / future option (low priority):** the multi-factor book's drawdown reduction is real
   and regime-complementary to momentum. A *drawdown-oriented* multi-factor overlay (not a replacement)
   is a defensible future study — but it competes with vol-scaling, which already provides DD control
   more simply.
4. **"More strategies" answer (the owner's `comments.md` question):** the sanctioned next books remain
   the **vol-target Risk Profiles** (Conservative/Balanced/Growth — same strategy, risk dial), *not* a
   multi-factor book. Strategy count stays a function of *evidence*.

## Caveats (honest boundaries)

- **~10-year SF1 depth (2016+, ADR 0023).** 2017-2026 spans several regimes but is shorter than the
  28-year price store. A deeper-history SF1 tier (ADR 0023 re-eval trigger) could revisit — more
  pre-2016 regimes is the cleanest way to tighten the still-wide ΔSharpe CI.
- **Equal-weight, no factor-timing, no in-sample tuning** (honest defaults). A tuned blend could look
  better in-sample; that is exactly the overfitting ADR 0014 guards against.
- Single liquidity universe (top-200); a broader/survivorship-free-appendix run is a follow-on.

## Reproduce

```
PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe apps/backend/scripts/multifactor_retest.py \
    --store data/factor_data_full.duckdb --start 2017-01-01 --end 2026-03-31 \
    --n 200 --windows 5 --bootstrap 2000 --seed 17 \
    --report-dir docs/implementation/evidence/p14_s1_multifactor
```
Seeded + deterministic → identical store + args reproduce the verdict.
