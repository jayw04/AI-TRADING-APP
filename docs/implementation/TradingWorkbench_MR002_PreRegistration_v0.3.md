# MR-002 — Pre-Registration v0.3 (DRAFT) · Sector-Neutral Residual Reversion

**Date:** 2026-07-11 · **Owner:** Jay Wang · **Program ID:** MR-002 · **Registry:** → **Planning**
(**Running** on Research-Design Freeze) · **Authority:** owner proposal
`Docs/Strategies/Proposed Strategies.txt` + review 1
(`Docs/Strategies/MR002_PreRegistration_Review_and_Recommendations.md`) + review 2
(`Docs/implementation/MR002_PreRegistration_v0.2_Review_and_Recommendations.md`), both 2026-07-11.
**Supersedes v0.2.**
**Status:** 🟡 **DRAFT v0.3 — NOT FROZEN.** Review 2's four specification blockers (**S1–S4**) are
resolved in this document (§14 changelog). Freeze (v1.0) is blocked on the four **data verifications
V1–V4** (§8) plus owner sign-off. Per review 2, the core is deliberately unchanged: hypothesis, z-entry
levels, five-day hold, universe breadth, and sealed-OOS structure. The remaining work eliminates
implementation discretion — it does not try to improve the anticipated result.

> **Governance disposition (binding, unchanged):** RNG-001 remains **Completed · Rejected (Evidenced) ·
> Archived**. MR-002 is a new hypothesis, not a continuation. RNG-002 is chartered separately, later.
> No momentum, volatility, RSI, or market-regime filters may be added before the first test.

## 1. Hypothesis (unchanged)

After removing broad-market and sector movements, unusually large company-specific (residual) price
moves frequently represent temporary liquidity pressure rather than information, and **partially reverse
over the following one to five trading sessions**. The mechanism is liquidity provision; the edge must
come from **breadth and repeatability** (tested by the §10 breadth gates).

## 2. Universe (point-in-time, reconstituted monthly)

- **Reconstitution timing (frozen):** computed **after the prior month-end close**, using data through
  that close only; **effective at the first trading session of the month**.
- **Longs: top 250** US common stocks by trailing 60-session median dollar volume; **shorts: top 150**
  by the same measure. **Dollar volume = raw (unadjusted) close × raw volume** — one mutually consistent
  unadjusted pair (V3).
- Close price **> $10** at reconstitution · trailing 60-session **median dollar volume > $25M** ·
  common stocks only (no ETFs/ADRs/preferreds/SPACs/units) · ≥ 252 prior sessions of history (no recent
  IPOs).
- **Short side additionally:** any available PIT hard-to-borrow flag excludes the name (V4; if no PIT
  source exists, the §9 no-data fallback applies).
- **Sector-proxy availability:** a stock is eligible only while its **PIT sector** (V2) has a live
  registered ETF proxy (XLK/XLF/XLE/XLV/XLI/XLP/XLY/XLU/XLB; XLRE 2015-10+; XLC 2018-06+). No parent-ETF
  remapping; a sector without a live proxy excludes its stocks for that period.
- Mid-month departures from the universe: no forced exit; positions run to normal exit; no new entries.
- Universe sizes 200 and 300 are **post-verdict diagnostics only**.

Survivorship-freedom is mandatory: membership from PIT price/volume history (Sharadar SEP), never a
current-day constituent list.

## 3. Signal construction (frozen — S1 resolved: orthogonalized sector factor)

**Step 1 — orthogonalized sector factor.** For each sector ETF, estimate the rolling 60-session
regression **ending at `t−1`**:

`r_Sector,t = a + β_Sector · r_SPY,t + u_Sector,t`

and use the residual **`u_Sector,t`** as the sector-specific factor (β_Sector from the `t−60 … t−1`
window applied to day `t`). This gives the stock regression a clean interpretation: SPY = broad market ·
`u_Sector` = sector-specific movement · residual = stock-specific movement. (The v0.2 spread
`r_Sector − r_SPY` only *reduces* collinearity because sector betas are rarely exactly 1.0; the
orthogonalized factor is the registered choice.)

**Step 2 — stock model.** Rolling **60-session** OLS on daily arithmetic total returns, estimated on
`t−60 … t−1` (never day `t`):

`r_i,t = α_i + β_m,i · r_SPY,t + β_s,i · u_Sector,t + ε_i,t`

