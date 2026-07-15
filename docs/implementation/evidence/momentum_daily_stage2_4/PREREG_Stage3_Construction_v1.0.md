# Momentum-Daily — Stage 3 Pre-Registration: Portfolio Construction

| | |
|---|---|
| Stage | **Stage 3 — Portfolio construction** (proposal v1.1 §6, §9) |
| Status | **FROZEN before any Stage-3 backtest is run** |
| Inherits | Stage-2 winner **C — Daily conditional (§5.1)**, frozen (`4ec4923`); owner-confirmed |
| Harness | `apps/backend/scripts/backtest_momentum_stage3.py` (this branch) |
| Data | `factor_data_full.duckdb` (Sharadar SEP + `tickers.sector`) |

Stage 3 holds the **signal (12-1) and the rebalance policy (daily conditional §5.1)** fixed and sweeps
**portfolio construction**: name count × sizing × sector cap. No threshold is re-fit after seeing results.

## 1. Frozen from Stages 1-2 (the controls)

Universe top-200 PIT · 12-1 signal (252/21) · eligibility raw>0 ∧ z≥0 · **daily conditional §5.1 rebalance
policy** (the six triggers, hold-band + 2-close exit confirm + 0.30-z displacement) · regime OFF (Stage 4) ·
10 bps one-way · $100k · window 2005-01-03 → 2026-06-12.

## 2. Sweep grid (§6) — 3 × 2 × 2 = 12 configurations

| Dimension | Values | Source |
|---|---|---|
| **Name count** | 5, 8, 10 | §6.1 (15 optional, omitted) |
| **Sizing** | `equal_weight` · `hybrid_50_50` (capped 50/50 EW+inverse-vol) | §6.3 |
| **Sector cap** | OFF · ON | §6.2 |

The name-count parameter widens the selection bands proportionally to the book size while preserving the
§5.1 shape: `max_names = N`, `entry_rank = N`, `hold_rank = 2N` (so 5→entry5/hold10 reproduces Stage 2
exactly; 8→entry8/hold16; 10→entry10/hold20). This is the pre-registered generalization of the fixed
5/10 bands to a size-N book — fixed here before the run.

### 2.1 Sector cap (§6.2), when ON

- **Selection:** at most **2 holdings per sector**. Enforced during selection — when filling/【displacing】
  the book, a candidate whose sector already holds 2 names is skipped in favor of the next eligible name.
- **Weight:** aggregate sector weight capped — **40%** for N=5 (§6.2 explicit); **30%** for N=8 and N=10
  (derived: the 2-per-sector count cap × the §6.3 15% per-name bound ⇒ ≤30% — fixed here, pre-run).
  Applied via the existing `_apply_sector_cap` water-filling primitive.

### 2.2 Sizing (§6.3)

- `equal_weight` — `1/N` per name (Stage-2 sizing).
- `hybrid_50_50` — `w_i ∝ 0.5·(1/N) + 0.5·(invvol_i / Σ invvol)`, `invvol_i` from trailing realized vol
  (`_trailing_vol`, 63-day lookback), then clip to per-name bounds and renormalize:
  - N=5 → per-name **max 20%** (§6.3 "respect the existing 20% cap"); min = none.
  - N=8, N=10 → per-name **[7.5%, 15%]** (§6.3).
  When the sector cap is ON, it is applied **on top** of the sizing (sizing → per-name clip → sector cap →
  renormalize). Pure inverse-vol is excluded (§6.3).

## 3. Metric set (§9) — identical to Stage 2

Net CAGR, Sharpe, Calmar, max drawdown, annualized turnover, average holding period, worst single-name
gap loss, and the three crash-window returns (2008 GFC / 2020 COVID / 2022). No config adopted on CAGR
alone (§9); Stage 4's metric set is decided here, not CAGR (§6.1).

## 4. Winner rule (frozen)

Same discipline as Stage 2 §4: best on the full metric set, weighting Sharpe / Calmar / max-drawdown /
crash-window behavior above raw CAGR; near-ties resolve toward the more **robust** book — more names,
sector-diversified, lower drawdown (§6.1 "accepting lower max backtested CAGR for better Sharpe, drawdown,
and out-of-sample stability… decide on the metric set, not CAGR"). The winning **(name count, sizing,
sector cap)** is frozen into Stage 4 (regime).

## 5. ⚠ Disclosed limitation — sector classification is static-current, not PIT

`tickers.sector` is a single current classification per ticker, applied to all historical dates. Coverage
is 100% of the PIT universe (11 sectors) at 2008/2020/2026, but sector *assignment* is not point-in-time.
Because GICS sector membership is highly stable over a name's life, this is a small, standard, disclosed
approximation — and it is the **same** source the live `_apply_sector_cap` uses in production, so backtest
and live behavior are consistent. A truly-PIT sector store remains the MOM-002 "Future Research/Medium"
item; it is not built here. Any sector-cap result is reported with this caveat attached.

## 6. Prior expectation (§6.1)

Likely production candidate **8–10 names** — lower max CAGR, better Sharpe / drawdown / out-of-sample
stability than the 5-name book; the sector cap should most help crash-window drawdown (it prevents the
book from becoming a single-sector bet exactly when momentum crashes are worst, §6.2).

*Frozen: 2026-07-15. Changes after the first Stage-3 run require a new version + re-run.*
