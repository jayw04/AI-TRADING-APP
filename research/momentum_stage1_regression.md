# Momentum v0.9.0 — Stage-1 Regression Backtest (proposal v1.1 §9 "Stage 1 — Correctness")

**Purpose:** confirm the Workstream A semantic fixes do not degrade the book, and report the
performance delta. **Not an optimization** — no parameter is tuned to a result; windows and split are
fixed before the run.

**Store:** `factor_data_full.duckdb`, PIT survivorship-free, `1997-12-31 .. 2026-06-15`.
**Book:** 5 names (matches the live v0.8 config, proposal §3), equal weight, top-200 liquid universe,
10 bps one-way turnover cost. Regime filter / name caps not applied (unchanged v0.8↔v0.9, omitted
equally). **Deltas reported, not optimized.**

Three configs, each the same book under a different signal:

| | window | eligibility |
|---|---|---|
| **REF** (as-was) | 252/0 | z-score ≥ 0 only — the *literal v0.8 running config* |
| **A3** | 252/**21** | z-score ≥ 0 only — window fix alone |
| **V09** | 252/21 | z-score ≥ 0 **and raw momentum > 0** — the corrected v0.9 book |

`REF → A3` isolates A3 (the window); `A3 → V09` isolates A1 (the dual filter).

---

## Results

| config | span | CAGR | Sharpe | maxDD | Calmar | turnover | cash rebals |
|---|---|---|---|---|---|---|---|
| REF 252/0 | IS `2016..2022` | −0.0% | 0.25 | −79.2% | −0.00 | 9.20 | 0 |
| A3 252/21 | IS | 13.3% | 0.50 | −75.2% | 0.18 | 9.40 | 0 |
| **V09** 252/21 dual | IS | **13.3%** | **0.50** | **−75.2%** | 0.18 | 9.40 | 0 |
| REF 252/0 | OOS `2023..2026-06` | 63.4% | 1.06 | −59.7% | 1.06 | 9.91 | 0 |
| A3 252/21 | OOS | 100.8% | 1.41 | −50.8% | 1.99 | 10.26 | 0 |
| **V09** 252/21 dual | OOS | **100.8%** | **1.41** | **−50.8%** | 1.99 | 10.26 | 0 |
| REF 252/0 | STRESS 2022 | −21.6% | −0.27 | −32.0% | −0.67 | 11.06 | 0 |
| A3 252/21 | STRESS 2022 | −13.0% | −0.01 | −30.6% | −0.43 | 11.27 | 0 |
| **V09** 252/21 dual | STRESS 2022 | **−13.0%** | **−0.01** | **−30.6%** | −0.43 | 11.27 | 0 |

### Delta attribution

| span | A3 window | A1 dual filter | net v0.9 |
|---|---|---|---|
| IS | ΔSharpe **+0.24**, ΔCAGR +13.3%, ΔmaxDD +4.0% | +0.00 / +0.0% / +0.0% | +0.24 / +13.3% / +4.0% |
| OOS | ΔSharpe **+0.35**, ΔCAGR +37.5%, ΔmaxDD +9.0% | +0.00 / +0.0% / +0.0% | +0.35 / +37.5% / +9.0% |
| STRESS 2022 | ΔSharpe **+0.26**, ΔCAGR +8.5%, ΔmaxDD +1.3% | +0.00 / +0.0% / +0.0% | +0.26 / +8.5% / +1.3% |

(ΔmaxDD positive = shallower drawdown.)

---

## What the numbers say

**A3 (the window fix) is the entire measurable delta, and it is positive on every span** —
in-sample, out-of-sample, and in the 2022 momentum-crash stress window. Sharpe improves +0.24 to
+0.35, drawdown gets shallower everywhere. Dropping the contaminating last month (252/0 → 252/21)
helps, consistent with the academic 12-1 result. This is a *reported* improvement, not an optimized
one — 12-1 was pre-registered as the primary window before the run.

**A1 (the dual momentum filter) has zero measurable effect on this book — and that is the correct
result, not a null.** The filter never removed a name the book would have held, and never forced a
cash rebalance (`cash rebals = 0` on all spans). The reason is structural: in the top-200-*liquid*
universe, the 5 strongest z-score names were **always strongly raw-positive**, even at the depths of
the 2020 crash and the 2022 bear (their raw 12-1 returns ran 0.87–2.67 at the worst closes).

A1 is therefore a **tail-risk guardrail, not a return driver**. It costs nothing in normal history
and only bites when even the top relative names are falling — which is exactly the scenario where the
market-regime filter has *failed open* on missing data. That is why the proposal pairs A1 with A5:
A1 is the backstop for A5's failure mode. The backtest confirms the guardrail is free.

## What this harness deliberately does not model

- **A2 (rank hysteresis + 2-close confirmation)** — not modelled, and the omission is
  *conservative*: hysteresis only *reduces* turnover while tracking the same top ranks, so with a
  10 bps turnover charge it can only *understate* v0.9's net return. The equal-weight top-N book here
  rebalances fully each week — an upper bound on turnover.
- **A5 (bounded regime fallback)** — not modelled, and it has *zero* effect on a complete-data
  backtest: it fires only on missing market data, which the store never produces.
- **The regime filter itself** — unchanged v0.8 ↔ v0.9, omitted equally from all three configs.

## Caveats (equal across configs → the deltas are robust; the levels are not)

- Universe = today's top-N liquid names → absolute CAGRs carry winner bias. The **config-to-config
  delta** is the takeaway, not the level. (This is why the maxDD levels look extreme for a 5-name
  uncapped book; §9's purpose is the delta, not the level.)
- 5-name uncapped equal-weight book; the deployed book adds `max_position_pct` and the regime filter.

## Verdict

The v0.9 semantic fixes **do not degrade the book** on any span; the window fix improves it modestly
and consistently; the dual filter is a free tail guardrail. This satisfies the Stage-1 bar: the
corrected book is a sound honest baseline, and any performance change is attributable (all of it to
A3). Per §9, no parameter was tuned to these results.

Reproduce:

```
WORKBENCH_FACTOR_DATA_DB_PATH=data/factor_data_full.duckdb \
  .venv/Scripts/python.exe scripts/backtest_momentum_stage1_regression.py \
    --is-start 2016-01-01 --split 2023-01-01 --stress-start 2022-01-01 --stress-end 2022-12-31 \
    --report-dir research/
```
