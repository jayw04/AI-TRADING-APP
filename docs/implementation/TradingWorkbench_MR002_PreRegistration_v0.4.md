# MR-002 — Pre-Registration v0.4 (DRAFT for owner sign-off) · Sector-Neutral Residual Reversion

**Date:** 2026-07-11 · **Owner:** Jay Wang · **Program ID:** MR-002 · **Registry:** → **Planning**
(**Running** on Research-Design Freeze) · **Authority:** owner proposal
`Docs/Strategies/Proposed Strategies.txt` + review 1 (`Docs/Strategies/…Review_and_Recommendations.md`)
+ review 2 (`…v0.2_Review_and_Recommendations.md`) + **owner v0.3 review & V1–V4 decision
(`Docs/implementation/comments.md`, 2026-07-11)** + verification results
(`evidence/mr_002/MR002_V1_V4_DataVerification_v0.1.md`). **Supersedes v0.3.**
**Status:** 🟢 **BUILD-AUTHORIZING DRAFT (owner-approved 2026-07-11) — NOT FROZEN.** The owner's final
sign-off approved both EDGAR builds and confirmed no further conceptual redesign is needed; v1.0 waits
only on the builds, the Data Availability Gate, and a fully recorded §8a. The 2-session post-release
cooling rule is **KEPT (owner decision)** with frozen session semantics (§4). During the builds, **no
MR-002 signals, development results, or portfolio backtests may be run** — work is limited to data
provenance, mappings, coverage, and frozen sample construction.
**Freeze path (§0):** V1/V2 builds → manual validation samples → V1/V2 re-verification → full Data
Availability Gate → §8a filled → completed freeze candidate → **Research-Design Freeze v1.0**.

> **Governance disposition (binding, unchanged):** RNG-001 stays **Completed · Rejected (Evidenced) ·
> Archived**. MR-002 is a new hypothesis. RNG-002 is chartered separately, later. No momentum,
> volatility, RSI, or market-regime filters before the first test.

## 0. Lifecycle (REORDERED — the gate now precedes the freeze)

`V1–V4 verification (✅ ran 2026-07-11) → build V1 earnings anchors + V2 SIC history → re-run V1/V2
verification → full Data Availability Gate → freeze exact data window, sample boundaries, and data
snapshots (§8a) → v0.4/v1.0 owner sign-off → RESEARCH-DESIGN FREEZE v1.0 → development implementation →
IMPLEMENTATION FREEZE → validation → sealed OOS (B, once)`

The v0.3 ordering (freeze first, gate after) was a governance weakness: sample dates weren't knowable at
freeze, so a data-driven window change could have moved the sealed period. **Data snapshots are pinned
before development** — never first pinned at Implementation Freeze — so development and validation
cannot read different historical values across vendor revisions.

## 1. Hypothesis (unchanged)

After removing broad-market and sector movements, unusually large company-specific (residual) price
moves frequently represent temporary liquidity pressure rather than information, and **partially reverse
over the following one to five trading sessions**. The edge must come from breadth and repeatability
(§10 breadth gates).

## 2. Universe (point-in-time, reconstituted monthly)

- **Reconstitution:** computed after the prior month-end close (data through that close only), effective
  the first trading session of the month.
- **Longs: top 250** US common stocks by trailing 60-session median dollar volume; **shorts: top 150**.
  **Dollar volume = SEP `close` × SEP `volume`** — verified as a mutually consistent split-adjusted pair
  (equals raw dollar volume by split-invariance; `closeunadj × volume` would mix bases — V3 verification).
- Close > $10 at reconstitution · 60-session median dollar volume > $25M · common stocks only ·
  ≥ 252 prior sessions of history.
- **Short side additionally:** any available PIT hard-to-borrow flag excludes (none exists — §9 V4
  fallback applies and is disclosed).
- **Sector-proxy availability:** eligible only while the stock's **PIT sector** (§8 V2 build) maps,
  through the effective-dated mapping table, to a sector ETF trading at that date. No parent-ETF
  remapping; unmapped periods exclude the stock.
- **Earnings-anchor availability (V1):** a stock without a prior confirmed earnings anchor (§4) is
  ineligible.
- Mid-month universe departures: no forced exit; no new entries. Universe sizes 200/300: post-verdict
  diagnostics only.

