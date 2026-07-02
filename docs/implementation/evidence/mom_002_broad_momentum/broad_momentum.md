# MOM-002 Broad Momentum — Evidence (Breadth Sweep v1)

_Survivorship-free SEP + `run_momentum_backtest` · universe n=150 · 2019-01-01..2026-06-13 · IS/OOS split 2023-01-01 · weekly rebalance, long-only, equal-weight, last-price-to-cash · store 1997-12-31..2026-06-16_

> Chartered from the 2026-07-02 daily-report review. The ★★★★★ question the review posed:
> **"Does Top-20 Momentum outperform Top-5 on a risk-adjusted basis?"** — motivated by the observation
> that the live Top-5 book is effectively *one macro theme* (semis / storage / AI infrastructure), not
> five independent bets. This is a **measurement** study; no strategy was changed. Breadth N is the only
> variable — same construction rules as the live book.

## Books (full window 2019–2026)

| Config | CAGR | Sharpe | MaxDD | Calmar | OOS Sharpe (post-2023) | avg turnover |
|---|---|---|---|---|---|---|
| **Top-5** | **+77.4%** | **1.37** | −55.3% | **1.40** | **1.67** | 24.3% |
| Top-10 | +53.8% | 1.25 | −48.5% | 1.11 | 1.39 | 21.0% |
| Top-15 | +50.1% | 1.28 | −41.7% | 1.20 | 1.50 | 19.5% |
| Top-20 | +38.5% | 1.12 | **−40.2%** | 0.96 | 1.33 | 19.0% |

## Answer to the research question: **No — broadening the book did NOT improve risk-adjusted return.**

On this window, concentration *won* on every risk-adjusted measure:
- **Sharpe** falls monotonically-ish with breadth: 1.37 (Top-5) → 1.12 (Top-20).
- **Calmar** falls: 1.40 → 0.96.
- **CAGR** falls: +77% → +38%.
- The direction **holds out-of-sample** (post-2023 Sharpe 1.67 → 1.33) — not a single-regime artifact.

The **one** thing breadth buys is a **shallower max drawdown**: −55.3% (Top-5) → −40.2% (Top-20), a
~15pp reduction. So breadth is a **return-for-drawdown trade**, not a free lunch — a risk-averse allocator
may still prefer Top-15/Top-20 for the smoother ride, but it costs ~0.25 Sharpe and ~40pp of CAGR to get it.

## The more important finding: breadth does NOT create independent evidence

Cross-config **monthly-return correlation**:

```
        Top-5  Top-10  Top-15  Top-20
Top-5    1.00    0.96    0.93    0.90
Top-20   0.90    0.96    0.99    1.00
```