with the day-`t` residual computed from the `t−1` coefficient estimates. PIT sector mapping per V2; an
unresolvable sector ⇒ excluded, never defaulted.

**Step 3 — signal.** `R5_i,t = Σ_{k=0..4} ε_i,t−k` and `z_i,t = (R5_i,t − μ_i,t−1) / σ_i,t−1`.

Registered normalization rules (unchanged from v0.2): `μ, σ` from rolling windows **ending at `t−1`** ·
exactly **60 complete five-day observations** (overlapping) · **`ddof=1`** · arithmetic **total returns
(signal series only — see §4 price-series policy)** · any missing observation ⇒ ineligible that day ·
**no winsorization**.

## 4. Price series, execution, and event handling (frozen — V3 policy + S-corrections)

**Registered price-series policy (V3):**

| Use | Series |
|---|---|
| Signal returns (§3) | total-return-adjusted (splits + dividends) |
| Execution prices (fills at the open) | **split-adjusted, NON-dividend-adjusted** open/close |
| Gap filter | split-adjusted prices, **economically adjusted for known cash distributions** (an ex-dividend drop is not a gap) |
| Dollar-volume ranking | raw close × raw volume (consistent unadjusted pair) |

**Timing:** signals computed after the close of session `t`; entries and exits execute at the **next
session's official opening price** (`t+1` open). Close-to-close execution is diagnostic only.
**Hold-period convention:** the entry session is **session 1**; the five-session time-stop exit executes
at the **open of session 6**.

**Gap filter (execution-day, distribution-adjusted):** entry order **cancelled at the `t+1` open** if
`|AdjOpen_t+1 / AdjClose_t − 1| ≥ 6%`.

**Long entry — all must hold at close `t`:** `z ≤ −Z_entry` · bottom 10% of that day's
**long-eligible** residual z-scores (percentiles computed within each side's eligible pool; ties broken
by |z| then permanent security identifier) · earnings-clearance rule (below) · no *announced*
merger/split/delisting/major-corporate-action (announcement-date-based) · gap filter passes · liquidity
envelope (§9). **Short entry — mirror** on the short-eligible pool (top 10%), plus §2 borrow rules.

**Earnings-clearance rule (V1 — replaces the fixed `[t−2, t+2]` window):**

> **Do not open a position when a PIT-known earnings announcement falls anywhere between the proposed
> execution time (`t+1` open) and the maximum possible exit time (the open of session 6). An existing
> position exits at the last executable open before the event.**

Session semantics: for a **before-market-open** event on session `s`, the last executable open before
the event is the **`s−1` open** — the position must be exited at or before it, and an entry at the `s−1`
open or later is prohibited. For an **after-market-close** event on session `s`, the last executable
open is the **`s` open** — the position must be exited at or before it (entry at the `s` open itself is
therefore also prohibited, since it could not be exited before the event). Overnight or intraday
earnings exposure is **never permitted**. Schedule revisions are recognized **only from their
revised-timestamp availability** (V1). If the calendar cannot distinguish BMO/AMC, the event is treated
conservatively as BMO.

**Exit — first occurrence of:** `|z|` inside **±0.35** · time stop (open of session 6) · residual
beyond **±3.5** with market/sector confirmation (SPY or the sector ETF moves the same direction ≥ 1σ of
its 60-session daily vol that day) · earnings-clearance forces exit · mandatory §5 reduction. Exits
execute at the next official open. **No tight ordinary price stop.**

**Halts / missing opens (V3 — implementable with daily data only):**

> **Entries without a valid official opening price are cancelled. Exits without a valid official opening
> price remain pending and execute at the next available official regular-session open.**

No intraday first-print fills are assumed (no intraday data is in the frozen data plan).

**Delisting valuation (registered priority order):** 1) vendor-provided delisting return or cash
consideration → 2) verified transaction consideration → 3) final executable market price → 4)
**conservative fallback: long positions are marked to zero; short positions are covered at the last
available close.** Delisted names are never silently dropped from the P&L series; exclusions begin at
the public announcement date, never retroactively.

## 5. Portfolio construction (frozen, deterministic — S2 resolved)

**Gross exposure is a 100%-of-NAV MAXIMUM, not a target.** Unused capital remains cash; **no return is
credited to cash** in the primary result (cash-yield variant = labelled secondary).

**Deterministic daily algorithm:**

1. **Exits first**, then entries. One position per symbol; no pyramiding; no re-entry at the same open a
   symbol exited.
