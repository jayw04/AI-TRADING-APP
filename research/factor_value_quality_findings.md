# Value & Quality factor study — findings (R2)

**Question:** now that FMP fundamentals are ingested (PIT, survivorship-aware), do
**Value** and **Quality** factors add a robust out-of-sample edge on our universe —
i.e. is a multi-factor book worth building?

**Method:** the existing factor-research harness (`scripts/factor_research.py
--with-fundamentals`), top-200 liquid US names, 2016-01..2026-06, IS < 2023-01-01 /
OOS ≥ 2023-01-01. Fundamentals as-of-joined on SEC `accepted_date` (no look-ahead),
197/200 names covered, 5,762 annual statements. Factors (higher = long): Value =
earnings/FCF/sales yield; Quality = ROE, gross profitability (Novy-Marx), ROIC,
−debt/equity. Full table: `research/factor_report.md`.

## Result — only momentum survives OOS

| Factor | IS IC | OOS IC | OOS LS-Sharpe | Verdict |
|---|---|---|---|---|
| **mom_12** | 0.017 | **0.060** | **+1.33** | ✅ the edge |
| mom_12_1 | 0.020 | 0.041 | +0.94 | ✅ weaker |
| mom_6_1 (old prod) | 0.015 | 0.004 | +0.42 | ~flat |
| debt_to_equity (low lev) | 0.015 | 0.001 | +0.87 | flat / noise |
| gross_profitability | **0.037 (t 1.87)** | −0.017 | −1.47 | ❌ IS-only, collapses OOS |
| roic | 0.016 | −0.031 | −1.79 | ❌ negative OOS |
| roe | 0.008 | −0.038 | −1.82 | ❌ negative OOS |
| earnings_yield | −0.013 | −0.041 | −1.78 | ❌ negative OOS |
| fcf_yield | 0.009 | −0.053 | −1.92 | ❌ negative OOS |
| sales_yield | −0.014 | 0.001 | −0.82 | ❌ negative OOS |
| lowvol_6m | −0.014 | −0.089 | −1.98 | ❌ negative (prior finding) |

**Value and Quality are negative or flat out-of-sample on this universe.** The one
quality factor with a real in-sample signal — gross profitability (IS t-stat 1.87)
— **collapses OOS** (LS-Sharpe −1.47). That is the same curve-fit signature the
§5c/OOS discipline caught on RangeTrader: the gate is working.

## Why — and the load-bearing caveat

This is a *universe + regime* result, not "value/quality don't work, ever":

1. **The universe is the top-200 by liquidity = mega-caps** (NVDA, TSLA, MSFT,
   AAPL, …). 2023–2026 was an extreme mega-cap **growth/momentum** regime: the
   expensive, low-yield AI/growth names led. So "cheap" (high earnings/FCF yield)
   was a *negative* signal here, and quality/low-vol (defensive) lagged badly. This
   is value's worst environment in decades, concentrated in exactly the names
   where value has least to work with.
2. **Value & Quality need breadth.** They earn their premium across a wide
   cross-section (small/mid caps, high dispersion), not among 200 mega-caps. The
   liquidity screen selects away the part of the market where these factors pay.
3. **The correlation panel confirms it:** earnings/FCF/sales yield, ROE, ROIC and
   low-vol are all highly correlated (0.8–0.97) — one "cheap-and-defensive" axis
   that got crushed together — and **negatively correlated with momentum** (≈ −0.3
   to −0.55). On this universe they are momentum's *opposite*, not a diversifier.

## Implication for the multi-factor book

**Do not build a momentum + value + quality composite on the current (top-200
liquid) universe.** A naive 40/30/30 blend would *dilute* the only working signal
(momentum) with factors that are negatively correlated and negative OOS here — it
would underperform pure 12-month momentum. The honest call on this universe is the
one R1 already shipped: **a momentum book (12-month)**, full stop.

Multi-factor only becomes worth revisiting **after broadening the universe** beyond
mega-caps — which our data can support: Sharadar SEP is survivorship-free and broad,
and FMP fundamentals (now ingested, 1985→2026) cover small/mid caps too. A fair
Value/Quality test = re-run this study on a small/mid-cap-inclusive universe (e.g.
top-1000–3000 by dollar volume, or an explicit size bucket), where value/quality
historically pay. Until then, treat them as **not validated on our tradeable
universe**, not as validated.

## What shipped vs deferred

- ✅ **Infrastructure (this PR):** FMP `/stable` provider, PIT fundamentals store +
  ingestion, Value/Quality factor definitions, `--with-fundamentals` study path.
  All reusable — a broader-universe re-test is now just an ingest + a flag.
- ⏸ **Multi-factor book:** deferred — no robust OOS edge on the current universe.
- **Recommendation:** stay with the 12-month momentum book (R1); pursue
  **R3 risk overlays + the momentum-crash study** next (no new data); revisit
  Value/Quality only with a broadened universe.

*Caveat shared with all our studies: a single OOS regime (2023–2026) and a
winner-biased liquid universe inflate absolute numbers; the robust takeaway is the
**relative** ranking — momentum the only OOS-positive factor, value/quality not.*
