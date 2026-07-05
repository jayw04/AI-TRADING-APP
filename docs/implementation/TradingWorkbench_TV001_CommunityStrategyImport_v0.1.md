# TV-001 — Community Strategy Import Test (v0.1)

| Field | Value |
|---|---|
| Program ID | **TV-001** (first **external / community-strategy import** program) |
| Family | External Strategy Import |
| Philosophy | *Can a popular public TradingView strategy be imported and promoted into TradingWorkbench?* |
| Status | **Completed** · Research line **Open** (TV-001-SUPERTREND follow-on) |
| Verdict | 🔴 **Not Approved** — none promoted; one kept as a research candidate |
| Capability Maturity | **L2** (validated result on the test sample) — *not* L3/L4 |
| Date | 2026-06-29 |
| Owner | Jay Wang |
| Evidence | `Docs/Strategies/TradingView Top Strategies 2026.md` (full results); recon Pine + screener under `Docs/Strategies/pine/`; Strategy-Tester screenshots under `~/tradingview-mcp/screenshots/` |

---

## Charter

The 2026 TradingView community-strategies library ranks scripts by **popularity (boosts)**, not realized
performance. TV-001 asks whether that popularity signal transfers into a deployable edge under
TradingWorkbench's own controlled conditions — and, by doing so, exercises the platform's discipline that
**every external strategy must pass Evidence Engineering before paper deployment**. The test is the point as
much as the strategies are: it establishes the precedent for importing *any* third-party strategy.

The top-3 community strategies (by boosts) were reconstructed as faithful Pine recons and Strategy-Tested
across two windows and a deliberately-selected symbol set (15m, US-RTH gating, 0.02% commission + 2 ticks
slippage, $10k). 28 backtests total. See the results doc for every cell.

## Verdict — Not Approved (per-strategy)

| Community strategy (boosts) | Engine | Result | Verdict |
|---|---|---|---|
| #1 HalfTrend SNIPERMONKEY (398) | trend-follow, frequent auto-flip | Flips sign across windows; overtrades; −33% worst cell | 🔴 **Reject** |
| #2 Universal Strategy Feed (75) | RSI 30/70 mean-reversion + ATR exits | No edge; best case **breakeven** (+0.5% on SPY, its ideal symbol) | 🔴 **Reject** |
| #3 Supertrend KivancOzbilgic (33) | trend-follow, wide ATR trail | Only repeatable winner (MSFT both windows, PLTR +26%), but window/symbol dependent | 🟡 **Research Candidate → TV-001-SUPERTREND** |

**Program verdict: Not Approved.** Nothing meets the promotion bar. HalfTrend and Universal RSI are
rejected outright. Supertrend is retained as the single follow-on research candidate
(**TV-001-SUPERTREND**) for a controlled study — *not* a deployment decision.

## Key findings (why)

1. **Popularity ≠ edge.** The most-boosted script (HalfTrend, 398) was the *worst* trend-follower; the
   least-hyped (Supertrend, 33) did best. The public popularity signal carried **no** predictive information
   about realized performance — the core lesson, and the reason the platform does not trust community rank.
2. **Window sensitivity is severe.** Of the cells comparable between the ~8-month and last-3-month windows,
   **3 of 4 flipped sign** (TSLA Supertrend +23%→−16%, MSFT HalfTrend +23%→−6%, AMD HalfTrend −26%→+9%).
   A sign that depends on the start date is not an edge — it is window-dependent noise.
3. **Symbol selection mattered more than strategy choice.** A data-driven screen (Kaufman segment-Efficiency
   Ratio, ADX, Choppiness Index, per-bar noise; composite **TrendScore = segER ÷ TR%**) ranked the
   calibration anchors in exact order of their trend-follower outcomes. Selecting symbols by character
   improved the odds (PLTR → Supertrend +26%), gave the mean-reversion strategy its only non-loss (SPY
   +0.5%), and **materially reduced drawdown** (selected low-noise names 4–16% DD vs AMD's 33–39%).
4. **Selection improves odds, not certainty.** QQQ topped the trend screen yet both trend-followers lost on
   it — the window simply lacked a directional leg. The screen shapes risk and probability; it does not
   manufacture a trend that isn't there.
5. **Strategy × symbol-noise interaction is the real variable.** Same symbol (PLTR), opposite outcomes:
   Supertrend +26% vs HalfTrend −28.5% — purely a trade-frequency effect (28 patient trades vs 52
   whipsawed ones). The patient trail rides PLTR's noise; the twitchy flipper gets chopped.

## Capability produced (the lasting asset)

- **Strategy × Symbol Fit screener** (`Docs/Strategies/pine/trendiness_screener.pine`) — measures
  trend-quality-per-unit-noise and chop, and matches a symbol's character to a strategy's nature. This is the
  most reusable output of TV-001 and belongs in **Discovery Lab** as a layer between the Opportunity Registry
  and Candidate Strategy Test: `Opportunity Registry → Strategy × Symbol Fit → Candidate Strategy Test`.
  Registered as **CAP-020** (documented direction; Discovery-Lab integration not yet built).
- **External-strategy import workflow** — reconstruct → cost/session/date-gated Strategy-Test → multi-window
  + selected-symbol matrix → Evidence-Engineering verdict. The precedent any future community/partner strategy
  follows.

## Follow-on: TV-001-SUPERTREND (research candidate — open line)

Supertrend is the only candidate worth further controlled research. It must pass a **real promotion gate**
before any paper deployment; until then it is a research candidate, not a strategy:

- More symbols (broader, fit-screened universe) and more timeframes.
- Longer windows + **walk-forward** (the direct answer to the window-sensitivity finding).
- Cost sweep (commission/slippage robustness) and **bootstrap confidence intervals** on the edge.
- **Realistic position sizing — NOT 100% equity** (see methodology rule below).

HalfTrend and Universal RSI get no further time **unless a fundamentally new hypothesis** appears
(the platform's standard closed-line rule).

## Methodology rule established by TV-001

> **No 100%-equity sizing in promotion-grade tests.** 100% equity is acceptable for *stress-testing* and for
> apples-to-apples comparison, but it compounds unrealistically and inflates both winners and losers. Any
> candidate moving toward promotion must be re-run with **10–25% equity sizing, a max-position cap, realistic
> slippage/commission, and a daily-loss cap.** (Proposed for ratification into the Evidence-Engineering
> promotion gate; recorded here, not yet folded into the methodology doc.)

## Caveats

- Recon scripts are faithful reconstructions of the documented engines, not byte-exact originals (SNIPERMONKEY's
  source is closed). The AMD #1/#2 cells reproduce the prior standalone runs to within rounding, validating the
  recons.
- Two windows, one timeframe (15m), modest samples (28–187 trades/cell), 100%-equity sizing throughout (the
  very thing the methodology rule above forbids for promotion). These results justify a *research candidate*,
  nothing more.
- TradingView's structured Strategy-Tester API returned empty this session; all figures were read from the
  Strategy-Tester UI (screenshots archived).

## Outcome taxonomy

- **Research verdict:** Not Approved (Rejected ×2 + Research Candidate ×1).
- **Platform contribution:** *Methodology Improvement* (the external-import workflow + the no-100%-equity
  promotion rule) **+** *Reusable Capability* (the Strategy × Symbol Fit screener, CAP-020) **+** *Negative
  Finding preserved* (popularity ≠ edge, with quantified window sensitivity).

*Every exit is a success: TV-001 declined three popular strategies and kept one honest candidate, and its
durable asset — symbol-fit selection — is worth more than the scripts themselves.*