Survivorship-freedom mandatory: membership from PIT price/volume history (Sharadar SEP), never a
current-day list.

## 3. Signal construction (frozen — PIT-recursive sector residuals)

**Step 1 — orthogonalized sector factor, generated recursively and point-in-time.** For every session
`s`, sector-regression coefficients estimated on sessions `s−60 … s−1` are applied to session `s`:

`r_Sector,s = a + β_Sector · r_SPY,s + u_Sector,s`

producing a **stored PIT sequence** of sector residuals — each `u_Sector,s` computed using only
information available before its own session. **The stock regression at `t` uses these previously
generated PIT residuals `u_Sector,t−60 … u_Sector,t−1`** (and the day-`t` value for the day-`t`
residual). It is prohibited to estimate one sector regression at `t−1` and apply its coefficients
retrospectively across the prior 60 observations — that would be an internally inconsistent factor
history.

**Step 2 — stock model.** Rolling 60-session OLS on daily arithmetic total returns, estimated on
`t−60 … t−1`:

`r_i,t = α_i + β_m,i · r_SPY,t + β_s,i · u_Sector,t + ε_i,t`

**Registered estimation rules:** OLS **includes an intercept** · **no ridge or other regularization** ·
if a regression is singular or the sector-factor variance is zero, the observation is **unavailable and
the stock is ineligible that day** · PIT sector mapping per §8 V2; unresolvable ⇒ excluded, never
defaulted.

**Step 3 — signal.** `R5_i,t = Σ_{k=0..4} ε_i,t−k`, `z_i,t = (R5_i,t − μ_i,t−1) / σ_i,t−1`, with the
v0.2-registered normalization rules unchanged: `μ, σ` from windows ending `t−1` · exactly 60 complete
five-day observations · `ddof=1` · arithmetic total returns (signal series per §4 policy) · missing
observation ⇒ ineligible · no winsorization.

## 4. Entry, exit, and execution (frozen)

**Price-series policy (V3, verified):** signal = `closeadj` total-return series · execution =
split-adjusted non-dividend-adjusted `open`/`close` · **gap = economic:**

`economic_gap_t+1 = (open_t+1 + known_cash_distribution_t+1) / close_t − 1`

(split-adjusted fields; the distribution term uses ACTIONS dividend values, whose split basis is
confirmed at Implementation Freeze before the formula is applied — §7) · ranking = `close × volume`.

**Timing:** signals after close `t`; entries/exits at the **next session's official opening price**.
Entry session = session 1; time-stop exit at the open of session 6. Close-to-close = diagnostic only.
**Gap filter:** entry cancelled at the `t+1` open if `|economic_gap_t+1| ≥ 6%`.

**Earnings rule (V1 — owner-approved: “PIT estimated earnings-risk blackout”).** This is an
**estimated blackout, not a forward calendar**, and is labelled as such in every artifact:

> For each stock, the most recently confirmed earnings release — derived from an EDGAR **8-K Item
> 2.02** filing — is the PIT anchor. **Beginning 70 calendar days after that release, the stock is
> ineligible for new entry, and any existing position exits at the first available official open. The
> stock remains ineligible until the next confirmed earnings release resets the anchor.**

Registered companion rules: a stock without a prior confirmed anchor is **ineligible** (§2) · the SEC
**filing acceptance timestamp** assigns the event session — acceptance before the regular-session open =
BMO; after the close = AMC; ambiguous or in-session = **BMO (conservative)** · **no retroactive exit is
ever permitted** — if an earnings filing (or any schedule information) becomes known only after the last
pre-event open has passed, the position exits at the **first executable open after the information
becomes available**, and the case is recorded as an **earnings-calendar exception** (reported: number of
late cases, positions affected, P&L attributable to unavoidable event exposure) · the V1 build must
**validate that the selected EDGAR form/item consistently represents earnings releases** — not every 8-K
is an earnings event · **diagnostic only, after freeze:** blackout starts at 60 and 80 calendar days are
reported but never used for selection; the verdict rests on **70 days only**.

**Post-release cooling (KEPT — owner decision 2026-07-11, frozen wording):**