2. Candidate sides from §4; raw weight ∝ 1/σ_resid (60-session 5-day residual vol), normalized within
   each side.
3. **Entry-dollar-neutrality:** new books are matched at order time — long gross = short gross =
   min(feasible long side, feasible short side, 50% of NAV). No forced trade solely to satisfy
   neutrality.
4. Constraints applied in registered reduction order: **(i) position cap → (ii) sector caps → (iii) beta
   limit → (iv) nothing else** (the volatility overlay is secondary reporting only, §5a). **Removal of a
   candidate never renormalizes the remaining weights upward** — freed capacity always goes to cash. If
   constraints are infeasible, remove the candidate with the smallest |z| first (tie: older signal, then
   permanent identifier) and re-apply.
5. **Fixed shares until exit** — existing positions are not re-marked to target weights.

**Drift policy (S2 — entry-neutral with tolerance bands, registered):** price drift is allowed; **no
rebalance while |net dollar exposure| ≤ 5% of gross**. When the band is breached, reduce positions on
the larger side only until back inside the band, selecting by **smallest |entry z| first (tie: oldest
position, then permanent identifier)** — one frozen rule. These mandatory reductions trade at the next
open and incur §9 costs.

**Registered limits (all deterministic):**

- **Position cap: max position market value = 1.5% of current portfolio NAV** (non-recursive).
- **Sector caps:** net dollar exposure per sector ≤ **5% of gross**; gross per sector ≤ **20% of gross**.
- **Beta limit:** with signed weights `w_i` as fractions of NAV and `β_i` = each stock's §3 β̂_m:
  `|Σ w_i β_i| / gross_exposure ≤ 0.10`.
- **The 3% projected-risk-contribution cap is REMOVED from MR-002** (S2): it required an unregistered
  covariance model; inverse residual-vol weighting already controls single-name risk. It may be evaluated
  later as a post-verdict portfolio overlay.

**§5a Volatility overlay (secondary only, unchanged):** primary result = unscaled (≤1.0× gross). The 8%
vol target is reported as a secondary transformation: scale-down only, factor = min(1, 8% / realized
63-day vol) from returns through the prior session, capped at 1.0, whole-portfolio scalar, full §9 costs
on its rebalancing trades. All §10 gates read on the primary.

## 6. Frozen parameter policy (exactly three configurations — unchanged)

| Config | Entry `Z_entry` | Exit z | Max hold | Role |
|---|---|---|---|---|
| A | 1.75 | 0.35 | 5 sessions | neighborhood sensitivity |
| **B (PRIMARY)** | **2.00** | 0.35 | 5 sessions | **verdict configuration** |
| C | 2.25 | 0.35 | 5 sessions | neighborhood sensitivity |

Verdict reads on B only; no other combinations run; multiple-testing burden tracked by the §10 trial
ledger.

## 7. Testing sequence & the two-stage freeze (S4 resolved)

**Stage 1 — Research-Design Freeze (= v1.0 of this document):** occurs **before any development data is
inspected**. Freezes hypothesis, parameters, data rules, gates, and samples. Registry → Running.

**Stage 2 — Implementation Freeze:** occurs **after** the development sample is used for harness
verification and **before validation begins**. Freezes: source-code commit hash · dependency lockfile ·
data-transformation code · unit + synthetic tests · configuration hash · data snapshot identifiers ·
**the DSR implementation** (formula per Bailey & López de Prado, skew/kurtosis treatment, exact
trial-ledger count) · **the frozen MOM-001 correlation artifact hash**. After Implementation Freeze:
validation may run; **only genuine implementation defects may be corrected**, each requiring a
documented defect report and a **complete validation rerun**; **no economic-rule change is permitted**;
the sealed OOS stays unopened until the corrected implementation is re-frozen.

**Sequence:**

1. **Development (first 50%):** A/B/C, implementation verification only; no winner selection; no gate
   read. → Implementation Freeze.
2. **Walk-forward validation (next 25%):** A/B/C; **five contiguous, non-overlapping, nearly equal
   trading-session blocks — any remainder sessions are assigned to the final fold** (fixed rule). B is
   primary; A/C feed the stability gate (validation only). Positive-folds gate = **≥ 3 of 5** on B.
3. **Sealed OOS (final 25%):** **B only, exactly once.** All OOS diagnostics use B.
4. Stationary bootstrap (§10) · regime decomposition (§10a definitions) · cost grid 0.5×/1×/2× + 30
   bps severe + breakeven headline · PBO (diagnostic) + DSR (gate) · paper verification before any
   production discussion (CEE from day one).

