# GAPPER-001 — Pre-Registration v0.2 (FROZEN) · Gap + RVOL Opening Continuation

**Date:** 2026-07-08 · **Owner:** Jay Wang · **Program ID:** GAPPER-001 · **Registry:** Planning →
**Running (ACTIVE-accruing)** · **Authority:** Sprint Plan v0.4 (Week 2) + owner review of v0.1
(`comments.md`, 2026-07-08). **Supersedes v0.1.**

**Status:** ✅ **DESIGN FROZEN v0.2 (2026-07-08), locked BLIND** — the verdict metric + book assumptions
are fixed **before** any additional candidate data is materialized (per the owner: lock the metric now so
it can't appear chosen after seeing the accumulated candidate distribution). GAPPER-001 stays
**ACTIVE-accruing, not validated**; verdict pending the ≥40-date / ≥100-event sample gate.
*(Owner final-review edits folded 2026-07-08: precise top-5 tie-break; spread-missing + sector-unresolved
replay exclusions; SPY + sector-ETF in the intraday cache set; account-level usability reporting; backfill
manifest. These clarify execution — the locked §4 verdict metric is unchanged.)*

> Unchanged from v0.1 (see that file): the hypothesis, SCAN-001 candidate source, the primary entry
> design, the liquidity floor, the slippage grid, and the CAP-025 replay method. v0.2 **locks the
> verdict metric, the trading-book assumptions, the promotion criteria, the accrual health-checks, the
> intraday-caching requirement, and the shadow-paper status.**

## 1. Hypothesis (unchanged)

*High-quality gap/RVOL candidates that hold above VWAP / the 30-min opening-range high continue —
intraday.* Continuation, not fade (not a Range Trader revival). Provenance: **live-files-only**.

## 2. Primary design (unchanged, locked)

SCAN-001 candidate → **enter on the 30-min opening-range high break** → **require price above VWAP** →
**require market & sector positive** (SPY *and* the GICS sector SPDR above prior close at the entry bar)
→ **exit at same-day close**. Entry fills at the OR-high break **+ half the prevailing spread**.
Sensitivities (never primary): 15-min break · 1/3/5-day hold · ATR trailing · VWAP-only.

## 3. Trading-book assumptions (v0.2 — LOCKED, so the replay can't become a portfolio search)

- **Max positions per day: 5.** If more than 5 candidates trigger, select the **top 5 by Discovery
  Confidence**; **tie-breaker: higher RVOL, then higher dollar volume**. **No additional score** unless
  pre-registered.
- **Weighting: equal-weight** among the triggered candidates that day.
- **Capital basis: deployed capital**; **idle capital = 0 return** (a 0-candidate or no-trigger day returns 0).
- **Entry deadline: no new entries after 11:00 ET** (a candidate that hasn't broken the OR high by 11:00 is skipped).
- **Exit: same-day close.**
- **One trade per ticker per day** (no re-entry).

## 4. Verdict metric (v0.2 — LOCKED)

- **PRIMARY:** the **date-clustered daily equal-weight candidate-book net return, in bps on deployed
  capital.** Each trading day is one observation = the equal-weight net return of that day's triggered
  candidates (≤5), after costs; idle days = 0. The bootstrap is **clustered by date** (each date is a
  resampling unit). *This is what a user actually experiences — a daily book — not an abstract per-trade
  average.*
- **SECONDARY (diagnostic only, never the promotion gate):** net per-trade edge in bps.
- **Assumed primary slippage:** **10 bps/side** (the verdict's base cost; the 5–100 bps grid is the
  sensitivity, and **breakeven slippage** is reported as a headline).

## 5. Promotion criteria (v0.2 — LOCKED; ALL must hold)

1. The **date-clustered CI on the daily net book return excludes zero**.
2. **Breakeven slippage ≥ 2× the assumed primary slippage** (i.e. the edge survives to **≥ 20 bps/side**).
3. The **sample gate clears**: ≥100 eligible gap events across **≥40 distinct dates** (after the
   liquidity floor).
4. **No single date contributes more than 25% of total P&L** (concentration guard — the edge must not be
   one lucky gap day).

Otherwise: **`insufficient_sample`** (gate not met / power-limited, labelled as such) or **Rejected**
(adequate sample, CI spans zero or breakeven < 2× cost or one date dominates).

## 6. Accrual health-checks (v0.2 — NEW, run daily; the first failure was a sync/timing bug, not strategy)

Per trading day, record + alert on: `same_day_gapper_file_present` · `scan_time_after_file_sync` ·
`fresh_non_empty_day_count` · `candidate_count` · `intraday_bar_coverage_count` ·
`invalid_or_stale_day_count`. (The `morning_opportunities.py` accrual counter already counts only
**fresh, non-empty** days; these checks make the pipeline's health visible.)

## 7. Intraday-bar requirement (v0.2 — NEW infra requirement, the true replay blocker)

**When a candidate appears in the daily report, auto-cache its same-day 1-min (and 5-min) bars.** Without
this we will reach 40 dates but still lack replayable intraday data (currently **0** current candidates
have intraday bars cached). This is a Week-2 infrastructure task, gating the eventual replay — not the
accrual of candidate sets.

**Cache set (LOCKED):** for each candidate, cache same-day intraday bars for the **candidate ticker,
SPY, and the candidate's GICS sector SPDR** — all three are required (the entry rule needs SPY *and* the
sector above prior close).

**Replay data-handling rules (LOCKED — no silent defaults):**
- If the **entry-time spread cannot be observed**, the candidate is **excluded from the primary replay**
  — a missing spread is **never** defaulted to zero. A conservative spread-imputation run may be reported
  as **sensitivity only**.
- If the **sector ETF cannot be resolved**, the candidate is **excluded from the primary replay** — no
  SPY-only fallback (that would change the rule after the fact).

## 8. Deliverable & product surface (v0.2 — status line + shadow-paper status)

- **Morning Opportunities Candidate Report** (`scripts/reports/morning_opportunities.py`) — ADR-0037
  labels only (Watch / Research / **Backtest Pending** / Validated Pattern / Rejected Pattern); no
  Buy/Sell/target/conviction language. **Required status line:**
  *"Backtest Pending — N/40 valid accrual days. Not a validated trading signal."*
- **Status = GAPPER-001 Shadow Paper / Forward Observation** — explicitly **not** "GAPPER-001 Paper
  Strategy." (Paper trading risks no money, but mislabeling risks premature credibility.)
  - **Allowed now:** generate the Candidate Report · track whether each candidate triggered the rule ·
    record hypothetical/paper fills to an **isolated shadow ledger** · accumulate real-time
    execution/slippage/VWAP/trigger-time/exit data · show the accrual counter · label everything
    Backtest Pending.
  - **NOT allowed:** promote to a user strategy · show Buy/Sell · rank as validated · include in the
    strategy-performance lineup · imply it passed evidence gates.
  - **Do not tune** parameters before the ≥40-date / ≥100-event gate; promotion requires the §5 CI gate.

**Account-level usability reporting (v0.2 — secondary to the deployed-capital verdict).** The §4 metric
tests the *signal* (deployed capital); this answers *"would it help a user's account?"* — reported, not
gated: **daily return on allocated capital · average capital deployed · candidate trigger rate ·
0-trade-day frequency · monthly paper-equivalent CAGR · max drawdown of the shadow ledger.**

## 9. Data status (carried from v0.1 gate + the 2026-07-08 correction)

Data-gated; **live-files-only** provenance. Sync-timing bug fixed (laptop sync 09:00 CT → 08:00 CT,
before the 09:25 ET scan). Stale records corrected (07-02/06/07/08 regenerated from same-day files;
07-01/07-03 purged). **Valid accrual = 4/40** at freeze. The sibling `claude-trading-view` app holds
**20 same-day gappers files (2026-06-08 → 07-08)**; backfilling them (PIT-valid, real premarket
snapshots) is the **next step, executed only AFTER this v0.2 freeze** so the metric was locked blind.

**Backfill DONE (2026-07-08, after the freeze).** All 20 dates regenerated from their same-day files
(store-as-of-that-day; marked `backfilled` + note) → **accrual = 20/40 valid dates, 72/100
candidate-events** (1–6 candidates/day). ~20 more dates + ~28 events needed → forward accrual (~1
gappers file per trading day, now landing before the 09:25 ET scan) ≈ early August. **Remaining replay
blocker (§7): 0 candidates have intraday 1/5-min bars** — auto-caching those is the next infrastructure
task, and it gates the eventual CAP-025 replay (not the candidate-set accrual).

**Backfill manifest** (`evidence/gapper_001/backfill_manifest.md`) records every backfilled file — date ·
source path · file timestamp · sha256 · candidate count · fresh/non-empty flag · included/excluded reason.
Rule: the backfill includes **all** available same-day files, **not** a selected subset (no
cherry-picking); any skipped date is listed with its reason.

## 10. Lifecycle

No paper promotion unless §5 clears. Paper requires CEE from day one, the Week-3 paper protocol, and the
ADR-0040 minimal metrics. Stopping rule: one primary design; a revision is **GAPPER-002** (fresh
pre-registration), not an edit.

---

*Frozen 2026-07-08 (blind). Next: backfill the 20 sibling-app gappers days (sync missing files → box →
regenerate evidence, PIT-valid) → accrual toward ~20/40; then wire the §7 intraday auto-cache. Verdict
runs only when §5's sample gate clears.*