> No entry may execute during the first two regular trading sessions following a confirmed earnings
> release. For a BMO release on session `s`, prohibited execution opens are `s` and `s+1`. For an AMC
> release on session `s`, prohibited execution opens are `s+1` and `s+2`. An in-session or ambiguous
> release is treated as BMO. The earnings release resets the 70-calendar-day blackout anchor.

The 70-day blackout protects against an *approaching* release; the cooling period protects against the
opposite — entering immediately *after* one, when the residual move is likely information-driven rather
than liquidity pressure. Both derive from the MR-002 hypothesis; neither is a performance filter.

**V1 reset semantics (explicit — the cooling period and forward blackout are separate controls):** each
next confirmed earnings release simultaneously **(a) ends any existing 70-day blackout, (b) starts the
two-session cooling period, and (c) becomes the new anchor for the next 70-day count.**

**Long entry — all must hold at close `t`:** `z ≤ −Z_entry` · bottom 10% of the day's long-eligible
z-scores (side-scoped percentiles; ties by |z| then permanent identifier) · earnings blackout clear ·
no announced prohibited corporate action · gap filter passes at execution · liquidity envelope (§9).
**Short entry — mirror** (top 10% of short-eligible pool; §2 borrow rules).

**Exit — first occurrence of:** `|z|` inside ±0.35 · time stop (open of session 6) · residual beyond
±3.5 with market/sector confirmation (≥ 1σ same-direction move in SPY or the sector ETF) · earnings
blackout engages (70-day rule above) · **a newly announced prohibited corporate action (merger,
delisting, reorganization) forces exit at the next available official open** · mandatory §5 reduction.
Exits execute at the next official open. No tight ordinary price stop.

**Missing-signal rule for OPEN positions (registered):** a missing z-score does **not** itself trigger
an exit · the time stop continues to advance · earnings and corporate-action exits remain active · a
scheduled exit still executes if a valid official open exists; if not, the missing-open rule governs ·
missing-z-score days are counted and reported.

**Halts / missing opens:** entries without a valid official opening price are cancelled; exits remain
pending and execute at the next available official regular-session open. No intraday fills assumed.

**Delisting valuation (V3-amended priority order):** vendor delisting return is **unavailable in the
current data profile** (verified) and is therefore not listed as an active source. Order: **1)** verified
transaction consideration → **2)** final executable market price → **3)** conservative fallback —
**longs marked to zero; shorts covered at the GREATER of the last available close and any identifiable
announced cash/exchange consideration; if neither is verifiable, last close × 1.25 (registered punitive
markup)**. Fallback cases must be rare (higher priorities normally apply); their **count and P&L impact
are reported**. Delisted names never silently dropped; exclusions begin at announcement dates.

## 5. Portfolio construction (frozen, deterministic — incremental allocation registered)

**Gross exposure is a 100%-of-NAV MAXIMUM.** Unused capital = cash; no return credited to cash in the
primary result.

**Incremental daily algorithm (at each execution open):**

1. **Process exits first.** One position per symbol; no pyramiding; no same-open re-entry.
2. Compute the incremental capacity around what already exists:

   ```
   current_gross          = current_long_gross + current_short_gross
   gross_headroom         = max(0, 100% NAV − current_gross)
   long_increment_capacity  = min(candidate_long_capacity,  long-side constraint headroom,  gross_headroom / 2)
   short_increment_capacity = min(candidate_short_capacity, short-side constraint headroom, gross_headroom / 2)
   matched_increment        = min(long_increment_capacity, short_increment_capacity)
   ```

   New long orders and new short orders are **each limited to `matched_increment`**.
3. Candidate weights (∝ 1/σ_resid within each side) are **normalized to the incremental matched amount,
   not to 50% of NAV**. Unused incremental capacity remains cash. **Existing positions are never
   increased to consume unused headroom.**
4. The **1.5%-of-NAV position cap applies to the combination of a new order with any existing exposure**
   (pyramiding is prohibited regardless).
5. Existing positions remain at fixed shares until exit, except mandatory reductions.