**Drawdown samples:** the maxDD gate reads validation + sealed OOS combined; sealed-OOS maxDD is also
reported separately.

**Sealed-run defect policy (S4, registered):**

> A **material** implementation or data defect discovered after the sealed run **invalidates the sealed
> result**. The result remains archived but cannot support a verdict. The corrected strategy requires
> **MR-003** or a newly identified untouched test period. Typographical, display-only, and
> non-calculation reporting corrections may be applied without creating a new program.

**"Material"** = anything capable of changing orders, position size, cost, daily return, sample
membership, or any pass/fail statistic.

## 8. Pre-freeze data verifications (the four FREEZE BLOCKERS — V1–V4)

| # | Verification | Registered acceptance rule |
|---|---|---|
| **V1** | **PIT earnings schedule.** Must include: when the schedule became known (date/timestamp) · subsequent revisions · BMO / in-session / AMC designation · the associated trading session. A final-realized-dates table is **not** sufficient. | §4 earnings-clearance rule uses schedules known at `t` only; revisions recognized from revised timestamps; missing BMO/AMC ⇒ treat as BMO. If no genuinely PIT calendar exists, any fallback needs explicit owner re-approval before freeze. |
| **V2** | **PIT sector history.** Must establish: effective date · previous classification · new classification · availability timestamp · mapping to the registered ETF proxy. | Accept only **(1)** a genuinely PIT sector/industry history, or **(2)** historically effective SIC/NAICS converted through a **frozen mapping table whose hash ships in the evidence package**. A "measured reclassification rate" approximation is NOT auto-accepted — sector identity enters the signal. |
| **V3** | **Consistent price/volume series.** Verify the data supports the §4 four-series policy: total-return signal series · split-only execution opens/closes · distribution-adjusted gap series · raw close×volume pair · official-open availability flags · vendor delisting returns/consideration. | §4 policy is frozen; V3 verifies Sharadar SEP/ACTIONS can deliver each series without mixing adjustments. |
| **V4** | **Historical borrow / HTB source.** Determine whether any PIT borrow-availability source exists. | If yes: register it. **If no (expected):** the §9 no-data fallback applies verbatim and is disclosed in every result artifact. |

**Data plan:** Sharadar SEP (prices/volume, survivorship-free) · TICKERS (category filters) · sector =
pending V2 · earnings = pending V1 (Sharadar EVENTS candidate) · ACTIONS (announcement-dated corporate
actions, delistings) · SPY + sector ETFs = Yahoo adjusted close (TREND precedent; no SFP access).
**Data Availability Gate (first post-freeze step):** SEP depth/coverage for top-250/150 across the
window · ETF proxy history · EVENTS/ACTIONS coverage · realized window + monthly universe counts to the
manifest. Window materially shorter than ~10 years ⇒ stop and re-review (power).

## 9. Cost model, borrow fallback, and capacity

- **Base:** 10 bps/side (spread + impact) · short borrow 50 bps/yr, accrued daily.
- **Mandatory stress (gate):** 20 bps/side · **300 bps/yr** borrow.
- **Severe diagnostics (reported, not gated):** 30 bps/side · **1,000 bps/yr** borrow.
- **Borrow no-data fallback (V4, registered disclosure):**
  > No reliable PIT historical borrow-availability data is available. The primary backtest assumes
  > availability in the top-150 short universe. **Mandatory diagnostics deny the most extreme 10% and
  > 25% of short signals** (by |z| — denial removes the *strongest* short opportunities, because
  > unavailable borrow concentrates in crowded/extreme names) **and apply 300-bps and 1,000-bps annual
  > borrow costs.**
- Long-only and short-only P&L attribution at every cost tier.
- **Reference NAV: $10M** · orders capped at **2% of trailing 20-session median dollar volume**, clipped
  not delayed, unfilled notional stays cash. **Registered modeling limitation:** fills at the official
  open up to 2% of *full-day* ADV assume adequate opening-auction capacity; reported as a limitation
  unless opening-auction volume data is added.
- **Capacity reporting:** max scalable NAV at which 95% of orders remain below the cap + diagnostics at
  $10/25/50/100M.
- Binding rejection rule: passing only under zero-cost or close-price execution ⇒ **Rejected**.

## 10. Verdict framework & pass gates (LOCKED at freeze)

