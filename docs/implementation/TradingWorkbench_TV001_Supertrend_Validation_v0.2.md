# TV-001-SUPERTREND — Validation Study (Pre-Registration)

| Field | Value |
|---|---|
| Version | v0.2 (owner review folded, 9.5/10 → publication-grade; still pre-registration — results in the companion result doc) |
| Date | 2026-07-04 |
| Program | TV-001 (Community Strategy Import) → candidate **TV-001-SUPERTREND** |
| Predecessor | TV-001 initial import test (verdict Not Approved; Supertrend kept as a *research candidate*, `research/tv-001`) |
| Status | Pre-registered; harness `scripts/tv001_supertrend_validation.py` |

## Why this study exists

The TV-001 import test screened the top-3 TradingView community strategies; two were rejected and only
**Supertrend (KivancOzbilgic, ATR 10 / mult 3.0, 15m, stop-and-reverse)** survived as a *candidate* —
the only repeatable winner (MSFT +59%/+35%, PLTR +26%), but **window- and symbol-dependent**, tested on
only two windows at **100% equity** (explicitly *not* promotion-grade). The candidate is `research`
status, not a deployment decision. Freed paper-account capacity (post-consolidation) is **not** grounds
to promote — a verdict is (ADR 0036 / "no deployment ahead of a verdict"). This study runs the pass the
import test itself prescribed: **walk-forward + more symbols/timeframes + cost sweep + bootstrap CIs +
realistic sizing** — to earn a verdict or an honest rejection.

## Two questions (research vs deployment — review #4)

- **Research question:** does Supertrend possess a *statistically defensible timing edge* at all?
- **Deployment question:** is that edge *sufficiently strong after realistic costs* to justify capital
  over the trivial alternative (buy-and-hold)?

These are related but not identical — a strategy can have a faint real signal (research: yes) yet not be
worth deploying (deployment: no). The verdict below answers the deployment question; the per-trade
bootstrap answers the research question.

## Hypotheses (pre-registered)

- **Default assumption (H0):** *no generalizable edge exists until the evidence demonstrates otherwise.*
  The MSFT/PLTR wins are presumed symbol/window artifacts unless a broad test says otherwise.
- **H1 (generalization):** Supertrend produces **statistically significant incremental risk-adjusted
  performance relative to buy-and-hold, after realistic transaction costs**, on a *majority* of a broad
  liquid symbol set — not just the two names it was fit-selected on.