**Targeted constraint reduction (replaces v0.3's single smallest-|z| rule):**

| Breach | Removal / reduction target |
|---|---|
| Sector cap | least-extreme candidate (smallest \|z\|) **in the offending sector** |
| Beta limit | the candidate whose exclusion most reduces \|normalized beta\|; tie-break smallest \|z\| |
| Gross cap | the globally least-extreme candidate |
| Net-exposure drift (±5% band) | reduce the **larger side** by smallest \|entry z\| first (tie: oldest, then identifier) |

Removal never renormalizes remaining weights upward; freed capacity goes to cash.

**Registered limits (unchanged from v0.3):** position ≤ 1.5% of NAV · sector net ≤ 5% of gross · sector
gross ≤ 20% of gross · `|Σ w_i β_i| / gross ≤ 0.10` (signed NAV-fraction weights, §3 β̂_m) · the 3%
projected-risk cap remains removed. **Drift policy:** entry-neutral; no rebalance while |net| ≤ 5% of
gross. **Vol overlay:** unchanged — primary is unscaled; 8% target reported as a secondary
scale-down-only transformation with full costs.

## 6. Frozen parameter policy (unchanged)

A: z 1.75 · **B (PRIMARY): z 2.00** · C: z 2.25 — exit z 0.35, max hold 5 sessions, all three. Verdict
on B only. Trial ledger governs the multiple-testing count.

## 7. Testing sequence & the two-stage freeze

**Research-Design Freeze (v1.0):** signed only after §8a is fully recorded (§0 ordering). Freezes
hypothesis, parameters, data rules, gates, samples, **and the exact sample dates + snapshot hashes**.

**Implementation Freeze** (after development harness verification, before validation): source commit ·
dependency lockfile · transformation code · unit + synthetic tests · configuration hash · data snapshot
identifiers (must equal §8a's) · DSR implementation (formula, skew/kurtosis treatment, trial count) ·
MOM-001 correlation artifact hash · **the ACTIONS dividend-value split-basis check** (cross-checked
against `closeadj` steps on a sample of split+dividend names) **and the resulting confirmation of the §4
economic-gap formula** · **the V2 mapping-table + crosswalk hashes (must equal §8a's)**. After it:
validation runs; only documented implementation defects may be corrected (defect report + full
validation rerun); no economic-rule change; sealed OOS stays unopened until re-freeze.

**Sequence:** development (first 50%; A/B/C; verification only) → Implementation Freeze → validation
(next 25%; A/B/C; five contiguous near-equal trading-session folds, remainder to the final fold; ≥3/5
positive on B; stability gate on A/C here) → sealed OOS (final 25%; **B only, exactly once**) →
stationary bootstrap (§10) → regime decomposition (§10a) → cost grid + breakeven → PBO (diagnostic) +
DSR (gate) → paper verification (CEE from day one). MaxDD gate = validation + sealed combined; sealed
maxDD also reported separately.

**Sealed-run defect policy (unchanged):** a material defect (changes orders, size, cost, daily return,
sample membership, or any pass/fail statistic) invalidates the sealed result → archived, no verdict;
correction requires **MR-003** or a new untouched period. Typographical/display-only corrections exempt.

## 8. Data verifications & builds (V1–V4 status + the §8a register)

**Verification run 2026-07-11** (`evidence/mr_002/MR002_V1_V4_DataVerification_v0.1.md`): V3 ✅ passed
(with the §2 dollar-volume amendment, owner-approved) · V4 ✅ fallback approved · V1/V2 🔴 failed as
originally specified → **owner-approved builds below**, then V1/V2 re-verification.

**V1 build — EDGAR earnings anchors (owner-authorized 2026-07-11):** derive per-stock confirmed
earnings releases from EDGAR 8-K Item 2.02 filings via CAP-015 (fair-access client), using **acceptance
timestamps** for known-at and session assignment. **Each anchor record carries:** filing accession
number · CIK + permanent security identifier · acceptance timestamp **normalized to Eastern Time** ·
assigned BMO / AMC / conservative-BMO status · original 8-K vs amendment flag · validation result that
Item 2.02 represents an earnings release · rejection reason for any rejected candidate filing.
**Duplicate anchors are collapsed to one confirmed release event; an 8-K/A does not create a new anchor
unless it represents a genuinely new release — ordinarily it amends the existing anchor record.**
**Required output metrics:** % of eligible securities with ≥ 1 anchor · % of universe-months excluded
for missing anchors · median + distribution of days between anchors · **% of inter-anchor intervals
< 60 days or > 110 days** (the false-anchor / duplicate / missed-release detector) · BMO / AMC /
ambiguous counts · manual validation error rate. EDGAR depth may extend the window before Sharadar
EVENTS' ~2016 floor.
**Re-verification labelling (registered):** because a genuine PIT forward calendar remains unavailable,
the V1 re-verification result is reported as **“V1 — Approved alternative implemented: PIT estimated
earnings-risk blackout”**, never as a plain “PASS” — preserving the auditable distinction between
satisfying the original data requirement and implementing the approved conservative substitute.

**V2 build — EDGAR effective-dated SIC history (owner-authorized 2026-07-11):** per security: join
EDGAR filings to `permaticker` through a **frozen CIK/permaticker crosswalk — itself effective-dated
where identity changes occur** (SHA-256 in §8a) · multiple share classes may share a CIK but **retain
distinct permanent security identifiers** · extract the SIC from each accepted filing · **a new SIC
becomes effective only when its filing is accepted; a missing SIC value never overwrites the last valid
SIC** · forward-fill only until the next accepted filing supplies a new SIC · **conflicting same-day
SIC values are logged and resolved by a frozen precedence rule** · map through an **effective-dated**
SIC→sector-ETF table (fields: `sic_start · sic_end · effective_from · effective_to · research_sector ·
sector_etf · mapping_rationale`) — explicit date ranges for taxonomy changes; a period with no valid
proxy excludes the stock · unresolved/conflicting records are excluded, **never silently defaulted to
current TICKERS sector** · **mapping and crosswalk hashes are generated AFTER manual validation and
BEFORE the Data Availability Gate** · mapping exceptions logged · report the % of universe-months
excluded for missing sector mapping.
**Pre-freeze validation sample (mandatory):** known reclassifications (**META mandatory**), ticker
changes, dual-class issuers, spin-offs, acquisitions, SIC-changed companies, sector-changed-without-
SIC-change companies, **and securities mapped to XLC or XLRE near their proxy-inception boundaries** —
manually verified and recorded.

**§8a — Frozen data window & snapshot register (RECORDED AT THE GATE; every field must be non-empty
before the v1.0 signature):**

| Field | Value |
|---|---|
| Trading calendar | ☐ (NYSE full sessions; half-day treatment stated) |
| First / last eligible trading date | ☐ / ☐ |
| Development start / end | ☐ / ☐ |
| Validation start / end | ☐ / ☐ |
| Sealed-OOS start / end | ☐ / ☐ |
| Partial first/last calendar-year treatment | ☐ |
| Stock-data (SEP) snapshot hash | ☐ |
| ETF-data snapshot hash | ☐ |
| Corporate-event (ACTIONS) snapshot hash | ☐ |
| Earnings-anchor (V1 build) snapshot hash | ☐ |
| SIC history + mapping-table hash (V2 build) | ☐ |
| CIK/permaticker crosswalk hash | ☐ |
| EDGAR coverage rate / excluded universe-months (V1, V2) | ☐ / ☐ |

**Data plan:** Sharadar SEP · TICKERS (category filters + `permaticker` only — never sector) · ACTIONS ·
EDGAR (anchors + SIC) · Yahoo adjusted close (SPY + sector ETFs). Window materially shorter than ~10
years at the gate ⇒ stop and re-review (power).

## 9. Cost model, borrow fallback, and capacity

Base 10 bps/side + 50 bps/yr borrow · mandatory stress 20 bps/side + 300 bps/yr · severe diagnostics
30 bps/side + 1,000 bps/yr · long-only/short-only attribution at every tier. **Borrow no-data fallback
(approved):** primary assumes availability in the top-150 short universe; **mandatory denial diagnostics
remove the most extreme 10% and 25% of short signals — applied among otherwise-eligible short entries,
on each entry date, BEFORE portfolio sizing, beginning with the most extreme positive z-scores**;
limitation disclosed in every result artifact. **Borrow accrual convention (registered): annual rate /
360, accrued per calendar day on short market value.** Transaction costs are charged **against traded
notional at execution**. Reference NAV $10M · 2%-of-20-session-median-dollar-volume participation cap,
clipped not delayed · opening-auction capacity limitation disclosed · capacity reporting: max scalable
NAV at 95%-under-cap + $10/25/50/100M diagnostics. Zero-cost-only pass ⇒ Rejected.

## 10. Verdict framework & pass gates (LOCKED at freeze)

Verdict on **config B, primary (unscaled), net of base costs, $10M NAV**.

**Registered definition — “profitable”:** cumulative net return > 0 over the named evaluation sample,
after all registered execution, transaction-cost, and borrow assumptions. (Used by the cost-stress,
parameter-stability, capacity, and regime gates.) For parameter stability, per the owner's option, the
gate stays **cumulative-return-only**; each config's validation Sharpe is additionally **reported** (the
Sharpe ≥ −0.25 condition is a diagnostic, not a gate).

**§10a Regime definitions (frozen; prior-session data):** Trend: SPY 126-session total return — Bull >
+5% · Bear < −5% · Sideways otherwise. Volatility: SPY 21-session annualized realized vol — High ≥ 20% ·
Low < 20%. Two separate axes, never one denominator. **Regime-loss denominator (registered):**
`loss_contribution_regime = Σ|negative daily net P&L in regime| / Σ|negative daily net P&L across all
trend regimes|` — net daily P&L, all evaluation trading days, each day in exactly one trend regime,
zero-exposure days retained in the series but contributing no loss. **Vol-regime adequacy:** ≥ 60
trading sessions **with nonzero gross exposure** in that regime; otherwise n/a, not failed.

**Bootstrap:** stationary, net daily portfolio returns, 10,000 reps, seed 20260711, expected block 5
sessions (+10-session sensitivity), 95% one-sided lower bound on mean daily net return.

**✅ Approved — ALL of** (unchanged from v0.3): Sharpe ≥ 0.70 (sealed) · Calmar ≥ 0.75 (sealed) · maxDD
≤ 15% (val+sealed) · folds ≥ 3/5 (val) · bootstrap lower bound > 0 (sealed) · cost stress profitable at
20 bps + 300 bps borrow (sealed) · A and C profitable (val) · DSR ≥ 95% per trial ledger (sealed) · net
annualized return ≥ 3% (sealed) · breadth ≥ 500 trades / ≥ 100 dates / ≥ 100 long / ≥ 100 short (sealed)
· top-10 trades ≤ 20% and single stock ≤ 10% of positive P&L (sealed) · ≥ 3 positive years AND largest
positive year ≤ 50% of positive annual P&L, Herfindahl diagnostic (val+sealed) · regime gates: positive
net P&L in ≥ 2 of 3 trend regimes · no trend regime > 60% of losses (formula above) · no vol-regime
Sharpe < −0.50 (val+sealed) · capacity positive at $10M (sealed).

PBO = diagnostic ("N=3 underpowered"). Positive-P&L regime concentration = diagnostic. Trial ledger =
A/B/C + the RNG-001 family + logged informal variants.

**🟡 Diversifier (B):** net sealed Sharpe ≥ 0.40 · bootstrap lower bound > 0 · |corr| ≤ 0.30 vs MOM-001
(frozen artifact hash, aligned net daily returns, no rescaling) · cost, DSR, breadth, concentration,
annual, regime gates pass.

**Power rule:** minimum relevant Sharpe 0.40 · 80% power · 95% confidence. Positive Sharpe + CI spans
zero + power < 80% ⇒ Power-Limited · Inconclusive. CI spans zero with power ≥ 80% ⇒ Rejected. Negative
Sharpe ⇒ Rejected.

**§10b Frozen metrics appendix:** Sharpe = mean/std of daily net returns × √252, risk-free = 0
(registered), std `ddof=1` · daily return series includes **every exchange trading session, including
zero-exposure days** · daily return = net P&L / **prior-day NAV** · CAGR = (NAV_end/NAV_start)^(252/N)
− 1 over the named sample's N sessions · maxDD = largest peak-to-trough decline of the cumulative net
NAV series · Calmar = CAGR / |maxDD| (same sample) · Sortino uses downside `ddof=1` vs 0 · borrow: annual
rate/360 per calendar day (§9) · transaction costs at traded notional (§9).

## 11. Evidence package (`Docs/implementation/evidence/mr_002/`)

As v0.3, plus: the **§8a register** (dates + all hashes) · V1 anchor + V2 SIC/mapping build records with
coverage rates and excluded-universe-month percentages · the V2 validation-sample record (META et al.) ·
earnings-calendar exception report (late revisions: count, positions, P&L) · missing-z-day counts ·
delisting-fallback case count + P&L impact · borrow-denial diagnostics · blackout 60/80-day diagnostics ·
"PIT estimated earnings-risk blackout" labelling in every artifact.

## 12. Owner decisions — record

Q1–Q5 (review 1) · S1–S4 (review 2) · **V1 = Option 1 as corrected by the owner: 70-calendar-day
one-sided blackout, labelled an estimated earnings-risk blackout · V2 = EDGAR-SIC build with
effective-dated mapping + hashed crosswalk · V3 = close×volume amendment accepted · V4 = fallback
approved with application clarifications** (comments.md, 2026-07-11). **Final sign-off (owner,
2026-07-11): both EDGAR builds authorized · the 2-session post-release cooling rule KEPT with frozen
session semantics · V1 reset semantics made explicit · V1 re-verification labelled "Approved
alternative implemented" · no signals/backtests during the builds. No open items remain in this draft;
v1.0 waits on §8a.**

## 13. Stopping rule & lifecycle (unchanged)

One primary design; one sealed test; substantive post-OOS revision = **MR-003**. §7 defect policy
governs corrections. No paper promotion unless Approved/Diversifier; CEE from day one. Registry entry at
Research-Design Freeze.

## 14. Changelog v0.3 → v0.4 (owner review folded)

1. **Lifecycle reordered (§0):** Data Availability Gate + exact sample dates + snapshot pinning now
   precede Research-Design Freeze; §8a register added — v1.0 cannot be signed with an empty field.
2. **V1 resolution (owner-corrected):** the 80–100-session proposal replaced by the **70-calendar-day
   one-sided blackout** anchored on EDGAR 8-K Item 2.02 acceptance timestamps, with the
   no-anchor-ineligible, BMO/AMC-assignment, no-retroactive-exit + exception-reporting, and
   item-validation rules; renamed **"PIT estimated earnings-risk blackout"**; 60/80-day diagnostics
   reported only. Restored the proposal's 2-session post-release entry cooling (flagged for sign-off).
3. **V2 resolution:** EDGAR effective-dated SIC history + **effective-dated** SIC→ETF mapping table
   (registered field schema) + frozen hashed CIK/permaticker crosswalk + mandatory validation sample
   (META et al.) + coverage/exclusion reporting.
4. **Incremental allocation registered (§5):** headroom/matched-increment formula around existing
   positions; weights normalized to the increment; 1.5%-NAV cap on combined exposure; unused capacity
   stays cash; existing positions never increased.
5. **Targeted constraint reduction (§5):** per-breach removal targets replace the single smallest-|z|
   rule.
6. **PIT-recursive sector residuals (§3):** stored recursive PIT `u_Sector` sequence; intercept, no
   ridge, singular ⇒ ineligible.
7. **Edge cases registered (§4):** late earnings revisions (first-open-after-knowledge + exception
   report) · announced corporate action forces exit of open positions · missing-z rule for open
   positions · delisting fallback corrected (short cover = max(last close, identifiable consideration),
   else last close × 1.25; cases counted + P&L-reported); vendor delisting return marked unavailable.
8. **Metrics frozen (§10/§10b):** "profitable" defined once; regime-loss denominator formula;
   vol-regime exposure adequacy; full metrics appendix (√252, rf=0, prior-day NAV, zero-exposure days
   included, CAGR/Calmar/maxDD conventions, borrow /360 calendar-day accrual, costs at traded notional);
   parameter-stability Sharpe condition recorded as diagnostic-not-gate per the owner's option.
9. **V3 details:** exact economic-gap formula registered (adoption confirmed at Implementation Freeze
   after the dividend-basis check); §2 dollar volume = close × volume.
10. **V4 clarifications:** denial diagnostics applied among otherwise-eligible short entries, per entry
    date, before sizing, most-extreme-first.

---

*v0.4 → build V1 anchors + V2 SIC/mapping → re-run V1/V2 verification → full Data Availability Gate →
fill §8a → owner sign-off → **Research-Design Freeze v1.0** → development → Implementation Freeze →
validation → sealed OOS. Hypothesis, thresholds, holding period, universe, and gate structure unchanged
since v0.3.*