Verdict reads on **config B, primary (unscaled), net of base costs, $10M NAV**, samples per gate.

**Bootstrap (registered):** stationary bootstrap on net daily portfolio returns · 10,000 replications ·
seed **20260711** · expected block length 5 sessions (+10-session sensitivity) · statistic = 95%
one-sided lower confidence bound on mean daily net return.

**§10a Regime definitions (S3 — frozen, two SEPARATE axes, classified from data through the prior
session):**

- **Trend axis (SPY trailing 126-session total return):** Bull > +5% · Bear < −5% · Sideways otherwise.
- **Volatility axis (SPY trailing 21-session annualized realized vol):** High ≥ 20% · Low < 20%.
- The axes are never combined into one denominator (categories overlap).

**✅ Approved (standalone)** — ALL of:

| Gate | Requirement | Sample |
|---|---|---|
| Net Sharpe | ≥ 0.70 | sealed OOS |
| Net Calmar | ≥ 0.75 | sealed OOS |
| Max drawdown (net) | ≤ 15% | validation + sealed OOS (sealed also separately) |
| Positive walk-forward folds | ≥ 3 of 5 | validation |
| Bootstrap lower bound (95%, one-sided) | > 0 | sealed OOS |
| Cost stress | profitable at 20 bps/side + 300 bps borrow | sealed OOS |
| Parameter stability | A and C profitable (net) | validation |
| Deflated Sharpe | ≥ 95% significance, per the trial ledger + frozen implementation | sealed OOS |
| Net annualized return | ≥ 3% at the registered gross cap | sealed OOS |
| Breadth | ≥ 500 completed trades · ≥ 100 distinct entry dates · ≥ 100 long · ≥ 100 short | sealed OOS |
| Trade concentration | top-10 trades ≤ 20% of total positive trade P&L · single stock ≤ 10% of total positive P&L | sealed OOS |
| **Annual profile (revised — review 2 §10)** | **≥ 3 positive calendar years** AND **largest positive year ≤ 50% of the sum of positive annual P&L** (annual-P&L Herfindahl reported as a diagnostic) | validation + sealed OOS |
| **Regime gates (revised — review 2 §5)** | positive net P&L in **≥ 2 of 3 trend regimes** · no trend regime contributes **> 60% of total losses** · neither volatility regime has Sharpe **< −0.50** (regimes with < 60 sessions of exposure are reported n/a, not failed) | validation + sealed OOS |
| Capacity | positive net edge at $10M under the 2% participation cap | sealed OOS |

Positive-P&L regime concentration is a **diagnostic**, not a rejection criterion (a reversion strategy
legitimately earning most of its return in high-vol liquidity disruptions *supports* the hypothesis).
**PBO remains a diagnostic** with the "N=3 — underpowered" label. **Trial ledger:** configs A/B/C + the
mean-reversion family's prior examined variants (RNG-001 and documented sub-studies; informal MR
variants logged before freeze); a first-class evidence artifact.

**🟡 Diversifier (B)** — fails Approved, but ALL of: net sealed-OOS Sharpe ≥ 0.40 · bootstrap lower
bound > 0 · |corr| ≤ 0.30 vs MOM-001 (**frozen artifact hash; aligned net daily returns; no volatility
rescaling**) · cost-stress, DSR, breadth, trade-concentration, annual-profile, and regime gates all pass.

**Power rule (registered):** minimum relevant Sharpe **0.40** · required power **80%** · confidence
**95%**. Positive Sharpe + CI spans zero + power < 80% ⇒ **Power-Limited · Inconclusive**. CI spans zero
with power ≥ 80% ⇒ **Rejected**. Negative observed Sharpe ⇒ **Rejected** regardless of power.

**🔴 Rejected** additionally fires when any mandatory gate fails with adequate power, or the zero-cost
rule fires. Decision metric = credible net return after robustness and cost gates, never highest CAGR.

## 11. Evidence package (`evidence/mr_002/`, seeded & reproducible)

Pre-reg (frozen) · **both freeze records** (research-design + implementation: commit, lockfile, config
hash, data snapshot IDs, DSR implementation, V2 mapping-table hash, MOM-001 artifact hash) · defect
reports (if any) · run manifest (data hashes, realized window, monthly universe counts, V1–V4
verification records, PIT-exclusion log) · trial ledger · results: Performance (primary + 8% overlay
secondary) · Trade quality (incl. long/short attribution) · Robustness (folds, bootstrap + block
sensitivity, A/C, PBO diagnostic) · Costs (0.5×/1×/2×/severe grids, borrow-denial 10%/25% diagnostics,
breakeven) · Stability (annual + two-axis regime attribution, Herfindahl) · Concentration · Capacity
($10–100M, max scalable NAV, opening-auction limitation note) · Validation (DSR + ledger, power
computation) · Evidence Brief + registry/`programs.py` entry.