- **H2 (robustness):** where it works, the edge does not flip sign across walk-forward windows or
  timeframes, survives realistic cost, **and does not depend on a single (ATR, multiplier) point**
  (parameter stability — review #2).

## Method

- **Signal:** faithful recon of `supertrend_kivanc_recon.pine` — `hl2` source, **Wilder ATR period 10**,
  **multiplier 3.0**, trailing Supertrend bands, trend flips → **stop-and-reverse** (long on up-flip).
  Two position variants: **long/flat** (promotion-grade — no shorting) and **long/short** (the recon).
- **Universe (~15, sector-spread, to test generalization not cherry-pick):** MSFT, PLTR, AMD, NVDA, AAPL,
  TSLA, AMZN, META, GOOGL, JPM, XOM, WMT, JNJ, SPY, QQQ. (Includes the two fit-winners *and* names the
  study did not select, plus index ETFs — the honest test is the whole set, not the winners.)
- **Timeframes:** **15m primary**; 5m / 30m / 1H as a sensitivity check on a subset.
- **Window:** 2023-01 → 2026-06 (RTH bars, Alpaca IEX), **walk-forward in ~6-month blocks** (the edge must
  not depend on one window). Data fetched in time-chunks to avoid the 10k-page intraday truncation.
- **Cost:** round-trip cost **sweep 0 / 5 / 10 / 20 bps** applied on every position change (Supertrend
  flips frequently on 15m → cost is a primary kill risk). The pass/fail call is made at **10 bps**.
- **Sizing (review #5):** *research sizing* = single-symbol sleeve, fully invested when in-position (to
  isolate the signal). *Deployment sizing* (only relevant IF it validates) = a vol-target sleeve at the
  platform's 10% / 15% / 20% presets inside a diversified book — never 100%-portfolio-on-one-signal. This
  study reports research sizing; the deployment-sizing translation is a follow-on for a validated result.
  No overnight flattening (the recon holds across sessions — overnight gaps included when in-position).
- **Parameter stability (review #2):** re-run the ATR×multiplier grid **{8,10,12} × {2.5,3.0,3.5}**; if
  only (10, 3.0) works it is curve-fitting — a validated edge must survive neighbours, and a *robust
  rejection* is confirmed when no neighbour rescues it.
- **Turnover (review #3):** report **trades/year, average holding period, turnover** per symbol —
  Supertrend is notoriously high-turnover, and turnover × cost is a primary kill risk (as load-bearing
  as CAGR).
- **Statistical power (review #1):** an informative test needs **≥ 100 trades/symbol** (preferred 200+;
  expected 150–500 at 15m over 3.5y). Below that, "only N trades" undercuts confidence — the run must
  clear it (it does: ~90–110 trades/yr → hundreds over the window).
- **Benchmark:** **buy-and-hold the same symbol** — does the timing add value over just holding, net of cost?
- **Significance:** circular-block **bootstrap CI** on the per-trade net return (reuse `evidence.py`).

## Acceptance criteria (pre-registered — the verdict mapping)

Evaluated at **10 bps**, **long/flat** variant, **OOS/walk-forward**, net of cost:

| Result | Verdict |
|---|---|
| Beats buy-and-hold on **≥ 60%** of the universe **and** robust across windows/TFs **and** aggregate per-trade net-return CI **excludes zero** | **Approved** — generalizable standalone edge → eligible for paper promotion |
| Beats buy-and-hold in aggregate but not standalone-decisive (works as an overlay/on a subset), robustness partial | **Diversifier / Candidate-Promising** — more work or overlay-only |
| Wins only on a minority of symbols / flips sign across windows / dies at realistic cost / CI spans zero | **🔴 Rejected (Evidenced)** — symbol/window-specific, not a general strategy |

**Prior expectation (honest):** the default assumption is that no generalizable edge exists until the
evidence demonstrates otherwise; the import test already found Supertrend window- and symbol-dependent, so
H1 must clear a real generalization bar to overturn that default.

## Decision risk (review — the "biggest improvement")

| Error | What it means | Cost | 
|---|---|---|
| **False positive** | Deploy a strategy with no real edge | Capital loss + operational complexity + credibility of the methodology |
| **False negative** | Reject a strategy that had a modest edge | Missed opportunity only |

**Decision preference: bias toward avoiding false positives.** A wrongly-deployed strategy costs real
capital and erodes the platform's evidence credibility; a wrongly-rejected one costs only an opportunity
that the open-ended registry can revisit. This is *why the acceptance bar is intentionally high*
(generalization ≥ 60% + CI-excludes-zero + parameter/window robustness), and why a candidate is never
promoted on freed capacity alone.

## Post-verdict lifecycle (review #7 — closing the loop)

- **If Approved →** paper trading → 90-day continuous-evidence accrual → production (per ADR-0022 §7 /
  the promotion discipline). Consider a permanent catalog ID (e.g. **TREND-001 / ST-001**) — the "TV"
  prefix marks the *import* provenance; a validated strategy earns a characteristic-based name (review).
- **If Diversifier →** test it *with* the existing books (Momentum, LOW-001) and inside the combined-book
  portfolio construction — value as an overlay, not a standalone.
- **If Rejected →** archive; registry updated with the evidence; **no further work unless a
  fundamentally new hypothesis emerges** (the RNG-001 stopping-rule pattern). The candidate keeps its
  `TV-001-SUPERTREND` provenance ID as the citable record.

## Reproducibility (review #6)

The result doc embeds: Python version, key package versions (numpy/pandas), git commit, the fixed
**bootstrap seed (17)**, the data snapshot date + feed (Alpaca IEX), the symbol set, and the study window
— so the run reconstructs identically months later.

## Deliverables
- `scripts/tv001_supertrend_validation.py` (harness) + `tests/scripts/test_tv001_supertrend_validation.py`.
- Evidence package JSON + result doc; registry verdict for TV-001-SUPERTREND.

_v0.1 — 2026-07-04. Pre-registered; run before reading results into any promotion decision._
