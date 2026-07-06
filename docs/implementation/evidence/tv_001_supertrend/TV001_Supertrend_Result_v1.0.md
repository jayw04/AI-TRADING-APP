# TV-001-SUPERTREND — Validation Result v1.0 (FINAL)

| Field | Value |
|---|---|
| Program | TV-001 (Community Strategy Import) → candidate **TV-001-SUPERTREND** |
| Pre-registration | `TradingWorkbench_TV001_Supertrend_Validation_v0.2.md` (owner-reviewed 9.5/10) |
| Harness | `scripts/tv001_supertrend_validation.py` (+ 6 offline tests) |
| Date | 2026-07-04 |
| **Verdict** | **🔴 Rejected (Evidenced)** — no generalizable, cost-surviving timing edge over buy-and-hold |

## Bottom line

Run against the pre-registered protocol — Supertrend (ATR 10 / mult 3.0, 15m, stop-and-reverse), 15 liquid
symbols, 2023-01→2026-06 walk-forward, 10 bps cost, buy-and-hold benchmark — **TV-001-SUPERTREND is
rejected.** It beats buy-and-hold on **1 of 15 symbols (7%)**, far below the 60% generalization bar, and
**both fit-winners (MSFT, PLTR) fail** — confirming the import test's caution that their earlier "wins"
were window/symbol-specific, not a general edge. The rejection is **robust**, not a parameter artifact.

## Evidence (15Min, long/flat, 10 bps, net of cost, OOS/walk-forward)

| Test | Result | Bar | Pass? |
|---|---|---|---|
| **Generalization** — beats buy-and-hold | **1/15 = 7%** (only WMT +0.4%) | ≥ 60% | ❌ |
| **Fit-winners** (the names it was selected on) | MSFT −1.03, **PLTR −13.8** vs B&H | should hold up | ❌ |
| **Parameter stability** — best of ATR{8,10,12}×mult{2.5,3.0,3.5} | best setting beats B&H on **13%** of the universe; range 0–13% | ≥ 60% | ❌ (no neighbour rescues it) |
| **Walk-forward robustness** — windows beating B&H | mostly 0–3 of 7 windows/symbol | consistent | ❌ |
| **Turnover** | median **97.8 trades/yr**, ~35-bar (~1.3-day) avg hold | — | high → cost-sensitive |
| **Statistical power** | hundreds of trades/symbol | ≥ 100 | ✅ (well-powered) |

## Research vs deployment (the honest nuance)

- **Research question — is there *any* timing signal?** Marginally **yes**: the aggregate per-trade mean
  net return is **+0.00162, bootstrap CI [0.00077, 0.00249]** (excludes zero). Supertrend's average
  trade is faintly positive after cost.
- **Deployment question — is it worth capital over just holding?** **No, decisively.** On strongly
  trending names, being flat during pullbacks forfeits the buy-and-hold compounding, and ~98 round-trips/yr
  of turnover bleeds cost. The strategy underperforms simply holding on 14/15 names (PLTR by 13.8×
  cumulative). A faint per-trade edge is *not* a deployable strategy.

This is the exact distinction the protocol pre-registered: a real-but-tiny signal that fails the
deployment bar. Bias-toward-avoiding-false-positives → **reject**.

## Why this matters (methodology)

- **We did not promote on freed capacity.** The consolidation freed two paper accounts; the platform's
  discipline (ADR 0036 / "no deployment ahead of a verdict") held — we validated first, and the evidence
  says do not deploy. The freed slot stays open for a *validated* program.
- **The import test's caution was right.** MSFT/PLTR were window/symbol-fit artifacts; a broad,
  parameter-robust, cost-realistic test overturns the interim optimism. A faithful validation *is* the win,
  independent of the verdict.

## Disposition

- **TV-001-SUPERTREND → Rejected (Evidenced).** Archived; **no further work unless a fundamentally new
  hypothesis emerges** (the RNG-001 stopping-rule pattern). Keeps its provenance ID as the citable record.
- **TV-001 (Community Strategy Import) program: closed.** All three top-TradingView strategies now have a
  verdict — 2 rejected at import, 1 (Supertrend) rejected on full validation. The lasting asset is the
  reusable **import → recon → validation** pipeline + the Strategy×Symbol-Fit screener, not any signal.

## Reproducibility

| | |
|---|---|
| Python / packages | 3.12.13 · numpy 2.2.6 · pandas 2.3.3 |
| Bootstrap seed | 17 (fixed) |
| Data | Alpaca IEX, 15Min RTH bars, 2023-01-01→2026-06-13; 15 symbols; ~22.3k bars/symbol |
| Signal | faithful recon of `docs/strategies/pine/supertrend_kivanc_recon.pine` (hl2, Wilder ATR 10, mult 3.0, stop-and-reverse) |
| Artifact | `data/tv001_supertrend/tv001_supertrend_results.json` (box) |

_v1.0 — 2026-07-04. FINAL. Feeds the registry TV-001 line (Supertrend candidate → Rejected)._