## 12. Owner decisions — resolved

Q1–Q5 per review 1 (kept MR-002; post-sealed substantive change = **MR-003**; cost stack per §9;
next-open execution + execution-day gap; shorts top-150; no parent-ETF remapping). S1–S4 per review 2,
resolved in §§3, 5, 7, 10a of this draft.

## 13. Stopping rule & lifecycle

One primary design; one sealed test; no parameter adjustment after sealed OOS — a substantive revision
is **MR-003** with a fresh pre-registration and untouched test period. The §7 sealed-run defect policy
governs post-run corrections. No paper promotion unless Approved or Diversifier clears; paper requires
CEE from day one. If Rejected: archive with the evidence brief (CAP-011). Registry entry at
Research-Design Freeze.

## 14. Changelog v0.2 → v0.3 (review 2 folded)

1. **S1:** sector factor upgraded from the spread `r_Sector − r_SPY` to the **orthogonalized residual
   `u_Sector`** from a rolling SPY regression ending `t−1` (the spread only reduces collinearity).
2. **V1 rule upgraded:** earnings exclusion now covers the **entire possible holding period** (execution
   time → open of session 6), with BMO/AMC session semantics, revision-timestamp recognition, and a
   conservative BMO default — replacing the fixed `[t−2, t+2]` window that could leave a position
   exposed to earnings on sessions 3–5.
3. **V2 tightened:** only a genuine PIT sector history or historically effective SIC/NAICS through a
   frozen, hashed mapping table; approximations are not auto-accepted.
4. **V3 added:** four-series price/adjustment policy (signal TR / execution split-only / gap
   distribution-adjusted / ranking raw×raw); halt rule replaced with the official-opening-price rule
   (implementable on daily data); delisting valuation priority order with a conservative registered
   fallback (longs → 0, shorts cover at last close).
5. **S2:** position cap re-based to **1.5% of NAV** (non-recursive) · **3% projected-risk cap removed**
   (unregistered covariance model; post-verdict overlay candidate) · beta limit formalized
   (`|Σ w_i β_i|/gross ≤ 0.10`, signed NAV-fraction weights) · **entry-neutral with ±5%-of-gross
   tolerance band** replaces implicit daily neutrality (reduction rule: larger side, smallest |entry z|,
   then oldest, then identifier) · candidate removal never renormalizes remaining weights upward.
6. **S3:** regime definitions frozen (trend ±5% on SPY 126-session return; vol 20% on 21-session
   realized, prior-session data, two separate axes); the 60%-of-positive-P&L regime gate **replaced** by
   ≥2-of-3-positive-trend-regimes + ≤60%-of-losses + vol-regime Sharpe ≥ −0.50; positive-concentration
   demoted to diagnostic.
7. **S4:** two-stage freeze added (Research-Design + Implementation, with the frozen artifact list and
   defect-correction protocol) + the sealed-run defect policy with a registered definition of
   "material".
8. **Review-2 §10:** the 35% annual-concentration gate replaced by ≥3 positive years + largest year ≤50%
   of positive annual P&L + Herfindahl diagnostic (35% was structurally unpassable over ~5 years).
9. **Review-2 §9:** borrow no-data fallback registered verbatim, incl. extreme-signal denial diagnostics
   (10%/25% by |z|) and the 1,000-bps severe borrow tier.
10. **Smaller corrections:** reconstitution timing (prior month-end close → first session) ·
    side-scoped percentile pools · |z|-then-identifier tie-breaks · entry session = session 1, time stop
    at open of session 6 · fold construction (5 near-equal blocks, remainder to final fold) · DSR
    implementation frozen at Implementation Freeze · MOM-001 correlation artifact hash frozen · the
    opening-auction capacity limitation disclosed.

---

*Draft v0.3 → run verifications V1–V4 → owner sign-off → **Research-Design Freeze (v1.0)** → Data
Availability Gate → development sample → Implementation Freeze → validation → sealed OOS (B, once).
Core hypothesis, z levels, 5-day hold, universe breadth, and sealed-OOS structure unchanged since v0.1.*