Even a **4× broader** book (Top-20) still correlates **0.90** with Top-5. Widening the *same factor* does
not manufacture diversification — it is still one momentum bet. **This is the load-bearing result for the
portfolio question:** the redundancy the review flagged (three momentum books at ~1.00 correlation, 100%
holdings overlap — see the live Portfolio Analytics Engine run, PR #322) cannot be fixed by broadening any
single book. Independent evidence has to come from a **different factor** (Low-Vol, Sector), not a different
breadth of momentum.

## What this says about the portfolio (evidence-first, no promotion)

1. **Do not broaden the live momentum book to "diversify" it.** Top-5 is the stronger risk-adjusted single
   book; broadening trades Sharpe/CAGR for drawdown. That is a legitimate choice, but it is not a
   diversification fix.
2. **The real redundancy is running three near-identical Top-5 momentum books.** MOM-002 confirms the fix is
   *fewer momentum books + more distinct factors*, not *wider momentum books*.
3. **Keep one concentrated momentum book** (its OOS Sharpe of 1.67 is the platform's strongest single-factor
   evidence to date) and let Low-Vol / Sector / Combined carry the diversification, exactly as the review's
   revised lineup proposes.

## Caveats & scope

- **Sector-cap arm not yet run.** The review also asked for a per-sector cap. `run_momentum_backtest`
  supports `max_sector_pct`, but the **local factor store has 0 tickers with sector data** (`tickers.sector`
  all NULL → the cap fails open). The arm is wired and skipped with a notice; re-run on the sector-populated
  store (AWS box / after a TICKERS re-ingest) to test whether a sector cap recovers drawdown *without* the
  Sharpe cost that raw breadth incurs. **This is the natural v2.**
- Single universe (n=150), single 7.5-yr window, 10 bps turnover cost baked in. Top-5's higher turnover
  (24% vs 19%) means its edge narrows under higher costs — a cost-sweep is a cheap follow-up.
- Equal-weight Top-N implicitly caps each position at 1/N, so the review's separate "position cap" knob only
  binds under inverse-vol weighting; not exercised here.

## v2 — Sector-cap arm (run on the sector-populated box store, 2026-07-02)

The sector-cap arm was run on the AWS box store (the only store with `tickers.sector`
populated — 21,679 names, 11 sectors). **Important caveat:** that store has full universe
breadth only **from 2025-01** (pre-2025 SEP holds ~4 names/yr), so 309 of 389 weekly
rebalances were skipped as thin and the surviving **80 rebalances all fall in ~2025-01→2026-06**
— an ~18-month recent window, not 2019–2026. Absolute magnitudes (e.g. the 170%+ CAGRs) and
long-window generalization are therefore **not** comparable to the primary run above. But all
8 configs ran on the **identical 80 rebalances**, so the **sector-cap comparison is internally
valid**.

| Config | Sharpe | +sec30 Sharpe | ΔSharpe | MaxDD | +sec30 MaxDD |
|---|---|---|---|---|---|
| Top-5 | 1.70 | 1.73 | +0.03 (negligible) | −55.3% | −55.4% |
| Top-10 | 1.51 | **1.22** | **−0.29** | −48.5% | **−51.3%** (deeper) |
| Top-15 | 1.52 | **1.24** | **−0.28** | −41.7% | −42.5% (deeper) |
| Top-20 | 1.32 | **1.15** | **−0.17** | −40.2% | −41.1% (deeper) |

**Answer: a 30% sector cap does NOT recover drawdown, and it costs Sharpe.** For Top-10/15/20 it
cuts Sharpe by 0.17–0.29 *and* slightly deepens the max drawdown; for Top-5 it is negligible (five
equal-weight 20% names rarely breach a 30% weight cap). The cap forces the book off its strongest
momentum names into weaker sectors — hurting return while the drawdown (driven by broad market beta,
not single-sector concentration) barely moves. Artifacts: `research/mom002/v2_sectorcap_box/`.

**Combined v1 + v2 verdict:** neither *breadth* nor *sector-capping* improves the momentum book on a
risk-adjusted basis. Concentration keeps winning; the fix for the portfolio's redundancy is **distinct
factors, not a reshaped momentum book**. A definitive long-window (2019–2026) sector-cap test remains
blocked by a data gap on *both* stores (local: full history, no sector; box: sector, no pre-2025 breadth)
— it needs one store with **both** full history and sector data (re-ingest `tickers.sector` into the
local full-history store, or back-fill pre-2025 SEP breadth into the box store).

## Reproduce

```
cd apps/backend
.venv/Scripts/python.exe scripts/mom002_broad_momentum.py \
    --start 2019-01-01 --end 2026-06-13 --n 150 --split 2023-01-01 \
    --max-sector-pct 0.30 --report-dir research/mom002/
```

Artifacts: `apps/backend/research/mom002/mom002_report.md` + `mom002_results.json`. Deterministic for a
given store + args. Framework change: `app/factor_data/backtest.py` gained a backward-compatible `top_n`
absolute-count override (tests in `tests/factor_data/test_backtest.py`).

## Verdict: **Neither breadth nor a sector cap improves the momentum book risk-adjusted.** Top-20 does not beat Top-5 (breadth = a drawdown-for-Sharpe trade, breadth ≠ diversification); a 30% sector cap costs Sharpe without recovering drawdown (v2, recent-window). Portfolio fix = fewer momentum books + distinct factors, NOT a reshaped momentum book. Definitive long-window sector-cap test still blocked by a both-stores data gap.

_Whatever the number, the evidence package is the deliverable. 12-1 momentum frozen — no optimization performed._
